"""Typed submission and immutable runtime facts through the real Agent graph (scripted model)."""

from typing import Any

import pytest
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from pydantic import Field, ValidationError

from easydesign.agent.contracts import (
    AgentBoundaryError,
    TargetFacts,
    TargetInterpretation,
    TargetRecommendationMismatch,
)
from easydesign.agent.harness import create_harness
from easydesign.agent.phase2 import Phase2Bridge
from easydesign.agent.phase2_tools import PHASE2_ALLOWED
from easydesign.agent.session_store import SessionStore
from easydesign.agent.target_assessment import (
    HardFactContradiction,
    check_fact_claims,
    check_interpretation,
    register_target,
)
from tests.agent_golden_support import golden_truth
from tests.agent_support import scripted_config
from tests.unit.agent.test_phase2_golden_spec import resolve
from tests.unit.agent.test_prerequisite_recovery import RecoveryModel


def runtime_evidence() -> dict[str, Any]:
    report = resolve(golden_truth()["soluble"])
    return {
        "source_evidence_id": "verified-test-source",
        "evidence_refs": [],
        "options": [],
        "hard_facts": TargetFacts(
            canonical_accession=report.canonical.accession,
            canonical_length=report.canonical.sequence_length,
            chains=[
                {
                    "auth_chain": report.construct_identity.auth_chain_id,
                    "construct_length": report.construct_identity.sequence_length,
                    "observed_length": len(report.observed.observed_construct_positions),
                    "missing_construct_positions": list(
                        report.observed.missing_construct_positions
                    ),
                }
            ],
        ).model_dump(mode="json"),
    }


def opinion(
    text: str = "The precursor/construct difference requires a scoped interpretation.",
) -> dict[str, Any]:
    return {
        "interpretation": [text],
        "unresolved_identity": [],
        "limitations": ["Structure does not establish biological efficacy."],
        "recommended_action": "Request independent review of the verified choice.",
    }


class SubmissionModel(RecoveryModel):
    fault: str = "prose"
    submissions: int = 0
    forever: bool = False
    seen_diagnostics: list[str] = Field(default_factory=list)

    def answer(self, messages: Any) -> AIMessage:
        if self.role == "coordinator":
            return super().answer(messages)
        if not any(isinstance(m, ToolMessage) for m in messages):
            return self.call("read_file", file_path="/skills/target-intelligence/SKILL.md")
        self.submissions += 1
        self.seen_diagnostics.extend(
            m.text for m in messages if "SUBMISSION" in m.text or "CONTRADICTION" in m.text
        )
        if self.fault == "option-after-prose":
            if self.submissions == 1:
                return AIMessage(content="Submit the verified Target conclusion.")
            if self.submissions == 2:
                return self.call("TargetInterpretation", **opinion())
            return self.call(
                "TargetInterpretation", **opinion(), recommended_option="chain-a"
            )
        if self.fault == "option-forever":
            return self.call("TargetInterpretation", **opinion())
        if self.submissions == 1 or self.forever:
            if self.fault == "prose":
                return AIMessage(content='Explanation. ```json {"canonical_length":132} ```')
            if self.fault == "json-text":
                import json

                return AIMessage(content=json.dumps(opinion()))
            if self.fault == "schema":
                return self.call("TargetInterpretation", **opinion(), canonical_length=132)
            if self.fault == "invalid-json":
                return AIMessage(
                    content="",
                    invalid_tool_calls=[
                        {
                            "id": "malformed-submit",
                            "name": "TargetInterpretation",
                            "args": "{bad json",
                            "error": "invalid JSON",
                        }
                    ],
                )
            if self.fault == "contradiction":
                return self.call(
                    "TargetInterpretation",
                    **opinion("The canonical protein contains 132 residues."),
                )
            if self.fault == "mixed":
                submitted = self.call("TargetInterpretation", **opinion())
                return submitted.model_copy(
                    update={
                        "tool_calls": [
                            *submitted.tool_calls,
                            *self.call("prepare_target").tool_calls,
                        ]
                    }
                )
        return self.call("TargetInterpretation", **opinion())


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fault", ["prose", "json-text", "schema", "invalid-json", "contradiction", "mixed"]
)
async def test_typed_submission_corrects_once_without_prose_authority(
    bridge: Any, monkeypatch: Any, fault: str
) -> None:
    b = Phase2Bridge(bridge.project, bridge.thread, bridge.store)
    evidence = runtime_evidence()
    monkeypatch.setattr(b, "target_submission_evidence", lambda: evidence)
    execution = b.store.begin_execution(b.thread, "Assess the construct")
    models = {role: SubmissionModel(role=role, fault=fault) for role in PHASE2_ALLOWED}
    graph = create_harness(
        b,
        models,
        scripted_config(),
        MemorySaver(),
        "Assess the construct",
        execution_id=execution["execution_id"],
    )
    await graph.ainvoke(
        {"messages": [{"role": "user", "content": "Assess the construct"}]},
        {"configurable": {"thread_id": b.thread}},
    )
    events = b.store.events(b.thread)
    assessments = [e["payload"] for e in events if e["kind"] == "target-assessment"]
    assert len(assessments) == 1
    assert assessments[0]["hard_facts"]["canonical_length"] == 147
    assert assessments[0]["hard_facts"]["chains"][0]["construct_length"] == 129
    assert assessments[0]["hard_facts"]["chains"][0]["observed_length"] == 127
    assert assessments[0]["interpretation"] == TargetInterpretation.model_validate(
        opinion()
    ).model_dump(mode="json")
    assert len([e for e in events if e["kind"] == "contract-repair"]) == 1
    assert models["target"].seen_diagnostics
    assert not b._jobs()
    assert b.store.db.execute("SELECT count(*) FROM cards").fetchone()[0] == 0


@pytest.mark.asyncio
async def test_repeated_bad_submission_exhausts_durable_budget_without_registering(
    bridge: Any,
) -> None:
    b = Phase2Bridge(bridge.project, bridge.thread, bridge.store)
    execution = b.store.begin_execution(b.thread, "Assess")
    models = {role: SubmissionModel(role=role, forever=True) for role in PHASE2_ALLOWED}
    graph = create_harness(
        b,
        models,
        scripted_config(),
        MemorySaver(),
        "Assess",
        execution_id=execution["execution_id"],
    )
    with pytest.raises(AgentBoundaryError, match="contract repair budget"):
        await graph.ainvoke(
            {"messages": [{"role": "user", "content": "Assess"}]},
            {"configurable": {"thread_id": b.thread}},
        )
    assert not any(e["kind"] == "target-assessment" for e in b.store.events(b.thread))
    reopened = SessionStore(b.project)
    try:
        with pytest.raises(AgentBoundaryError, match="contract repair budget"):
            reopened.reserve_contract_repair(
                b.thread, "judge", execution["execution_id"], "bad schema"
            )
        following = reopened.begin_execution(b.thread, "Clarification", followup=True)
        assert (
            reopened.reserve_contract_repair(
                b.thread, "target", following["execution_id"], "bad schema"
            )
            == 1
        )
    finally:
        reopened.close()


@pytest.mark.asyncio
async def test_target_option_mismatch_uses_remaining_typed_contract_repair(
    bridge: Any, monkeypatch: Any
) -> None:
    b = Phase2Bridge(bridge.project, bridge.thread, bridge.store)
    evidence = {
        **runtime_evidence(),
        "options": [
            {"option_id": "chain-a", "eligible": True},
            {"option_id": "chain-b", "eligible": False},
        ],
    }
    monkeypatch.setattr(b, "target_submission_evidence", lambda: evidence)
    execution = b.store.begin_execution(b.thread, "Choose one eligible target chain")
    models = {
        role: SubmissionModel(role=role, fault="option-after-prose") for role in PHASE2_ALLOWED
    }
    graph = create_harness(
        b,
        models,
        scripted_config(),
        MemorySaver(),
        "Choose one eligible target chain",
        execution_id=execution["execution_id"],
    )

    await graph.ainvoke(
        {"messages": [{"role": "user", "content": "Choose one eligible target chain"}]},
        {"configurable": {"thread_id": b.thread}},
    )

    events = b.store.events(b.thread)
    repairs = [event["payload"] for event in events if event["kind"] == "contract-repair"]
    assert [repair["contract"] for repair in repairs] == [
        "TargetInterpretation",
        "TargetInterpretation",
    ]
    assert [repair["attempt"] for repair in repairs] == [1, 2]
    rejected = [
        event["payload"]["diagnostic"]
        for event in events
        if event["kind"] == "rejected-submission"
    ]
    assert any("must name one eligible option" in diagnostic for diagnostic in rejected)
    assessment = next(
        event["payload"] for event in events if event["kind"] == "target-assessment"
    )
    assert assessment["interpretation"]["recommended_option"] == "chain-a"
    assert models["target"].submissions == 3


@pytest.mark.asyncio
async def test_repeated_target_option_mismatch_exhausts_without_fourth_submission(
    bridge: Any, monkeypatch: Any
) -> None:
    b = Phase2Bridge(bridge.project, bridge.thread, bridge.store)
    evidence = {
        **runtime_evidence(),
        "options": [{"option_id": "chain-a", "eligible": True}],
    }
    monkeypatch.setattr(b, "target_submission_evidence", lambda: evidence)
    execution = b.store.begin_execution(b.thread, "Keep omitting the eligible target chain")
    models = {
        role: SubmissionModel(role=role, fault="option-forever") for role in PHASE2_ALLOWED
    }
    graph = create_harness(
        b,
        models,
        scripted_config(),
        MemorySaver(),
        "Keep omitting the eligible target chain",
        execution_id=execution["execution_id"],
    )

    with pytest.raises(AgentBoundaryError, match="contract repair budget exhausted"):
        await graph.ainvoke(
            {"messages": [{"role": "user", "content": "Omit the eligible target chain"}]},
            {"configurable": {"thread_id": b.thread}},
        )

    assert models["target"].submissions == 3
    events = b.store.events(b.thread)
    assert len([event for event in events if event["kind"] == "contract-repair"]) == 2
    assert not any(event["kind"] == "target-assessment" for event in events)


@pytest.mark.parametrize("stop_reason", ["max_tokens", "end_turn"])
def test_schema_failure_metadata_survives_exhausted_budget_without_reasoning_text(
    bridge: Any, stop_reason: str
) -> None:
    from langchain.agents.structured_output import StructuredOutputValidationError

    from easydesign.agent.harness import RoleBoundary

    b = Phase2Bridge(bridge.project, bridge.thread, bridge.store)
    eid = b.store.begin_execution(b.thread, "SYNTHETIC empty synthesis diagnostic")["execution_id"]
    boundary = RoleBoundary(
        b, "site", scripted_config(), "SYNTHETIC evidence", execution_id=eid, site_stage="synthesis"
    )
    boundary.contract_error("SYNTHETIC prior correction 1")
    boundary.contract_error("SYNTHETIC prior correction 2")
    message = AIMessage(
        content=[{"type": "thinking", "thinking": "SYNTHETIC_PRIVATE_SENTINEL", "signature": "x"}],
        tool_calls=[{"name": "SiteDecision", "args": {}, "id": "synthetic-empty"}],
        response_metadata={"stop_reason": stop_reason},
        usage_metadata={"input_tokens": 100, "output_tokens": 200, "total_tokens": 300},
    )
    error = StructuredOutputValidationError("SiteDecision", ValueError("Required fields"), message)
    with pytest.raises(AgentBoundaryError, match="contract repair budget"):
        boundary.contract_error(error)
    event = b.thread_latest("structured-output-error")
    assert event["site_stage"] == "synthesis" and event["execution_id"] == eid
    assert event["stop_reason"] == stop_reason
    assert event["usage"] == message.usage_metadata
    assert event["tool_calls"] == message.tool_calls
    assert "SYNTHETIC_PRIVATE_SENTINEL" not in str(event)
    assert "do not count this usage twice" in event["usage_scope"]
    assert len([e for e in b.store.events(b.thread) if e["kind"] == "contract-repair"]) == 2
    assert b.store.db.execute("SELECT count(*) FROM cards").fetchone()[0] == 0


def test_fresh_synthesis_corrections_are_separate_but_persist_and_share_call_limit(
    bridge: Any,
) -> None:
    from easydesign.agent.harness import RoleBoundary

    b = Phase2Bridge(bridge.project, bridge.thread, bridge.store)
    eid = b.store.begin_execution(b.thread, "SYNTHETIC isolated contract corrections")[
        "execution_id"
    ]
    config = scripted_config()
    research = RoleBoundary(b, "site", config, "SYNTHETIC", execution_id=eid, site_stage="research")
    synthesis = RoleBoundary(
        b, "site", config, "SYNTHETIC", execution_id=eid, site_stage="synthesis"
    )
    for _ in range(2):
        research.contract_error("SYNTHETIC Handoff correction")
    for _ in range(2):
        synthesis.contract_error("SYNTHETIC SiteDecision correction")
    for boundary in (research, synthesis):
        with pytest.raises(AgentBoundaryError, match="contract repair budget"):
            boundary.contract_error("Still invalid")
    reopened = SessionStore(b.project)
    try:
        for contract in ("SiteResearchHandoff", "RankedSiteDecision"):
            with pytest.raises(AgentBoundaryError, match="contract repair budget"):
                reopened.reserve_contract_repair(
                    b.thread, "site", eid, "SYNTHETIC restart", contract=contract
                )
        for _ in range(config.max_model_calls):
            reopened.reserve_model_call(b.thread, "site", config.max_model_calls, eid)
        with pytest.raises(AgentBoundaryError, match="model-call budget"):
            reopened.reserve_model_call(b.thread, "judge", config.max_model_calls, eid)
    finally:
        reopened.close()
    assert b.store.db.execute("SELECT count(*) FROM cards").fetchone()[0] == 0


@pytest.mark.parametrize(
    "claim",
    [
        "canonical length is 132",
        "canonical protein contains 132 residues",
        "canonical 132 aa",
        "canonical_sequence_length: 132",
        "canonical 长度为132",
        "canonical length = 147/148",
        "132-residue canonical sequence",
        "Chain L construct length is 148",
        "Chain L observed length is 129",
        "Chain L observed 129 residues",
        "Chain L construct length = 129/148",
    ],
)
def test_known_fact_contradictions_cannot_register(
    bridge: Any, monkeypatch: Any, claim: str
) -> None:
    evidence = runtime_evidence()
    monkeypatch.setattr(bridge, "target_submission_evidence", lambda: evidence)
    with pytest.raises(HardFactContradiction, match="HARD_FACT_CONTRADICTION"):
        register_target(bridge, TargetInterpretation.model_validate(opinion(claim)), None)
    assert evidence["hard_facts"]["canonical_length"] == 147
    assert not any(e["kind"] == "target-assessment" for e in bridge.store.events(bridge.thread))


@pytest.mark.parametrize(
    "claim",
    [
        "The catalytic dyad is at canonical 53 (=Glu35, label 35) and 70 (=Asp52, label 52).",
        "Canonical 53 and canonical 70 are residue positions, not lengths.",
        "Canonical 19–147 corresponds to the mature construct.",
        "Chain L construct 35 maps to canonical 53; chain L observed 35 has coordinates.",
        {"topic": "canonical", "passage": "53 residues form a separately described fragment."},
        "The canonical length is 147; chain L construct length is 129 and "
        "chain L observed length is 127.",
    ],
)
def test_count_guard_does_not_treat_residue_positions_as_sequence_lengths(claim: Any) -> None:
    from easydesign.agent.target_assessment import check_fact_claims

    check_fact_claims(claim, runtime_evidence())


def test_unresolved_canonical_length_cannot_be_invented_from_construct_length() -> None:
    evidence = runtime_evidence()
    evidence["hard_facts"] = {**evidence["hard_facts"], "canonical_length": None}
    with pytest.raises(HardFactContradiction, match='"expected":"unresolved"'):
        check_interpretation(
            TargetInterpretation.model_validate(
                opinion("The canonical sequence contains 406 aa."),
            ),
            evidence,
        )


def test_structure_resolution_superlative_must_match_runtime_options() -> None:
    evidence = {
        **runtime_evidence(),
        "options": [
            {
                "option_id": "pdb-9w1j-entity-5",
                "eligible": True,
                "payload": {"candidate_summary": {"resolution_angstrom": 2.97}},
            },
            {
                "option_id": "pdb-9w2j-entity-4",
                "eligible": True,
                "payload": {"candidate_summary": {"resolution_angstrom": 2.82}},
            },
        ],
    }
    bad = TargetInterpretation.model_validate(
        {
            **opinion(),
            "recommended_option": "pdb-9w1j-entity-5",
            "recommended_action": "Select 9W1J because it has the best resolution.",
        }
    )
    with pytest.raises(HardFactContradiction, match="structure_resolution_superlative"):
        check_interpretation(bad, evidence)

    good = bad.model_copy(
        update={
            "recommended_action": (
                "Select 9W1J at 2.97 Angstrom because its endogenous-ligand context is preferred."
            )
        }
    )
    check_interpretation(good, evidence)

    with pytest.raises(HardFactContradiction, match="structure_resolution_superlative"):
        check_fact_claims(
            {
                "reasons": ["9W1J has the highest resolution in the eligible set."],
                "recommendation": {"option_id": "pdb-9w1j-entity-5"},
            },
            evidence,
        )


def test_resolution_superlative_honors_explicit_runtime_verifiable_subset() -> None:
    evidence = {
        **runtime_evidence(),
        "options": [
            {
                "option_id": "pdb-9w1j-entity-5",
                "eligible": True,
                "payload": {
                    "pdb_id": "9W1J",
                    "candidate_summary": {
                        "resolution_angstrom": 2.97,
                        "source_part_count": 1,
                        "multiple_source_flag": "N",
                    },
                },
            },
            {
                "option_id": "pdb-9w2j-entity-4",
                "eligible": True,
                "payload": {
                    "pdb_id": "9W2J",
                    "candidate_summary": {
                        "resolution_angstrom": 2.82,
                        "source_part_count": 1,
                        "multiple_source_flag": "N",
                    },
                },
            },
            {
                "option_id": "pdb-7xwo-entity-1",
                "eligible": True,
                "payload": {
                    "pdb_id": "7XWO",
                    "candidate_summary": {
                        "resolution_angstrom": 2.70,
                        "source_part_count": 2,
                        "multiple_source_flag": "Y",
                    },
                },
            },
        ],
    }
    check_fact_claims(
        {
            "recommended_action": "9W2J has the best resolution among non-fused entries.",
            "recommended_option": "pdb-9w2j-entity-4",
        },
        evidence,
    )
    check_fact_claims(
        {
            "reasons": ["7XWO has the best nominal resolution, but it is a fusion."],
            "recommendation": {"option_id": "pdb-9w2j-entity-4"},
        },
        evidence,
    )
    with pytest.raises(HardFactContradiction, match="structure_resolution_superlative"):
        check_fact_claims(
            {
                "reasons": ["9W1J has the best resolution in the clean 9W series."],
                "recommendation": {"option_id": "pdb-9w1j-entity-5"},
            },
            evidence,
        )


def test_model_cannot_supply_runtime_fields_and_open_interpretation_is_allowed() -> None:
    for key in (
        "canonical_length",
        "hard_facts",
        "evidence_refs",
        "source_evidence_id",
        "selectable_options",
    ):
        with pytest.raises(ValidationError):
            TargetInterpretation.model_validate({**opinion(), key: "forged"})
    check_interpretation(
        TargetInterpretation.model_validate(
            opinion(
                "The canonical length is 147. Removal of the precursor signal peptide is "
                "consistent with this construct; function requires experiments."
            )
        ),
        runtime_evidence(),
    )


def test_target_interpretation_requires_an_option_when_runtime_offers_choices() -> None:
    evidence = {
        **runtime_evidence(),
        "options": [
            {"option_id": "chain-a", "eligible": True},
            {"option_id": "chain-b", "eligible": True},
        ],
    }
    with pytest.raises(TargetRecommendationMismatch, match="must name one eligible option"):
        check_interpretation(TargetInterpretation.model_validate(opinion()), evidence)

    with pytest.raises(TargetRecommendationMismatch, match="missing/ineligible option"):
        check_interpretation(
            TargetInterpretation.model_validate(
                {**opinion(), "recommended_option": "chain-missing"}
            ),
            evidence,
        )

    check_interpretation(
        TargetInterpretation.model_validate({**opinion(), "recommended_option": "chain-a"}),
        evidence,
    )


def test_public_target_facts_are_rendered_without_coordinator_restatement() -> None:
    from easydesign.agent.target_assessment import present_target

    evidence = runtime_evidence()
    raw = {
        "status": "finished",
        "message": "Canonical protein contains 132 residues. Binding needs experiments.",
    }
    public = present_target(raw, evidence)
    assert "132" not in public["message"]
    assert "Binding needs experiments" in public["message"]
    assert public["target"]["facts"]["canonical_length"] == 147
    assert "132" in raw["message"]  # Original diagnostic message retained independently.


def test_public_target_fact_filter_does_not_split_decimals_or_file_extensions() -> None:
    from easydesign.agent.target_assessment import present_target

    public = present_target(
        {
            "status": "finished",
            "message": (
                "Selected chain R uses the 9W1J structure at 2.97 Å. "
                "Viewer: results/report/index.html. Binding needs experiments."
            ),
        },
        runtime_evidence(),
    )
    assert "97 Å" not in public["message"]
    assert "index.html" in public["message"]
    assert "Binding needs experiments" in public["message"]


def test_gate_payload_uses_runtime_facts_and_old_judge_cannot_approve_new_interpretation(
    bridge: Any,
) -> None:
    from easydesign.agent.contracts import ApplyDecision
    from tests.agent_support import judge_card, terminal

    bridge.prepare_target()
    terminal(bridge)
    before = bridge.read_evidence()
    owner = register_target(
        bridge,
        TargetInterpretation.model_validate({**opinion(), "recommended_option": "chain-a"}),
        None,
    )
    first = judge_card(bridge)
    assert first.scientific_summary["hard_facts"] == before["hard_facts"] == owner["hard_facts"]
    assert first.scientific_summary["interpretation"] == owner["interpretation"]
    changed = TargetInterpretation.model_validate(
        {
            **opinion("The alternative chain warrants a separate review."),
            "recommended_option": "chain-a",
        }
    )
    register_target(bridge, changed, None)
    with pytest.raises(AgentBoundaryError, match="Evidence/request changed"):
        bridge.decision_card(
            ApplyDecision(assessment_id=first.assessment_id, option_id=first.option_id)
        )
    assert bridge.read_evidence()["hard_facts"] == before["hard_facts"]
    second = judge_card(bridge)
    assert second.evidence_id != first.evidence_id
    assert second.scientific_summary["hard_facts"] == before["hard_facts"]
    assert not bridge.store.response(bridge.thread, first.card_id)


def test_site_and_judge_cannot_publish_known_target_count_contradiction(site_bridge: Any) -> None:
    from easydesign.agent.contracts import EvidenceBinding, JudgeVerdict
    from easydesign.agent.tools import JUDGE_EVIDENCE
    from tests.unit.agent.test_site_runtime import propose, site_intent

    bad = site_intent().model_copy(
        update={"mechanistic_rationale": "Chain A observed length is 9999."}
    )
    with pytest.raises(HardFactContradiction):
        propose(site_bridge, bad)
    assert site_bridge.current_site() is None
    snapshot = propose(site_bridge)
    assert snapshot["target_facts"] == site_bridge.read_evidence()["hard_facts"]
    before = site_bridge.store.db.execute("SELECT count(*) FROM assessments").fetchone()[0]
    token = JUDGE_EVIDENCE.set(
        EvidenceBinding.model_validate({key: snapshot[key] for key in EvidenceBinding.model_fields})
    )
    try:
        with pytest.raises(HardFactContradiction):
            site_bridge.register_judge(
                JudgeVerdict(
                    verdict="ready-to-ask",
                    reasons=["Chain A observed length is 9999."],
                    limitations=["No efficacy result."],
                )
            )
    finally:
        JUDGE_EVIDENCE.reset(token)
    assert site_bridge.store.db.execute("SELECT count(*) FROM assessments").fetchone()[0] == before


def test_binder_cannot_publish_known_target_count_contradiction(design_bridge: Any) -> None:
    from tests.unit.agent.test_design_runtime import binder_intent, propose_design

    bad = binder_intent().model_copy(
        update={"context_rationale": "Chain A observed length is 9999."}
    )
    with pytest.raises(HardFactContradiction):
        propose_design(design_bridge, bad)
    assert design_bridge.current_design() is None
