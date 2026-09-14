#!/usr/bin/env python3
"""Run a durable, test-only Phase 3 -> Phase 4 control-flow replay."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path

from easydesign.agent.phase3 import (
    build_gate4_card,
    build_pilot_diagnosis,
    build_pilot_dossier,
    project_pilot_measurement,
)
from easydesign.agent.phase4 import (
    build_candidate_dossiers,
    build_final_review_dossier,
    build_gate5_card,
    build_global_candidate_pool,
    build_review_shortlist,
    build_wet_lab_handoff,
)
from easydesign.agent.phase34_bridge import Phase34Bridge
from easydesign.agent.phase34_contracts import (
    AcceptedGate3Fixture,
    DiversityContext,
    ExecutionProjection,
    FinalCandidateJudgeFinding,
    FinalSelectionProposal,
    Gate4Recommendation,
    Gate5JudgeAssessment,
    MetricObservation,
    PilotDiagnosisHypothesis,
    PilotJudgeAssessment,
    ScaleCampaignSpecification,
    ScaleCandidateLineageV3,
    ScaleCandidateObservation,
    ScientificContextReferences,
    ValidationExecutionAuthority,
)
from easydesign.agent.session_store import SessionStore
from easydesign.core import ArtifactRef, canonical_model_sha256
from easydesign.orchestration.profile import initialize_runtime_profile
from easydesign.orchestration.research import initialize_research_project
from easydesign.stages.s04_pilot_generation import CandidateIndex, CandidateRecord
from easydesign.stages.s05_pilot_filtering import (
    CandidateFilterRecord,
    FilterDecision,
    FilterMetric,
    PilotFilterReportV1_6,
    StrategyFilterSummary,
    StrategyTier,
)
from easydesign.workspace_context import WorkspaceContext

NOW = datetime(2026, 9, 14, 12, 0, tzinfo=UTC)
SEQUENCES = (
    "ACDEFGHIK",
    "LMNPQRSTV",
    "WYACDEFGH",
    "IKLMNPQRS",
)


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _write_once(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_text() != content:
            raise RuntimeError(f"immutable validation artifact changed: {path}")
        return
    path.write_text(content)


def _artifact(
    project: Path,
    *,
    name: str,
    producer_stage: str,
) -> ArtifactRef:
    relative = f"validation-artifacts/{name}.cif"
    _write_once(project / relative, f"# TEST-ONLY {name}\n")
    return ArtifactRef.from_file(
        run_root=project,
        relative_path=relative,
        artifact_id=name,
        role="validation-only-evidence",
        file_format="cif",
        producer_stage=producer_stage,
        producer_attempt="attempt-0001",
    )


def _initialize_validation_project(workspace: Path) -> Path:
    workspace.mkdir(parents=True, exist_ok=True)
    _write_once(
        workspace / "easydesign-workspace.yaml",
        'schema_version: "0.1"\nworkspace_id: phase34-validation\n',
    )
    os.environ["EASYDESIGN_WORKSPACE"] = str(workspace)
    context = WorkspaceContext.from_root(workspace)
    context.ensure_layout()
    if not context.profile_path.exists():
        initialize_runtime_profile(context.profile_path)
    source = workspace / "runtime/tmp/validation-target.pdb"
    _write_once(
        source,
        "ATOM      1  CA  ALA A   1       0.000   0.000   0.000  1.00 20.00           C\nEND\n",
    )
    project = context.projects_root / "phase34-validation"
    if not project.exists():
        initialize_research_project(project_root=project, target=source)
    return project


def _pilot_index(project: Path) -> CandidateIndex:
    candidates = tuple(
        CandidateRecord(
            candidate_id=f"pilot-candidate-{ordinal}",
            backend_candidate_id=f"validation-pilot-{ordinal}",
            strategy_id="arm-a",
            task_id="pilot-arm-a",
            task_attempt_number=1,
            ordinal_within_strategy=ordinal,
            original_structure=_artifact(
                project,
                name=f"pilot-{ordinal}-original",
                producer_stage="04-pilot-generation",
            ),
            refolded_structure=_artifact(
                project,
                name=f"pilot-{ordinal}-refolded",
                producer_stage="04-pilot-generation",
            ),
            metrics={"fixture": "test-only-control-flow"},
        )
        for ordinal in (1, 2)
    )
    return CandidateIndex(
        generated_at=NOW,
        strategy_bundle_sha256="1" * 64,
        required_per_strategy=2,
        candidates=candidates,
    )


def _pilot_report(index: CandidateIndex) -> PilotFilterReportV1_6:
    records = []
    for ordinal, score in ((1, 0.82), (2, 0.61)):
        sequence = SEQUENCES[ordinal - 1]
        passed = ordinal == 1
        records.append(
            CandidateFilterRecord(
                candidate_id=f"pilot-candidate-{ordinal}",
                strategy_id="arm-a",
                sequence=sequence,
                sequence_sha256=_sha(sequence),
                metrics=(
                    FilterMetric(
                        metric_id="interface-confidence",
                        value=score,
                        source="derived",
                        definition_version="validation-v1",
                    ),
                ),
                hard_gate_decisions=(
                    FilterDecision(
                        rule_id="legacy-confidence-threshold",
                        metric_id="interface-confidence",
                        operator="ge",
                        threshold=0.7,
                        observed=score,
                        passed=passed,
                        reason="Historical threshold retained only as an annotation.",
                    ),
                ),
                hard_gate_pass=passed,
                eligible_unique_pass=passed,
                score_screen=score,
                normalization_group="arm-a",
            )
        )
    return PilotFilterReportV1_6(
        generated_at=NOW,
        profile_sha256="2" * 64,
        candidate_index_sha256=canonical_model_sha256(index),
        candidate_records=tuple(records),
        strategy_summaries=(
            StrategyFilterSummary(
                strategy_id="arm-a",
                candidate_count=2,
                unique_sequence_count=2,
                boltzgen_hard_pass_count=1,
                final_gate_pass_count=1,
                final_gate_pass_rate=0.5,
                score_screen_top_quartile_mean=0.82,
                score_screen_all_median=0.715,
                score_yaml=0.715,
                tier=StrategyTier.B,
            ),
        ),
        promoted_strategy_ids=(),
        status="stopped-no-tier-a",
    )


def _scale_candidate(
    project: Path,
    *,
    ordinal: int,
) -> ScaleCandidateObservation:
    candidate_id = f"scale-candidate-{ordinal}"
    batch_id = "scale-batch-1" if ordinal <= 2 else "scale-batch-2"
    sequence = SEQUENCES[ordinal - 1]
    score = 0.96 - ordinal * 0.04
    cluster = "cluster-1" if ordinal <= 2 else f"cluster-{ordinal - 1}"
    prediction_id = f"prediction-{candidate_id}"
    return ScaleCandidateObservation(
        lineage=ScaleCandidateLineageV3(
            campaign_id="scale-validation-campaign",
            batch_id=batch_id,
            shard_id=f"shard-{batch_id}",
            candidate_id=candidate_id,
            strategy_id="arm-a",
            strategy_ordinal=ordinal,
            generation_task_id=f"generation-{batch_id}",
            generation_attempt=1,
            backend_candidate_id=f"validation-scale-{ordinal}",
            prediction_id=prediction_id,
            prediction_seed=101,
            prediction_ids=(prediction_id,),
            prediction_seeds=(101,),
            sequence_sha256=_sha(sequence),
            artifact_refs=(
                _artifact(
                    project,
                    name=f"scale-{ordinal}-prediction",
                    producer_stage="07-final-filtering-and-selection",
                ),
            ),
        ),
        validity="valid-evaluated",
        metrics=(
            MetricObservation(
                metric_id="validation-development-score",
                value=score,
                available=True,
                source="test-only-control-flow",
                definition_version="validation-v1",
            ),
        ),
        legacy_policy_pass=ordinal != 4,
        development_score=score,
        diversity=DiversityContext(
            sequence_cluster_id=cluster,
            method="test-only exact fixture grouping",
        ),
        evaluation_level="multi-seed",
    )


def replay(
    *,
    workspace: Path,
    fixture_path: Path,
    fixture_id: str,
) -> dict[str, object]:
    project = _initialize_validation_project(workspace)
    fixtures = tuple(
        AcceptedGate3Fixture.model_validate(item)
        for item in json.loads(fixture_path.read_text())["fixtures"]
    )
    try:
        fixture = next(item for item in fixtures if item.fixture_id == fixture_id)
    except StopIteration as exc:
        available = ", ".join(item.fixture_id for item in fixtures)
        raise ValueError(
            f"unknown accepted Gate 3 fixture {fixture_id!r}; available: {available}"
        ) from exc
    store = SessionStore(project)
    try:
        thread = "phase34-validation-replay"
        store.thread(
            thread,
            "phase34-validation-replay-v1",
            "TEST-ONLY replay of Phase 3 and Phase 4 scientific control flow.",
        )
        bridge = Phase34Bridge(project, thread, store)
        bridge.publish_contract(
            kind="phase34-gate3-fixture",
            contract=fixture,
            dependencies={"accepted-snapshot": fixture.gate3_snapshot_sha256},
        )
        authority = ValidationExecutionAuthority(
            authority_id="phase34-validation-pilot-authority",
            fixture_id=fixture.fixture_id,
            reason="Exercise downstream control flow without claiming Gate 3 approval.",
        )
        pilot_index = _pilot_index(project)
        pilot_report = _pilot_report(pilot_index)
        pilot_measurement = project_pilot_measurement(
            candidate_index=pilot_index,
            candidate_index_sha256=canonical_model_sha256(pilot_index),
            filter_report=pilot_report,
            filter_report_sha256=canonical_model_sha256(pilot_report),
            execution=ExecutionProjection(
                mode="validation-micro",
                requested_production_candidates=fixture.planned_candidates,
                execution_candidates=2,
                uses_real_generation_backend=False,
                uses_real_prediction_backend=False,
                purpose="Test-only Phase 3 control-flow replay.",
            ),
            predicted_candidate_ids=frozenset({"pilot-candidate-1"}),
        )
        bridge.publish_contract(
            kind="phase34-pilot-measurement",
            contract=pilot_measurement,
            dependencies={"gate3-fixture": canonical_model_sha256(fixture)},
        )
        pilot_interpretation = Gate4Recommendation(
            outcome="PROMOTE_TO_SCALE",
            selected_strategy_ids=("arm-a",),
            requested_scale_candidates=50_000,
            production_strategy_allocations={"arm-a": 50_000},
            evidence_sufficiency="INCONCLUSIVE",
            scientific_supporting_candidate_count=0,
            observations=("Two deterministic validation candidates were measured.",),
            interpretations=("This result tests control flow and has no biological meaning.",),
            alternative_explanations=("All apparent differences are fixture construction.",),
            uncertainties=("Scientific Pilot performance remains entirely unresolved.",),
            falsifiers_or_next_measurements=(
                "Run a licensed, formally authorized real Pilot after Phase 2 freeze.",
            ),
            evidence_refs=("validation:pilot-measurement",),
            test_only_control_flow_fixture=True,
        )
        pilot_diagnosis = build_pilot_diagnosis(
            measurement=pilot_measurement,
            hypotheses=(
                PilotDiagnosisHypothesis(
                    category="insufficient-evidence",
                    status="SUPPORTED",
                    observations=("The validation projection contains only two candidates.",),
                    implications=("No site or strategy failure can be inferred.",),
                    evidence_refs=("validation:pilot-measurement",),
                ),
                PilotDiagnosisHypothesis(
                    category="prediction-uncertainty",
                    status="UNRESOLVED",
                    observations=("Only one fixture candidate carries prediction coverage.",),
                    implications=("Prediction uncertainty dominates any apparent ordering.",),
                    evidence_refs=("validation:pilot-measurement",),
                ),
            ),
            conclusion=("The micro result validates state transitions only.",),
            uncertainties=("All scientific failure modes remain unresolved.",),
            evidence_refs=("validation:pilot-measurement",),
            confidence="INCONCLUSIVE",
        )
        pilot_dossier = build_pilot_dossier(
            project_id="phase34-validation",
            pilot_run_id="pilot-validation-replay",
            upstream_fixture=fixture,
            execution_authority=authority,
            measurement=pilot_measurement,
            diagnosis=pilot_diagnosis,
            proposed_interpretation=pilot_interpretation,
            evidence_refs=("validation:pilot-index", "validation:pilot-filter-report"),
        )
        bridge.publish_contract(
            kind="phase34-pilot-dossier",
            contract=pilot_dossier,
            dependencies={"measurement": canonical_model_sha256(pilot_measurement)},
        )
        pilot_judge = PilotJudgeAssessment(
            assessment_id="pilot-validation-judge",
            dossier_sha256=canonical_model_sha256(pilot_dossier),
            verdict="ready-to-ask",
            recommendation="PROMOTE_TO_SCALE",
            reasons=("The test-only evidence is internally consistent for routing.",),
            limitations=("No scientific scale promotion is supported.",),
            evidence_refs=("validation:pilot-dossier",),
        )
        bridge.publish_contract(
            kind="phase34-pilot-judge",
            contract=pilot_judge,
            dependencies={"pilot-dossier": canonical_model_sha256(pilot_dossier)},
        )
        gate4_card = build_gate4_card(dossier=pilot_dossier, assessment=pilot_judge)
        bridge.publish_gate_card(card=gate4_card, evidence_contract=pilot_dossier)
        store.respond(thread, gate4_card.card_id, "approve", "validation-scientist")
        promotion = bridge.gate4_promotion_authority(
            dossier=pilot_dossier,
            card=gate4_card,
            selected_strategy_ids=("arm-a",),
        )
        campaign = ScaleCampaignSpecification(
            campaign_id="scale-validation-campaign",
            promotion_authority=promotion,
            execution=ExecutionProjection(
                mode="validation-micro",
                requested_production_candidates=50_000,
                execution_candidates=4,
                uses_real_generation_backend=False,
                uses_real_prediction_backend=False,
                purpose="Test-only Phase 4 control-flow replay.",
            ),
            strategy_allocations={"arm-a": 4},
            generation_backend="deterministic-validation-fixture",
            prediction_backend="deterministic-validation-fixture",
            allocation_policy="single-strategy-validation-projection",
        )
        bridge.publish_contract(
            kind="phase34-scale-campaign",
            contract=campaign,
            dependencies={"gate4-card": gate4_card.card_id},
        )
        scale_candidates = tuple(
            _scale_candidate(project, ordinal=ordinal) for ordinal in range(1, 5)
        )
        partial_pool = build_global_candidate_pool(
            campaign=campaign,
            source_candidate_index_sha256=_sha("scale-index-checkpoint-batch-1"),
            source_metric_report_sha256=_sha("scale-metrics-checkpoint-batch-1"),
            planned_batches=2,
            completed_batch_ids=("scale-batch-1",),
            failed_batch_ids=(),
            resumable_batch_ids=("scale-batch-2",),
            candidates=scale_candidates[:2],
        )
        bridge.publish_contract(
            kind="phase34-global-candidate-pool-checkpoint",
            contract=partial_pool,
            dependencies={"scale-campaign": canonical_model_sha256(campaign)},
        )
        global_pool = build_global_candidate_pool(
            campaign=campaign,
            source_candidate_index_sha256=_sha("scale-index-complete"),
            source_metric_report_sha256=_sha("scale-metrics-complete"),
            planned_batches=2,
            completed_batch_ids=("scale-batch-1", "scale-batch-2"),
            failed_batch_ids=(),
            resumable_batch_ids=(),
            candidates=scale_candidates,
        )
        bridge.publish_contract(
            kind="phase34-global-candidate-pool",
            contract=global_pool,
            dependencies={
                "checkpoint": canonical_model_sha256(partial_pool),
                "scale-campaign": canonical_model_sha256(campaign),
            },
        )
        shortlist = build_review_shortlist(
            pool=global_pool,
            requested_count=3,
            sequence_cluster_cap=1,
        )
        bridge.publish_contract(
            kind="phase34-review-shortlist",
            contract=shortlist,
            dependencies={"global-pool": canonical_model_sha256(global_pool)},
        )
        shortlisted_ids = tuple(item.candidate_id for item in shortlist.entries)
        sequence_by_id = {
            f"scale-candidate-{ordinal}": SEQUENCES[ordinal - 1] for ordinal in range(1, 5)
        }
        context = ScientificContextReferences(
            target_identity=fixture.target_identity,
            target_snapshot_sha256=fixture.target_bundle_sha256,
            site_intent_sha256=fixture.site_intent_sha256,
            design_specification_sha256=fixture.strategy_sha256,
            pilot_dossier_sha256=canonical_model_sha256(pilot_dossier),
            evidence_refs=fixture.evidence_refs
            + ("validation:pilot-dossier", "validation:scale-campaign"),
        )
        candidate_dossiers = build_candidate_dossiers(
            pool=global_pool,
            shortlist=shortlist,
            context=context,
            sequences_by_candidate={item: sequence_by_id[item] for item in shortlisted_ids},
            concerns_by_candidate={
                item: ("Development score has no calibrated biological interpretation.",)
                for item in shortlisted_ids
            },
            uncertainties_by_candidate={
                item: ("Binding, function, expression, and developability are untested.",)
                for item in shortlisted_ids
            },
            provenance_by_candidate={
                item: (f"validation:scale/{item}",) for item in shortlisted_ids
            },
        )
        selection = FinalSelectionProposal(
            primary_candidate_ids=shortlisted_ids[:2],
            backup_candidate_ids=shortlisted_ids[2:],
            requested_primary_count=2,
            requested_backup_count=1,
            rationale=("Exercise global rank, advisory diversity, and primary/backup arithmetic.",),
        )
        final_review = build_final_review_dossier(
            project_id="phase34-validation",
            pool=global_pool,
            shortlist=shortlist,
            candidate_dossiers=candidate_dossiers,
            proposed_selection=selection,
            evidence_refs=("validation:global-pool", "validation:review-shortlist"),
        )
        bridge.publish_contract(
            kind="phase34-final-review-dossier",
            contract=final_review,
            dependencies={"shortlist": canonical_model_sha256(shortlist)},
        )
        gate5_judge = Gate5JudgeAssessment(
            assessment_id="final-validation-judge",
            final_review_dossier_sha256=canonical_model_sha256(final_review),
            verdict="ready-to-ask",
            recommendation="APPROVE_WET_LAB_HANDOFF",
            candidate_findings=tuple(
                FinalCandidateJudgeFinding(
                    candidate_id=item,
                    status="SUPPORTED",
                    reasons=("The validation dossier is complete and traceable.",),
                    concerns=("No biological or experimental evidence is present.",),
                )
                for item in shortlisted_ids
            ),
            reasons=("The panel is coherent for control-flow validation only.",),
            limitations=("No experiment may be authorized from this fixture.",),
            evidence_refs=("validation:final-review",),
        )
        bridge.publish_contract(
            kind="phase34-final-judge",
            contract=gate5_judge,
            dependencies={"final-review": canonical_model_sha256(final_review)},
        )
        gate5_card = build_gate5_card(dossier=final_review, assessment=gate5_judge)
        bridge.publish_gate_card(card=gate5_card, evidence_contract=final_review)
        store.respond(thread, gate5_card.card_id, "approve", "validation-scientist")
        gate5_authority = bridge.gate5_approval_authority(
            final_review_dossier_sha256=canonical_model_sha256(final_review),
            card=gate5_card,
            primary_candidate_ids=selection.primary_candidate_ids,
            backup_candidate_ids=selection.backup_candidate_ids,
        )
        handoff = build_wet_lab_handoff(
            dossier=final_review,
            gate5_card=gate5_card,
            authority=gate5_authority,
        )
        bridge.publish_contract(
            kind="phase34-wet-lab-handoff",
            contract=handoff,
            dependencies={
                "final-review": canonical_model_sha256(final_review),
                "gate5-card": gate5_card.card_id,
            },
        )
        state = bridge.downstream_state()
        return {
            "schema_version": "0.1",
            "status": "PASS",
            "execution_scope": "test-only-control-flow",
            "scientific_validation": False,
            "production_compute_used": False,
            "project": str(project),
            "accepted_fixture": fixture.fixture_id,
            "gate3_status": fixture.gate3_status,
            "pilot_measurement_sha256": canonical_model_sha256(pilot_measurement),
            "gate4_card_id": gate4_card.card_id,
            "gate4_authority_scope": promotion.authority_scope,
            "partial_scale_pool_sha256": canonical_model_sha256(partial_pool),
            "global_scale_pool_sha256": canonical_model_sha256(global_pool),
            "shortlist_candidate_ids": shortlisted_ids,
            "gate5_card_id": gate5_card.card_id,
            "gate5_authority_scope": gate5_authority.authority_scope,
            "handoff_sha256": canonical_model_sha256(handoff),
            "handoff_status": handoff.handoff_status,
            "ordering_status": handoff.ordering_status,
            "recovery_state": state,
        }
    finally:
        store.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument(
        "--fixtures",
        type=Path,
        default=Path("tests/fixtures/agent/phase34_gate3_fixtures.json"),
    )
    parser.add_argument(
        "--fixture-id",
        default="accepted-standard-gate3-live162",
        help="Exact accepted Gate 3 fixture to project through the shared downstream path.",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = replay(
        workspace=args.workspace,
        fixture_path=args.fixtures,
        fixture_id=args.fixture_id,
    )
    encoded = json.dumps(report, indent=2, sort_keys=True) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(encoded)
    print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
