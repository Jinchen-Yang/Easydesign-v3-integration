from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

pytest.importorskip("deepagents")

from tests.agent_support import make_project, scripted_config, scripted_models


def test_cli_entrypoint_restores_in_a_new_process(tmp_path: Path, monkeypatch: Any) -> None:
    bridge = make_project(tmp_path, monkeypatch)
    bridge.store.close()
    config = tmp_path / "runtime/tmp/models.yaml"
    config.write_text(yaml.safe_dump(scripted_config().model_dump(mode="json")))
    launcher = (
        "from importlib.metadata import entry_points; "
        "import easydesign.agent.models as m; "
        "from tests.agent_support import scripted_models; "
        "m.create_models = lambda config: scripted_models(); "
        "raise SystemExit(entry_points(group='console_scripts')['easydesign-agent'].load()())"
    )

    def run(*arguments: str) -> dict[str, Any]:
        process = subprocess.run(
            [
                sys.executable,
                "-c",
                launcher,
                *arguments,
                "--models",
                str(config),
                "--thread",
                "cli-process-thread",
            ],
            capture_output=True,
            text=True,
            timeout=90,
        )
        assert process.returncode == 0, process.stdout + process.stderr
        return json.loads(process.stdout)

    pending = run("start", str(bridge.project), "--goal", "Prepare the local chain A")
    assert pending["status"] == "awaiting-human-approval"
    reopened = run("resume", str(bridge.project))
    assert reopened["card"] == pending["card"]
    done = run(
        "resume", str(bridge.project), "--card", pending["card"]["card_id"], "--decision", "approve"
    )
    assert done["status"] == "finished"
    assert done["job"]["status"] == "succeeded"


@pytest.mark.asyncio
async def test_target_slice_and_checkpoint_size(tmp_path: Path, monkeypatch: Any) -> None:
    from easydesign.agent.cli import run_session

    bridge = make_project(tmp_path, monkeypatch)
    try:
        config = scripted_config()
        pending = await run_session(bridge, config, scripted_models(), "Prepare the local chain A")
        assert pending["status"] == "awaiting-human-approval"
        done = await run_session(
            bridge,
            config,
            scripted_models(),
            "Prepare the local chain A",
            decision="approve",
            card_id=pending["card"]["card_id"],
            user="synthetic-fixture-user",
        )
        assert done["status"] == "finished"
        evidence = bridge.read_evidence()
        assert evidence["bundle"]["producer_attempt"] == "attempt-0002"
        assert evidence["viewer"]["status"] == "verified"
        total = sum(p.stat().st_size for p in bridge.store.root.glob("agent-checkpoints.sqlite*"))
        assert total < 2_000_000, total
        events = bridge.store.events(bridge.thread)
        assert {e["payload"]["role"] for e in events if e["kind"] == "model-call"} == {
            "coordinator",
            "target",
            "judge",
        }
        serialized = json.dumps(events)
        assert "ATOM      " not in serialized
    finally:
        bridge.store.close()


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.environ.get("EASYDESIGN_AGENT_LIVE") != "1",
    reason="Live model API requires explicit opt-in and configured credentials",
)
async def test_live_model_target_slice(tmp_path: Path, monkeypatch: Any) -> None:
    from easydesign.agent.cli import run_session
    from easydesign.agent.models import ModelConfig, create_models

    path = os.environ.get("EASYDESIGN_AGENT_MODEL_CONFIG")
    assert path, "Set EASYDESIGN_AGENT_MODEL_CONFIG to the private model config path"
    config = ModelConfig.model_validate(yaml.safe_load(Path(path).read_text()))
    assert config.max_model_calls <= 32, "Live smoke permits at most 32 API calls"
    bridge = make_project(tmp_path, monkeypatch)
    try:
        models = create_models(config)
        goal = (
            "Prepare this synthetic local structure. I want chain A. Ask me for confirmation; "
            "then assess the target bundle and stop."
        )
        pending = await run_session(bridge, config, models, goal)
        assert pending["status"] == "awaiting-human-approval", pending
        done = await run_session(
            bridge,
            config,
            models,
            goal,
            decision="approve",
            card_id=pending["card"]["card_id"],
            user="explicit-live-smoke-synthetic-fixture",
        )
        assert done["status"] == "finished", done
        evidence = bridge.read_evidence()
        assert evidence["bundle"]["producer_attempt"] == "attempt-0002"
        assert evidence["provenance"]["fallback_used"] is False
        assert evidence["approval_provenance"]["status"] == "not-in-snapshot"
        assert len(bridge._jobs()) == 2
        events = bridge.store.events(bridge.thread)
        calls = [event["payload"] for event in events if event["kind"] == "model-call"]
        assert len({call["execution_id"] for call in calls}) == 1
        assert len(calls) <= config.max_model_calls
        assessments = [event["payload"] for event in events if event["kind"] == "judge-assessment"]
        assert [item["verdict"] for item in assessments] == ["ready-to-ask", "assessed"]
        assert all(item["source_role"] == "evidence-judge" for item in assessments)
        assert assessments[-1]["evidence_refs"] == evidence["evidence_refs"]
        assert assessments[-1]["request_identity"] is None
        print(
            json.dumps(
                {
                    "live": "passed",
                    "provider": config.default.provider,
                    "model": config.default.model,
                    "events": events,
                },
                ensure_ascii=False,
            )
        )
    finally:
        bridge.store.close()
