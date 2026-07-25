from __future__ import annotations

import csv
from datetime import UTC, datetime
from pathlib import Path

import gemmi
import numpy as np
import yaml

from easydesign.backends.boltzgen import (
    BoltzGenGenerationRequest,
    BoltzGenGenerationResult,
)
from easydesign.backends.executors import GpuResourceSnapshot
from easydesign.core import (
    ArtifactRef,
    Attempt,
    CodeIdentity,
    CodeIdentitySource,
    ExecutionStatus,
    ProgressSnapshot,
    RunManifest,
    RuntimeProfileRef,
    StageId,
    StageManifest,
    dump_model,
    load_model,
    sha256_file,
)
from easydesign.orchestration.stage04 import execute_stage04
from easydesign.orchestration.task_tracking import atomic_dump_runtime_model
from easydesign.orchestration.workspace import initialize_run_workspace
from easydesign.stages.s03_boltzgen_configuration import (
    ScaffoldAsset,
    StrategyBundle,
    StrategyRecord,
)
from easydesign.stages.s04_pilot_generation import (
    CandidateIndex,
    PilotBundle,
    PilotExecutionState,
)
from easydesign.stages.s04_pilot_generation.models import TaskTable

NOW = datetime(2026, 7, 26, 3, 0, tzinfo=UTC)


class _FakeGpuProbe:
    def wait_until_idle(
        self,
        devices: tuple[int, ...],
        **_: object,
    ) -> tuple[GpuResourceSnapshot, ...]:
        return tuple(
            GpuResourceSnapshot(
                device=device,
                name="Fake GPU",
                uuid=f"GPU-{device}",
                memory_total_mib=32_000,
                memory_used_mib=0,
                utilization_percent=0,
            )
            for device in devices
        )


class _FakeGenerationAdapter:
    def __init__(self, *, complete: bool = True) -> None:
        self.complete = complete

    def probe(self) -> dict[str, str]:
        return {
            "backend": "boltzgen",
            "version": "0.3.2",
            "commit": "a3149cf18eeb58648d1abbb27539bd73f746cdda",
            "random_seed_status": "unsupported-by-boltzgen-0.3.2",
        }

    def build_command(self, request: BoltzGenGenerationRequest) -> tuple[str, ...]:
        return (
            "fake-boltzgen",
            str(request.design_specification),
            str(request.requested_candidates),
        )

    def execute(self, request: BoltzGenGenerationRequest) -> BoltzGenGenerationResult:
        output = request.output_directory
        originals = output / "intermediate_designs_inverse_folded"
        refolds = originals / "refold_cif"
        metrics = output / "final_ranked_designs/all_designs_metrics.csv"
        refolds.mkdir(parents=True)
        metrics.parent.mkdir(parents=True)
        rows: list[dict[str, object]] = []
        output_count = (
            request.requested_candidates
            if self.complete
            else max(request.requested_candidates - 1, 0)
        )
        for index in range(output_count):
            candidate_id = f"generic_{index}"
            file_name = f"{candidate_id}.cif"
            structure = gemmi.Structure()
            model = gemmi.Model("1")
            for chain_id, residue_names in (
                ("A", ("GLY", "ALA")),
                ("B", ("ALA", "CYS", "ASP", "GLU", "PHE", "GLY")),
            ):
                chain = gemmi.Chain(chain_id)
                for number, residue_name in enumerate(residue_names, start=1):
                    residue = gemmi.Residue()
                    residue.name = residue_name
                    residue.seqid = gemmi.SeqId(number, " ")
                    atom = gemmi.Atom()
                    atom.name = "CA"
                    atom.element = gemmi.Element("C")
                    atom.pos = gemmi.Position(float(number), 0, 0)
                    residue.add_atom(atom)
                    chain.add_residue(residue)
                model.add_chain(chain)
            structure.add_model(model)
            document = structure.make_mmcif_document()
            document.write_file(str(originals / file_name))
            document.write_file(str(refolds / file_name))
            np.savez_compressed(
                originals / f"{candidate_id}.npz",
                design_mask=np.asarray(
                    (0, 0, 0, 1, 1, 0, 1, 0),
                    dtype=np.float32,
                ),
            )
            rows.append(
                {
                    "id": candidate_id,
                    "file_name": file_name,
                    "pass_filters": index == 0,
                    "design_to_target_iptm": 0.5 + index / 10,
                    "designed_chain_sequence": "ACDEFG",
                    "designed_sequence": "CDF",
                    "num_design": 3,
                }
            )
        with metrics.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=(
                    "id",
                    "file_name",
                    "pass_filters",
                    "design_to_target_iptm",
                    "designed_chain_sequence",
                    "designed_sequence",
                    "num_design",
                ),
            )
            writer.writeheader()
            writer.writerows(rows)
        request.stdout_path.parent.mkdir(parents=True, exist_ok=True)
        request.stdout_path.write_text("ok\n", encoding="utf-8")
        request.stderr_path.write_text("", encoding="utf-8")
        return BoltzGenGenerationResult(
            command=self.build_command(request),
            command_sha256="a" * 64,
            started_at=NOW,
            ended_at=NOW,
            return_code=0,
            stdout_path=request.stdout_path,
            stderr_path=request.stderr_path,
            output_directory=output,
        )


def _prepared_stage03_run(tmp_path: Path) -> Path:
    pse = tmp_path / "target.pse"
    pse.write_bytes(b"synthetic")
    project = tmp_path / "project"
    project.mkdir()
    config = project / "easydesign.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "schema_version": "0.7",
                "project_id": "generic-project",
                "design": {
                    "binder_profile": "vhh",
                    "intent": "exploratory",
                    "required_reviews": [],
                },
                "workflow": {
                    "execution_mode": "unattended",
                    "stop_after_stage": 4,
                    "max_strategy_rounds": 1,
                },
                "stage01": {
                    "target": {
                        "id": "generic-target",
                        "source": {
                            "type": "local-file",
                            "path": str(pse),
                            "format": "pse",
                            "identity": {},
                        },
                        "scope": {"type": "full-sequence"},
                    },
                    "structure_selection": {},
                    "structure_prediction": None,
                },
                "stage02": {
                    "mode": "user-provided",
                    "methods": [],
                    "automatic": None,
                    "user_regions": {
                        "source": {"type": "pse-colors"},
                        "approval": {
                            "approved_by": "fixture",
                            "acknowledge_user_provided_regions": True,
                            "acknowledge_evidence_limitations": True,
                            "selections": [
                                {
                                    "id": "A",
                                    "design_goal": "exploratory",
                                    "biological_rationale": "fixture",
                                    "structural_rationale": "fixture",
                                }
                            ],
                        },
                    },
                },
                "stage03": {
                    "profile": "boltzgen-vhh-basic-v1",
                    "scaffold_registry": "official-vhh7-v1",
                    "candidates_per_strategy": 2,
                },
                "stage04": {
                    "backend": "boltzgen-0.3.2",
                    "executor": {
                        "type": "local-multi-gpu",
                        "devices": [0],
                        "workers_per_device": 1,
                        "max_task_attempts": 2,
                    },
                    "required_complete_candidates_per_strategy": 2,
                },
                "stage05": None,
                "stage06": None,
                "stage07": None,
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    prepared = initialize_run_workspace(
        config_path=config,
        runs_root=tmp_path / "runs",
        easydesign_version="0.1.0.dev5",
        code_identity=CodeIdentity(
            version="0.1.0.dev5",
            source=CodeIdentitySource.INSTALLED_PACKAGE,
            dirty=False,
            content_sha256="a" * 64,
        ),
        runtime_profile=RuntimeProfileRef(
            profile_id="fixture",
            sha256="b" * 64,
        ),
        run_id="generic-stage04",
        created_at=NOW,
    )
    root = prepared.workspace.run_root
    stage_root = root / str(StageId.BOLTZGEN_CONFIGURATION) / "attempt-0001"
    artifacts = stage_root / "artifacts"
    spec = artifacts / "strategies/generic-strategy/design.yaml"
    spec.parent.mkdir(parents=True)
    spec.write_text("entities: []\n", encoding="utf-8")
    scaffold_spec = artifacts / "assets/scaffold.yaml"
    scaffold_structure = artifacts / "assets/scaffold.cif"
    scaffold_spec.parent.mkdir(parents=True, exist_ok=True)
    scaffold_spec.write_text("entities: []\n", encoding="utf-8")
    scaffold_structure.write_text("data_scaffold\n#\n", encoding="utf-8")
    scaffold = ScaffoldAsset(
        scaffold_id="fixture-scaffold",
        specification_path="assets/scaffold.yaml",
        specification_sha256=sha256_file(scaffold_spec),
        structure_path="assets/scaffold.cif",
        structure_sha256=sha256_file(scaffold_structure),
        source_repository="https://example.test/repository",
        source_commit="c" * 40,
    )
    strategy = StrategyRecord(
        strategy_id="generic-strategy",
        region_id="generic-region",
        source_hotspot_set_id="generic",
        scaffold_id=scaffold.scaffold_id,
        binding_label_seq_ids=(1, 2),
        candidates_per_strategy=2,
        design_specification_path="strategies/generic-strategy/design.yaml",
        design_specification_sha256=sha256_file(spec),
    )
    bundle = StrategyBundle(
        generated_at=NOW,
        project_id="generic-project",
        run_id="generic-stage04",
        target_id="generic-target",
        target_structure_sha256="d" * 64,
        target_bundle_sha256="e" * 64,
        hotspots_sha256="f" * 64,
        source_stage02_manifest_sha256="1" * 64,
        validation_report_sha256="2" * 64,
        scaffold_assets=(scaffold,),
        strategies=(strategy,),
    )
    bundle_path = artifacts / "strategy-bundle.json"
    dump_model(bundle, bundle_path)
    strategy_ref = ArtifactRef.from_file(
        run_root=root,
        relative_path=spec.relative_to(root).as_posix(),
        artifact_id="strategy-generic-strategy",
        role="boltzgen-design-specification",
        file_format="yaml",
        producer_stage=str(StageId.BOLTZGEN_CONFIGURATION),
        producer_attempt="attempt-0001",
    )
    bundle_ref = ArtifactRef.from_file(
        run_root=root,
        relative_path=bundle_path.relative_to(root).as_posix(),
        artifact_id="strategy-bundle",
        role="stage04-strategy-input",
        file_format="json",
        producer_stage=str(StageId.BOLTZGEN_CONFIGURATION),
        producer_attempt="attempt-0001",
    )
    attempt = Attempt(
        attempt_id="attempt-0001",
        status=ExecutionStatus.SUCCEEDED,
        created_at=NOW,
        started_at=NOW,
        ended_at=NOW,
        backend_name="fixture",
        executor_name="fixture",
    )
    dump_model(attempt, stage_root / "attempt-manifest.json")
    stage_manifest = StageManifest(
        stage_id=StageId.BOLTZGEN_CONFIGURATION,
        contract_version="0.1",
        status=ExecutionStatus.SUCCEEDED,
        created_at=NOW,
        completed_at=NOW,
        output_artifacts=(bundle_ref, strategy_ref),
        attempts=(attempt,),
        selected_attempt_id="attempt-0001",
    )
    stage_manifest_path = artifacts / "stage-manifest.json"
    dump_model(stage_manifest, stage_manifest_path)
    stage_ref = ArtifactRef.from_file(
        run_root=root,
        relative_path=stage_manifest_path.relative_to(root).as_posix(),
        artifact_id="stage-03-manifest",
        role="stage-manifest",
        file_format="json",
        producer_stage=str(StageId.BOLTZGEN_CONFIGURATION),
        producer_attempt="attempt-0001",
    )
    initial = load_model(prepared.workspace.run_manifest, RunManifest)
    running = initial.next_revision(
        updated_at=datetime(2026, 7, 26, 3, 0, 1, tzinfo=UTC),
        status=ExecutionStatus.RUNNING,
        stage_manifest_refs=(stage_ref,),
    )
    running_path = root / "manifests/run-manifest.v0002.json"
    dump_model(running, running_path)
    (root / "manifests/LATEST").write_text(
        running_path.name + "\n",
        encoding="utf-8",
    )
    return root


def test_stage04_executes_generic_strategy_and_publishes_manifest_only_handoff(
    tmp_path: Path,
) -> None:
    root = _prepared_stage03_run(tmp_path)

    outcome = execute_stage04(
        run_root=root,
        adapter=_FakeGenerationAdapter(),  # type: ignore[arg-type]
        gpu_probe=_FakeGpuProbe(),  # type: ignore[arg-type]
        executed_at=NOW,
    )

    assert outcome.status == "succeeded"
    assert outcome.strategy_count == 1
    assert outcome.complete_candidate_count == 2
    assert outcome.pilot_bundle is not None
    bundle = load_model(outcome.pilot_bundle, PilotBundle)
    index = load_model(bundle.candidate_index.verify(root), CandidateIndex)
    assert len(index.candidates) == 2
    assert {candidate.pass_filters for candidate in index.candidates} == {
        True,
        False,
    }
    run = load_model(outcome.run_manifest, RunManifest)
    assert run.status is ExecutionStatus.SUCCEEDED
    assert tuple(
        reference.producer_stage for reference in run.stage_manifest_refs
    ) == (
        str(StageId.BOLTZGEN_CONFIGURATION),
        str(StageId.PILOT_GENERATION),
    )


def test_stage04_resume_preserves_complete_candidates_and_runs_only_deficit(
    tmp_path: Path,
) -> None:
    root = _prepared_stage03_run(tmp_path)
    adapter = _FakeGenerationAdapter(complete=False)

    incomplete = execute_stage04(
        run_root=root,
        adapter=adapter,  # type: ignore[arg-type]
        gpu_probe=_FakeGpuProbe(),  # type: ignore[arg-type]
        executed_at=NOW,
    )

    assert incomplete.status == "incomplete"
    assert incomplete.complete_candidate_count == 1
    first_candidate = next(
        (
            root
            / "04-pilot-generation/attempt-0001/tasks"
            / "pilot-generic-strategy/attempt-0001/backend-output"
            / "intermediate_designs_inverse_folded"
        ).glob("*.cif")
    )
    first_hash = sha256_file(first_candidate)
    state_path = (
        root
        / "04-pilot-generation/attempt-0001/runtime/task-state.json"
    )
    state = load_model(state_path, PilotExecutionState)
    elapsed_before_resume = state.progress.elapsed_seconds
    atomic_dump_runtime_model(
        state.model_copy(
            update={
                "candidates": tuple(
                    candidate.model_copy(
                        update={
                            "design_mask_source": None,
                            "designed_binder_residue_ids": (),
                        }
                    )
                    for candidate in state.candidates
                )
            }
        ),
        state_path,
    )
    adapter.complete = True

    completed = execute_stage04(
        run_root=root,
        adapter=adapter,  # type: ignore[arg-type]
        gpu_probe=_FakeGpuProbe(),  # type: ignore[arg-type]
    )

    assert completed.status == "succeeded"
    assert completed.complete_candidate_count == 2
    assert sha256_file(first_candidate) == first_hash
    assert completed.pilot_bundle is not None
    bundle = load_model(completed.pilot_bundle, PilotBundle)
    final_progress = bundle.progress_final.verify(root)
    assert (
        load_model(final_progress, ProgressSnapshot).elapsed_seconds
        >= elapsed_before_resume
    )
    index = load_model(bundle.candidate_index.verify(root), CandidateIndex)
    assert all(candidate.design_mask_source is not None for candidate in index.candidates)
    assert all(candidate.designed_binder_residue_ids for candidate in index.candidates)
    tasks = load_model(bundle.task_table.verify(root), TaskTable)
    assert len(tasks.tasks[0].attempts) == 3
    assert tuple(
        attempt.requested_candidates for attempt in tasks.tasks[0].attempts
    ) == (2, 1, 1)
    assert tasks.tasks[0].status.value == "succeeded"
