from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from easydesign.core import (
    AssertionDomain,
    ClaimEvidenceRef,
    ClaimReceipt,
    ClaimStatus,
    ClaimType,
    ConfigurationError,
    EvidenceKind,
    ManifestStateError,
    sha256_file,
)
from easydesign.orchestration.research_graph import (
    ConfidenceCategory,
    ExperimentEvent,
    HypothesisEvent,
    HypothesisStatus,
    InterpretationEvent,
    ObservationEvent,
    append_research_event,
    load_research_events,
    research_state_summary,
)
from easydesign.orchestration.research_interpretation import (
    InterpretationSubmission,
    follow_up_research_event_ids,
    record_interpretation,
    validate_follow_up_research_refs,
)


def _claim(identifier: str, statement: str) -> ClaimReceipt:
    return ClaimReceipt(
        claim_id=f"claim-{identifier}",
        claim_type=ClaimType.HYPOTHESIS,
        statement=statement,
        scope="target:foundation",
    )


def _scientific_lineage(tmp_path: Path) -> tuple[Path, Path]:
    for identifier in ("h1", "h2"):
        append_research_event(
            tmp_path,
            HypothesisEvent(
                event_id=f"hypothesis-event-{identifier}",
                author_kind="agent-proposal",
                hypothesis_id=identifier,
                target_foundation_sha256="a" * 64,
                statement=f"Hypothesis {identifier}",
                mechanism="A scoped mechanism.",
                predictions=("A measurable outcome.",),
                falsifiers=("The outcome is absent.",),
                claim=_claim(identifier, f"Hypothesis {identifier}"),
            ),
        )
    append_research_event(
        tmp_path,
        ExperimentEvent(
            event_id="experiment-event-one",
            author_kind="agent-proposal",
            experiment_id="experiment-one",
            hypothesis_ids=("h1", "h2"),
            strategy_revision_sha256="b" * 64,
            strategy_variant_ids=("baseline", "diagnostic"),
            changed_factors=("binding residues",),
            held_constant=("target state", "scaffold panel"),
            expected_observations=("A measurable pass-rate difference.",),
            protocol_identity="first-pilot-vhh7-40-v1",
            plan_sha256="c" * 64,
        ),
    )
    report = tmp_path / "pilot-filter-report.json"
    report.write_text('{"candidate_records":[{}]}\n', encoding="utf-8")
    claim = ClaimReceipt(
        claim_id="claim-observation-one",
        claim_type=ClaimType.OBSERVATION,
        statement="0/1 candidates passed deterministic hard gates.",
        scope="pilot:pilot-one",
        assertion_domain=AssertionDomain.COMPUTATIONAL_METRIC,
        evidence_refs=(
            ClaimEvidenceRef(
                evidence_id="pilot-filter-report",
                sha256=sha256_file(report),
                kind=EvidenceKind.COMPUTATIONAL,
                path=str(report),
            ),
        ),
        status=ClaimStatus.VERIFIED,
    )
    _, observation_path = append_research_event(
        tmp_path,
        ObservationEvent(
            event_id="observation-pilot-one",
            author_kind="deterministic-code",
            observation_id="observation-pilot-one",
            experiment_ids=("experiment-one",),
            run_id="pilot-one",
            run_manifest_sha256="d" * 64,
            backend_identity="afo-release-one",
            profile_identity="filter-profile-one",
            denominator=1,
            passing_count=0,
            failure_or_missingness=("target-ca-rmsd",),
            claim=claim,
        ),
    )
    hypothesis_path = tmp_path / "research/events/research-event-r000001.json"
    return hypothesis_path, observation_path


def _submission(identifier: str = "interpretation-one") -> InterpretationSubmission:
    return InterpretationSubmission(
        interpretation_id=identifier,
        observation_refs=("observation-pilot-one",),
        supports=("h1",),
        unresolved=("h2",),
        conclusion="The current result supports h1 but does not resolve h2.",
        alternative_explanations=("The backend may be sensitive to this target state.",),
        limitations=("This is computational pilot evidence, not functional evidence.",),
        open_scientific_questions=("Does the result reproduce under a second seed set?",),
        suggested_next_step="Run one held-constant diagnostic condition.",
        confidence=ConfidenceCategory.PLAUSIBLE,
    )


def test_full_loop_derives_hypothesis_status_without_rewriting_history(
    tmp_path: Path,
) -> None:
    hypothesis_path, observation_path = _scientific_lineage(tmp_path)
    hypothesis_before = hypothesis_path.read_bytes()
    observation_before = observation_path.read_bytes()

    first, first_path = record_interpretation(
        tmp_path,
        source_run_id="pilot-one",
        submission=_submission(),
    )
    first_before = first_path.read_bytes()
    state = research_state_summary(tmp_path)
    statuses = {item.hypothesis_id: item for item in state.active_hypotheses}

    assert first.claim.claim_type is ClaimType.INFERENCE
    assert first.claim.status is ClaimStatus.PROPOSED
    assert statuses["h1"].status is HypothesisStatus.SUPPORTED
    assert statuses["h1"].status_interpretation_id == "interpretation-one"
    assert statuses["h1"].status_observation_ids == ("observation-pilot-one",)
    assert statuses["h2"].status is HypothesisStatus.UNRESOLVED
    assert state.open_scientific_questions
    assert state.recommended_next_direction == "Run one held-constant diagnostic condition."

    second_submission = _submission("interpretation-two").model_copy(
        update={
            "supports": (),
            "unresolved": (),
            "weakens": ("h1",),
            "conclusion": "The additional interpretation weakens h1.",
            "suggested_next_step": "Test the competing mechanism explicitly.",
        }
    )
    record_interpretation(
        tmp_path,
        source_run_id="pilot-one",
        submission=second_submission,
    )
    updated = research_state_summary(tmp_path)
    current_h1 = next(item for item in updated.active_hypotheses if item.hypothesis_id == "h1")

    assert current_h1.status is HypothesisStatus.WEAKENED
    assert current_h1.status_interpretation_id == "interpretation-two"
    assert hypothesis_path.read_bytes() == hypothesis_before
    assert observation_path.read_bytes() == observation_before
    assert first_path.read_bytes() == first_before


def test_interpretation_is_fail_closed_for_invalid_refs_or_effects(tmp_path: Path) -> None:
    _scientific_lineage(tmp_path)

    with pytest.raises(ConfigurationError, match="ObservationEvent"):
        record_interpretation(
            tmp_path,
            source_run_id="pilot-one",
            submission=_submission().model_copy(
                update={"observation_refs": ("experiment-event-one",)}
            ),
        )
    with pytest.raises(ConfigurationError, match="hypothesis 不存在"):
        record_interpretation(
            tmp_path,
            source_run_id="pilot-one",
            submission=_submission().model_copy(update={"supports": ("h-missing",)}),
        )
    with pytest.raises(ValueError, match="至少一个 hypothesis"):
        InterpretationSubmission(
            interpretation_id="interpretation-empty",
            observation_refs=("observation-pilot-one",),
            conclusion="No hypothesis update was asserted.",
            alternative_explanations=("Insufficient information.",),
            limitations=("No status effect.",),
            suggested_next_step="Collect more evidence.",
        )
    with pytest.raises(ValueError, match="冲突状态"):
        InterpretationSubmission.model_validate(
            {
                **_submission().model_dump(mode="json"),
                "weakens": ["h1"],
            }
        )


def test_follow_up_requires_connected_hypothesis_observation_interpretation(
    tmp_path: Path,
) -> None:
    _scientific_lineage(tmp_path)
    record_interpretation(
        tmp_path,
        source_run_id="pilot-one",
        submission=_submission(),
    )

    lineage = follow_up_research_event_ids(tmp_path, source_run_id="pilot-one")
    assert lineage == (
        "hypothesis-event-h1",
        "hypothesis-event-h2",
        "observation-pilot-one",
        "interpretation-one",
    )
    validate_follow_up_research_refs(tmp_path, lineage)

    record_interpretation(
        tmp_path,
        source_run_id="pilot-one",
        submission=InterpretationSubmission(
            interpretation_id="interpretation-two-unrelated",
            observation_refs=("observation-pilot-one",),
            supports=("h1",),
            conclusion="This interpretation updates h1 only.",
            alternative_explanations=("An alternative explanation remains.",),
            limitations=("This remains a computational inference.",),
            suggested_next_step="Test h1 directly.",
        ),
    )

    with pytest.raises(ConfigurationError, match="未形成可追溯"):
        validate_follow_up_research_refs(
            tmp_path,
            (
                "hypothesis-event-h2",
                "observation-pilot-one",
                "interpretation-two-unrelated",
            ),
        )


def test_legacy_interpretation_1_0_remains_readable_and_maps_contradiction(
    tmp_path: Path,
) -> None:
    _scientific_lineage(tmp_path)
    legacy_claim = ClaimReceipt(
        claim_id="claim-legacy-interpretation",
        claim_type=ClaimType.INFERENCE,
        statement="Legacy interpretation contradicted h1.",
        scope="pilot:pilot-one",
        alternative_explanations=("Legacy alternative.",),
    )
    _, legacy_path = append_research_event(
        tmp_path,
        InterpretationEvent(
            schema_version="1.0",
            event_id="legacy-interpretation",
            author_kind="agent-proposal",
            interpretation_id="legacy-interpretation",
            contradicts_hypothesis_ids=("h1",),
            reasoning_summary="Legacy interpretation contradicted h1.",
            evidence_event_ids=("observation-pilot-one",),
            alternative_explanations=("Legacy alternative.",),
            confidence=ConfidenceCategory.CONTRADICTED,
            claim=legacy_claim,
        ),
    )
    legacy_payload = json.loads(legacy_path.read_text(encoding="utf-8"))
    for added_in_1_1 in (
        "weakens_hypothesis_ids",
        "rejects_hypothesis_ids",
        "unresolved_hypothesis_ids",
        "limitations",
        "open_scientific_questions",
        "suggested_next_step",
    ):
        legacy_payload.pop(added_in_1_1)
    legacy_path.write_text(
        json.dumps(legacy_payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    historical_digest = hashlib.sha256(
        json.dumps(
            legacy_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    _, next_path = append_research_event(
        tmp_path,
        HypothesisEvent(
            event_id="hypothesis-event-h3",
            author_kind="agent-proposal",
            hypothesis_id="h3",
            target_foundation_sha256="a" * 64,
            statement="Hypothesis h3",
            mechanism="A third scoped mechanism.",
            predictions=("A measurable outcome.",),
            falsifiers=("The outcome is absent.",),
            claim=_claim("h3", "Hypothesis h3"),
        ),
    )

    state = research_state_summary(tmp_path)
    h1 = next(item for item in state.active_hypotheses if item.hypothesis_id == "h1")
    assert h1.status is HypothesisStatus.REJECTED
    events = load_research_events(tmp_path)
    assert events[-2].schema_version == "1.0"
    assert json.loads(next_path.read_text(encoding="utf-8"))["predecessor_sha256"] == (
        historical_digest
    )


def test_duplicate_hypothesis_identity_is_rejected_even_with_new_event_id(
    tmp_path: Path,
) -> None:
    hypothesis_path, _ = _scientific_lineage(tmp_path)
    original = load_research_events(tmp_path)[0]
    assert isinstance(original, HypothesisEvent)
    duplicate = original.model_copy(update={"event_id": "another-event-id"})

    with pytest.raises(ManifestStateError, match="hypothesis_id 已存在"):
        append_research_event(tmp_path, duplicate)
    assert hypothesis_path.is_file()


def test_new_hypothesis_cannot_forge_status_without_interpretation() -> None:
    with pytest.raises(ValueError, match="只能由 Interpretation 派生"):
        HypothesisEvent(
            event_id="hypothesis-event-forged",
            author_kind="agent-proposal",
            hypothesis_id="h-forged",
            target_foundation_sha256="a" * 64,
            statement="A forged supported hypothesis.",
            mechanism="No grounded transition exists.",
            predictions=("A measurable outcome.",),
            falsifiers=("The outcome is absent.",),
            status=ConfidenceCategory.SUPPORTED,
            claim=_claim("h-forged", "A forged supported hypothesis."),
        )

    legacy = HypothesisEvent(
        schema_version="1.0",
        event_id="hypothesis-event-legacy-supported",
        author_kind="agent-proposal",
        hypothesis_id="h-legacy-supported",
        target_foundation_sha256="a" * 64,
        statement="A legacy supported hypothesis.",
        mechanism="Historical schema semantics.",
        predictions=("A measurable outcome.",),
        falsifiers=("The outcome is absent.",),
        status=ConfidenceCategory.SUPPORTED,
        claim=_claim("h-legacy-supported", "A legacy supported hypothesis."),
    )
    assert legacy.schema_version == "1.0"


def test_append_rejects_model_copy_status_bypass(tmp_path: Path) -> None:
    valid = HypothesisEvent(
        event_id="hypothesis-event-valid",
        author_kind="agent-proposal",
        hypothesis_id="h-valid",
        target_foundation_sha256="a" * 64,
        statement="A valid new hypothesis.",
        mechanism="A testable mechanism.",
        predictions=("A measurable outcome.",),
        falsifiers=("The outcome is absent.",),
        claim=_claim("h-valid", "A valid new hypothesis."),
    )

    with pytest.raises(ManifestStateError, match="只能由 Interpretation 派生"):
        append_research_event(
            tmp_path,
            valid.model_copy(update={"status": ConfidenceCategory.SUPPORTED}),
        )
