from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from easydesign.backends.target_sources import (
    PYMOL_PYTHON_ENV,
    PseBackendExecutionError,
    PyMOLPseAdapter,
)
from easydesign.core import BackendContractError, TargetInputError


def adapter() -> PyMOLPseAdapter:
    return PyMOLPseAdapter(
        python_executable=Path("/opt/conda/envs/pymol-pse/bin/python"),
        timeout_seconds=17,
    )


def test_adapter_requires_explicit_absolute_interpreter(monkeypatch) -> None:
    monkeypatch.delenv(PYMOL_PYTHON_ENV, raising=False)
    with pytest.raises(BackendContractError, match="必须显式设置"):
        PyMOLPseAdapter.from_environment()
    with pytest.raises(BackendContractError, match="绝对路径"):
        PyMOLPseAdapter(python_executable=Path("python"))


def test_version_probe_requires_exact_310() -> None:
    adapter().validate_version_output("launch noise\n3.1.0\n")
    with pytest.raises(BackendContractError, match="版本不匹配"):
        adapter().validate_version_output("3.2.0\n")


def test_invocation_is_argument_vector_without_shell(tmp_path: Path) -> None:
    invocation = adapter().extraction_invocation(
        request_path=tmp_path / "pse-request.json",
        run_root=tmp_path / "run",
        output_dir=tmp_path / "work",
    )

    assert invocation.argv[0] == "/opt/conda/envs/pymol-pse/bin/python"
    assert invocation.argv[1].endswith("pymol_pse_worker.py")
    assert "--request" in invocation.argv
    assert "--run-root" in invocation.argv
    assert invocation.timeout_seconds == 17


def test_build_request_rejects_source_outside_run(tmp_path: Path) -> None:
    source = tmp_path / "outside.pse"
    source.write_bytes(b"pse")
    with pytest.raises(TargetInputError, match="run snapshot"):
        adapter().build_request(
            run_root=tmp_path / "run",
            source_path=source,
            target_id="target",
        )


def test_extract_reports_worker_timeout(monkeypatch, tmp_path: Path) -> None:
    calls = 0

    def fake_run(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            return subprocess.CompletedProcess(args[0], 0, stdout="3.1.0\n", stderr="")
        raise subprocess.TimeoutExpired(args[0], timeout=17, output="partial", stderr="slow")

    monkeypatch.setattr(subprocess, "run", fake_run)
    request = tmp_path / "request.json"
    request.write_text("{}\n", encoding="utf-8")

    with pytest.raises(PseBackendExecutionError, match="超时") as captured:
        adapter().extract(
            request_path=request,
            run_root=tmp_path,
            output_dir=tmp_path / "work",
        )
    assert captured.value.error_code == "pymol-worker-timeout"


def test_extract_uses_worker_failure_code(monkeypatch, tmp_path: Path) -> None:
    calls = 0

    def fake_run(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            return subprocess.CompletedProcess(args[0], 0, stdout="3.1.0\n", stderr="")
        output = tmp_path / "work" / "pse-response.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(
                {
                    "schema_version": "0.1",
                    "status": "failed",
                    "error_code": "protein-chain-count",
                    "message": "发现两条 chain",
                }
            ),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(args[0], 2, stdout="", stderr="failed")

    monkeypatch.setattr(subprocess, "run", fake_run)
    request = tmp_path / "request.json"
    request.write_text("{}\n", encoding="utf-8")

    with pytest.raises(PseBackendExecutionError, match="发现两条 chain") as captured:
        adapter().extract(
            request_path=request,
            run_root=tmp_path,
            output_dir=tmp_path / "work",
        )
    assert captured.value.error_code == "protein-chain-count"


def test_extract_rejects_success_without_outputs(monkeypatch, tmp_path: Path) -> None:
    calls = 0

    def fake_run(*args, **kwargs):
        nonlocal calls
        calls += 1
        return subprocess.CompletedProcess(
            args[0],
            0,
            stdout="3.1.0\n" if calls == 1 else "",
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    request = tmp_path / "request.json"
    request.write_text("{}\n", encoding="utf-8")

    with pytest.raises(PseBackendExecutionError, match="缺少 response JSON"):
        adapter().extract(
            request_path=request,
            run_root=tmp_path,
            output_dir=tmp_path / "work",
        )
