import json
from typing import Any

import pytest
from pydantic import ValidationError

from easydesign.agent.cli import _display
from easydesign.agent.contracts import (
    AgentBoundaryError,
    EvidenceBinding,
    JudgeVerdict,
    TargetProvenance,
)
from easydesign.agent.tools import JUDGE_EVIDENCE, build_tools
from tests.agent_support import judge_card, terminal


def opinion() -> JudgeVerdict:
    return JudgeVerdict(
        verdict="ready-to-ask",
        reasons=["Two eligible chains require a choice."],
        limitations=["Biological identity is unconfirmed."],
    )


def binding(evidence: dict[str, Any]) -> EvidenceBinding:
    return EvidenceBinding.model_validate({k: evidence[k] for k in EvidenceBinding.model_fields})


def test_judge_only_authors_opinion_and_cannot_supply_authority() -> None:
    assert set(JudgeVerdict.model_json_schema()["properties"]) == {
        "verdict",
        "reasons",
        "limitations",
        "recommendation",
        "site_claim_corrections",
        "fact_refs",
        "fact_claims",
    }
    for field in (
        "evidence_id",
        "request_identity",
        "evidence_refs",
        "assessment_id",
        "source_role",
    ):
        with pytest.raises(ValidationError):
            JudgeVerdict.model_validate({**opinion().model_dump(), field: "forged"})


def test_callback_attaches_canonical_binding_and_rejects_stale_snapshot(bridge: Any) -> None:
    bridge.prepare_target()
    terminal(bridge)
    evidence = bridge.read_evidence()
    with pytest.raises(AgentBoundaryError, match="delegated"):
        bridge.register_judge(opinion())
    token = JUDGE_EVIDENCE.set(binding(evidence))
    try:
        assessment = bridge.register_judge(opinion())
        assert assessment.evidence_refs == tuple(evidence["evidence_refs"])
        assert assessment.request_identity == evidence["request_identity"]
        assert assessment.source_role == "evidence-judge"
        assert bridge.store.assessment(bridge.thread, assessment.assessment_id) == assessment
        with pytest.raises(AgentBoundaryError, match="no supplied fact collection"):
            bridge.register_judge(opinion().model_copy(update={"fact_refs": ["candidate:0"]}))
        from easydesign.agent.target_assessment import HardFactContradiction

        chain = evidence["hard_facts"]["chains"][0]
        wrong_count = chain["observed_length"] + 1
        with pytest.raises(HardFactContradiction):
            bridge.register_judge(
                opinion().model_copy(
                    update={
                        "reasons": [f"chain {chain['auth_chain']} observed length {wrong_count}"],
                    }
                )
            )
        from easydesign.orchestration.decisions import load_pending_decision

        root, _ = bridge.run()
        request, path = load_pending_decision(root)
        path.write_text(
            request.model_copy(update={"message": "Changed question"}).model_dump_json()
        )
        with pytest.raises(AgentBoundaryError, match="stale"):
            bridge.register_judge(opinion())
    finally:
        JUDGE_EVIDENCE.reset(token)
    assert bridge.store.db.execute("SELECT count(*) FROM assessments").fetchone()[0] == 1


@pytest.mark.asyncio
async def test_completed_judge_receives_false_provenance_and_no_approval_claim(bridge: Any) -> None:
    bridge.prepare_target()
    terminal(bridge)
    card = judge_card(bridge)
    bridge.store.respond(bridge.thread, card.card_id, "approve", "synthetic-test-user")
    bridge.apply_decision(card)
    terminal(bridge)
    current = bridge.read_evidence()
    tool = next(t for t in build_tools(bridge, "judge") if t.name == "read_target_evidence")
    token = JUDGE_EVIDENCE.set(binding(current))
    try:
        seen = json.loads(await tool.ainvoke({}))
        assert seen["provenance"]["fallback_used"] is False
        assert "fields" not in seen["provenance"]
        assert {k: seen["provenance"][k] for k in ("origin", "source", "selected_chain")} == {
            "origin": "experimental",
            "source": "local-file",
            "selected_chain": "A",
        }
        assert seen["approval_provenance"]["status"] == "not-in-snapshot"
        assert "does not verify" in seen["approval_provenance"]["limitation"]
        # The same actual snapshot drives the opinion, rather than key-presence speculation.
        result = bridge.register_judge(
            JudgeVerdict(
                verdict="assessed",
                reasons=[
                    "No fallback was used."
                    if seen["provenance"]["fallback_used"] is False
                    else "Fallback needs review."
                ],
                limitations=[seen["approval_provenance"]["limitation"]],
            )
        )
        assert result.reasons == ["No fallback was used."]
        assert result.request_identity is None
    finally:
        JUDGE_EVIDENCE.reset(token)
    with pytest.raises(AgentBoundaryError, match="delegated"):
        await tool.ainvoke({})
    with pytest.raises(ValidationError):
        TargetProvenance(fallback_used="false")


def test_normal_output_hides_diagnostics_without_changing_stored_result(capsys: Any) -> None:
    raw = (
        "链 A 已准备完成。\nSHA-256: "
        + "a" * 64
        + "\nassessment_id: judge-internal\n生物学身份仍未确认。"
    )
    value = {
        "status": "finished",
        "message": raw,
        "job": {"status": "succeeded", "job_id": "job-internal"},
    }
    _display(value)
    normal = json.loads(capsys.readouterr().out)
    assert "链 A 已准备完成" in normal["message"]
    assert "身份仍未确认" in normal["message"]
    assert "SHA" not in normal["message"] and "judge-internal" not in normal["message"]
    assert "job_id" not in normal["job"]
    assert value["message"] == raw
    _display(value, technical_details=True)
    assert json.loads(capsys.readouterr().out) == value
