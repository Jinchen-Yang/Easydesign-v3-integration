"""Typed submission and immutable runtime facts through the real Agent graph (scripted model)."""

from typing import Any

import pytest
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from pydantic import Field, ValidationError

from easydesign.agent.contracts import AgentBoundaryError, TargetFacts, TargetInterpretation
from easydesign.agent.harness import create_harness
from easydesign.agent.phase2 import Phase2Bridge
from easydesign.agent.phase2_tools import PHASE2_ALLOWED
from easydesign.agent.session_store import SessionStore
from easydesign.agent.target_assessment import (
    HardFactContradiction,
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


@pytest.mark.parametrize(
    "claim",
    [
        "canonical length is 132",
        "canonical protein contains 132 residues",
        "canonical length = 147/148",
        "132-residue canonical sequence",
        "Chain L construct length is 148",
        "Chain L observed length is 129",
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


def test_gate_payload_uses_runtime_facts_and_old_judge_cannot_approve_new_interpretation(
    bridge: Any,
) -> None:
    from easydesign.agent.contracts import ApplyDecision
    from tests.agent_support import judge_card, terminal

    bridge.prepare_target()
    terminal(bridge)
    before = bridge.read_evidence()
    owner = register_target(bridge, TargetInterpretation.model_validate(opinion()), None)
    first = judge_card(bridge)
    assert first.scientific_summary["hard_facts"] == before["hard_facts"] == owner["hard_facts"]
    assert first.scientific_summary["interpretation"] == owner["interpretation"]
    changed = TargetInterpretation.model_validate(
        opinion("The alternative chain warrants a separate review.")
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
