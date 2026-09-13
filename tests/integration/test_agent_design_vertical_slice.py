"""Opt-in real model + real BoltzGen validation through Gate 3, without generation."""

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
from easydesign.agent.design import DesignBridge
from easydesign.agent.models import PHASE2_MODEL_CALL_LIMIT, ModelConfig, create_models
from easydesign.agent.phase2 import Phase2Bridge
from easydesign.agent.session_store import SessionStore
from tests.agent_phase2_support import configure_live_validation
from tests.agent_support import make_project, terminal
from tests.unit.agent.test_site_runtime import propose, reviewed_card


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.environ.get("EASYDESIGN_AGENT_LIVE") != "1", reason="Opt-in live API/backend smoke"
)
async def test_live_model_design_cdr_revision(tmp_path: Path, monkeypatch: Any) -> None:
    config = ModelConfig.model_validate(
        yaml.safe_load(Path(os.environ["EASYDESIGN_AGENT_MODEL_CONFIG"]).read_text())
    )
    assert config.max_model_calls == PHASE2_MODEL_CALL_LIMIT
    target = make_project(tmp_path, monkeypatch, chains="A")
    target.prepare_target()
    terminal(target)
    site = Phase2Bridge(target.project, target.thread, target.store)
    propose(site)
    approved = reviewed_card(site)
    site.store.respond(
        site.thread, approved.card_id, "approve", "explicit-live-smoke-synthetic-fixture"
    )
    site.apply_decision(approved)
    runtime = configure_live_validation()
    bridge = DesignBridge(site.project, "live-design-thread", site.store)
    goal = (
        "This is an isolated synthetic six-residue regression, not a validated biological target. "
        "The target and hotspot (labels 1,2,3) are already approved. Propose one focused VHH "
        "design arm with the full prepared target and official default scaffold/CDR settings, "
        "all seven scaffolds and 40 candidates per scaffold. Preserve canonical-identity and "
        "docking limitations. Validate using the real compiler/backend and ask for Gate 3. "
        "Respect my revision; freeze only after the human card response, and do not generate."
    )
    try:
        models = create_models(config)
        original = (bridge.target_state()["binding"], bridge.approved_site()["hotspots_sha256"])
        pending = await run_session(bridge, config, models, goal)
        assert pending["status"] == "awaiting-human-approval", pending
        assert pending["card"]["gate_type"] == "design-specification"
        assert pending["card"]["judge_status"] != "BLOCKED", pending["card"]
        probe = bridge.terminal_result("Everything is finished")
        assert probe["status"] == "incomplete-turn"
        revised = await run_session(
            bridge,
            config,
            models,
            goal,
            decision="revise",
            card_id=pending["card"]["card_id"],
            user="explicit-live-smoke-synthetic-fixture",
            human_instruction=(
                "Keep target, hotspot, full context, one arm and seven-by-40 coverage. "
                "Shorten CDR3 exploration: use the shared template design range 100..105 and "
                "insertion_num_residues 1..3 for CDR 3; verify the actual template evidence. "
                "Explain the CDR hypothesis and limitations; validate and request Gate 3."
            ),
        )
        assert revised["status"] == "awaiting-human-approval", revised
        assert revised["card"]["parent_card_id"] == pending["card"]["card_id"]
        assert revised["card"]["judge_status"] in {"SUPPORTED", "DISCOURAGED"}, revised["card"]
        assert (
            bridge.target_state()["binding"],
            bridge.approved_site()["hotspots_sha256"],
        ) == original
        intent = bridge.current_design()["intent"]
        assert len(intent["arms"]) == 1
        assert intent["arms"][0]["cdr_overrides"] == [
            {
                "cdr": 3,
                "design_res_index": "100..105",
                "insertion_num_residues": "1..3",
            }
        ]
        bridge.store.close()
        bridge = DesignBridge(site.project, "live-design-thread", SessionStore(site.project))
        discouraged = revised["card"]["judge_status"] == "DISCOURAGED"
        extra = (
            {
                "optional_reason": (
                    "Test constrained CDR3 exploration in this synthetic validation fixture."
                ),
                "explicit_acknowledgement": "I acknowledge the listed scientific and CDR warnings.",
            }
            if discouraged
            else {}
        )
        done = await run_session(
            bridge,
            config,
            models,
            goal,
            decision="override" if discouraged else "approve",
            card_id=revised["card"]["card_id"],
            user="explicit-live-smoke-synthetic-fixture",
            **extra,
        )
        assert done["status"] == "finished" and done["scientific_state"] == "design-frozen", done
        assert done["generation_started"] is False
        frozen = bridge.scientific_state()["frozen_design"]
        assert (
            frozen["cdr_template_validation"][0]["within_declared_loop_of_all_seven_scaffolds"]
            is True
        )
        assert frozen["arms"][0]["binding_label_seq_ids"] == [1, 2, 3]
        assert frozen["design_viewer_url"] is None
        assert bridge.approved_design() is not None
        assert len(list((bridge.project / "strategies").glob("strategy-r*.yaml"))) == 1
        assert all(j.step <= 2 for j in bridge.controller.list(project_id=bridge.project_id))
        events = bridge.store.events(bridge.thread)
        calls = [e["payload"] for e in events if e["kind"] == "model-call"]
        executions = Counter(c["execution_id"] for c in calls)
        assert max(executions.values()) <= config.max_model_calls
        assert {c["role"] for c in calls} == {"coordinator", "binder", "judge"}
        result = {
            "live": "passed",
            "gate": 3,
            "model": config.default.model,
            "runtime": runtime,
            "target_hotspot_unchanged": True,
            "calls_by_role": dict(Counter(c["role"] for c in calls)),
            "calls_by_execution": dict(executions),
            "terminal_guard_probe": probe,
            "first_card": pending["card"],
            "revised_card": revised["card"],
            "final": done,
            "events": events,
        }
        (tmp_path / "live-design-result.json").write_text(
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
