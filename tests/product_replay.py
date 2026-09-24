"""Explicit isolated Product E2E driver; synthetic providers, real Runtime and API.

Run only in a NEW runtime/tmp workspace. Never import into production service.
The compute substitutions below publish typed validation evidence, never launch GPUs.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from easydesign.agent.phase3_native import project_native_measurement
from easydesign.agent.phase4 import build_global_candidate_pool, build_review_shortlist
from easydesign.agent.phase4_native import native_scale_observations
from easydesign.agent.phase34_authority import plan_for_design
from easydesign.agent.phase34_contracts import (
    ExecutionProjection,
    Gate4PromotionAuthority,
    Gate4Recommendation,
    PilotEvidenceDossier,
    ScaleCampaignSpecification,
    ScientificContextReferences,
)
from easydesign.agent.phase34_execution import register_micro_plan
from easydesign.agent.phase34_plan import ValidatedDesignContext
from easydesign.agent.phase34_runtime import Phase34Runtime
from easydesign.agent.phase34_scale import publish_review_inputs
from easydesign.agent.phase34_science import bind_pilot_opinion
from easydesign.core import ArtifactRef, canonical_model_sha256
from easydesign.product.domain import NativeGateway
from easydesign.product.server import ProductServer
from easydesign.product.service import ProductService
from easydesign.workspace_context import WorkspaceContext
from tests.agent_phase2_support import configure_offline_validation
from tests.agent_support import scripted_config, structure
from tests.unit.agent.test_design_harness import DesignModel
from tests.unit.agent.test_phase3_native_ranking import opinion_for, population
from tests.unit.agent.test_site_runtime import site_intent

ROOT: Path


class ReplayModel(DesignModel):
    def bind_tools(self, tools, **kwargs):
        if self.role in {"pilot-diagnosis", "final-selection"}:
            self.offered = {getattr(t, "__name__", getattr(t, "name", "")) for t in tools}
            return self
        return super().bind_tools(tools, **kwargs)

    def answer(self, messages):
        if messages and "read-only conversation" in str(messages[0].content):
            from langchain_core.messages import AIMessage

            return AIMessage(
                content=(
                    "Site B is the alternative candidate. Its hotspot residues are 3 and 4 "
                    "in this synthetic fixture. The comparison has uncertainties; the Gate "
                    "remains pending until you choose Approve or Edit."
                )
            )
        if self.role == "pilot-diagnosis":
            opinion = json.loads((ROOT / "runtime/tmp/pilot-opinion.json").read_text())
            return self.call("PilotDiagnosisOpinion", **opinion)
        if self.role == "final-selection":
            ids = json.loads((ROOT / "runtime/tmp/final-ids.json").read_text())
            return self.call(
                "FinalSelectionOpinion",
                primary_candidate_ids=ids[:1],
                backup_candidate_ids=ids[1:2],
                selection_rationale=["Synthetic interface comparison"],
                major_risks=["Fixture metrics do not establish efficacy."],
                diversity_coverage=["Distinct synthetic sequences"],
                unresolved_questions=["All experimental outcomes remain unknown."],
            )
        result = super().answer(messages)
        for call in result.tool_calls:
            if call["name"] == "SiteResearchHandoff":
                call["args"]["candidates"] = [
                    site_intent(labels).selected_site.model_dump(mode="json")
                    for labels in ([1, 2], [3, 4], [5, 6])
                ]
        return result


def synthetic_pilot(b, _authority):
    directory = ROOT / "runtime/tmp/native-fixture"
    directory.mkdir(exist_ok=True)
    # Preserve approved Design and production intent; independently register a clearly
    # bounded validation projection through the existing trusted validation entry point.
    original = b.plan()
    plan = plan_for_design(
        b,
        b.current_design(),
        prediction_backend=original.prediction_backend,
        mode="validation-micro",
        execution_allocations={s: 2 for s in list(original.production_allocations)[:3]},
    )
    authority = register_micro_plan(
        b, plan, reason="Product E2E only; synthetic evidence, no compute authority"
    )
    fake, arms, candidates, profile = population(
        directory, (("arm-a", (1, 1, 1, 0, 0, 0, 0)),), per_strategy=2
    )
    mapping = dict(zip(arms[0].strategy_ids, plan.arms[0].strategy_ids, strict=True))
    remapped = []
    for index, c in enumerate(candidates):
        if mapping[c.strategy_id] not in plan.execution_allocations:
            continue
        source = directory / f"candidate-{index}.pdb"
        source.write_text(structure("AB"))
        ref = ArtifactRef.from_file(
            run_root=directory,
            relative_path=source.name,
            artifact_id=f"synthetic-complex-{index}",
            role="synthetic-fixture",
            file_format="pdb",
        )
        remapped.append(
            c.model_copy(
                update={
                    "strategy_id": mapping[c.strategy_id],
                    "candidate_id": f"synthetic-candidate-{index}",
                    "metrics": {
                        **c.metrics,
                        "designed_chain_sequence": "ACDEFGHIK" + "ACDEFGHIKLMNPQRS"[index],
                    },
                    "original_structure": ref,
                    "refolded_structure": ref,
                }
            )
        )
    measurement = project_native_measurement(
        candidates=tuple(remapped),
        profiles={s: profile for s in plan.execution_allocations},
        planned=plan.execution_allocations,
        execution=ExecutionProjection(
            mode="validation-micro",
            requested_production_candidates=sum(plan.production_allocations.values()),
            execution_candidates=sum(plan.execution_allocations.values()),
            uses_real_generation_backend=False,
            uses_real_prediction_backend=False,
            purpose="Synthetic product transport verification",
        ),
        source_sha256="b" * 64,
    )
    b.store.event(
        b.thread,
        "phase34-pilot-execution",
        {
            "authority": authority.authority_id,
            "job_id": "product-synthetic-worker",
            "run_id": "product-synthetic-pilot",
        },
    )
    b.publish_contract(
        kind="phase34-pilot-measurement",
        contract=measurement,
        dependencies={
            "authority": authority.authority_id,
            "execution_job_id": "product-synthetic-worker",
        },
    )
    opinion = opinion_for(measurement, plan.arms)
    opinion = opinion.model_copy(
        update={"candidate_order": [r.candidate_id for r in opinion.candidate_rankings]}
    )
    (ROOT / "runtime/tmp/pilot-opinion.json").write_text(opinion.model_dump_json())
    # Saved/replay Pilot evidence follows the existing test-only Gate 4 contract.
    # Micro evidence cannot recommend scientific Scale. Keep that INCONCLUSIVE
    # diagnosis and explicitly attach an engineering-only transition for this E2E.
    diagnosis, _ = bind_pilot_opinion(
        measurement, plan.arms, opinion, evidence_refs=("synthetic:product-e2e",)
    )
    recommendation = Gate4Recommendation(
        outcome="PROMOTE_TO_SCALE",
        selected_strategy_ids=tuple(plan.execution_allocations),
        requested_scale_candidates=30,
        production_strategy_allocations={s: 10 for s in plan.execution_allocations},
        evidence_sufficiency="INCONCLUSIVE",
        scientific_supporting_candidate_count=0,
        observations=("Synthetic measured fixture",),
        interpretations=("Engineering-only transition; not scientific promotion",),
        alternative_explanations=("No real design or prediction has run",),
        uncertainties=("Biology untested",),
        falsifiers_or_next_measurements=("A formal Pilot is required for science",),
        evidence_refs=("synthetic:product-e2e",),
        test_only_control_flow_fixture=True,
    )
    dossier = PilotEvidenceDossier(
        project_id=b.project_id,
        pilot_run_id="product-synthetic-pilot",
        upstream_fixture=b.load_contract(
            kind="phase34-approved-gate3", contract_type=ValidatedDesignContext
        ),
        execution_authority=authority,
        measurement=measurement,
        diagnosis=diagnosis,
        proposed_interpretation=recommendation,
        evidence_refs=("synthetic:product-e2e",),
    )
    b.publish_contract(
        kind="phase34-pilot-dossier",
        contract=dossier,
        dependencies={"authority": authority.authority_id},
    )
    return {"status": "succeeded", "validation_only": True}


def synthetic_scale(b):
    pilot = b.current_pilot_dossier()
    authority = b.load_contract(
        kind="phase34-scale-authority", contract_type=Gate4PromotionAuthority
    )
    assert not authority.authorizes_production_compute and not authority.authorizes_scientific_scale
    campaign = ScaleCampaignSpecification(
        campaign_id="product-validation-scale",
        promotion_authority=authority,
        execution=ExecutionProjection(
            mode="synthetic-stress",
            requested_production_candidates=authority.requested_scale_candidates,
            execution_candidates=2 * len(authority.selected_strategy_ids),
            uses_real_generation_backend=False,
            uses_real_prediction_backend=False,
            purpose="Synthetic product Scale replay; no generation",
        ),
        strategy_allocations={s: 2 for s in authority.selected_strategy_ids},
        generation_backend="synthetic-none",
        prediction_backend="synthetic-none",
        allocation_policy="validation-projection",
        evidence_policy="boltzgen-native-v1",
    )
    rows = native_scale_observations(
        root=ROOT / "runtime/tmp/native-fixture",
        campaign_id=campaign.campaign_id,
        batch_id="product-synthetic-batch",
        run_id="product-synthetic-scale",
        measurement=pilot.measurement,
    )
    pool = build_global_candidate_pool(
        campaign=campaign,
        source_candidate_index_sha256="c" * 64,
        source_metric_report_sha256="d" * 64,
        planned_batches=1,
        completed_batch_ids=("product-synthetic-batch",),
        failed_batch_ids=(),
        resumable_batch_ids=(),
        candidates=rows,
    )
    shortlist = build_review_shortlist(pool=pool, requested_count=30)
    ids = [entry.candidate_id for entry in shortlist.entries]
    by_id = {c.lineage.candidate_id: c for c in rows}
    context = pilot.upstream_fixture
    publish_review_inputs(
        b,
        pool,
        context=ScientificContextReferences(
            target_identity=context.target_identity,
            target_snapshot_sha256=context.target_bundle_sha256,
            site_intent_sha256=context.site_intent_sha256,
            design_specification_sha256=context.strategy_sha256,
            pilot_dossier_sha256=canonical_model_sha256(pilot),
            evidence_refs=(
                "target:" + context.target_bundle_sha256,
                "site:" + context.site_intent_sha256,
                "design:" + context.strategy_sha256,
                "pilot:" + canonical_model_sha256(pilot),
            ),
        ),
        sequences={i: by_id[i].native_evidence.metrics["designed_chain_sequence"] for i in ids},
        concerns={i: ("Synthetic data only",) for i in ids},
        uncertainties={i: ("No biological validation",) for i in ids},
        provenance={i: ("synthetic:" + i,) for i in ids},
        primary_count=1,
        backup_count=1,
    )
    (ROOT / "runtime/tmp/final-ids.json").write_text(json.dumps(ids))
    return {"status": "review-inputs-ready", "validation_only": True}


def configure(root: Path):
    global ROOT
    ROOT = root.resolve()
    if "runtime/tmp/" not in str(ROOT) or not (ROOT / ".product-synthetic-e2e").is_file():
        raise RuntimeError("Use an explicitly initialized disposable runtime/tmp workspace")
    os.environ["EASYDESIGN_WORKSPACE"] = str(ROOT)
    context = WorkspaceContext.from_root(ROOT)
    context.ensure_layout()
    patch = pytest.MonkeyPatch()
    if not (context.runtime_root / "offline-validator").exists():
        configure_offline_validation(patch, ROOT)
    else:
        # Reinstall only process-local backend validation substitutions after restart.
        from easydesign.backends.boltzgen.check import BoltzGenCheckAdapter
        from easydesign.stages.s03_boltzgen_configuration.models import (
            BOLTZGEN_COMMIT,
            BOLTZGEN_VERSION,
        )

        patch.setattr(
            BoltzGenCheckAdapter,
            "probe",
            lambda self: {"version": BOLTZGEN_VERSION, "commit": BOLTZGEN_COMMIT},
        )
        patch.setattr(
            BoltzGenCheckAdapter,
            "_run",
            lambda self, argv, **kw: subprocess.CompletedProcess(
                argv, 0, stdout="OFFLINE MOCK", stderr=""
            ),
        )
    from easydesign.agent.tools import LocalStepJobController

    original_load = LocalStepJobController.load
    patch.setattr(
        LocalStepJobController,
        "load",
        lambda self, j: (
            SimpleNamespace(status="succeeded", job_id=j)
            if j == "product-synthetic-worker"
            else original_load(self, j)
        ),
    )
    original_run = Phase34Runtime.run
    patch.setattr(
        Phase34Runtime,
        "run",
        lambda self, run_id=None: (
            (ROOT / "runtime/tmp/native-fixture", None)
            if run_id in {"product-synthetic-pilot", "product-synthetic-scale"}
            else original_run(self, run_id)
        ),
    )
    patch.setattr("easydesign.agent.phase34_runtime.execute_pilot", synthetic_pilot)
    patch.setattr("easydesign.agent.phase34_scale.advance_scale", synthetic_scale)
    config_path = ROOT / "models.yaml"
    config_path.write_text(scripted_config().model_dump_json())
    gateway = NativeGateway(
        context,
        config_path,
        model_factory=lambda *a, **k: {
            r: ReplayModel(role=r)
            for r in (
                "coordinator",
                "target",
                "site",
                "binder",
                "judge",
                "pilot-diagnosis",
                "final-selection",
            )
        },
    )
    return ProductService(gateway, actor="synthetic-product-scientist"), patch


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("--init", action="store_true")
    parser.add_argument("--worker")
    parser.add_argument("--port", type=int, default=14381)
    parser.add_argument("--web", type=Path)
    args = parser.parse_args()
    if args.init:
        args.root.mkdir(parents=True, exist_ok=False)
        (args.root / ".product-synthetic-e2e").write_text(
            "Synthetic Product E2E; no science or production authority"
        )
        (args.root / "easydesign-workspace.yaml").write_text(
            'schema_version: "0.1"\nworkspace_id: product-e2e\n'
        )
        context = WorkspaceContext.from_root(args.root)
        context.ensure_layout()
        from easydesign.orchestration.profile import initialize_runtime_profile

        initialize_runtime_profile(context.profile_path)
        (args.root / "input.pdb").write_text(structure("AB"))
    service, patch = configure(args.root)
    if args.worker:
        service.run(args.worker)
        return

    def launch(request_id):
        with (service.root / (request_id + ".worker.log")).open("ab") as log:
            subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "tests.product_replay",
                    str(args.root),
                    "--worker",
                    request_id,
                ],
                cwd=Path(__file__).resolve().parents[1],
                env=os.environ,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=log,
                start_new_session=True,
            )

    service.launcher = launch
    server = ProductServer(service, port=args.port, web_root=args.web)
    print("Synthetic Product API ready", flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()
        patch.undo()


if __name__ == "__main__":
    main()
