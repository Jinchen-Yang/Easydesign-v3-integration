"""Actual native graph: engineering-only Gate 4 promotion through Gate 5 revision/handoff."""

import json
from types import SimpleNamespace

import pytest

from easydesign.agent.cli import run_session
from easydesign.agent.phase3 import build_pilot_diagnosis
from easydesign.agent.phase4 import build_global_candidate_pool
from easydesign.agent.phase34_authority import plan_for_design
from easydesign.agent.phase34_cards import pilot_card
from easydesign.agent.phase34_contracts import (
    ExecutionProjection,
    Gate4Recommendation,
    PilotArmDenominator,
    PilotDiagnosisHypothesis,
    PilotEvidenceDossier,
    PilotMeasurement,
    ScaleCampaignSpecification,
    ScientificContextReferences,
)
from easydesign.agent.phase34_execution import register_micro_plan
from easydesign.agent.phase34_opinions import DownstreamJudgeOpinion
from easydesign.agent.phase34_plan import ValidatedDesignContext
from easydesign.agent.phase34_runtime import Phase34Runtime
from easydesign.agent.phase34_scale import publish_review_inputs
from easydesign.core import canonical_model_sha256
from tests.agent_support import scripted_config
from tests.unit.agent.test_phase4_pool import _candidate
from tests.unit.agent.test_phase34_authority import prepared
from tests.unit.agent.test_phase34_runtime import DownstreamModel


def micro_fixture(design_bridge):
    original, _, _ = prepared(design_bridge)
    bridge = Phase34Runtime(original.project, original.thread, original.store, through="handoff")
    full = plan_for_design(bridge, bridge.current_design(), prediction_backend="openfold3-af3-jax")
    chosen = sorted(full.production_allocations)[:2]
    plan = plan_for_design(
        bridge,
        bridge.current_design(),
        prediction_backend="openfold3-af3-jax",
        mode="validation-micro",
        execution_allocations={s: 2 for s in chosen},
    )
    authority = register_micro_plan(
        bridge, plan, reason="Synthetic control flow only; no experimental authority"
    )
    context = bridge.load_contract(
        kind="phase34-approved-gate3", contract_type=ValidatedDesignContext
    )
    measurement = PilotMeasurement(
        execution=ExecutionProjection(
            mode="validation-micro",
            requested_production_candidates=sum(plan.production_allocations.values()),
            execution_candidates=4,
            uses_real_generation_backend=False,
            uses_real_prediction_backend=False,
            purpose="Synthetic validation of Gate 4 / Gate 5 authority",
        ),
        source_candidate_index_sha256="a" * 64,
        source_filter_report_sha256="b" * 64,
        candidates=(),
        arms=tuple(
            PilotArmDenominator(
                strategy_id=s,
                planned_candidates=2,
                generated_candidates=0,
                valid_execution_products=0,
                predicted_candidates=0,
                metric_evaluable_candidates=0,
                unique_sequences=0,
                legacy_policy_pass_count=0,
                operational_failure_count=2,
                missing_by_metric={},
            )
            for s in chosen
        ),
    )
    bridge.publish_contract(
        kind="phase34-pilot-measurement",
        contract=measurement,
        dependencies={"authority": authority.authority_id},
    )
    diagnosis = build_pilot_diagnosis(
        measurement=measurement,
        hypotheses=(
            PilotDiagnosisHypothesis(
                category="insufficient-evidence",
                status="UNRESOLVED",
                observations=("No measured data.",),
                implications=("No biological inference.",),
                evidence_refs=("synthetic:pilot",),
            ),
        ),
        conclusion=("No biological conclusion; fixture steering only.",),
        uncertainties=("Synthetic evidence.",),
        evidence_refs=("synthetic:pilot",),
        confidence="INCONCLUSIVE",
    ).model_copy(update={"design_arms": plan.arms})
    recommendation = Gate4Recommendation(
        outcome="PROMOTE_TO_SCALE",
        selected_strategy_ids=tuple(chosen),
        requested_scale_candidates=20,
        production_strategy_allocations={s: 10 for s in chosen},
        evidence_sufficiency="INCONCLUSIVE",
        scientific_supporting_candidate_count=0,
        observations=("Synthetic state transition.",),
        interpretations=("No scientific promotion.",),
        alternative_explanations=("No real measurements.",),
        uncertainties=("Biology untested.",),
        falsifiers_or_next_measurements=("Run a formal Scientist-approved Pilot.",),
        evidence_refs=("synthetic:pilot",),
        test_only_control_flow_fixture=True,
    )
    dossier = PilotEvidenceDossier(
        project_id=bridge.project_id,
        pilot_run_id="synthetic-pilot",
        upstream_fixture=context,
        execution_authority=authority,
        measurement=measurement,
        diagnosis=diagnosis,
        proposed_interpretation=recommendation,
        evidence_refs=("synthetic:pilot",),
    )
    bridge.publish_contract(
        kind="phase34-pilot-dossier",
        contract=dossier,
        dependencies={"authority": authority.authority_id},
    )
    bridge.store.event(
        bridge.thread,
        "phase34-pilot-execution",
        {
            "authority": authority.authority_id,
            "job_id": "synthetic-worker",
            "run_id": "synthetic-pilot",
        },
    )
    bridge.controller = SimpleNamespace(
        load=lambda _: SimpleNamespace(status="succeeded"), list=bridge.controller.list
    )
    card = pilot_card(
        dossier,
        DownstreamJudgeOpinion(
            review="NO_MATERIAL_ISSUE",
            brief_rationale="Validation control flow only.",
            uncertainties=["No biological evidence."],
        ),
    )
    bridge.publish_gate_card(card=card, evidence_contract=dossier)
    return bridge, dossier, context


def scale_fixture(bridge, pilot, context):
    from easydesign.agent.phase34_contracts import Gate4PromotionAuthority

    authority = bridge.load_contract(
        kind="phase34-scale-authority", contract_type=Gate4PromotionAuthority
    )
    assert not authority.authorizes_scientific_scale and not authority.authorizes_production_compute
    chosen = authority.selected_strategy_ids
    campaign = ScaleCampaignSpecification(
        campaign_id="scale-validation-1",
        promotion_authority=authority,
        execution=ExecutionProjection(
            mode="synthetic-stress",
            requested_production_candidates=20,
            execution_candidates=4,
            uses_real_generation_backend=False,
            uses_real_prediction_backend=False,
            purpose="Synthetic global selection validation",
        ),
        strategy_allocations={s: 2 for s in chosen},
        generation_backend="synthetic-none",
        prediction_backend="synthetic-none",
        allocation_policy="validation-projection",
    )
    candidates = tuple(
        _candidate(f"candidate-{arm}{i}", "arm-" + arm, "batch-" + arm, i, score).model_copy(
            update={
                "lineage": _candidate(
                    f"candidate-{arm}{i}", "arm-" + arm, "batch-" + arm, i, score
                ).lineage.model_copy(update={"strategy_id": chosen[0 if arm == "a" else 1]})
            }
        )
        for arm, score in (("a", 0.6), ("b", 0.9))
        for i in (1, 2)
    )
    pool = build_global_candidate_pool(
        campaign=campaign,
        source_candidate_index_sha256="c" * 64,
        source_metric_report_sha256="d" * 64,
        planned_batches=2,
        completed_batch_ids=("batch-a", "batch-b"),
        failed_batch_ids=(),
        resumable_batch_ids=(),
        candidates=candidates,
    )
    ids = [c.lineage.candidate_id for c in candidates]
    refs = ScientificContextReferences(
        target_identity=context.target_identity,
        target_snapshot_sha256=context.target_bundle_sha256,
        site_intent_sha256=context.site_intent_sha256,
        design_specification_sha256=context.strategy_sha256,
        pilot_dossier_sha256=canonical_model_sha256(pilot),
        evidence_refs=("synthetic:target", "synthetic:site", "synthetic:design", "synthetic:pilot"),
    )
    publish_review_inputs(
        bridge,
        pool,
        context=refs,
        sequences={i: "ACDEFGHIK" if "-a" in i else "LMNPQRSTV" for i in ids},
        concerns={i: ("Experimental activity unknown.",) for i in ids},
        uncertainties={i: ("Synthetic metrics are not biological evidence.",) for i in ids},
        provenance={i: ("synthetic:" + i,) for i in ids},
        primary_count=2,
        backup_count=2,
        review_count=4,
    )


class FinalModel(DownstreamModel):
    def bind_tools(self, tools, **kwargs):
        if self.role == "final-selection":
            assert [getattr(t, "__name__", "") for t in tools] == ["FinalSelectionOpinion"]
            return self
        return super().bind_tools(tools, **kwargs)

    def answer(self, messages):
        if self.role != "final-selection":
            return super().answer(messages)
        packet = json.loads(messages[-1].content)
        ids = sorted(packet["facts"])
        return self.call(
            "FinalSelectionOpinion",
            primary_candidate_ids=ids[:2],
            backup_candidate_ids=ids[2:],
            selection_rationale=["Balanced validation panel across strategies."],
            major_risks=["No binding or efficacy data."],
            diversity_coverage=["Two sequence families."],
            unresolved_questions=["All wet-lab outcomes remain unknown."],
        )


@pytest.mark.asyncio
async def test_actual_gate4_resume_final_specialist_gate5_revision_and_validation_handoff(
    design_bridge,
):
    bridge, pilot, context = micro_fixture(design_bridge)
    models = {
        r: FinalModel(role=r)
        for r in (
            "coordinator",
            "target",
            "site",
            "binder",
            "judge",
            "pilot-diagnosis",
            "final-selection",
        )
    }
    goal = "SYNTHETIC validation-only downstream review"
    first = await run_session(bridge, scripted_config(), models, goal)
    assert first["card"]["gate_type"] == "pilot-promotion"
    card4 = bridge.downstream_card()
    bridge.store.respond(
        bridge.thread,
        card4.card_id,
        "approve",
        "synthetic-scientist",
        selected_option_id="PROMOTE_TO_SCALE",
    )
    bridge.apply_decision(card4)
    scale_fixture(bridge, pilot, context)
    result = await run_session(bridge, scripted_config(), models, goal)
    assert result["card"]["gate_type"] == "wet-lab-handoff", result
    card5 = bridge.downstream_card()
    revised = await run_session(
        bridge,
        scripted_config(),
        models,
        goal,
        decision="revise",
        card_id=card5.card_id,
        user="synthetic-scientist",
        revision_gate="wet-lab-handoff",
        human_instruction="Keep the same panel; explicitly retain all uncertainty.",
    )
    assert revised["status"] == "awaiting-human-approval", revised
    revised_card = bridge.downstream_card()
    assert revised_card.card_id != card5.card_id
    final = await run_session(
        bridge,
        scripted_config(),
        models,
        goal,
        decision="approve",
        card_id=revised_card.card_id,
        user="synthetic-scientist",
        selected_option_id="wet-lab-panel",
    )
    assert final["status"] == "finished", final
    handoff = bridge.document(bridge.project_latest("phase34-wet-lab-handoff")["ref"])
    assert handoff["handoff_status"] == "validation-only-not-authorized-for-experiment"
    assert handoff["ordering_status"] == "not-ordered"
    assert len(handoff["candidates"]) == 4
    before = len(
        [e for e in bridge.store.events(bridge.thread) if e["kind"] == "phase34-wet-lab-handoff"]
    )
    bridge.apply_decision(revised_card)
    assert (
        len(
            [
                e
                for e in bridge.store.events(bridge.thread)
                if e["kind"] == "phase34-wet-lab-handoff"
            ]
        )
        == before
    )
