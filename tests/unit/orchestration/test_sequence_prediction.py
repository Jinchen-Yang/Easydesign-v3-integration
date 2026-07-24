from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

from easydesign.backends.structure_prediction import (
    ProtenixMsaProvider,
    ProtenixV2Adapter,
)
from easydesign.core import ExecutionStatus, RunManifest, StageManifest, load_model
from easydesign.orchestration import (
    SequencePredictionExecutionError,
    execute_sequence_prediction,
    initialize_sequence_run,
)
from easydesign.orchestration.config import ResolvedProtenixMsaProviderConfig

ROOT = Path(__file__).resolve().parents[3]
APOE_CONFIG = ROOT / "examples/stage01-apoe/input/easydesign.yaml"
ONE_TO_THREE = {
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
    "P": "PRO",
    "Q": "GLN",
    "R": "ARG",
    "S": "SER",
    "T": "THR",
    "V": "VAL",
    "W": "TRP",
    "Y": "TYR",
}


def option(args: list[str], name: str) -> str:
    return args[args.index(name) + 1]


def write_prediction(output_dir: Path, job_name: str, sequence: str) -> None:
    predictions = output_dir / job_name / "seed_101" / "predictions"
    predictions.mkdir(parents=True)
    structure = predictions / f"{job_name}_sample_0.cif"
    lines = [
        "data_target",
        "loop_",
        "_atom_site.group_PDB",
        "_atom_site.label_comp_id",
        "_atom_site.label_asym_id",
        "_atom_site.label_seq_id",
        "_atom_site.auth_asym_id",
        "_atom_site.auth_seq_id",
        "_atom_site.pdbx_PDB_ins_code",
    ]
    lines.extend(
        f"ATOM {ONE_TO_THREE[amino_acid]} A {index} A {index} ."
        for index, amino_acid in enumerate(sequence, start=1)
    )
    lines.append("#")
    structure.write_text("\n".join(lines) + "\n", encoding="utf-8")
    confidence = predictions / f"{job_name}_summary_confidence_sample_0.json"
    confidence.write_text(
        json.dumps(
            {
                "plddt": 84.0,
                "gpde": 3.5,
                "ptm": 0.5,
                "iptm": 0.0,
                "ranking_score": 0.5,
                "has_clash": False,
                "num_recycles": 10,
            }
        ),
        encoding="utf-8",
    )


def successful_fake_run(
    args: list[str],
    *,
    check: bool,
    capture_output: bool,
    text: bool,
    env: dict[str, str],
    timeout: int | None,
) -> subprocess.CompletedProcess[str]:
    del check, capture_output, text, timeout
    if args[1] == "--version":
        return subprocess.CompletedProcess(args, 0, "protenix, version 2.0.0\n", "")
    input_path = Path(option(args, "--input"))
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    job_name = payload[0]["name"]
    sequence = payload[0]["sequences"][0]["proteinChain"]["sequence"]
    if args[1] == "msa":
        assert env["MMSEQS_SERVICE_HOST_URL"] == "https://api.colabfold.com"
        output_dir = Path(option(args, "--out_dir"))
        a3m = output_dir / job_name / "msa" / "0" / "0" / "non_pairing.a3m"
        a3m.parent.mkdir(parents=True)
        a3m.write_text(
            f">query\n{sequence}\n>homolog\n{sequence}\n",
            encoding="utf-8",
        )
        payload[0]["sequences"][0]["proteinChain"]["unpairedMsaPath"] = str(
            a3m.resolve()
        )
        updated = input_path.with_name(f"{input_path.stem}-update-msa.json")
        updated.write_text(json.dumps(payload), encoding="utf-8")
        return subprocess.CompletedProcess(args, 0, "MSA complete\n", "")
    assert args[1] == "pred"
    assert option(args, "--use_msa") == "true"
    write_prediction(Path(option(args, "--out_dir")), job_name, sequence)
    return subprocess.CompletedProcess(args, 0, "Prediction complete\n", "")


def adapter_builder(
    provider: ResolvedProtenixMsaProviderConfig,
) -> ProtenixV2Adapter:
    custom_endpoint = (
        provider.endpoint
        if provider.provider is ProtenixMsaProvider.CUSTOM_COLABFOLD
        else None
    )
    return ProtenixV2Adapter(
        executable=Path("/envs/protenix-v2/bin/protenix"),
        model_root=Path("/models/protenix"),
        cuda_visible_devices="0",
        remote_msa_provider=provider.provider,
        remote_msa_endpoint=custom_endpoint,
        remote_msa_timeout_seconds=provider.timeout_seconds,
        prediction_timeout_seconds=7200,
    )


def prepared_run(tmp_path: Path):
    return initialize_sequence_run(
        config_path=APOE_CONFIG,
        runs_root=tmp_path / "runs",
        input_writer=adapter_builder(
            ResolvedProtenixMsaProviderConfig(
                provider="colabfold-public",
                endpoint="https://api.colabfold.com",
                server_mode="colabfold",
                timeout_seconds=1800,
                max_attempts=3,
                retry_backoff_seconds=30,
            )
        ),
        code_commit="f600b9a",
        easydesign_version="0.1.0.dev0",
        run_id="20260724-006-stage01-msa",
        created_at=datetime(2026, 7, 24, 12, 0, tzinfo=UTC),
    )


def test_execute_sequence_prediction_publishes_stage01_handoff(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(subprocess, "run", successful_fake_run)
    prepared = prepared_run(tmp_path)

    completed = execute_sequence_prediction(
        prepared=prepared,
        adapter_builder=adapter_builder,
        model_checkpoint_sha256="8" * 64,
        sleep=lambda _: None,
    )

    run_root = prepared.workspace.run_root
    bundle = completed.built_bundle.bundle
    assert bundle.origin == "predicted"
    assert bundle.target_structure.file_format == "mmcif"
    assert bundle.target_structure.verify(run_root).name == "target.cif"
    assert completed.msa_artifact.verify(run_root).name == "target-msa.a3m"
    provenance = json.loads(bundle.provenance.verify(run_root).read_text())
    assert provenance["msa_provider"] == "colabfold-public"
    assert provenance["msa_endpoint"] == "https://api.colabfold.com"
    assert provenance["msa_depth"] == 2
    assert provenance["msa_ticket_status"] == "not-exposed-by-protenix-cli-2.0.0"

    stage = load_model(completed.stage_manifest, StageManifest)
    assert stage.status is ExecutionStatus.SUCCEEDED
    assert stage.selected_attempt_id == "attempt-0001"
    assert stage.require_output("target-bundle") == completed.built_bundle.bundle_artifact
    assert stage.require_output("target-msa") == completed.msa_artifact
    run = load_model(completed.run_manifest, RunManifest)
    assert run.status is ExecutionStatus.SUCCEEDED


def test_execute_sequence_prediction_retries_msa_as_new_attempt(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    msa_calls = 0

    def fail_once(args: list[str], **kwargs):
        nonlocal msa_calls
        if args[1] == "msa":
            msa_calls += 1
            if msa_calls == 1:
                return subprocess.CompletedProcess(args, 1, "", "temporary queue error")
        return successful_fake_run(args, **kwargs)

    monkeypatch.setattr(subprocess, "run", fail_once)
    prepared = prepared_run(tmp_path)

    completed = execute_sequence_prediction(
        prepared=prepared,
        adapter_builder=adapter_builder,
        model_checkpoint_sha256="8" * 64,
        sleep=lambda _: None,
    )

    assert msa_calls == 2
    assert len(completed.attempt_manifests) == 2
    first = json.loads(completed.attempt_manifests[0].read_text())
    second = json.loads(completed.attempt_manifests[1].read_text())
    assert first["status"] == "failed"
    assert first["error"]["retryable"] is True
    assert second["status"] == "succeeded"
    stage = load_model(completed.stage_manifest, StageManifest)
    assert stage.selected_attempt_id == "attempt-0002"


def test_execute_sequence_prediction_publishes_terminal_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def always_fail(args: list[str], **kwargs):
        if args[1] == "msa":
            return subprocess.CompletedProcess(args, 1, "", "queue unavailable")
        return successful_fake_run(args, **kwargs)

    monkeypatch.setattr(subprocess, "run", always_fail)
    prepared = prepared_run(tmp_path)

    with pytest.raises(SequencePredictionExecutionError, match="Backend 调用失败"):
        execute_sequence_prediction(
            prepared=prepared,
            adapter_builder=adapter_builder,
            model_checkpoint_sha256="8" * 64,
            sleep=lambda _: None,
        )

    attempt_manifests = sorted(
        prepared.workspace.stage_root("01-target-preparation").glob(
            "attempt-*/attempt-manifest.json"
        )
    )
    assert len(attempt_manifests) == 3
    stage = load_model(
        prepared.workspace.stage_root("01-target-preparation")
        / "stage-manifest.v0001.json",
        StageManifest,
    )
    assert stage.status is ExecutionStatus.FAILED
    run = load_model(
        prepared.workspace.run_root / "manifests/run-manifest.v0002.json",
        RunManifest,
    )
    assert run.status is ExecutionStatus.FAILED
