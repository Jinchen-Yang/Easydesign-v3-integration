"""Opt-in live Site/Gate 2 regression on an isolated synthetic structure."""

from __future__ import annotations

import json
import os
from collections import Counter
from pathlib import Path
from typing import Any

import pytest
import yaml

pytest.importorskip("deepagents")

from easydesign.agent.cli import run_session
from easydesign.agent.models import PHASE2_MODEL_CALL_LIMIT, ModelConfig, create_models
from easydesign.agent.phase2 import Phase2Bridge
from easydesign.agent.session_store import SessionStore
from tests.agent_support import make_project, terminal


@pytest.mark.asyncio
@pytest.mark.skipif(os.environ.get("EASYDESIGN_AGENT_LIVE") != "1", reason="Opt-in live API smoke")
async def test_live_model_site_revision(tmp_path: Path, monkeypatch: Any) -> None:
    config = ModelConfig.model_validate(
        yaml.safe_load(Path(os.environ["EASYDESIGN_AGENT_MODEL_CONFIG"]).read_text())
    )
    assert config.max_model_calls == PHASE2_MODEL_CALL_LIMIT
    target = make_project(tmp_path, monkeypatch, chains="A")
    target.prepare_target()
    terminal(target)
    bridge = Phase2Bridge(target.project, target.thread, target.store)
    goal = (
        "This is a synthetic six-residue structural regression, not a biological target. "
        "Assess mapped residues 1, 2, 3 as one exploratory VHH hotspot using actual structure "
        "tools. Do not claim biological function, activity, specificity, or successful binding. "
        "No canonical sequence or external annotations are provided. Compare another site "
        "only if informative. Ask for a Gate 2 decision, respect my revisions, and stop after "
        "the hotspot is approved. No generation."
    )
    try:
        models = create_models(config)
        target_binding = bridge.target_state()["binding"]
        pending = await run_session(bridge, config, models, goal)
        assert pending["status"] == "awaiting-human-approval", pending
        assert pending["card"]["gate_type"] == "site-hotspot"
        assert bridge.current_site()["intent"]["selected_site"]["hotspot_label_seq_ids"] == [
            1,
            2,
            3,
        ]
        probe = bridge.terminal_result("Finished")
        assert probe["status"] == "incomplete-turn"
        assert bridge.approved_site() is None
        revised = await run_session(
            bridge,
            config,
            models,
            goal,
            decision="revise",
            card_id=pending["card"]["card_id"],
            user="explicit-live-smoke-synthetic-fixture",
            human_instruction=(
                "Keep the same target and original exploratory goal. Replace the hotspot "
                "with mapped label_seq_ids 4, 5, 6. Re-evaluate geometry and limitations, "
                "explain the alternative, and present a new Gate 2 card."
            ),
        )
        assert revised["status"] == "awaiting-human-approval", revised
        assert revised["card"]["parent_card_id"] == pending["card"]["card_id"]
        assert bridge.target_state()["binding"] == target_binding
        bridge.store.close()
        bridge = Phase2Bridge(target.project, target.thread, SessionStore(target.project))
        status = revised["card"]["judge_status"]
        assert status in {"SUPPORTED", "DISCOURAGED"}
        kwargs = (
            {}
            if status == "SUPPORTED"
            else {
                "optional_reason": "Synthetic geometry test; no biological success claimed.",
                "explicit_acknowledgement": "I acknowledge all listed scientific warnings.",
            }
        )
        done = await run_session(
            bridge,
            config,
            models,
            goal,
            decision="approve" if status == "SUPPORTED" else "override",
            card_id=revised["card"]["card_id"],
            user="explicit-live-smoke-synthetic-fixture",
            **kwargs,
        )
        assert done["status"] == "finished", done
        approved = bridge.approved_site()
        assert approved["hotspots"]["hotspot_sets"][0]["label_seq_ids"] == [4, 5, 6]
        assert bridge.target_state()["binding"] == target_binding
        assert len(bridge._jobs()) == 1
        assert all(j.step <= 2 for j in bridge.controller.list(project_id=bridge.project_id))
        events = bridge.store.events(bridge.thread)
        calls = [e["payload"] for e in events if e["kind"] == "model-call"]
        executions = Counter(c["execution_id"] for c in calls)
        assert max(executions.values()) <= config.max_model_calls
        assert {c["role"] for c in calls} == {"coordinator", "site", "judge"}
        result = {
            "live": "passed",
            "gate": 2,
            "provider": config.default.provider,
            "model": config.default.model,
            "calls_by_role": dict(Counter(c["role"] for c in calls)),
            "calls_by_execution": dict(executions),
            "target_unchanged": True,
            "final_hotspots": [4, 5, 6],
            "terminal_guard_probe": probe,
            "first_card": pending["card"],
            "revised_card": revised["card"],
            "final": done,
            "events": events,
        }
        (tmp_path / "live-site-result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2)
        )
        print(
            json.dumps(
                {
                    k: v
                    for k, v in result.items()
                    if k not in {"events", "first_card", "revised_card"}
                },
                ensure_ascii=False,
            )
        )
    finally:
        bridge.store.close()
