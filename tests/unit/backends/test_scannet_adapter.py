from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

from easydesign.backends.scannet import (
    SCANNET_COMMIT,
    ScanNetBackendConfig,
    ScanNetBackendError,
    ScanNetEpitopeAdapter,
)
from easydesign.stages.s02_hotspot_discovery import StructureContext
from easydesign.stages.s02_hotspot_discovery.models import ResidueIdentity


def synthetic_context() -> StructureContext:
    residues = {
        label: SimpleNamespace(
            identity=ResidueIdentity(
                sequence_index=label,
                amino_acid="A",
                label_asym_id="Axp",
                label_seq_id=label,
                auth_asym_id="A",
                auth_seq_id=str(label + 22),
            )
        )
        for label in range(1, 19)
    }
    return cast(StructureContext, SimpleNamespace(residues=residues))


def adapter(tmp_path: Path) -> ScanNetEpitopeAdapter:
    python = tmp_path / "env" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.touch()
    repository = tmp_path / "ScanNet"
    repository.mkdir()
    (repository / "predict_bindingsites.py").touch()
    return ScanNetEpitopeAdapter(
        ScanNetBackendConfig(
            python_path=python,
            repository_root=repository,
            timeout_seconds=17,
        )
    )


def test_config_requires_absolute_paths() -> None:
    with pytest.raises(ValueError, match="绝对路径"):
        ScanNetBackendConfig(
            python_path=Path("python"),
            repository_root=Path("/opt/ScanNet"),
        )


def test_missing_python_fails_explicitly(tmp_path: Path) -> None:
    backend = ScanNetEpitopeAdapter(
        ScanNetBackendConfig(
            python_path=tmp_path / "missing-python",
            repository_root=tmp_path,
        )
    )
    with pytest.raises(ScanNetBackendError, match="Python 不存在") as captured:
        backend.probe_runtime()
    assert captured.value.error_code == "scannet-python-missing"


def test_parse_predictions_maps_tool_indices_to_label_ids(tmp_path: Path) -> None:
    backend = adapter(tmp_path)
    context: StructureContext = synthetic_context()
    csv_path = tmp_path / "predictions.csv"
    rows = ["Model,Chain,Residue Index,Sequence,Binding site probability"]
    rows.extend(
        f"0,A,{index},A,{index / 100:.3f}"
        for index in range(1, len(context.residues) + 1)
    )
    csv_path.write_text("\n".join(rows) + "\n", encoding="utf-8")

    raw, probabilities = backend._parse_predictions(csv_path, context)

    assert len(raw) == len(context.residues)
    assert probabilities[1] == pytest.approx(0.01)
    assert probabilities[18] == pytest.approx(0.18)


def test_cpu_runtime_disables_gpu(tmp_path: Path) -> None:
    backend = adapter(tmp_path)

    environment = backend._environment()

    assert environment["EASYDESIGN_SCANNET_DEVICE"] == "cpu"
    assert environment["CUDA_VISIBLE_DEVICES"] == "-1"
    assert "TF_FORCE_GPU_ALLOW_GROWTH" not in environment


def test_cpu_probe_accepts_cpu_result(monkeypatch, tmp_path: Path) -> None:
    backend = adapter(tmp_path)
    calls = 0

    def fake_run(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            return subprocess.CompletedProcess(args[0], 0, SCANNET_COMMIT + "\n", "")
        payload = (
            'EASYDESIGN_RUNTIME_PROBE={"execution_device":"cpu",'
            '"gpu_available":false,'
            '"gpu_device_name":"","keras_version":"2.2.5",'
            '"tensorflow_version":"1.14.0","test_operation_device":"/device:CPU:0"}\n'
        )
        return subprocess.CompletedProcess(args[0], 0, payload, "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    probe = backend.probe_runtime()

    assert probe.execution_device == "cpu"
    assert probe.test_operation_device == "/device:CPU:0"


def test_explicit_gpu_probe_rejects_cpu_only_result(
    monkeypatch,
    tmp_path: Path,
) -> None:
    original = adapter(tmp_path)
    backend = ScanNetEpitopeAdapter(
        original.config.model_copy(update={"execution_device": "gpu"})
    )
    calls = 0

    def fake_run(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            return subprocess.CompletedProcess(args[0], 0, SCANNET_COMMIT + "\n", "")
        payload = (
            'EASYDESIGN_RUNTIME_PROBE={"execution_device":"gpu",'
            '"gpu_available":false,'
            '"gpu_device_name":"","keras_version":"2.2.5",'
            '"tensorflow_version":"1.14.0","test_operation_device":"/device:CPU:0"}\n'
        )
        return subprocess.CompletedProcess(args[0], 0, payload, "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(ScanNetBackendError, match="设备契约") as captured:
        backend.probe_runtime()
    assert captured.value.error_code == "scannet-device-unavailable"
