"""Runtime authority regressions. Every model is synthetic; no scientific acceptance."""

import json
from types import SimpleNamespace
from typing import Any

import pytest
from langchain_core.messages import AIMessage, SystemMessage, ToolMessage

from easydesign.agent.cli import run_session
from easydesign.agent.contracts import AgentBoundaryError
from easydesign.agent.control_flow import next_action
from easydesign.agent.harness import RuntimeCoordinator
from easydesign.agent.phase2 import Phase2Bridge
from easydesign.agent.phase2_tools import DESIGN_ALLOWED, PHASE2_ALLOWED
from easydesign.agent.session_store import SessionStore
from tests.agent_support import judge_card, scripted_config, terminal
from tests.unit.agent.test_command_recovery import Crash, crash_at
from tests.unit.agent.test_design_harness import DesignModel
from tests.unit.agent.test_site_harness import SiteModel


class HostileCoordinator(SiteModel):
    def answer(self, messages: Any) -> AIMessage:
        if self.role == "coordinator":
            pytest.fail("Workflow selection must not call the Coordinator model")
        result = super().answer(messages)
        if self.role == "target":
            for call in result.tool_calls:
                if call["name"] == "TargetInterpretation":
                    evidence = next(
                        json.loads(m.content)
                        for m in reversed(messages)
                        if isinstance(m, ToolMessage) and m.name == "read_target_evidence"
                    )
                    if evidence.get("options"):
                        call["args"]["recommended_option"] = "chain-a"
        return result


@pytest.mark.asyncio
@pytest.mark.parametrize("restart", [False, True])
async def test_gate1_to_actual_research_without_coordinator(bridge: Any, restart: bool) -> None:
    b = Phase2Bridge(bridge.project, bridge.thread, bridge.store)
    models = {r: HostileCoordinator(role=r) for r in PHASE2_ALLOWED}
    goal = "SYNTHETIC prepare chain A, then review a mapped Site."
    first = await run_session(b, scripted_config(), models, goal)
    assert first["status"] == "awaiting-human-approval", first
    assert first["card"]["gate_type"] == "target-structure"
    old_jobs = b._jobs()
    if restart:
        crash_at(b, "after_response_intent")
        with pytest.raises(Crash):
            await run_session(
                b,
                scripted_config(),
                models,
                goal,
                decision="approve",
                card_id=first["card"]["card_id"],
                user="synthetic-scientist",
            )
        store = SessionStore(b.project)
        b = Phase2Bridge(b.project, b.thread, store)
        try:
            result = await run_session(b, scripted_config(), models, goal)
        finally:
            store.close()
    else:
        result = await run_session(
            b,
            scripted_config(),
            models,
            goal,
            decision="approve",
            card_id=first["card"]["card_id"],
            user="synthetic-scientist",
        )
    assert result["status"] == "awaiting-human-approval", result
    assert result["card"]["gate_type"] == "site-hotspot"
    assert len(models["site"].tasks) == 1
    # The original awaiting-human-approval receipt is deliberately preserved.
    assert old_jobs[-1].status == "awaiting-human-approval"
    response = bridge.store.response(bridge.thread, first["card"]["card_id"])
    assert response and response["delivered"]
    calls = [e["payload"] for e in bridge.store.events(bridge.thread) if e["kind"] == "model-call"]
    assert not any(c["role"] == "coordinator" for c in calls)


@pytest.mark.asyncio
async def test_stale_pending_history_cannot_change_actual_dispatch(site_bridge: Any) -> None:
    b = site_bridge
    execution = b.store.begin_execution(b.thread, "SYNTHETIC Site scope")
    boundary = RuntimeCoordinator(
        b,
        "coordinator",
        scripted_config(),
        "SYNTHETIC Site scope",
        execution_id=execution["execution_id"],
    )
    request = SimpleNamespace(
        messages=[
            AIMessage(content="Gate 1 — pending your response. Please confirm chain A again."),
            ToolMessage(content='{"status":"awaiting-human-approval"}', tool_call_id="old-gate"),
        ],
        system_message=SystemMessage(content="Historical pending Gate 1"),
    )

    async def forbidden(_: Any) -> Any:
        pytest.fail("No model is needed to select Site")

    result = await boundary.awrap_model_call(request, forbidden)
    call = result.result[0].tool_calls[0]
    assert call["name"] == "task" and call["args"]["subagent_type"] == "site-mechanism"
    models = {r: HostileCoordinator(role=r) for r in PHASE2_ALLOWED}
    actual = await run_session(b, scripted_config(), models, "SYNTHETIC Site scope")
    assert actual["card"]["gate_type"] == "site-hotspot"
    assert len(models["site"].tasks) == 1


@pytest.mark.asyncio
async def test_product_target_to_site_boundary_starts_no_site_work_in_same_execution(
    site_bridge: Any,
) -> None:
    from easydesign.agent.phase34_runtime import Phase34Runtime

    runtime = Phase34Runtime(
        site_bridge.project,
        "product-phase-boundary-thread",
        site_bridge.store,
        through="handoff",
        product_auto_continue=False,
    )
    runtime.store.event(runtime.thread, "product-title", {"title": "Synthetic product"})
    execution = runtime.store.begin_execution(runtime.thread, "Prepare an exact PDB target")
    runtime.store.event(
        runtime.thread,
        "runtime-action-timing",
        {
            "execution_id": execution["execution_id"],
            "action_id": "target-action",
            "stage": "not-prepared",
            "tool": "task",
            "specialist": "target-intelligence",
            "status": "completed",
        },
    )
    boundary = RuntimeCoordinator(
        runtime,
        "coordinator",
        scripted_config(),
        "Prepare an exact PDB target",
        execution_id=execution["execution_id"],
    )
    request = SimpleNamespace(messages=[], system_message=SystemMessage(content="Runtime"))

    async def forbidden(_: Any) -> Any:
        pytest.fail("The coordinator model must not run at a product phase boundary")

    result = await boundary.awrap_model_call(request, forbidden)
    assert result.result[0].tool_calls == []
    assert "separate bounded continuation" in result.result[0].content
    assert not any(
        event["kind"] == "runtime-dispatch"
        and event["payload"].get("specialist") == "site-mechanism"
        for event in runtime.store.events(runtime.thread)
    )


@pytest.mark.asyncio
async def test_ended_checkpoint_recovers_stale_confirmation_in_same_execution(
    site_bridge: Any,
    monkeypatch: Any,
) -> None:
    from langchain.agents.middleware.types import ModelResponse

    b = site_bridge
    goal = "SYNTHETIC saved premature Gate 1 confirmation"
    models = {r: HostileCoordinator(role=r) for r in PHASE2_ALLOWED}

    async def stale_final(self: Any, request: Any, handler: Any) -> Any:
        return ModelResponse(
            result=[
                AIMessage(
                    content=(
                        "Gate 1 — Target structure chain selection (pending your response). "
                        "Please confirm chain A. Once you respond, I will proceed to Site."
                    )
                )
            ]
        )

    with monkeypatch.context() as patch:
        patch.setattr(RuntimeCoordinator, "awrap_model_call", stale_final)
        stopped = await run_session(b, scripted_config(), models, goal)
    assert stopped["status"] == "incomplete-turn"
    execution = b.store.latest_execution(b.thread)
    reopened = SessionStore(b.project)
    try:
        resumed = Phase2Bridge(b.project, b.thread, reopened)
        result = await run_session(resumed, scripted_config(), models, goal)
        assert result["card"]["gate_type"] == "site-hotspot"
        assert reopened.latest_execution(b.thread) == execution
        assert len(models["site"].tasks) == 1
    finally:
        reopened.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "point", ["before_runtime_dispatch_checkpoint", "after_runtime_action_before_checkpoint"]
)
async def test_crash_around_dispatch_reuses_published_science(site_bridge: Any, point: str) -> None:
    b = site_bridge
    models = {r: HostileCoordinator(role=r) for r in PHASE2_ALLOWED}
    goal = "SYNTHETIC Site publication crash recovery"
    crash_at(b, point)
    with pytest.raises(Crash):
        await run_session(b, scripted_config(), models, goal)
    execution = b.store.latest_execution(b.thread)
    reopened = SessionStore(b.project)
    try:
        resumed = Phase2Bridge(b.project, b.thread, reopened)
        result = await run_session(resumed, scripted_config(), models, goal)
        assert result["card"]["gate_type"] == "site-hotspot"
        assert reopened.latest_execution(b.thread) == execution
        assert len(models["site"].tasks) == 1
        assert len([e for e in reopened.events(b.thread) if e["kind"] == "site-proposal"]) == 1
    finally:
        reopened.close()


@pytest.mark.asyncio
async def test_continuation_reuses_prepared_target_and_gate2_approval(design_bridge: Any) -> None:
    b = design_bridge
    assert next_action(b).arguments["subagent_type"] == "binder-strategy"

    class GuardedDesign(DesignModel):
        def answer(self, messages: Any) -> AIMessage:
            assert self.role not in {"coordinator", "target", "site"}
            return super().answer(messages)

    models = {r: GuardedDesign(role=r) for r in DESIGN_ALLOWED}
    result = await run_session(b, scripted_config(), models, "SYNTHETIC Design continuation")
    assert result["card"]["gate_type"] == "design-specification"
    assert len(models["binder"].tasks) == 1
    assert not models["site"].tasks


def test_approval_intent_and_stale_receipt_cannot_skip_target(
    bridge: Any, monkeypatch: Any
) -> None:
    b = Phase2Bridge(bridge.project, bridge.thread, bridge.store)
    b.prepare_target()
    terminal(b)
    card = judge_card(b)
    b.store.respond(b.thread, card.card_id, "approve", "synthetic-scientist")
    # Persisted intent without applied preparation cannot route to Site.
    assert next_action(b).arguments.get("subagent_type") != "site-mechanism"
    b.apply_decision(card)
    terminal(b)
    assert next_action(b).arguments["subagent_type"] == "site-mechanism"
    current = b.read_evidence()
    older_request = {
        **current,
        "status": "awaiting-human-approval",
        "request_identity": "new-target-revision",
        "evidence_id": "new-evidence",
        "source_evidence_id": "new-source",
    }
    monkeypatch.setattr(b, "read_evidence", lambda *a: older_request)
    assert next_action(b).arguments["subagent_type"] == "target-intelligence"


def test_reopening_site_requires_explicit_scientist_destination(design_bridge: Any) -> None:
    from tests.unit.agent.test_design_runtime import design_card, propose_design

    b = design_bridge
    propose_design(b)
    card = design_card(b)
    b.store.respond(
        b.thread,
        card.card_id,
        "revise",
        "synthetic-scientist",
        human_instruction="Change only CDR settings.",
    )
    b.apply_decision(card)
    b.store.begin_revision(b.thread, card.card_id, "SYNTHETIC design")
    with pytest.raises(AgentBoundaryError, match="explicit Scientist Site"):
        b.reopen_site("HARD_CONTRADICTION: model claims Site should change")
    assert b.project_latest("site-invalidated") is None


def test_old_site_revision_is_not_reapplied_after_a_later_event(design_bridge: Any) -> None:
    from tests.unit.agent.test_design_runtime import design_card, propose_design

    b = design_bridge
    propose_design(b)
    card = design_card(b)
    b.store.respond(
        b.thread,
        card.card_id,
        "revise",
        "synthetic-scientist",
        human_instruction="Reconsider the Site.",
        revision_gate="site-hotspot",
    )
    b.apply_decision(card)
    b.store.begin_revision(b.thread, card.card_id, "SYNTHETIC explicit Site revision")
    b.reopen_site("Reconsider the Site.")
    first = b.project_latest("site-invalidated")
    # A later trusted event must not make the earlier explicit revision look undelivered.
    b.store.event(
        b.thread,
        "site-invalidated",
        {
            "source_card": "synthetic-later-revision",
            "reason": "SYNTHETIC later state",
            "human_instruction": "SYNTHETIC later revision",
            "target_binding": first["target_binding"],
        },
    )
    before = b.store.events(b.thread)
    b.reopen_site("A model asks to replay the old rollback")
    assert b.store.events(b.thread) == before
    assert next_action(b).arguments["subagent_type"] == "site-mechanism"


@pytest.mark.parametrize(
    "gate,option",
    [
        ("pilot-promotion", "PROMOTE_TO_SCALE"),
        ("pilot-promotion", "RUN_ANOTHER_PILOT"),
        ("pilot-promotion", "REVISE_DESIGN"),
        ("pilot-promotion", "REVISE_SITE"),
        ("pilot-promotion", "STOP"),
        ("wet-lab-handoff", "APPROVE"),
    ],
)
def test_downstream_gates_are_ledger_enabled_without_phase2_routing(
    bridge: Any, gate: str, option: str
) -> None:
    from easydesign.agent.contracts import DecisionCard

    card = DecisionCard(
        gate_type=gate,
        card_id="future-gate",
        assessment_id="future-judge",
        project_id=bridge.project_id,
        run_id="future-run",
        request_identity="future",
        evidence_id="future-evidence",
        question="SYNTHETIC future Gate",
        option_id=option,
        options=[{"option_id": option, "label": option, "eligible": True}],
        evidence_refs=[],
        limitations=[],
    )
    bridge.store.save_card(bridge.thread, card)
    response = bridge.store.respond(
        bridge.thread,
        card.card_id,
        "approve",
        "synthetic-scientist",
        selected_option_id=option,
    )
    assert response["response"] == "approve"
    assert response["outcome"]["selected_option_id"] == option
    assert not bridge._jobs()


def test_budget_and_context_contract_unchanged() -> None:
    config = scripted_config()
    assert config.max_model_calls == 64
    assert config.max_input_chars == 120000
    assert config.hard_input_chars == 250000


@pytest.mark.parametrize("site_reused", [False, True])
def test_exam_requires_actual_dispatch_instead_of_coordinator_model_calls(
    site_reused: bool,
    monkeypatch: Any,
    tmp_path: Any,
) -> None:
    monkeypatch.setenv("EASYDESIGN_GOLDEN_SOURCE_ROOT", str(tmp_path))
    from scripts.validate_phase2_goldens import assert_runtime_dispatch

    roles = ["judge"] if site_reused else ["site", "judge"]
    specialists = ["evidence-judge"] if site_reused else ["site-mechanism", "evidence-judge"]
    events = [{"kind": "model-call", "payload": {"role": role}} for role in roles]
    events += [
        {
            "kind": "runtime-dispatch",
            "payload": {
                "specialist": specialist,
                "authority": "verified-runtime-state",
                "model_call": False,
            },
        }
        for specialist in specialists
    ]
    assert_runtime_dispatch(events, site_reused=site_reused)
    with pytest.raises(AssertionError):
        assert_runtime_dispatch(
            [e for e in events if e["kind"] == "runtime-dispatch"], site_reused=site_reused
        )
    with pytest.raises(AssertionError):
        assert_runtime_dispatch(
            [e for e in events if e["kind"] == "model-call"], site_reused=site_reused
        )
    with pytest.raises(AssertionError):
        assert_runtime_dispatch(
            events + [{"kind": "model-call", "payload": {"role": "coordinator"}}],
            site_reused=site_reused,
        )


@pytest.mark.asyncio
async def test_saved_dossier_resumes_synthesis_without_research(site_bridge: Any) -> None:
    from easydesign.agent.phase2 import SITE_EVIDENCE
    from easydesign.agent.site_dossier import persist_dossier
    from tests.unit.agent.test_site_dossier import bind, handoff

    b = site_bridge
    goal = "SYNTHETIC resume the published Dossier"
    execution = b.store.begin_execution(b.thread, goal)
    token = bind(b)
    try:
        persist_dossier(b, handoff(), execution["execution_id"])
    finally:
        SITE_EVIDENCE.reset(token)

    class SynthesisOnly(HostileCoordinator):
        def answer(self, messages: Any) -> AIMessage:
            if self.role == "site":
                assert "RankedSiteDecision" in self.offered, "Completed Research was repeated"
            return super().answer(messages)

    models = {r: SynthesisOnly(role=r) for r in PHASE2_ALLOWED}
    result = await run_session(b, scripted_config(), models, goal)
    assert result["card"]["gate_type"] == "site-hotspot"
    assert not models["site"].tasks
    assert len([e for e in b.store.events(b.thread) if e["kind"] == "site-evidence-dossier"]) == 1


@pytest.mark.asyncio
async def test_real_process_restart_after_applied_gate1(bridge: Any, tmp_path: Any) -> None:
    import asyncio
    import os
    import subprocess
    import sys

    b = Phase2Bridge(bridge.project, bridge.thread, bridge.store)
    goal = "SYNTHETIC chain A then Site, with process restart"
    models = {r: HostileCoordinator(role=r) for r in PHASE2_ALLOWED}
    result = await run_session(b, scripted_config(), models, goal)
    card = b.store.card(b.thread, result["card"]["card_id"])
    b.store.respond(b.thread, card.card_id, "approve", "synthetic-scientist")
    b.apply_decision(card)
    terminal(b)
    before_jobs = len(b._jobs())
    report = tmp_path / "restarted-process.json"
    code = """import asyncio,json,sys
from pathlib import Path
from easydesign.agent.cli import run_session
from easydesign.agent.phase2 import Phase2Bridge
from easydesign.agent.session_store import SessionStore
from easydesign.agent.phase2_tools import PHASE2_ALLOWED
from tests.agent_support import scripted_config
from tests.unit.agent.test_control_flow import HostileCoordinator
s=SessionStore(Path(sys.argv[1]));b=Phase2Bridge(s.project_root,sys.argv[2],s)
try:
 models={r:HostileCoordinator(role=r) for r in PHASE2_ALLOWED}
 result=asyncio.run(run_session(b,scripted_config(),models,sys.argv[3]))
 Path(sys.argv[4]).write_text(json.dumps(result))
finally:s.close()
"""
    process = await asyncio.to_thread(
        subprocess.run,
        [sys.executable, "-c", code, str(b.project), b.thread, goal, str(report)],
        env=dict(os.environ),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert process.returncode == 0, process.stderr
    restarted = json.loads(report.read_text())
    assert restarted["card"]["gate_type"] == "site-hotspot"
    assert len(b._jobs()) == before_jobs
    assert len([e for e in b.store.events(b.thread) if e["kind"] == "site-proposal"]) == 1


def test_supported_judge_alternative_routes_back_to_target_owner(bridge: Any) -> None:
    from easydesign.agent.contracts import EvidenceBinding, JudgeVerdict, TargetInterpretation
    from easydesign.agent.target_assessment import register_target
    from easydesign.agent.tools import JUDGE_EVIDENCE

    b = Phase2Bridge(bridge.project, bridge.thread, bridge.store)
    b.prepare_target()
    terminal(b)
    register_target(
        b,
        TargetInterpretation(
            interpretation=["SYNTHETIC owner confused the selectable chain namespace."],
            unresolved_identity=["SYNTHETIC namespace needs independent review."],
            limitations=["SYNTHETIC fixture has no biological identity."],
            recommended_action="Select chain B.",
            recommended_option="chain-b",
        ),
        None,
    )
    snapshot = b.judge_evidence()
    token = JUDGE_EVIDENCE.set(
        EvidenceBinding.model_validate({k: snapshot[k] for k in EvidenceBinding.model_fields})
    )
    try:
        b.register_judge(
            JudgeVerdict(
                verdict="reject",
                reasons=["SYNTHETIC chain B is not the requested target."],
                limitations=["SYNTHETIC identity remains for Scientist review."],
                recommendation={"option_id": "chain-a", "status": "SUPPORTED"},
            )
        )
    finally:
        JUDGE_EVIDENCE.reset(token)

    revision = next_action(b)
    assert revision.stage == "target-judge-revision"
    assert revision.arguments["subagent_type"] == "target-intelligence"
    assert "chain-a" in revision.arguments["description"]

    register_target(
        b,
        TargetInterpretation(
            interpretation=["SYNTHETIC owner rechecked the runtime chain namespace."],
            unresolved_identity=["SYNTHETIC biological identity remains unconfirmed."],
            limitations=["SYNTHETIC fixture supports only a chain choice."],
            recommended_action="Select chain A.",
            recommended_option="chain-a",
        ),
        None,
    )
    fresh_review = next_action(b)
    assert fresh_review.stage == "judge"
    assert fresh_review.arguments["subagent_type"] == "evidence-judge"


def test_insufficient_target_review_routes_discouraged_proposal_to_scientist(bridge: Any) -> None:
    from easydesign.agent.contracts import (
        ApplyDecision,
        EvidenceBinding,
        JudgeVerdict,
        TargetInterpretation,
    )
    from easydesign.agent.target_assessment import register_target
    from easydesign.agent.tools import JUDGE_EVIDENCE

    b = Phase2Bridge(bridge.project, bridge.thread, bridge.store)
    b.prepare_target()
    terminal(b)
    register_target(
        b,
        TargetInterpretation(
            interpretation=["SYNTHETIC owner selected the runtime-eligible target chain."],
            unresolved_identity=["SYNTHETIC post-approval identity details remain pending."],
            limitations=["SYNTHETIC fixture has only pre-approval facts."],
            recommended_action="Select chain A.",
            recommended_option="chain-a",
        ),
        None,
    )
    snapshot = b.judge_evidence()
    token = JUDGE_EVIDENCE.set(
        EvidenceBinding.model_validate({k: snapshot[k] for k in EvidenceBinding.model_fields})
    )
    try:
        assessment = b.register_judge(
            JudgeVerdict(
                verdict="insufficient",
                reasons=["SYNTHETIC canonical facts are pending until Gate 1 approval."],
                limitations=["SYNTHETIC absence is not a deterministic chain conflict."],
                recommendation={
                    "option_id": "chain-a",
                    "status": "DISCOURAGED",
                    "warnings": ["SYNTHETIC review concern must remain visible."],
                    "alternative": "SYNTHETIC revise the target evidence before approval.",
                },
            )
        )
    finally:
        JUDGE_EVIDENCE.reset(token)

    action = next_action(b)
    assert action.stage == "scientist-gate"
    card = b.decision_card(
        ApplyDecision(assessment_id=assessment.assessment_id, option_id="chain-a")
    )
    assert card.judge_status == "DISCOURAGED"
    assert "SYNTHETIC review concern" in card.warnings[0]


def test_target_judge_revision_is_bounded_across_restartable_state(bridge: Any) -> None:
    from easydesign.agent.contracts import EvidenceBinding, JudgeVerdict, TargetInterpretation
    from easydesign.agent.target_assessment import register_target
    from easydesign.agent.tools import JUDGE_EVIDENCE

    b = Phase2Bridge(bridge.project, bridge.thread, bridge.store)
    b.prepare_target()
    terminal(b)

    def owner() -> None:
        register_target(
            b,
            TargetInterpretation(
                interpretation=["SYNTHETIC owner proposal."],
                unresolved_identity=["SYNTHETIC identity unresolved."],
                limitations=["SYNTHETIC fixture limitation."],
                recommended_action="Select chain B.",
                recommended_option="chain-b",
            ),
            None,
        )

    def reject() -> None:
        snapshot = b.judge_evidence()
        token = JUDGE_EVIDENCE.set(
            EvidenceBinding.model_validate({k: snapshot[k] for k in EvidenceBinding.model_fields})
        )
        try:
            b.register_judge(
                JudgeVerdict(
                    verdict="reject",
                    reasons=["SYNTHETIC owner proposal remains contradictory."],
                    limitations=["SYNTHETIC correction is bounded."],
                    recommendation={"option_id": "chain-a", "status": "SUPPORTED"},
                )
            )
        finally:
            JUDGE_EVIDENCE.reset(token)

    owner()
    reject()
    assert next_action(b).stage == "target-judge-revision"
    owner()
    reject()
    assert next_action(b).stage == "target-judge-revision"
    owner()
    reject()
    blocked = next_action(b)
    assert blocked.stage == "scientific-review-blocked"
    assert blocked.tool is None
