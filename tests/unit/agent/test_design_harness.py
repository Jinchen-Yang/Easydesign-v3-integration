import json
from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from easydesign.agent.cli import run_session
from easydesign.agent.design import DesignBridge
from easydesign.agent.phase2_tools import DESIGN_ALLOWED, phase2_tools
from easydesign.agent.session_store import SessionStore
from easydesign.agent.site_contracts import ScientificTask
from tests.agent_support import scripted_config
from tests.unit.agent.test_design_runtime import binder_intent
from tests.unit.agent.test_site_harness import SiteModel


class DesignModel(SiteModel):
    def bind_tools(self, tools: Any, **kwargs: Any) -> Any:
        if self.role == "site" or (
            self.role == "judge"
            and {t.name for t in tools} <= {"SiteJudgeVerdict", "RecoverySiteJudgeVerdict"}
        ):
            return super().bind_tools(tools, **kwargs)
        names = {
            "target": "TargetInterpretation",
            "site": "SiteDecision",
            "binder": "BinderIntent",
            "judge": "JudgeVerdict",
        }
        expected = DESIGN_ALLOWED[self.role] | ({names[self.role]} if self.role in names else set())
        names = {t.name for t in tools}
        self.offered = names
        if self.role == "coordinator":
            expected -= {"read_file"}
        assert names <= expected and expected - names <= {
            "get_job_status",
            "prepare_target",
            "read_target_evidence",
            "read_evidence_result",
            "analyze_receptor_context",
            "continue_evidence",
        }
        return self

    def answer(self, messages: Any) -> AIMessage:
        if self.role in {"site", "judge", "target"}:
            return super().answer(messages)
        calls = {c["id"]: c for m in messages if isinstance(m, AIMessage) for c in m.tool_calls}
        results = [
            (calls.get(m.tool_call_id, {}), m) for m in messages if isinstance(m, ToolMessage)
        ]
        for _, message in results:
            assert message.status != "error", message.content
        if self.role == "binder":
            task = ScientificTask.model_validate_json(
                next(m.text for m in messages if isinstance(m, HumanMessage))
            )
            if not results:
                self.tasks.append(task.model_dump())
                return self.call("read_file", file_path="/skills/binder-strategy/SKILL.md")
            names = {c.get("name") for c, _ in results}
            if "read_design_evidence" not in names:
                return self.call("read_design_evidence")
            intent = (
                binder_intent(avoid_label_seq_ids=[6])
                if "exclude" in (task.current_revision_instruction or "")
                else binder_intent()
            )
            if "evaluate_design_constraints" not in names:
                return self.call("evaluate_design_constraints", **intent.model_dump(mode="json"))
            return self.call("BinderIntent", **intent.model_dump(mode="json"))
        if not results:
            return self.call("read_scientific_state")
        last, message = results[-1]
        value = json.loads(message.content)
        if last.get("name") == "read_scientific_state":
            status = value["scientific_state"]
            if status == "design-frozen":
                return AIMessage(
                    content="The VHH design specification is frozen; generation has not started."
                )
            if status == "awaiting-human-approval" and value.get("proposal"):
                specialist = "evidence-judge"
            elif status == "awaiting-human-approval" and value["gate_type"] == "target-structure":
                specialist = "evidence-judge"
            else:
                specialist = value["next_specialist"]
            return self.call(
                "task",
                subagent_type=specialist,
                description=(
                    "Assess the current scientific question within the original goal "
                    "and trusted revision."
                ),
            )
        if last.get("name") == "task":
            if last["args"]["subagent_type"] == "evidence-judge":
                state = json.loads(
                    next(
                        m.content
                        for c, m in reversed(results)
                        if c.get("name") == "read_scientific_state"
                    )
                )
                option = {
                    "target-structure": "chain-a",
                    "site-hotspot": "site",
                    "design-specification": "design",
                }[state["gate_type"]]
                return self.call(
                    "request_scientific_decision",
                    assessment_id=value["assessment_id"],
                    option_id=option,
                )
            return self.call("read_scientific_state")
        if last.get("name") == "request_scientific_decision":
            if value["status"] == "proposal-rejected":
                return AIMessage(
                    content="The proposal was rejected; the scientific project remains available."
                )
            if value["status"] == "revision-requested":
                instruction = value["steering"]["human_instruction"]
                if "reopen site" in instruction:
                    return self.call(
                        "reopen_site_decision",
                        reason="The trusted human revision changes hotspot location.",
                    )
                return self.call(
                    "task",
                    subagent_type=value["owner_specialist"],
                    description="Revise the current proposal using the trusted human instruction.",
                )
        return self.call("read_scientific_state")


@pytest.mark.asyncio
async def test_gate3_revision_restart_preserves_target_hotspot_and_goal(design_bridge: Any) -> None:
    bridge = design_bridge
    models = {r: DesignModel(role=r) for r in DESIGN_ALLOWED}
    goal = "Freeze an exploratory VHH design specification against the approved hotspot."
    before = (bridge.target_state()["binding"], bridge.approved_site()["hotspots_sha256"])
    pending = await run_session(bridge, scripted_config(), models, goal)
    assert pending["status"] == "awaiting-human-approval", pending
    assert pending["card"]["gate_type"] == "design-specification"
    assert bridge.terminal_result("finished")["status"] == "incomplete-turn"
    reopened = SessionStore(bridge.project)
    try:
        resumed = DesignBridge(bridge.project, bridge.thread, reopened)
        revised = await run_session(
            resumed,
            scripted_config(),
            models,
            goal,
            decision="revise",
            card_id=pending["card"]["card_id"],
            user="synthetic-scientist",
            human_instruction="Keep target and hotspot; exclude mapped residue 6 from contact.",
        )
        assert revised["status"] == "awaiting-human-approval", revised
        assert revised["card"]["parent_card_id"] == pending["card"]["card_id"]
        assert (
            resumed.target_state()["binding"],
            resumed.approved_site()["hotspots_sha256"],
        ) == before
        assert all(
            t["user_goal"] == goal and t["current_user_message"] == goal
            for t in models["binder"].tasks
        )
        assert models["binder"].tasks[-1]["current_revision_instruction"].startswith("Keep target")
        done = await run_session(
            resumed,
            scripted_config(),
            models,
            goal,
            decision="approve",
            card_id=revised["card"]["card_id"],
            user="synthetic-scientist",
        )
        assert done["status"] == "finished" and done["scientific_state"] == "design-frozen"
        assert done["generation_started"] is False
    finally:
        reopened.close()


@pytest.mark.asyncio
async def test_gate3_reject_and_binder_cannot_change_site(design_bridge: Any) -> None:
    bridge = design_bridge
    models = {r: DesignModel(role=r) for r in DESIGN_ALLOWED}
    goal = "Review a VHH design specification."
    pending = await run_session(bridge, scripted_config(), models, goal)
    rejected = await run_session(
        bridge,
        scripted_config(),
        models,
        goal,
        decision="reject",
        card_id=pending["card"]["card_id"],
        user="synthetic-scientist",
    )
    assert rejected["status"] == "proposal-rejected"
    assert bridge.approved_site() is not None and bridge.approved_design() is None
    assert {t.name for t in phase2_tools(bridge, "binder")} == {
        "read_design_evidence",
        "evaluate_design_constraints",
        "read_evidence_result",
    }


@pytest.mark.asyncio
async def test_gate3_upstream_site_revision_invalidates_design(design_bridge: Any) -> None:
    bridge = design_bridge
    models = {r: DesignModel(role=r) for r in DESIGN_ALLOWED}
    goal = "Freeze a VHH design against a scientist-approved hotspot."
    before = bridge.target_state()["binding"]
    pending = await run_session(bridge, scripted_config(), models, goal)
    revised = await run_session(
        bridge,
        scripted_config(),
        models,
        goal,
        decision="revise",
        card_id=pending["card"]["card_id"],
        user="synthetic-scientist",
        human_instruction=(
            "Please reopen site selection: use mapped residues 4–6 as the new hotspot."
        ),
        revision_gate="site-hotspot",
    )
    assert revised["status"] == "awaiting-human-approval", revised
    assert revised["card"]["gate_type"] == "site-hotspot"
    assert revised["card"]["parent_card_id"] == pending["card"]["card_id"]
    assert bridge.current_design() is None and bridge.approved_design() is None
    assert bridge.target_state()["binding"] == before
    assert len(bridge._jobs()) == 1


@pytest.mark.asyncio
async def test_full_input_to_frozen_design_uses_bounded_human_turns(
    tmp_path: Any, monkeypatch: Any
) -> None:
    from collections import Counter

    from tests.agent_phase2_support import configure_offline_validation
    from tests.agent_support import make_project

    target = make_project(tmp_path, monkeypatch)
    configure_offline_validation(monkeypatch, tmp_path)
    bridge = DesignBridge(target.project, "all-gates-thread", target.store)
    models = {r: DesignModel(role=r) for r in DESIGN_ALLOWED}
    goal = (
        "Prepare the synthetic local chain A and freeze a reviewed VHH "
        "design through Gate 3; do not generate."
    )
    try:
        result = await run_session(bridge, scripted_config(), models, goal)
        for gate in ("target-structure", "site-hotspot", "design-specification"):
            assert result["status"] == "awaiting-human-approval", result
            assert result["card"]["gate_type"] == gate
            from tests.unit.agent.test_command_recovery import Crash, crash_at

            prior_execution = bridge.store.latest_execution(bridge.thread)
            unchanged = await run_session(bridge, scripted_config(), models, goal)
            assert unchanged["card"]["card_id"] == result["card"]["card_id"]
            assert bridge.store.latest_execution(bridge.thread) == prior_execution
            crash_at(bridge, "after_gate_execution_intent")
            with pytest.raises(Crash, match="after_gate_execution_intent"):
                await run_session(
                    bridge,
                    scripted_config(),
                    models,
                    goal,
                    decision="approve",
                    card_id=result["card"]["card_id"],
                    user="synthetic-scientist",
                )
            accepted_execution = bridge.store.latest_execution(bridge.thread)
            assert accepted_execution["execution_id"] != prior_execution["execution_id"]
            # A process restart must reuse the persisted human turn, including its budget.
            bridge.store.close()
            bridge = DesignBridge(target.project, "all-gates-thread", SessionStore(target.project))
            result = await run_session(bridge, scripted_config(), models, goal)
            assert bridge.store.latest_execution(bridge.thread) == accepted_execution
        assert result["status"] == "finished" and result["scientific_state"] == "design-frozen"
        calls = [
            e["payload"] for e in bridge.store.events(bridge.thread) if e["kind"] == "model-call"
        ]
        assert max(Counter(c["execution_id"] for c in calls).values()) <= 32
    finally:
        calls = [
            e["payload"] for e in bridge.store.events(bridge.thread) if e["kind"] == "model-call"
        ]
        print("Full-path calls:", dict(Counter(c["role"] for c in calls)))
        print("Full-path executions:", dict(Counter(c["execution_id"] for c in calls)))
        bridge.store.close()


@pytest.mark.asyncio
async def test_oversized_delegation_does_not_dispatch(design_bridge: Any) -> None:
    from types import SimpleNamespace

    from easydesign.agent.harness import RoleBoundary

    boundary = RoleBoundary(
        design_bridge, "coordinator", scripted_config(), "Original research goal"
    )
    request = SimpleNamespace(
        tool_call={
            "name": "task",
            "id": "oversized",
            "args": {
                "subagent_type": "binder-strategy",
                "description": "x" * 1501,
            },
        }
    )

    async def must_not_dispatch(_request: Any) -> Any:
        raise AssertionError("Invalid delegation reached a specialist")

    result = await boundary.awrap_tool_call(request, must_not_dispatch)
    assert result.status == "error" and "not executed" in result.content
    assert design_bridge.current_design() is None
