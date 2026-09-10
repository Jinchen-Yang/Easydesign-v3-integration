from __future__ import annotations

from pathlib import Path

import pytest

from easydesign.core import (
    AssertionDomain,
    ClaimEvidenceRef,
    ClaimReceipt,
    ClaimStatus,
    ClaimType,
    EvidenceKind,
    ManifestStateError,
    sha256_file,
)
from easydesign.orchestration.research_graph import (
    HypothesisEvent,
    ObservationEvent,
    append_research_event,
    load_research_events,
    research_state_summary,
)


def _hypothesis(identifier: str) -> HypothesisEvent:
    return HypothesisEvent(
        event_id=f"event-{identifier}",
        author_kind="agent-proposal",
        hypothesis_id=identifier,
        target_foundation_sha256="a" * 64,
        statement=f"Hypothesis {identifier}",
        mechanism="A scoped mechanism.",
        predictions=("A measurable computational outcome.",),
        falsifiers=("The outcome is absent under the fixed protocol.",),
        claim=ClaimReceipt(
            claim_id=f"claim-{identifier}",
            claim_type=ClaimType.HYPOTHESIS,
            statement=f"Hypothesis {identifier}",
            scope="target:a",
        ),
    )


def test_competing_hypotheses_are_append_only_and_reconstructable(tmp_path: Path) -> None:
    _, first_path = append_research_event(tmp_path, _hypothesis("h1"))
    _, second_path = append_research_event(tmp_path, _hypothesis("h2"))

    events = load_research_events(tmp_path)
    state = research_state_summary(tmp_path)
    assert [event.revision for event in events] == [1, 2]
    assert [item.hypothesis_id for item in state.active_hypotheses] == ["h1", "h2"]
    assert first_path.is_file() and second_path.is_file()
    with pytest.raises(ManifestStateError, match="event_id 已存在"):
        append_research_event(tmp_path, _hypothesis("h1"))


def test_observation_requires_real_checksum_verified_artifact(tmp_path: Path) -> None:
    evidence = tmp_path / "pilot-filter-report.json"
    evidence.write_text("{}\n", encoding="utf-8")
    digest = sha256_file(evidence)
    claim = ClaimReceipt(
        claim_id="claim-observation-one",
        claim_type=ClaimType.OBSERVATION,
        statement="0/0 candidate records were present.",
        scope="pilot:one",
        assertion_domain=AssertionDomain.COMPUTATIONAL_METRIC,
        evidence_refs=(
            ClaimEvidenceRef(
                evidence_id="pilot-filter-report",
                sha256=digest,
                kind=EvidenceKind.COMPUTATIONAL,
                path=str(evidence),
            ),
        ),
        status=ClaimStatus.VERIFIED,
    )
    event = ObservationEvent(
        event_id="observation-one",
        author_kind="deterministic-code",
        observation_id="observation-one",
        run_id="pilot-one",
        run_manifest_sha256="b" * 64,
        backend_identity="stage05",
        profile_identity="pilot-filter-v1",
        denominator=0,
        passing_count=0,
        claim=claim,
    )
    append_research_event(tmp_path, event)
    evidence.write_text("changed\n", encoding="utf-8")

    stale = event.model_copy(update={"event_id": "observation-two"})
    with pytest.raises(ManifestStateError, match="checksum drift"):
        append_research_event(tmp_path, stale)


def test_predecessor_tamper_is_detected(tmp_path: Path) -> None:
    append_research_event(tmp_path, _hypothesis("h1"))
    _, second_path = append_research_event(tmp_path, _hypothesis("h2"))
    text = second_path.read_text(encoding="utf-8")
    second_path.write_text(
        text.replace('"predecessor_sha256": "', '"predecessor_sha256": "0'),
        encoding="utf-8",
    )

    with pytest.raises(ManifestStateError, match="predecessor SHA-256 drift|无法读取"):
        load_research_events(tmp_path)


def test_old_project_without_graph_has_honest_empty_state(tmp_path: Path) -> None:
    state = research_state_summary(tmp_path)

    assert state.status == "not-yet-initialized"
    assert state.revision == 0
    assert not state.active_hypotheses


def test_interpretation_claim_cannot_be_serialized_as_observation() -> None:
    inference = ClaimReceipt(
        claim_id="claim-inference-one",
        claim_type=ClaimType.INFERENCE,
        statement="The shared target context may explain the failures.",
        scope="pilot:one",
        alternative_explanations=("The backend may have failed operationally.",),
    )

    with pytest.raises(ValueError, match="observation claim"):
        ObservationEvent(
            event_id="observation-invalid",
            author_kind="agent-proposal",
            observation_id="observation-invalid",
            run_id="pilot-one",
            run_manifest_sha256="b" * 64,
            backend_identity="stage05",
            profile_identity="pilot-filter-v1",
            denominator=1,
            passing_count=0,
            claim=inference,
        )
