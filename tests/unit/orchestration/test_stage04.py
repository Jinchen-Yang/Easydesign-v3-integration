from __future__ import annotations

import csv
import json
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
from easydesign.backends.structure_prediction import (
    BackendInvocation,
    ComplexStructurePredictionRequest,
    PredictionRequest,
    StructurePredictionProduct,
)
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
from easydesign.orchestration import read_pipeline_progress
from easydesign.orchestration.stage04 import execute_stage04
from easydesign.orchestration.stage05 import execute_stage05
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
from easydesign.stages.s05_pilot_filtering import Stage05Bundle

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


def _write_complex(
    path: Path,
    *,
    target_names: tuple[str, ...] = ("GLY", "ALA", "SER"),
    binder_names: tuple[str, ...] = ("ALA", "CYS", "ASP", "GLU", "PHE", "GLY"),
) -> None:
    structure = gemmi.Structure()
    model = gemmi.Model("1")
    for chain_id, residue_names, y_position in (
        ("A", target_names, 0.0),
        ("B", binder_names, 4.0),
    ):
        chain = gemmi.Chain(chain_id)
        for number, residue_name in enumerate(residue_names, start=1):
            residue = gemmi.Residue()
            residue.name = residue_name
            residue.seqid = gemmi.SeqId(number, " ")
            residue.label_seq = number
            for atom_name, offset in (
                ("N", 0.0),
                ("CA", 0.5),
                ("C", 1.0),
                ("O", 1.5),
            ):
                atom = gemmi.Atom()
                atom.name = atom_name
                atom.element = gemmi.Element(
                    "N" if atom_name == "N" else "O" if atom_name == "O" else "C"
                )
                atom.pos = gemmi.Position(
                    float(number * 3) + offset,
                    y_position,
                    0,
                )
                residue.add_atom(atom)
            chain.add_residue(residue)
        model.add_chain(chain)
    structure.add_model(model)
    path.parent.mkdir(parents=True, exist_ok=True)
    structure.make_mmcif_document().write_file(str(path))


class _FakeGenerationAdapter:
    def __init__(self, *, complete: bool = True, all_pass: bool = False) -> None:
        self.complete = complete
        self.all_pass = all_pass

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
            sequence = "ACDEFG" if index % 2 == 0 else "HIKLMN"
            binder_names = (
                ("ALA", "CYS", "ASP", "GLU", "PHE", "GLY")
                if index % 2 == 0
                else ("HIS", "ILE", "LYS", "LEU", "MET", "ASN")
            )
            _write_complex(originals / file_name, binder_names=binder_names)
            _write_complex(refolds / file_name, binder_names=binder_names)
            np.savez_compressed(
                originals / f"{candidate_id}.npz",
                design_mask=np.asarray(
                    (0, 0, 0, 0, 1, 1, 0, 1, 0),
                    dtype=np.float32,
                ),
            )
            rows.append(
                {
                    "id": candidate_id,
                    "file_name": file_name,
                    "pass_filters": self.all_pass or index == 0,
                    "design_to_target_iptm": 0.5 + index / 10,
                    "min_design_to_target_pae": 8.0,
                    "filter_rmsd": 1.0,
                    "filter_rmsd_design": 1.0,
                    "design_ptm": 0.8,
                    "delta_sasa_refolded": 500.0,
                    "designed_chain_sequence": sequence,
                    "designed_sequence": "CDF" if index % 2 == 0 else "IKM",
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
                    "min_design_to_target_pae",
                    "filter_rmsd",
                    "filter_rmsd_design",
                    "design_ptm",
                    "delta_sasa_refolded",
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


class _FakeProtenixAdapter:
    def write_input(self, request: PredictionRequest, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps([{"name": request.job_name, "sequences": []}]),
            encoding="utf-8",
        )
        return path

    def msa_invocation(
        self,
        request: PredictionRequest,
        *,
        input_json: Path,
        output_dir: Path,
    ) -> BackendInvocation:
        del input_json
        output_dir.mkdir(parents=True, exist_ok=True)
        target_sequence = (
            request.target.sequence
            if hasattr(request, "target")
            else request.require_role("target").sequence
        )
        a3m = output_dir / "target.a3m"
        a3m.write_text(
            f">query\n{target_sequence}\n>homolog\n{target_sequence}\n",
            encoding="ascii",
        )
        (output_dir / "updated-input.json").write_text(
            json.dumps(
                [
                    {
                        "sequences": [
                            {
                                "proteinChain": {
                                    "unpairedMsaPath": str(a3m.resolve())
                                }
                            }
                        ]
                    }
                ]
            ),
            encoding="utf-8",
        )
        return BackendInvocation(
            backend_name="fake-protenix",
            backend_version="2.0.0",
            argv=("/usr/bin/true",),
            timeout_seconds=30,
        )

    def updated_msa_input_path(
        self,
        input_json: Path,
        output_dir: Path,
    ) -> Path:
        del input_json
        return output_dir / "updated-input.json"

    def prediction_invocation(
        self,
        request: PredictionRequest,
        *,
        input_json: Path,
        output_dir: Path,
    ) -> BackendInvocation:
        del request, input_json
        output_dir.mkdir(parents=True, exist_ok=True)
        return BackendInvocation(
            backend_name="fake-protenix",
            backend_version="2.0.0",
            argv=("/usr/bin/true",),
            timeout_seconds=30,
        )

    def collect_products(
        self,
        request: PredictionRequest,
        *,
        output_dir: Path,
    ) -> tuple[StructurePredictionProduct, ...]:
        assert isinstance(request, ComplexStructurePredictionRequest)
        residue_names = {
            "A": "ALA",
            "C": "CYS",
            "D": "ASP",
            "E": "GLU",
            "F": "PHE",
            "G": "GLY",
            "H": "HIS",
            "I": "ILE",
            "K": "LYS",
            "L": "LEU",
            "M": "MET",
            "N": "ASN",
        }
        binder = request.require_role("binder").sequence
        structure_path = output_dir / "prediction.cif"
        _write_complex(
            structure_path,
            binder_names=tuple(residue_names[item] for item in binder),
        )
        summary_path = output_dir / "summary.json"
        summary_path.write_text(
            json.dumps(
                {
                    "chain_pair_iptm": [[0.0, 0.75], [0.75, 0.0]],
                    "chain_ptm": [0.85, 0.80],
                }
            ),
            encoding="utf-8",
        )
        target_length = len(request.require_role("target").sequence)
        binder_length = len(binder)
        asym = [0] * target_length + [1] * binder_length
        size = len(asym)
        pae = [
            [
                0.0 if asym[first] == asym[second] else 5.0
                for second in range(size)
            ]
            for first in range(size)
        ]
        full_path = output_dir / "full.json"
        full_path.write_text(
            json.dumps(
                {
                    "token_asym_id": asym,
                    "token_has_frame": [1] * size,
                    "token_pair_pae": pae,
                }
            ),
            encoding="utf-8",
        )
        return (
            StructurePredictionProduct(
                backend_name="protenix-v2",
                backend_version="2.0.0",
                model_name="protenix-v2",
                seed=101,
                sample_index=0,
                structure_path=structure_path,
                structure_sha256=sha256_file(structure_path),
                confidence_path=summary_path,
                confidence_sha256=sha256_file(summary_path),
                full_confidence_path=full_path,
                full_confidence_sha256=sha256_file(full_path),
                plddt=0.9,
                gpde=0.1,
                ptm=0.85,
                iptm=0.75,
                ranking_score=0.8,
                has_clash=False,
                recycle_count=10,
            ),
        )


def _prepared_stage03_run(
    tmp_path: Path,
    *,
    through_stage05: bool = False,
) -> Path:
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
                    "stop_after_stage": 5 if through_stage05 else 4,
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
                "stage05": (
                    {
                        "filter_profile": "nanobody-filter-standard-v1.5",
                        "expanded_total_per_strategy": 4,
                        "maximum_tier_a_strategies": 1,
                        "strategy_selection": {
                            "full_target_refold_top_n": 1,
                            "require_unique_winner": True,
                        },
                    }
                    if through_stage05
                    else None
                ),
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
    target_stage_root = root / str(StageId.TARGET_PREPARATION) / "attempt-0001"
    target_artifacts = target_stage_root / "artifacts"
    target_artifacts.mkdir(parents=True)
    target = gemmi.Structure()
    target_model = gemmi.Model("1")
    target_chain = gemmi.Chain("A")
    for number, residue_name in enumerate(("GLY", "ALA", "SER"), start=1):
        residue = gemmi.Residue()
        residue.name = residue_name
        residue.seqid = gemmi.SeqId(number, " ")
        residue.label_seq = number
        atom = gemmi.Atom()
        atom.name = "CA"
        atom.element = gemmi.Element("C")
        atom.pos = gemmi.Position(float(number), 0, 0)
        residue.add_atom(atom)
        target_chain.add_residue(residue)
    target_model.add_chain(target_chain)
    target.add_model(target_model)
    target_path = target_artifacts / "target.cif"
    target.make_mmcif_document().write_file(str(target_path))
    sequence_path = target_artifacts / "sequence.fasta"
    sequence_path.write_text(">generic-target\nGAS\n", encoding="ascii")
    target_ref = ArtifactRef.from_file(
        run_root=root,
        relative_path=target_path.relative_to(root).as_posix(),
        artifact_id="target-structure",
        role="normalized-target-structure",
        file_format="mmcif",
        producer_stage=str(StageId.TARGET_PREPARATION),
        producer_attempt="attempt-0001",
    )
    sequence_ref = ArtifactRef.from_file(
        run_root=root,
        relative_path=sequence_path.relative_to(root).as_posix(),
        artifact_id="target-sequence",
        role="normalized-target-sequence",
        file_format="fasta",
        producer_stage=str(StageId.TARGET_PREPARATION),
        producer_attempt="attempt-0001",
    )
    target_attempt = Attempt(
        attempt_id="attempt-0001",
        status=ExecutionStatus.SUCCEEDED,
        created_at=NOW,
        started_at=NOW,
        ended_at=NOW,
        backend_name="fixture",
        executor_name="fixture",
    )
    dump_model(target_attempt, target_stage_root / "attempt-manifest.json")
    target_manifest = StageManifest(
        stage_id=StageId.TARGET_PREPARATION,
        contract_version="0.4",
        status=ExecutionStatus.SUCCEEDED,
        created_at=NOW,
        completed_at=NOW,
        output_artifacts=(target_ref, sequence_ref),
        attempts=(target_attempt,),
        selected_attempt_id="attempt-0001",
    )
    target_manifest_path = target_artifacts / "stage-manifest.json"
    dump_model(target_manifest, target_manifest_path)
    target_manifest_ref = ArtifactRef.from_file(
        run_root=root,
        relative_path=target_manifest_path.relative_to(root).as_posix(),
        artifact_id="stage-01-manifest",
        role="stage-manifest",
        file_format="json",
        producer_stage=str(StageId.TARGET_PREPARATION),
        producer_attempt="attempt-0001",
    )
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
        stage_manifest_refs=(target_manifest_ref, stage_ref),
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
        str(StageId.TARGET_PREPARATION),
        str(StageId.BOLTZGEN_CONFIGURATION),
        str(StageId.PILOT_GENERATION),
    )


def test_stage05_publishes_audited_scientific_stop_without_starting_backends(
    tmp_path: Path,
) -> None:
    root = _prepared_stage03_run(tmp_path, through_stage05=True)
    stage04 = execute_stage04(
        run_root=root,
        adapter=_FakeGenerationAdapter(),  # type: ignore[arg-type]
        gpu_probe=_FakeGpuProbe(),  # type: ignore[arg-type]
        executed_at=NOW,
    )
    assert stage04.status == "succeeded"

    def forbidden_protenix(*_: object) -> object:
        raise AssertionError("scientific stop 不应启动 Protenix")

    stage05 = execute_stage05(
        run_root=root,
        boltzgen_adapter=_FakeGenerationAdapter(),  # type: ignore[arg-type]
        protenix_adapter_builder=forbidden_protenix,  # type: ignore[arg-type]
        gpu_probe=_FakeGpuProbe(),  # type: ignore[arg-type]
        executed_at=NOW,
    )

    assert stage05.status == "stopped-no-tier-a"
    assert stage05.selected_strategy_id is None
    bundle = load_model(stage05.stage05_bundle, Stage05Bundle)
    assert bundle.status == "stopped-no-tier-a"
    assert bundle.expansion_candidate_index is None
    assert bundle.expansion_validation_report is None
    assert bundle.scientific_stop is not None
    bundle.progress_final.verify(root)
    bundle.task_events.verify(root)
    progress = read_pipeline_progress(root)
    assert progress.stage_id == str(StageId.PILOT_FILTERING)
    assert progress.phase == "stage05-complete"
    assert progress.status == "scientific-stop"
    run = load_model(stage05.run_manifest, RunManifest)
    assert run.status is ExecutionStatus.SUCCEEDED


def test_stage05_expands_and_selects_one_full_target_winner(
    tmp_path: Path,
) -> None:
    root = _prepared_stage03_run(tmp_path, through_stage05=True)
    generation = _FakeGenerationAdapter(all_pass=True)
    stage04 = execute_stage04(
        run_root=root,
        adapter=generation,  # type: ignore[arg-type]
        gpu_probe=_FakeGpuProbe(),  # type: ignore[arg-type]
        executed_at=NOW,
    )
    assert stage04.complete_candidate_count == 2

    stage05 = execute_stage05(
        run_root=root,
        boltzgen_adapter=generation,  # type: ignore[arg-type]
        protenix_adapter_builder=lambda _provider, _device: _FakeProtenixAdapter(),  # type: ignore[arg-type]
        gpu_probe=_FakeGpuProbe(),  # type: ignore[arg-type]
        executed_at=NOW,
    )

    assert stage05.status == "winner-selected"
    assert stage05.selected_strategy_id == "generic-strategy"
    bundle = load_model(stage05.stage05_bundle, Stage05Bundle)
    assert bundle.expansion_candidate_index is not None
    expanded = load_model(
        bundle.expansion_candidate_index.verify(root),
        CandidateIndex,
    )
    assert len(expanded.candidates) == 4
    assert tuple(
        item.ordinal_within_strategy for item in expanded.candidates
    ) == (1, 2, 3, 4)
    assert bundle.expansion_validation_report is not None
    assert bundle.scientific_stop is None


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
