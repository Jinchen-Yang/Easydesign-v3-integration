"""Synthetic populations test routing, not the biology of the real NK2R result."""

from pathlib import Path

import pytest

from easydesign.agent.contracts import AgentBoundaryError
from easydesign.agent.phase3_native import (
    native_candidate,
    native_profile,
    project_native_measurement,
)
from easydesign.agent.phase3_ranking import bind_native_ranking, native_working_set
from easydesign.agent.phase34_cards import pilot_card
from easydesign.agent.phase34_contracts import ExecutionProjection, PilotMeasurement
from easydesign.agent.phase34_measurement import attach_prediction_metrics
from easydesign.agent.phase34_opinions import PilotDiagnosisOpinion
from easydesign.agent.phase34_plan import PilotArmIntent
from easydesign.core import ArtifactRef, canonical_model_sha256
from easydesign.stages.s04_pilot_generation import CandidateRecord
from easydesign.stages.s05_pilot_filtering import FullTargetPredictionRecord
from tests.unit.agent.test_phase34_contracts import _pilot_dossier


def population(
    tmp_path: Path, layouts=(("arm-a", (1, 0, 0, 0, 0, 0, 0)),), incomplete=False, per_strategy=2
):
    path = tmp_path / "synthetic-profile.yaml"
    path.write_text("# synthetic fixture, not a scientific result\n")
    ref = ArtifactRef.from_file(
        run_root=tmp_path,
        relative_path=path.name,
        artifact_id="profile",
        role="synthetic-fixture",
        file_format="yaml",
    )
    config = {
        "_target_": "boltzgen.task.filter.filter.Filter",
        "filter_designfolding": False,
        "filter_cysteine": False,
        "filter_biased": False,
        "filter_bindingsite": False,
    }
    profile = native_profile(config, ref)
    candidates, profiles, planned, arms = [], {}, {}, []
    for arm, pass_counts in layouts:
        ids = tuple(f"{arm}-scaffold-{s}" for s in range(len(pass_counts)))
        arms.append(
            PilotArmIntent(
                arm_id=arm,
                strategy_ids=ids,
                hypothesis="Synthetic routing hypothesis",
                rationale="Test scientific Arm aggregation",
                changed_factors=("fixture",),
                held_constant=("target",),
                expected_result="No predetermined biology",
                failure_interpretation=None,
                role="baseline",
                compiled_settings=tuple({"strategy_id": s, "scaffold_id": s} for s in ids),
                target_context={"target": "synthetic"},
                evidence_refs=("synthetic",),
            )
        )
        for s, passes in zip(ids, pass_counts, strict=True):
            profiles[s], planned[s] = profile, per_strategy
            for i in range(1 if incomplete else per_strategy):
                passed = i < passes
                value = 1.0 if passed else 4.0
                metrics = {
                    "has_x": 0,
                    "CYS_fraction": 0,
                    "filter_rmsd": value,
                    "filter_rmsd_design": value,
                    "bb_rmsd": value,
                    "bb_rmsd_design": value,
                    "bb_target_aligned_rmsd_design": value + 1,
                    "design_to_target_iptm": 0.4,
                    "designed_chain_sequence": "ACDF",
                    "designed_sequence": "CDF",
                    "pass_filters": passed,
                }
                metrics.update(
                    {
                        "pass_has_x_filter": True,
                        "pass_filter_rmsd_filter": passed,
                        "pass_filter_rmsd_design_filter": passed,
                    }
                )
                candidates.append(
                    CandidateRecord(
                        candidate_id=f"{s}-candidate-{i + 1}",
                        backend_candidate_id=f"design_{i}",
                        strategy_id=s,
                        task_id="task-" + s,
                        task_attempt_number=1,
                        ordinal_within_strategy=i + 1,
                        original_structure=ref,
                        refolded_structure=ref,
                        metrics=metrics,
                        pass_filters=passed,
                    )
                )
    measurement = project_native_measurement(
        candidates=tuple(candidates),
        profiles=profiles,
        planned=planned,
        source_sha256="a" * 64,
        execution=ExecutionProjection(
            mode="formal-pilot",
            requested_production_candidates=sum(planned.values()),
            execution_candidates=sum(planned.values()),
            uses_real_generation_backend=False,
            uses_real_prediction_backend=False,
            purpose="Synthetic control flow",
        ),
    )
    return measurement, tuple(arms), tuple(candidates), profile


def opinion_for(measurement, arms):
    packet = native_working_set(measurement, arms)
    good = [a for a, f in packet["scientific_arms"].items() if f["mode"] == "PROMOTION"]
    strategies = sorted(
        {
            fact["strategy_id"]
            for fact in packet["pass_candidates"].values()
            if fact["arm_id"] in good
        }
    )
    return PilotDiagnosisOpinion(
        key_observations=["Synthetic measured values"],
        arm_findings=[
            dict(
                arm_id=a.arm_id,
                hypothesis_support="UNRESOLVED",
                observations=["Synthetic"],
                interpretation="Fixture only",
                alternative_explanation="No biological evidence",
            )
            for a in arms
        ],
        arm_comparisons=["No causal claim"],
        operational_confounders=["Fixture"],
        uncertainty=["Biology unknown"],
        next_discriminating_experiment=["Scientist decides"],
        recommended_action="PROMOTE_TO_SCALE" if good else "RUN_ANOTHER_PILOT",
        selected_strategy_ids=strategies,
        scale_allocations={s: 10 for s in strategies},
        supporting_candidate_ids=list(packet["pass_candidates"]),
        rationale="Synthetic routing",
        candidate_rankings=[
            dict(
                candidate_id=i,
                rationale="Pose evidence",
                risks=["Unknown"],
                metric_refs=["bb_rmsd_design"],
            )
            for i in packet["pass_candidates"]
        ],
        ranked_arm_ids=good,
        arm_recovery=[
            dict(
                arm_id=a,
                action="REVISE_DESIGN",
                rationale="Refold stress",
                proposed_change="Review CDR profile",
            )
            for a, f in packet["scientific_arms"].items()
            if f["mode"] == "RECOVERY"
        ],
    )


def test_seven_scaffolds_are_one_passing_scientific_arm(tmp_path):
    measured, arms, _, _ = population(tmp_path)
    packet = native_working_set(measured, arms)
    fact = packet["scientific_arms"]["arm-a"]
    assert fact["mode"] == "PROMOTION" and fact["native_pass_count"] == 1
    assert fact["planned"] == 14 and fact["native_pass_rate"] == 1 / 14
    assert fact["failure_dossier"] is None
    result = bind_native_ranking(measured, arms, opinion_for(measured, arms))
    assert len(result["candidate_leaderboard"]) == 1
    assert len(result["arm_leaderboard"]) == 1
    assert result["arm_leaderboard"][0]["recovery"] is None


def test_native_source_mutation_is_detected_on_read(tmp_path):
    from easydesign.agent.phase3_native import verify_native_measurement
    from easydesign.core.errors import ArtifactIntegrityError

    measured, _, _, _ = population(tmp_path)
    verify_native_measurement(tmp_path, measured)
    (tmp_path / "synthetic-profile.yaml").write_text("changed bytes")
    with pytest.raises(ArtifactIntegrityError):
        verify_native_measurement(tmp_path, measured)


def test_independent_prediction_enriches_without_replacing_native_authority(tmp_path):
    measured, _, _, _ = population(tmp_path, per_strategy=1)
    candidate = measured.candidates[0]
    ref = candidate.lineage.original_structure
    prediction = FullTargetPredictionRecord(
        candidate_id=candidate.lineage.candidate_id,
        strategy_id=candidate.lineage.strategy_id,
        predicted_structure=ref,
        summary_confidence=ref,
        full_confidence=ref,
        pairwise_iptm=0.72,
        minimum_interface_pae_angstrom=2.4,
        binder_ptm=0.84,
        binder_pose_rmsd_angstrom=3.1,
        target_ca_rmsd_angstrom=1.7,
        severe_clash_count=0,
        moderate_clash_count=0,
        structure_gate_decisions=(),
        structure_gate_pass=True,
        confidence_reference_pass=True,
        confidence_label="reference-supported",
    )

    enriched = attach_prediction_metrics(measured, (prediction,))

    assert enriched.native_evidence == measured.native_evidence
    assert enriched.source_filter_report_sha256 == measured.source_filter_report_sha256
    metrics = {m.metric_id: m for m in enriched.candidates[0].metrics}
    assert metrics["independent-prediction-pairwise_iptm"].value == 0.72
    assert metrics["independent-prediction-binder_pose_rmsd_angstrom"].value == 3.1


def test_scale_allocation_obeys_existing_scaffold_executor(tmp_path):
    measured, arms, _, _ = population(tmp_path, (("arm-a", (1, 1)),))
    opinion = opinion_for(measured, arms)
    allocations = {**opinion.scale_allocations, arms[0].strategy_ids[0]: 20}
    with pytest.raises(AgentBoundaryError, match="equal selected-scaffold"):
        bind_native_ranking(
            measured, arms, opinion.model_copy(update={"scale_allocations": allocations})
        )


def test_selected_scaffold_requires_its_own_native_pass_support(tmp_path):
    measured, arms, _, _ = population(tmp_path, (("arm-a", (1, 0)),))
    opinion = opinion_for(measured, arms)
    unsupported = arms[0].strategy_ids[1]
    with pytest.raises(AgentBoundaryError, match="exact strategy"):
        bind_native_ranking(
            measured,
            arms,
            opinion.model_copy(
                update={
                    "selected_strategy_ids": [unsupported],
                    "scale_allocations": {unsupported: 10},
                }
            ),
        )


def test_passing_arm_scientific_caveats_do_not_replace_promotion_with_recovery(tmp_path):
    measured, arms, _, _ = population(tmp_path)
    opinion = opinion_for(measured, arms).model_copy(
        update={
            "recommended_action": "REVISE_DESIGN",
            "selected_strategy_ids": [],
            "scale_allocations": {},
            "supporting_candidate_ids": [],
        }
    )
    with pytest.raises(AgentBoundaryError, match="ranked Scale proposal"):
        bind_native_ranking(measured, arms, opinion)


def test_complete_zero_pass_and_mixed_arm_routing(tmp_path):
    measured, arms, _, _ = population(tmp_path, (("arm-a", (1,)), ("arm-b", (0,))))
    packet = native_working_set(measured, arms)
    zero = packet["scientific_arms"]["arm-b"]
    assert zero["mode"] == "RECOVERY"
    assert zero["failure_dossier"]["native_filter_failure_histogram"] == {
        "filter_rmsd": 2,
        "filter_rmsd_design": 2,
    }
    opinion = opinion_for(measured, arms)
    result = bind_native_ranking(measured, arms, opinion)
    assert result["arm_leaderboard"][0]["arm_id"] == "arm-a"
    with pytest.raises(AgentBoundaryError, match="zero-pass or incomplete"):
        bind_native_ranking(
            measured,
            arms,
            opinion.model_copy(update={"selected_strategy_ids": ["arm-b-scaffold-0"]}),
        )


@pytest.mark.parametrize("passes", [0, 1])
def test_incomplete_never_recovers_or_claims_final_yield(tmp_path, passes):
    measured, arms, _, _ = population(tmp_path, (("arm-a", (passes,)),), incomplete=True)
    packet = native_working_set(measured, arms)
    fact = packet["scientific_arms"]["arm-a"]
    assert fact["mode"] == "OPERATIONAL_INCOMPLETE" and fact["native_pass_rate"] is None
    assert fact["failure_dossier"] is None
    op = opinion_for(measured, arms)
    assert bind_native_ranking(measured, arms, op)["arm_leaderboard"][0]["rank"] is None
    with pytest.raises(AgentBoundaryError, match="Operationally incomplete"):
        bind_native_ranking(
            measured, arms, op.model_copy(update={"recommended_action": "REVISE_SITE"})
        )


def test_native_profile_observation_conflict_and_optional_missingness(tmp_path):
    measured, arms, candidates, profile = population(tmp_path, (("arm-a", (1,)),))
    bad = candidates[0].model_copy(update={"pass_filters": False})
    with pytest.raises(AgentBoundaryError, match="aggregate"):
        native_candidate(bad, profile)
    assert native_working_set(measured, arms)["scientific_arms"]["arm-a"]["complete"]
    missing = dict(candidates[0].metrics)
    missing.pop("filter_rmsd")
    incomplete = native_candidate(candidates[0].model_copy(update={"metrics": missing}), profile)
    assert incomplete.native_pass is None
    additional = native_profile(
        {
            **profile.configuration,
            "additional_filters": [
                {"feature": "design_to_target_iptm", "lower_is_better": False, "threshold": 0.5}
            ],
        },
        profile.configuration_ref,
    )
    assert additional.rules[-1].threshold == 0.5  # Only explicitly configured, never a default.
    assert all(r.feature != "design_to_target_iptm" for r in profile.rules)


def test_candidate_attempt_profile_identity_survives_projection(tmp_path):
    measured, _, candidates, profile = population(tmp_path, (("arm-a", (1,)),))
    path = tmp_path / "second-attempt-profile.yaml"
    path.write_text("# independent saved attempt, identical filter rules\n")
    ref = ArtifactRef.from_file(
        run_root=tmp_path,
        relative_path=path.name,
        artifact_id="attempt-two-profile",
        role="synthetic-fixture",
        file_format="yaml",
    )
    second = profile.model_copy(update={"configuration_ref": ref})
    result = project_native_measurement(
        candidates=candidates,
        profiles={candidates[0].candidate_id: profile, candidates[1].candidate_id: second},
        planned={a.strategy_id: a.planned_candidates for a in measured.arms},
        execution=measured.execution,
        source_sha256="a" * 64,
    )
    assert len(result.native_evidence.profiles) == 2
    assert result.native_evidence.candidates[1].profile_sha256 == canonical_model_sha256(second)


@pytest.mark.parametrize("passes", [0, 1])
def test_native_micro_is_validation_only_even_when_complete(tmp_path, passes):
    from easydesign.agent.phase34_contracts import ExecutionMode

    measured, arms, _, _ = population(tmp_path, (("arm-a", (passes,)),))
    measured = measured.model_copy(
        update={
            "execution": measured.execution.model_copy(
                update={"mode": ExecutionMode.VALIDATION_MICRO}
            )
        }
    )
    fact = native_working_set(measured, arms)["scientific_arms"]["arm-a"]
    assert fact["mode"] == "VALIDATION_ONLY"
    assert fact["failure_dossier"] is None
    opinion = opinion_for(measured, arms)
    assert opinion.recommended_action == "RUN_ANOTHER_PILOT"
    assert bind_native_ranking(measured, arms, opinion)["arm_leaderboard"][0]["rank"] is None


def test_leaderboard_cannot_drop_passes_invent_metrics_or_recover_passing_arm(tmp_path):
    measured, arms, _, _ = population(tmp_path)
    opinion = opinion_for(measured, arms)
    with pytest.raises(AgentBoundaryError, match="every native PASS"):
        bind_native_ranking(measured, arms, opinion.model_copy(update={"candidate_rankings": []}))
    row = opinion.candidate_rankings[0].model_copy(update={"metric_refs": ["invented_affinity"]})
    with pytest.raises(AgentBoundaryError, match="unknown metric"):
        bind_native_ranking(
            measured, arms, opinion.model_copy(update={"candidate_rankings": [row]})
        )


def test_historical_measurement_identity_is_preserved_and_judge_is_optional():
    dossier = _pilot_dossier()
    old = dossier.measurement.model_dump(mode="json")
    assert "native_evidence" not in old and "ranked_pilot" not in dossier.diagnosis.model_dump()
    assert canonical_model_sha256(PilotMeasurement.model_validate(old)) == canonical_model_sha256(
        dossier.measurement
    )
    card = pilot_card(dossier)
    assert card.scientific_summary["independent_review"]["availability"] == "not-requested"
    assert card.option_id == dossier.proposed_interpretation.outcome


def test_material_site_change_returns_to_gate2(tmp_path):
    measured, arms, _, _ = population(tmp_path, (("arm-a", (0,)),))
    opinion = opinion_for(measured, arms)
    recovery = opinion.arm_recovery[0].model_copy(update={"changes_approved_site": True})
    with pytest.raises(AgentBoundaryError, match="Gate 2"):
        bind_native_ranking(measured, arms, opinion.model_copy(update={"arm_recovery": [recovery]}))
    recovery = recovery.model_copy(update={"action": "REVISE_SITE"})
    assert bind_native_ranking(
        measured, arms, opinion.model_copy(update={"arm_recovery": [recovery]})
    )


def test_columnar_packet_preserves_the_complete_native_vector(tmp_path):
    from easydesign.agent.phase3_ranking import compact_native_packet

    measured, arms, _, _ = population(tmp_path)
    packet = compact_native_packet(measured, arms)
    native = measured.native_evidence.candidates[0]
    fact = packet["facts"][native.candidate_id]
    restored = dict(zip(packet["native_metric_columns"], fact["native_metric_values"], strict=True))
    assert restored == native.metrics
    assert restored["CYS_fraction"] == 0
    assert packet["scientific_arm_ids"] == ["arm-a"]
    assert packet["native_pass_candidate_ids"] == [native.candidate_id]


def test_compact_profiles_preserve_attempt_identity_and_distinct_rules(tmp_path):
    from easydesign.agent.phase3_ranking import compact_native_packet
    from easydesign.agent.session_store import compact

    measured, arms, candidates, original = population(
        tmp_path, (("arm-a", (1,) * 7), ("arm-b", (1,) * 7)), per_strategy=1
    )
    profiles = {}
    for index, candidate in enumerate(candidates):
        path = tmp_path / f"attempt-{index}.yaml"
        path.write_text(f"# independent attempt {index}\n")
        ref = ArtifactRef.from_file(
            run_root=tmp_path,
            relative_path=path.name,
            artifact_id=f"profile-{index}",
            role="synthetic-fixture",
            file_format="yaml",
        )
        config = {**original.configuration, "refolding_rmsd_threshold": 1.5 if index == 13 else 2.5}
        profiles[candidate.candidate_id] = native_profile(config, ref)
    measured = project_native_measurement(
        candidates=candidates,
        profiles=profiles,
        planned={c.strategy_id: 1 for c in candidates},
        source_sha256="a" * 64,
        execution=measured.execution,
    )
    full = native_working_set(measured, arms)
    packet = compact_native_packet(measured, arms)
    definitions = packet["shared_filter_definitions"]
    assert len(packet["filter_profiles"]) == 14
    assert len(definitions) == 2
    for profile_id, encoded in packet["filter_profiles"].items():
        restored = {
            **definitions[encoded["shared_filter_definition_id"]],
            "configuration_ref": encoded["configuration_ref"],
        }
        assert restored == full["filter_profiles"][profile_id]
    assert len(compact([packet["filter_profiles"], definitions])) < len(
        compact(full["filter_profiles"])
    )
    assert set(packet["native_pass_candidate_ids"]) == {c.candidate_id for c in candidates}
    for candidate in measured.native_evidence.candidates:
        fact = packet["facts"][candidate.candidate_id]
        assert fact["profile_sha256"] == candidate.profile_sha256
        assert (
            dict(zip(packet["native_metric_columns"], fact["native_metric_values"], strict=True))
            == candidate.metrics
        )


def test_columnar_arm_distributions_preserve_zero_missingness_and_pass_ranks(tmp_path):
    from easydesign.agent.phase3_ranking import compact_native_packet

    measured, arms, _, _ = population(tmp_path, (("arm-a", (1,)), ("arm-b", (0,))))
    full = native_working_set(measured, arms)
    packet = compact_native_packet(measured, arms)
    metrics = packet["distribution_metric_columns"]
    statistics_columns = packet["distribution_statistic_columns"]
    for arm_id in packet["scientific_arm_ids"]:
        for field in ("all_candidate_distributions", "pass_candidate_distributions"):
            restored = {
                metric: dict(zip(statistics_columns, values, strict=True))
                for metric, values in zip(metrics, packet["facts"][arm_id][field], strict=True)
            }
            assert restored == full["scientific_arms"][arm_id][field]
    for candidate_id in packet["native_pass_candidate_ids"]:
        encoded = packet["facts"][candidate_id]["within_pilot_pass_rank_values"]
        restored = {
            metric: dict(zip(("rank", "population", "fraction_strictly_worse"), value, strict=True))
            for metric, value in zip(metrics, encoded, strict=True)
            if value is not None
        }
        assert restored == full["pass_candidates"][candidate_id]["within_pilot_pass_ranks"]


@pytest.mark.parametrize("passes,incomplete", [(0, False), (1, True)])
def test_native_steering_sufficiency_uses_completeness_not_presence_of_a_pass(
    tmp_path, passes, incomplete
):
    from easydesign.agent.phase34_science import bind_pilot_opinion

    measured, arms, _, _ = population(tmp_path, (("arm-a", (passes,)),), incomplete=incomplete)
    diagnosis, recommendation = bind_pilot_opinion(
        measured, arms, opinion_for(measured, arms), evidence_refs=("synthetic",)
    )
    assert diagnosis.confidence == ("INCONCLUSIVE" if incomplete else "BOUNDED")
    assert recommendation.evidence_sufficiency == (
        "INCONCLUSIVE" if incomplete else "SUFFICIENT_FOR_STEERING"
    )
    assert recommendation.completed_zero_pass_arm_ids == (() if incomplete else ("arm-a",))


def test_fabricated_complete_zero_pass_proof_cannot_change_historical_gate4():
    from easydesign.agent.phase34_contracts import PilotEvidenceDossier

    dossier = _pilot_dossier()
    assert "completed_zero_pass_arm_ids" not in dossier.proposed_interpretation.model_dump()
    raw = dossier.model_dump(mode="json")
    raw["proposed_interpretation"]["completed_zero_pass_arm_ids"] = ["invented"]
    with pytest.raises(ValueError, match="requires native measurements"):
        PilotEvidenceDossier.model_validate(raw)
