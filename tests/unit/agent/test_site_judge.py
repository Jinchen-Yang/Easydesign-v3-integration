"""Normal Site review and classified failure are separately observable outcomes."""

import json
from copy import deepcopy
from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from easydesign.agent.contracts import (
    AgentBoundaryError,
    ApplyDecision,
    EvidenceBinding,
    JudgeVerdict,
)
from easydesign.agent.session_store import compact
from easydesign.agent.site_judge import SiteJudgeUnavailable, create_site_judge
from easydesign.agent.tools import JUDGE_EVIDENCE
from tests.agent_support import scripted_config
from tests.unit.agent.test_judge_packet import packet_case as base_packet_case
from tests.unit.agent.test_site_harness import SiteModel


@pytest.fixture
def packet_case(site_bridge):
    return base_packet_case.__wrapped__(site_bridge)


def opinion() -> dict[str, Any]:
    return {
        "verdict": "ready-to-ask",
        "recommendation": "DISCOURAGED",
        "reasons": ["The extracellular candidate still has uncertain whole-VHH accessibility."],
        "uncertainties": ["Whole-binder access and biological function remain untested."],
        "warnings": ["Limited exposure raises a feasibility concern."],
        "alternative": "Revise the selected patch or explicitly acknowledge the risks.",
        "corrections": [],
        "fact_refs": ["candidate:0"],
    }


def test_recovery_packet_removes_repeated_corpus_but_keeps_every_candidate_and_prior_fact(
    packet_case,
):
    from easydesign.agent.site_judge import recovery_review_input, review_input

    packet = deepcopy(packet_case["bridge"].judge_evidence())
    packet["decision_evidence"]["source_passages"].append(
        {
            "card_id": "synthetic-large-passage",
            "passage": "SYNTHETIC repeated source corpus " * 4000,
            "source_verified": True,
        }
    )
    full_chars = len(compact(review_input(packet)))
    prior = opinion()
    recovery = recovery_review_input(
        packet,
        failure="MISSING_OR_INVALID_TYPED_SUBMISSION",
        prior_opinion=prior,
        schema_diagnostic="reasons.0 must contain at most 300 characters",
    )
    recovery_chars = len(compact(recovery))
    assert recovery_chars < 30_000
    assert recovery_chars < full_chars // 3
    assert [candidate["candidate_id"] for candidate in recovery["candidate_facts"]] == [
        candidate["candidate_id"] for candidate in packet["candidate_facts"]
    ]
    assert "decision_evidence" not in recovery
    assert recovery["submission_correction"]["prior_unvalidated_submission_to_correct"] == prior
    assert recovery["prior_referenced_facts"]["candidate:0"] == packet["candidate_facts"][0]
    assert json.dumps(recovery, ensure_ascii=False).count("SYNTHETIC repeated source corpus") == 0


class CompactJudgeModel(SiteModel):
    failures: int = 0
    invalid_fact: bool = False
    calls: int = 0

    def bind_tools(self, tools: Any, **kwargs: Any) -> Any:
        self.offered = {t.name for t in tools}
        return self

    def _generate(
        self, messages: Any, stop: Any = None, run_manager: Any = None, **kwargs: Any
    ) -> Any:
        self.calls += 1
        if self.calls <= self.failures:
            message = AIMessage(
                content="",
                response_metadata={"stop_reason": "max_tokens"},
                usage_metadata={"input_tokens": 100, "output_tokens": 8192, "total_tokens": 8292},
            )
        else:
            data = opinion()
            if self.invalid_fact:
                data["fact_claims"] = [
                    {
                        "fact_ref": "mapping:0",
                        "field": "canonical_position",
                        "value": 999,
                    }
                ]
            name = (
                "RecoverySiteJudgeVerdict"
                if "RecoverySiteJudgeVerdict" in self.offered
                else "SiteJudgeVerdict"
            )
            message = AIMessage(
                content="",
                tool_calls=[{"name": name, "args": data, "id": f"judge-{self.calls}"}],
                response_metadata={"stop_reason": "tool_use"},
            )
        return ChatResult(generations=[ChatGeneration(message=message)])


@pytest.mark.asyncio
@pytest.mark.parametrize("failures", [0, 1, 2])
async def test_normal_and_recovery_submit_actual_review(packet_case, failures):
    bridge = packet_case["bridge"]
    execution = bridge.store.latest_execution(bridge.thread)["execution_id"]
    packet = bridge.judge_evidence()
    token = JUDGE_EVIDENCE.set(
        EvidenceBinding.model_validate({k: packet[k] for k in EvidenceBinding.model_fields})
    )
    model = CompactJudgeModel(role="judge", failures=failures)
    try:
        await create_site_judge(bridge, model, scripted_config(), execution).ainvoke(
            {"messages": [HumanMessage(content="Review current proposal.")]}
        )
    finally:
        JUDGE_EVIDENCE.reset(token)
    records = bridge.store.events(bridge.thread)
    assert (
        sum(e["kind"] == "model-call" and e["payload"]["role"] == "judge" for e in records)
        == failures + 1
    )
    assert sum(e["kind"] == "contract-repair" for e in records) == failures
    assert any(e["kind"] == "judge-assessment" for e in records)
    modes = [e["payload"]["tool_mode"] for e in records if e["kind"] == "model-context"]
    assert modes == ["site-judge"] + ["site-judge-recovery"] * failures


@pytest.mark.asyncio
async def test_truncation_exhaustion_is_unavailable_without_fake_assessment(packet_case):
    bridge = packet_case["bridge"]
    execution = bridge.store.latest_execution(bridge.thread)["execution_id"]
    packet = bridge.judge_evidence()
    token = JUDGE_EVIDENCE.set(
        EvidenceBinding.model_validate({k: packet[k] for k in EvidenceBinding.model_fields})
    )
    try:
        with pytest.raises(SiteJudgeUnavailable):
            await create_site_judge(
                bridge, CompactJudgeModel(role="judge", failures=3), scripted_config(), execution
            ).ainvoke({"messages": [HumanMessage(content="Review.")]})
    finally:
        JUDGE_EVIDENCE.reset(token)
    assert not any(e["kind"] == "judge-assessment" for e in bridge.store.events(bridge.thread))
    from easydesign.agent.control_flow import next_action
    from easydesign.agent.site_review_availability import checked_failure, record_unavailable

    receipt = record_unavailable(bridge, execution)
    args = ApplyDecision(review_failure_id=receipt["record_id"], option_id="site")
    card = bridge.decision_card(args)
    assert card.assessment_id is None and card.judge_status is None
    assert card.scientific_summary["independent_review"]["reasons"] == []
    assert card.scientific_summary["independent_review"]["availability"] == "unavailable"
    assert card.scientific_summary["independent_review"]["runtime_facts"]
    assert next_action(bridge).arguments == {
        "review_failure_id": receipt["record_id"],
        "option_id": "site",
    }
    assert record_unavailable(bridge, execution) == receipt
    assert bridge.decision_card(args) == card
    with pytest.raises(AgentBoundaryError):
        bridge.store.respond(bridge.thread, card.card_id, "approve", "synthetic-scientist")
    with pytest.raises(AgentBoundaryError):
        bridge.store.respond(bridge.thread, card.card_id, "override", "synthetic-scientist")
    stale = {**packet, "evidence_id": "different-evidence"}
    with pytest.raises(AgentBoundaryError):
        checked_failure(bridge, stale, receipt["record_id"])
    # Even a later valid negative opinion cannot be hidden by an old outage receipt.
    token = JUDGE_EVIDENCE.set(
        EvidenceBinding.model_validate({k: packet[k] for k in EvidenceBinding.model_fields})
    )
    try:
        bridge.register_judge(
            JudgeVerdict(
                verdict="reject",
                reasons=["The premise is not supportable."],
                limitations=["A new proposal is needed."],
            )
        )
    finally:
        JUDGE_EVIDENCE.reset(token)
    with pytest.raises(AgentBoundaryError):
        bridge.decision_card(args)
    assert next_action(bridge).stage == "scientific-review-blocked"


@pytest.mark.asyncio
async def test_exhausted_review_cannot_restart_calls_or_erase_substantive_error(packet_case):
    from easydesign.agent.site_review_availability import record_unavailable

    bridge = packet_case["bridge"]
    execution = bridge.store.latest_execution(bridge.thread)["execution_id"]
    packet = bridge.judge_evidence()
    token = JUDGE_EVIDENCE.set(
        EvidenceBinding.model_validate({k: packet[k] for k in EvidenceBinding.model_fields})
    )
    try:
        model = CompactJudgeModel(role="judge", invalid_fact=True)
        with pytest.raises(AgentBoundaryError, match="substantive"):
            await create_site_judge(bridge, model, scripted_config(), execution).ainvoke(
                {"messages": [HumanMessage(content="Review.")]}
            )
        before = sum(e["kind"] == "model-call" for e in bridge.store.events(bridge.thread))
        with pytest.raises(AgentBoundaryError, match="substantive"):
            await create_site_judge(bridge, model, scripted_config(), execution).ainvoke(
                {"messages": [HumanMessage(content="Review again.")]}
            )
        assert sum(e["kind"] == "model-call" for e in bridge.store.events(bridge.thread)) == before
        with pytest.raises(AgentBoundaryError):
            record_unavailable(bridge, execution)
    finally:
        JUDGE_EVIDENCE.reset(token)


@pytest.mark.asyncio
@pytest.mark.parametrize("failures", [0, 3])
async def test_native_judge_to_gate_preserves_human_authority(packet_case, failures):
    from easydesign.agent.cli import run_session
    from easydesign.agent.design import DesignBridge
    from easydesign.agent.phase2_tools import PHASE2_ALLOWED

    bridge = packet_case["bridge"]
    models = {role: SiteModel(role=role) for role in PHASE2_ALLOWED}
    models["judge"] = CompactJudgeModel(role="judge", failures=failures)
    from easydesign.agent.harness import fingerprint

    goal = "SYNTHETIC structural exploration"
    # This synthetic packet fixture predates the harness; bind its test-only thread.
    bridge.store.db.execute(
        "UPDATE threads SET fingerprint=? WHERE id=?",
        (fingerprint(scripted_config()), bridge.thread),
    )
    bridge.store.db.commit()
    before = len(bridge.store.events(bridge.thread))
    pending = await run_session(bridge, scripted_config(), models, goal)
    assert pending["status"] == "awaiting-human-approval"
    events = bridge.store.events(bridge.thread)[before:]
    assert {e["payload"]["role"] for e in events if e["kind"] == "model-call"} == {"judge"}
    assert bridge.approved_site() is None
    card = bridge.store.card(bridge.thread, pending["card"]["card_id"])
    if failures:
        assert card.assessment_id is None and card.judge_status is None
        assert not any(e["kind"] == "judge-assessment" for e in events)
        assert card.scientific_summary["independent_review"]["availability"] == "unavailable"
    else:
        assert card.assessment_id is not None and card.judge_status == "DISCOURAGED"
        assert any(e["kind"] == "site-judge-submission" for e in events)
    approved = await run_session(
        bridge,
        scripted_config(),
        models,
        goal,
        decision="override",
        card_id=card.card_id,
        user="synthetic-scientist",
        explicit_acknowledgement="SYNTHETIC acknowledge the displayed review and its limitations",
        optional_reason="SYNTHETIC bounded structural exploration",
    )
    assert approved["status"] == "finished"
    assert bridge.approved_site() is not None
    downstream = DesignBridge(bridge.project, "synthetic-review-design", bridge.store)
    assert (
        downstream.read_design_evidence()["upstream_decision"]["judge_review"]
        == (card.scientific_summary["independent_review"])
    )
    if failures:
        assert models["judge"].calls == 3


class BrokenJudgeModel(CompactJudgeModel):
    failure_kind: str

    def _generate(self, messages: Any, stop: Any = None, run_manager: Any = None, **kwargs: Any):
        import httpx
        from anthropic import APITimeoutError

        if self.failure_kind == "unexpected":
            raise RuntimeError("synthetic unexpected implementation fault")
        if self.failure_kind == "timeout":
            raise APITimeoutError(request=httpx.Request("POST", "https://synthetic.invalid"))
        if self.failure_kind in {"invalid-schema", "invalid-negative", "invalid-fact-and-schema"}:
            self.calls += 1
            if self.calls == 1 or self.failure_kind != "invalid-schema":
                data = opinion()
                if self.failure_kind == "invalid-negative":
                    data["verdict"] = "reject"
                data["reasons"] = ["x" * 301]
                if self.failure_kind == "invalid-fact-and-schema":
                    data["fact_claims"] = [
                        {"fact_ref": "mapping:0"},
                        {
                            "fact_ref": "mapping:0",
                            "field": "canonical_position",
                            "value": 999,
                            "unexpected_field": "cannot mask the conflicting assertion",
                        },
                    ]
                return ChatResult(
                    generations=[
                        ChatGeneration(
                            message=AIMessage(
                                content="",
                                tool_calls=[
                                    {
                                        "name": next(iter(self.offered)),
                                        "args": data,
                                        "id": "invalid-schema",
                                    }
                                ],
                            )
                        )
                    ]
                )
            import json

            payload = json.loads(next(m.text for m in messages if isinstance(m, HumanMessage)))
            assert "300" in payload["submission_correction"]["schema_diagnostic"]
            assert payload["submission_correction"]["prior_unvalidated_submission_to_correct"][
                "reasons"
            ] == ["x" * 301]
        return super()._generate(messages, stop, run_manager, **kwargs)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kind",
    [
        "unexpected",
        "timeout",
        "invalid-schema",
        "invalid-negative",
        "invalid-fact-and-schema",
    ],
)
async def test_only_known_technical_failure_is_degraded_and_recovery_gets_diagnostic(
    packet_case, kind
):
    from easydesign.agent.site_judge import create_site_aware_judge

    bridge = packet_case["bridge"]
    execution = bridge.store.latest_execution(bridge.thread)["execution_id"]
    packet = bridge.judge_evidence()
    token = JUDGE_EVIDENCE.set(
        EvidenceBinding.model_validate({k: packet[k] for k in EvidenceBinding.model_fields})
    )

    async def never_legacy(state):
        raise AssertionError("Site must use its compact review contract")

    try:
        agent = create_site_aware_judge(
            bridge,
            BrokenJudgeModel(role="judge", failure_kind=kind),
            scripted_config(),
            execution,
            never_legacy,
        )
        if kind in {"invalid-negative", "invalid-fact-and-schema"}:
            with pytest.raises(AgentBoundaryError, match="substantive"):
                await agent.ainvoke({"messages": [HumanMessage(content="Review.")]})
        elif kind == "unexpected":
            with pytest.raises(RuntimeError, match="unexpected implementation fault"):
                await agent.ainvoke({"messages": [HumanMessage(content="Review.")]})
        else:
            await agent.ainvoke({"messages": [HumanMessage(content="Review.")]})
    finally:
        JUDGE_EVIDENCE.reset(token)
    events = bridge.store.events(bridge.thread)
    assert any(e["kind"] == "site-judge-unavailable" for e in events) == (kind == "timeout")
    assert any(e["kind"] == "judge-assessment" for e in events) == (kind == "invalid-schema")
    if kind == "invalid-fact-and-schema":
        rejected = [e["payload"] for e in events if e["kind"] == "rejected-submission"]
        assert len(rejected) == 3
        assert all("JUDGE_FACT_CONFLICT" in r["diagnostic"] for r in rejected)
        assert all(r["substantive_finding"] and not r["schema_valid"] for r in rejected)
    if kind == "unexpected":
        assert sum(e["kind"] == "model-call" for e in events) == 1


@pytest.mark.asyncio
async def test_unavailable_card_cannot_hide_hard_failure_or_later_negative(
    packet_case, monkeypatch
):
    from easydesign.agent.site_review_availability import record_unavailable

    bridge = packet_case["bridge"]
    execution = bridge.store.latest_execution(bridge.thread)["execution_id"]
    packet = bridge.judge_evidence()
    token = JUDGE_EVIDENCE.set(
        EvidenceBinding.model_validate({k: packet[k] for k in EvidenceBinding.model_fields})
    )
    try:
        with pytest.raises(SiteJudgeUnavailable):
            await create_site_judge(
                bridge, CompactJudgeModel(role="judge", failures=3), scripted_config(), execution
            ).ainvoke({"messages": [HumanMessage(content="Review.")]})
        failure = record_unavailable(bridge, execution)
        args = ApplyDecision(review_failure_id=failure["record_id"], option_id="site")
        original = bridge.site_snapshot

        def hard_failure(*args, **kwargs):
            raise AgentBoundaryError("HARD_FACT_CONTRADICTION synthetic stale source")

        with monkeypatch.context() as patch:
            patch.setattr(bridge, "site_snapshot", hard_failure)
            with pytest.raises(AgentBoundaryError, match="HARD_FACT_CONTRADICTION"):
                bridge.decision_card(args)
        assert bridge.site_snapshot == original
        proposal = bridge.current_site()
        with monkeypatch.context() as patch:
            patch.setattr(
                bridge,
                "current_site",
                lambda: {**proposal, "evaluation": {**proposal["evaluation"], "status": "BLOCKED"}},
            )
            with pytest.raises(AgentBoundaryError):
                bridge.decision_card(args)
        card = bridge.decision_card(args)
        bridge.store.respond(
            bridge.thread,
            card.card_id,
            "override",
            "synthetic-scientist",
            explicit_acknowledgement="SYNTHETIC acknowledge unavailable review",
            optional_reason="SYNTHETIC bounded structural exploration",
        )
        bridge.register_judge(
            JudgeVerdict(
                verdict="reject",
                reasons=["SYNTHETIC premise is not supportable."],
                limitations=["A new proposal is needed."],
            )
        )
        with pytest.raises(AgentBoundaryError, match="cannot be replaced"):
            bridge.apply_decision(card)
        assert bridge.approved_site() is None
    finally:
        JUDGE_EVIDENCE.reset(token)


def test_compact_opinion_binds_structured_claims_without_rewriting_prose(packet_case):
    from easydesign.agent.site_judge import SiteJudgeVerdict, normalize_opinion

    packet = packet_case["bridge"].judge_evidence()
    data = opinion()
    data["fact_claims"] = [
        {
            "fact_ref": "candidate:0",
            "field": "design_labels",
            "value": packet["candidate_facts"][0]["design_labels"],
        }
    ]
    result = normalize_opinion(SiteJudgeVerdict.model_validate(data), packet)
    assert result.reasons == data["reasons"]
    assert result.fact_refs == [f"{packet['fact_revision']}:candidate:0"]
    assert result.fact_claims[0].fact_ref == result.fact_refs[0]
    assert result.fact_claims[0].value == data["fact_claims"][0]["value"]


def test_all_structured_errors_are_reported_together_with_addressable_fields(packet_case):
    from easydesign.agent.site_judge import SiteJudgeVerdict, normalize_opinion

    packet = packet_case["bridge"].judge_evidence()
    data = opinion()
    data["alternative"] = None
    data["fact_refs"] = ["reference:0"]
    data["fact_claims"] = [
        {"fact_ref": "candidate:0", "field": "invented_location", "value": 113},
        {"fact_ref": "mapping:0", "field": "canonical_position", "value": 999},
    ]
    with pytest.raises(AgentBoundaryError) as caught:
        normalize_opinion(SiteJudgeVerdict.model_validate(data), packet)
    diagnostic = str(caught.value)
    for detail in (
        "DISCOURAGED requires",
        "reference:0",
        "available_collections",
        "candidate:0",
        "invented_location",
        "available_fields",
        "design_labels",
        "mapping:0",
        "canonical_position",
        "JUDGE_FACT_CONFLICT",
    ):
        assert detail in diagnostic
    fixed = opinion()
    assert (
        normalize_opinion(SiteJudgeVerdict.model_validate(fixed), packet).reasons
        == fixed["reasons"]
    )
