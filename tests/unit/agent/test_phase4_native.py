"""Native Scale product semantics; synthetic data never establishes biological efficacy."""

import pytest
from pydantic import ValidationError

from easydesign.agent.contracts import AgentBoundaryError
from easydesign.agent.phase3_native import native_profile, project_native_measurement
from easydesign.agent.phase4 import build_global_candidate_pool, build_review_shortlist
from easydesign.agent.phase4_native import native_scale_observations, selection_decision_view
from easydesign.agent.phase34_batches import ScaleBatchReceipt, ScaleBatchStore, partition_campaign
from easydesign.agent.phase34_contracts import (
    FinalCandidateDossier,
    ScaleCampaignSpecification,
    ScaleCandidateObservation,
    ScaleCandidateValidity,
    ScientificContextReferences,
)
from easydesign.agent.phase34_measurement import PilotPredictionEvidence
from easydesign.agent.phase34_partial_reference import PartialReferencePrediction
from easydesign.core import canonical_model_sha256
from tests.unit.agent.test_phase3_native_ranking import population
from tests.unit.agent.test_phase4_pool import _campaign, _candidate


def native_fixture(tmp_path, count=2):
    measured, arms, candidates, profile = population(
        tmp_path, (("arm-a", (count,)), ("arm-b", (count - 1,))), per_strategy=count
    )
    # Distinct sequences plus one exact duplicate across Arms; keep every source row.
    updated = []
    alphabet = "ACDEFGHIKLMNPQRSTVWY"
    for i, c in enumerate(candidates):
        sequence = "ACDF" + alphabet[i % 20] + alphabet[(i // 20) % 20]
        if i == count:
            sequence = "ACDFAA"
        metrics = {
            **c.metrics,
            "designed_chain_sequence": sequence,
            "bb_rmsd_design": 0.5 + i / 100,
        }
        updated.append(c.model_copy(update={"metrics": metrics}))
    measured = project_native_measurement(
        candidates=tuple(updated),
        profiles={s: profile for a in arms for s in a.strategy_ids},
        planned={a.strategy_ids[0]: count for a in arms},
        execution=measured.execution,
        source_sha256="a" * 64,
    )
    raw = _campaign().model_dump(mode="json")
    strategies = [a.strategy_ids[0] for a in arms]
    raw["promotion_authority"]["selected_strategy_ids"] = strategies
    raw["promotion_authority"]["production_strategy_allocations"] = {s: 25_000 for s in strategies}
    raw["strategy_allocations"] = {s: count for s in strategies}
    raw["execution"]["execution_candidates"] = count * 2
    raw["execution"]["mode"] = "synthetic-stress"
    raw["evidence_policy"] = "boltzgen-native-v1"
    raw["promotion_authority"]["evidence_policy"] = "boltzgen-native-v1"
    campaign = ScaleCampaignSpecification.model_validate(raw)
    return measured, campaign, profile, tuple(updated)


def observations(tmp_path, measured, campaign, **kwargs):
    return native_scale_observations(
        root=tmp_path,
        campaign_id=campaign.campaign_id,
        batch_id="batch-all",
        run_id="precomputed-validation",
        measurement=measured,
        **kwargs,
    )


def pool_for(campaign, rows):
    return build_global_candidate_pool(
        campaign=campaign,
        source_candidate_index_sha256="a" * 64,
        source_metric_report_sha256="b" * 64,
        planned_batches=1,
        completed_batch_ids=("batch-all",),
        failed_batch_ids=(),
        resumable_batch_ids=(),
        candidates=rows,
    )


def test_native_pass_without_afo_and_fail_are_evaluated_but_only_pass_competes(tmp_path):
    measured, campaign, _, _ = native_fixture(tmp_path)
    rows = observations(tmp_path, measured, campaign)
    assert all(c.validity is ScaleCandidateValidity.VALID_EVALUATED for c in rows)
    assert all(c.independent_prediction_status == "not-requested" for c in rows)
    pool = pool_for(campaign, rows)
    assert len(pool.candidates) == 4 and len(pool.global_ranking_candidate_ids) == 3
    failed = next(c for c in pool.candidates if c.native_evidence.native_pass is False)
    assert failed.global_development_rank is None and not failed.competition_eligible
    assert failed.metrics and failed.lineage.artifact_refs
    with pytest.raises(ValidationError, match="competition rank"):
        ScaleCandidateObservation.model_validate(
            {**failed.model_dump(), "global_development_rank": 1}
        )


def test_missing_native_evidence_is_operational_not_scientific_fail(tmp_path):
    measured, campaign, profile, candidates = native_fixture(tmp_path)
    c = candidates[0]
    metrics = {k: v for k, v in c.metrics.items() if k != "pass_filter_rmsd_filter"}
    incomplete = project_native_measurement(
        candidates=(c.model_copy(update={"metrics": metrics}), *candidates[1:]),
        profiles={s: profile for s in campaign.strategy_allocations},
        planned=campaign.strategy_allocations,
        execution=measured.execution,
        source_sha256="a" * 64,
    )
    row = observations(tmp_path, incomplete, campaign)[0]
    assert row.native_evidence.native_pass is None
    assert row.validity is ScaleCandidateValidity.UNEVALUABLE
    assert row.failure_reason == "Incomplete native filter evidence"
    assert not row.competition_eligible


def test_each_run_profile_controls_pass_and_conflicting_profiles_rejected(tmp_path):
    measured, campaign, profile, candidates = native_fixture(tmp_path)
    c = candidates[0]
    # Use an explicit native additional rule to prove Phase 4 reuses the active profile.
    profile2 = native_profile(
        {
            **profile.configuration,
            "additional_filters": [
                {"feature": "design_to_target_iptm", "lower_is_better": False, "threshold": 0.5}
            ],
        },
        profile.configuration_ref,
    )
    metrics = {**c.metrics, "pass_design_to_target_iptm_filter": False, "pass_filters": False}
    c = c.model_copy(update={"metrics": metrics, "pass_filters": False})
    measured2 = project_native_measurement(
        candidates=(c, *candidates[1:]),
        profiles={**{s: profile for s in campaign.strategy_allocations}, c.candidate_id: profile2},
        planned=campaign.strategy_allocations,
        execution=measured.execution,
        source_sha256="a" * 64,
    )
    rows = observations(tmp_path, measured2, campaign)
    assert rows[0].native_evidence.native_pass is False
    assert rows[1].native_evidence.native_pass is True  # same iPTM, no extra configured rule
    raw = rows[0].model_dump()
    raw["native_profile"] = profile.model_dump()
    with pytest.raises(ValidationError, match="active run profile"):
        ScaleCandidateObservation.model_validate(raw)


def test_native_plus_independent_evidence_does_not_change_partition(tmp_path):
    measured, campaign, profile, _ = native_fixture(tmp_path)
    line = measured.candidates[0].lineage
    ref = profile.configuration_ref
    prediction = PartialReferencePrediction(
        candidate_id=line.candidate_id,
        strategy_id=line.strategy_id,
        seed=101,
        backend_identity="synthetic-independent",
        model_identity="synthetic-model",
        predicted_structure=ref,
        summary_confidence=ref,
        full_confidence=ref,
        expected_target_residues=5,
        observed_reference_ca_residues=3,
        pairwise_iptm=0.1,
        minimum_interface_pae_angstrom=20,
        binder_ptm=0.2,
        severe_clash_count=0,
        moderate_clash_count=0,
        confidence_metric_definition_version="synthetic-confidence",
        release_identity={},
        prediction_input=ref,
        source_task=ref,
        reference_target=ref,
        designed_complex=ref,
        metric_collection_failed_attempts=1,
        unavailable_metric_reasons={
            "binder_pose_rmsd_angstrom": "partial reference",
            "target_ca_rmsd_angstrom": "partial reference",
        },
    )
    enrichment = PilotPredictionEvidence(
        authority_id="synthetic",
        candidate_index_sha256="a" * 64,
        predictions=(prediction,),
        evidence_refs=(ref,),
    )
    rows = observations(tmp_path, measured, campaign, predictions=enrichment)
    assert rows[0].competition_eligible and rows[0].independent_prediction_status == "available"
    assert rows[1].competition_eligible and rows[1].independent_prediction_status == "unavailable"
    assert rows[0].native_evidence == measured.native_evidence.candidates[0]
    assert any(
        m.metric_id == "independent-prediction-pairwise_iptm" and m.value == 0.1
        for m in rows[0].metrics
    )
    with pytest.raises(AgentBoundaryError, match="different population"):
        observations(
            tmp_path,
            measured,
            campaign,
            predictions=enrichment.model_copy(update={"candidate_index_sha256": "c" * 64}),
        )


def test_native_profiles_and_structures_rechecked_before_projection(tmp_path):
    measured, campaign, _, _ = native_fixture(tmp_path)
    (tmp_path / "synthetic-profile.yaml").write_text("changed input")
    with pytest.raises(Exception, match="checksum|sha256|SHA|size|大小|校验"):
        observations(tmp_path, measured, campaign)


def test_native_global_dedup_keeps_lineage_and_all_arms_visible(tmp_path):
    measured, campaign, _, _ = native_fixture(tmp_path, count=20)
    rows = observations(tmp_path, measured, campaign)
    pool = pool_for(campaign, rows)
    groups = {s: s.split("-scaffold-")[0] for s in campaign.strategy_allocations}
    shortlist = build_review_shortlist(
        pool=pool, requested_count=10, sequence_cluster_cap=1, strategy_groups=groups
    )
    by_id = {c.lineage.candidate_id: c for c in pool.candidates}
    selected = [by_id[e.candidate_id] for e in shortlist.entries]
    assert {groups[c.lineage.strategy_id] for c in selected} == {"arm-a", "arm-b"}
    assert len({c.lineage.sequence_sha256 for c in selected}) == len(selected)
    assert len(pool.candidates) == 40 and len(pool.global_ranking_candidate_ids) == 39
    duplicate = rows[0].lineage.sequence_sha256
    assert sum(c.lineage.sequence_sha256 == duplicate for c in pool.candidates) == 2


def test_native_batch_restart_failure_recovery_and_idempotency(tmp_path):
    measured, campaign, _, _ = native_fixture(tmp_path)
    manifest = partition_campaign("validation", campaign, batch_size=1)
    journal = ScaleBatchStore(tmp_path / "journal", manifest)
    rows = observations(tmp_path, measured, campaign)
    remaining = list(rows)
    receipts = []
    for batch in manifest.batches:
        strategy = next(iter(batch.strategy_allocations))
        row = next(c for c in remaining if c.lineage.strategy_id == strategy)
        remaining.remove(row)
        row = row.model_copy(
            update={
                "lineage": row.lineage.model_copy(
                    update={"batch_id": batch.batch_id, "shard_id": batch.batch_id}
                )
            }
        )
        receipts.append(
            ScaleBatchReceipt(
                manifest_sha256=journal.digest,
                batch_id=batch.batch_id,
                state="completed",
                candidates=(row,),
            )
        )
    for receipt in receipts[:-1]:
        journal.append(receipt)
    journal.append(
        ScaleBatchReceipt(
            manifest_sha256=journal.digest, batch_id=receipts[-1].batch_id, state="failed"
        )
    )
    assert len(journal.pool().candidates) == 3
    restored = ScaleBatchStore(tmp_path / "journal", manifest)
    assert restored.append(receipts[-1])
    for receipt in receipts:
        assert not restored.append(receipt)
    assert canonical_model_sha256(restored.pool()) == canonical_model_sha256(
        ScaleBatchStore(tmp_path / "journal", manifest).pool()
    )
    assert len(restored.pool().candidates) == 4


@pytest.mark.asyncio
async def test_compact_final_view_preserves_values_and_has_repair_headroom(tmp_path):
    from types import SimpleNamespace

    from langchain_core.messages import AIMessage
    from langchain_core.utils.function_calling import convert_to_openai_tool

    from easydesign.agent.harness import skill_root
    from easydesign.agent.phase34_model import structured_opinion
    from easydesign.agent.phase34_opinions import FinalSelectionOpinion
    from easydesign.agent.phase34_science import bind_selection_opinion
    from easydesign.agent.session_store import SessionStore, compact
    from tests.agent_support import scripted_config

    measured, campaign, _, candidates = native_fixture(tmp_path, count=20)
    pool = pool_for(campaign, observations(tmp_path, measured, campaign))
    by_id = {c.lineage.candidate_id: c for c in pool.candidates}
    original = {c.candidate_id: c for c in candidates}
    context = ScientificContextReferences(
        target_identity="synthetic",
        target_snapshot_sha256="a" * 64,
        site_intent_sha256="b" * 64,
        design_specification_sha256="c" * 64,
        pilot_dossier_sha256="d" * 64,
        evidence_refs=("target", "site", "design", "pilot"),
    )
    dossiers = tuple(
        FinalCandidateDossier(
            global_pool_sha256=canonical_model_sha256(pool),
            review_shortlist_sha256="e" * 64,
            context=context,
            candidate=by_id[cid],
            sequence=original[by_id[cid].native_evidence.candidate_id].metrics[
                "designed_chain_sequence"
            ],
            known_concerns=("synthetic",),
            uncertainties=("pose unverified",),
            provenance_refs=("synthetic",),
            scientific_claim_scope="development-evidence-only",
        )
        for cid in pool.global_ranking_candidate_ids[:30]
    )
    packet = selection_decision_view(dossiers, 6, 6)
    assert len(packet["facts"]) == 30
    for d in dossiers:
        row = packet["facts"][d.candidate.lineage.candidate_id]
        values = {
            **d.candidate.native_evidence.metrics,
            **d.candidate.native_evidence.additional_metrics,
        }
        for group, columns in packet["metric_columns"].items():
            assert row["metrics"][group] == [values.get(k) for k in columns]
    first = len(compact(packet)) + len(compact(convert_to_openai_tool(FinalSelectionOpinion)))
    assert first < 50_000
    ids = list(packet["facts"])
    good = dict(
        primary_candidate_ids=ids[:6],
        backup_candidate_ids=ids[6:12],
        selection_rationale=["Synthetic capacity validation."],
        major_risks=["Biology untested."],
        diversity_coverage=["Sequence only."],
        unresolved_questions=["Pose diversity unknown."],
    )
    responses = [{**good, "primary_candidate_ids": ["foreign", *ids[1:6]]}, good]

    class Model:
        def bind_tools(self, tools, **kwargs):
            assert tools == [FinalSelectionOpinion]
            return self

        async def ainvoke(self, messages):
            return AIMessage(
                content="",
                tool_calls=[
                    dict(name="FinalSelectionOpinion", args=responses.pop(0), id="selection")
                ],
            )

    (tmp_path / "capacity-session").mkdir()
    store = SessionStore(tmp_path / "capacity-session")
    try:
        store.thread("capacity", "config", "synthetic validation")
        execution = store.begin_execution("capacity", "validation")["execution_id"]
        opinion = await structured_opinion(
            bridge=SimpleNamespace(store=store, thread="capacity"),
            model=Model(),
            config=scripted_config(),
            execution_id=execution,
            role="final-selection",
            schema=FinalSelectionOpinion,
            packet=packet,
            prompt=(skill_root() / "final-selection/SKILL.md").read_text(),
            validate=lambda o: bind_selection_opinion(o, dossiers, primary_count=6, backup_count=6),
        )
        assert opinion.primary_candidate_ids == ids[:6]
        contexts = [e["payload"] for e in store.events("capacity") if e["kind"] == "model-context"]
        assert len(contexts) == 2
        assert contexts[0]["input_chars_with_schemas"] < 50_000
        assert contexts[1]["input_chars_with_schemas"] < 70_000
    finally:
        store.close()


def test_legacy_serialization_remains_identical():
    c = _candidate("c", "arm-a", "batch-a", 1, 0.4)
    assert "native_evidence" not in c.model_dump()
    assert "independent_prediction_status" not in c.model_dump()
    assert "evidence_policy" not in _campaign().model_dump()


def test_shared_native_adapter_uses_batch_allocation_not_full_pilot(tmp_path, monkeypatch):
    from collections import Counter
    from types import SimpleNamespace

    from easydesign.agent.phase3_native import measure_native_execution
    from easydesign.agent.phase34_contracts import ExecutionProjection
    from easydesign.core import ArtifactRef

    measured, campaign, profile, candidates = native_fixture(tmp_path)
    selected = (candidates[0],)
    allocation = dict(Counter(c.strategy_id for c in selected))
    upstream = SimpleNamespace(
        candidate_index=SimpleNamespace(candidates=selected),
        candidate_index_ref=profile.configuration_ref,
        strategy_bundle=SimpleNamespace(
            strategies=[SimpleNamespace(strategy_id=selected[0].strategy_id)]
        ),
        pilot_bundle=SimpleNamespace(task_table=profile.configuration_ref),
    )
    config = ExecutionProjection(
        mode="synthetic-stress",
        requested_production_candidates=1,
        execution_candidates=1,
        uses_real_generation_backend=False,
        uses_real_prediction_backend=False,
        purpose="synthetic batch adapter check",
    )
    monkeypatch.setattr("easydesign.orchestration.stage05._load_upstream", lambda _: upstream)
    monkeypatch.setattr(
        "easydesign.orchestration.workspace.load_resolved_run_config",
        lambda _: (SimpleNamespace(user_config=config), None),
    )
    monkeypatch.setattr(
        "easydesign.agent.phase3_native.task_filter_profiles",
        lambda *args: ({selected[0].strategy_id: profile}, ()),
    )
    monkeypatch.setattr(
        "easydesign.agent.phase3_native.load_model", lambda *args: SimpleNamespace(tasks=[])
    )
    monkeypatch.setattr(
        "easydesign.agent.phase3_native.refold_contact_metrics",
        lambda *args: {"refold_avoid_to_design_contact_count": 0},
    )
    bridge = SimpleNamespace(run=lambda _: (tmp_path, None))
    execution = {"run_id": "synthetic-run", "config_sha256": canonical_model_sha256(config)}
    plan = SimpleNamespace(execution_allocations=campaign.strategy_allocations)
    result = measure_native_execution(
        bridge,
        authority_id="batch-authority",
        plan=plan,
        execution=execution,
        allocations=allocation,
        projection=config,
    )
    assert len(result["measurement"].candidates) == 1
    assert result["measurement"].native_evidence.candidates[0].native_pass is True
    assert not result["measurement"].execution.uses_real_prediction_backend
    assert (
        ArtifactRef.model_validate(result["sources"]["native_evidence"]).verify(tmp_path).is_file()
    )
    with pytest.raises(AgentBoundaryError, match="exact approved allocation"):
        measure_native_execution(
            bridge,
            authority_id="wrong-allocation",
            plan=plan,
            execution=execution,
            allocations=campaign.strategy_allocations,
            projection=config,
        )


def test_native_incomplete_campaign_cannot_publish_final_inputs(tmp_path):
    from types import SimpleNamespace

    from easydesign.agent.phase34_scale import finalize_scale_inputs

    measured, campaign, _, _ = native_fixture(tmp_path)
    manifest = partition_campaign("validation", campaign, batch_size=2)
    journal = ScaleBatchStore(tmp_path / "journal", manifest)
    for batch in manifest.batches:
        journal.append(
            ScaleBatchReceipt(
                manifest_sha256=journal.digest, batch_id=batch.batch_id, state="failed"
            )
        )
    events = []
    bridge = SimpleNamespace(
        thread="validation",
        project_id="validation",
        store=SimpleNamespace(event=lambda *args: events.append(args)),
        controller=SimpleNamespace(list=lambda **kwargs: []),
    )
    assert finalize_scale_inputs(bridge, journal)["status"] == "scale-operationally-inconclusive"
    assert events[-1][1] == "phase34-scale-inconclusive"
    assert events[-1][2]["incomplete_native_campaign"]


def test_complete_zero_native_pass_is_distinct_from_operational_incomplete(tmp_path):
    from types import SimpleNamespace

    from easydesign.agent.phase34_scale import finalize_scale_inputs

    measured, campaign, profile, candidates = native_fixture(tmp_path)
    failed = tuple(
        c.model_copy(
            update={
                "metrics": {
                    **c.metrics,
                    "bb_rmsd_design": 8.0,
                    "filter_rmsd": 8.0,
                    "filter_rmsd_design": 8.0,
                    "pass_filter_rmsd_filter": False,
                    "pass_filter_rmsd_design_filter": False,
                    "pass_filters": False,
                },
                "pass_filters": False,
            }
        )
        for c in candidates
    )
    measured = project_native_measurement(
        candidates=failed,
        profiles={s: profile for s in campaign.strategy_allocations},
        planned=campaign.strategy_allocations,
        execution=measured.execution,
        source_sha256="a" * 64,
    )
    pool = pool_for(campaign, observations(tmp_path, measured, campaign))
    events = []
    bridge = SimpleNamespace(
        thread="validation",
        project_id="validation",
        store=SimpleNamespace(event=lambda *args: events.append(args)),
        controller=SimpleNamespace(list=lambda **kwargs: []),
    )
    result = finalize_scale_inputs(bridge, SimpleNamespace(pool=lambda: pool, digest="manifest"))
    assert result["status"] == "scale-no-native-pass"
    assert not events[-1][2]["incomplete_native_campaign"]
    assert all(c.native_evidence.native_pass is False for c in pool.candidates)


@pytest.mark.parametrize("incomplete", [False, True])
def test_scale_batch_dispatch_adapter_uses_native_without_independent_prediction(
    tmp_path, monkeypatch, incomplete
):
    from types import SimpleNamespace

    from easydesign.agent.phase34_scale_execution import measure_batch

    measured, campaign, profile, candidates = native_fixture(tmp_path)
    raw_campaign = campaign.model_dump(mode="json")
    raw_campaign["execution"]["mode"] = "validation-micro"
    raw_campaign["execution"]["uses_real_generation_backend"] = True
    campaign = ScaleCampaignSpecification.model_validate(raw_campaign)
    if incomplete:
        changed = candidates[0].model_copy(
            update={
                "metrics": {
                    k: v for k, v in candidates[0].metrics.items() if k != "pass_filter_rmsd_filter"
                }
            }
        )
        measured = project_native_measurement(
            candidates=(changed, *candidates[1:]),
            profiles={s: profile for s in campaign.strategy_allocations},
            planned=campaign.strategy_allocations,
            execution=measured.execution,
            source_sha256="a" * 64,
        )
    calls, receipts, events = [], [], []

    def native(*args, **kwargs):
        calls.append(kwargs)
        return {
            "measurement": measured,
            "sources": {
                "candidate_index": profile.configuration_ref.model_dump(mode="json"),
                "native_evidence": profile.configuration_ref.model_dump(mode="json"),
            },
        }

    def forbidden(*args, **kwargs):
        raise AssertionError(
            "Default native Scale must not invoke mandatory independent prediction"
        )

    monkeypatch.setattr("easydesign.agent.phase4_native.measure_native_execution", native)
    monkeypatch.setattr("easydesign.agent.phase34_measurement.measure_execution", forbidden)
    monkeypatch.setattr(
        "easydesign.agent.phase4_native.load_model",
        lambda *args: SimpleNamespace(candidates=candidates),
    )
    bridge = SimpleNamespace(
        thread="validation",
        run=lambda _: (tmp_path, None),
        pilot_authority=lambda: SimpleNamespace(pilot_plan=SimpleNamespace()),
        store=SimpleNamespace(event=lambda *args: events.append(args)),
    )
    journal = SimpleNamespace(
        digest="a" * 64,
        manifest=SimpleNamespace(campaign=campaign),
        append=lambda receipt: receipts.append(receipt),
    )
    batch = SimpleNamespace(
        batch_id="batch-all", strategy_allocations=campaign.strategy_allocations
    )
    result = measure_batch(bridge, journal, batch, {"run_id": "source", "job_id": "worker-1"})
    assert calls[0]["allocations"] == campaign.strategy_allocations
    assert not calls[0]["projection"].uses_real_prediction_backend
    assert receipts[0].state == ("failed" if incomplete else "completed")
    if incomplete:
        assert result["status"] == "scale-batch-operationally-incomplete"
        assert "incomplete-native-worker:worker-1" in receipts[0].source_refs
        assert not receipts[0].candidates and not events
    else:
        assert result["status"] == "scale-batch-measured"
        assert len(receipts[0].candidates) == 4
        assert all(
            c.independent_prediction_status == "not-requested" for c in receipts[0].candidates
        )
        assert len(events[0][2]["sequences"]) == 4
