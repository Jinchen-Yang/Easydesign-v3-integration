from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from easydesign.backends.tnp import (
    TNP_COMMIT,
    TnpAdapter,
    TnpBatchRequest,
    TnpBatchResult,
    _verified_tnp_source_snapshot,
)
from easydesign.core import BackendContractError, ManifestStateError
from easydesign.orchestration.git_sources import (
    GitSourceReceipt,
    directory_content_sha256,
)
from easydesign.stages.s07_final_filtering_and_selection import DevelopabilityRisk

NOW = datetime(2026, 7, 26, 8, 0, tzinfo=UTC)


def _adapter(tmp_path: Path) -> TnpAdapter:
    return TnpAdapter(
        python=tmp_path / "python",
        executable=tmp_path / "TNP",
        repository_root=tmp_path,
    )


def _request(tmp_path: Path) -> TnpBatchRequest:
    return TnpBatchRequest(
        sequences=(("candidate-one", "ACDEFG"),),
        output_directory=tmp_path / "output",
        input_fasta=tmp_path / "input.fasta",
        stdout_path=tmp_path / "stdout.log",
        stderr_path=tmp_path / "stderr.log",
    )


def test_exported_tnp_source_snapshot_is_verified_without_git(tmp_path: Path) -> None:
    source = tmp_path / "bin" / "TNP"
    source.parent.mkdir()
    source.write_text("#!/bin/sh\n", encoding="utf-8")
    marker = GitSourceReceipt(
        source="https://github.com/oxpig/TNP.git",
        revision=TNP_COMMIT,
        content_sha256=directory_content_sha256(tmp_path),
        transport_source_id="fixture-archive",
        transport_url="https://example.test/tnp.tar.gz",
        archive_sha256="a" * 64,
        recorded_at=NOW,
    )
    (tmp_path / ".easydesign-source.json").write_text(
        marker.model_dump_json(),
        encoding="utf-8",
    )

    assert _verified_tnp_source_snapshot(tmp_path) == TNP_COMMIT

    source.write_text("drift\n", encoding="utf-8")
    with pytest.raises(BackendContractError, match="现有内容不一致"):
        _verified_tnp_source_snapshot(tmp_path)


def _write_result(request: TnpBatchRequest, *, identity: str = "candidate-one") -> Path:
    request.output_directory.mkdir(parents=True)
    result = request.output_directory / "TNP_Results_Multientry.json"
    result.write_text(
        json.dumps(
            {
                identity: {
                    "Total CDR Length": 30,
                    "CDR3 Length": 12,
                    "CDR3 Compactness": 0.75,
                    "PSH": 0.2,
                    "PPC": 0.1,
                    "PNC": 0.1,
                    "Flags": {
                        "L": "green",
                        "L3": "green",
                        "C": "green",
                        "PSH": "amber",
                        "PPC": "amber",
                        "PNC": "green",
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    liabilities = request.output_directory / "Final_Models"
    liabilities.mkdir()
    (liabilities / f"{identity}_NanoBodyBuilder2_Sequence_Liabilities.json").write_text(
        "chain,position,aa,liability\nH,33,N,Asn deamidation (NG NS NT)\n",
        encoding="utf-8",
    )
    return result


def test_tnp_collect_converts_audited_json_and_csv_liabilities(tmp_path: Path) -> None:
    request = _request(tmp_path)
    result_path = _write_result(request)
    records = _adapter(tmp_path).collect(
        request,
        TnpBatchResult(
            started_at=NOW,
            ended_at=NOW,
            return_code=0,
            result_path=result_path,
            stdout_path=request.stdout_path,
            stderr_path=request.stderr_path,
        ),
    )

    assert len(records) == 1
    assert records[0].candidate_id == "candidate-one"
    assert records[0].risk is DevelopabilityRisk.MEDIUM
    assert records[0].cdr_vernier_liabilities[0].numbering == "imgt"
    assert records[0].cdr_vernier_liabilities[0].sequence_start == 33
    assert records[0].cdr_vernier_liabilities[0].numbering_label == "33"


def test_tnp_collect_rejects_candidate_identity_drift(tmp_path: Path) -> None:
    request = _request(tmp_path)
    result_path = _write_result(request, identity="other-candidate")

    with pytest.raises(ManifestStateError, match="candidate identity"):
        _adapter(tmp_path).collect(
            request,
            TnpBatchResult(
                started_at=NOW,
                ended_at=NOW,
                return_code=0,
                result_path=result_path,
                stdout_path=request.stdout_path,
                stderr_path=request.stderr_path,
            ),
        )


def test_tnp_collect_rejects_nonfinite_metric(tmp_path: Path) -> None:
    request = _request(tmp_path)
    result_path = _write_result(request)
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    payload["candidate-one"]["PSH"] = float("nan")
    result_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ManifestStateError, match="非有限"):
        _adapter(tmp_path).collect(
            request,
            TnpBatchResult(
                started_at=NOW,
                ended_at=NOW,
                return_code=0,
                result_path=result_path,
                stdout_path=request.stdout_path,
                stderr_path=request.stderr_path,
            ),
        )


def test_tnp_runtime_environment_is_prefix_bound_and_cpu_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PYTHONPATH", "/host/pythonpath")
    monkeypatch.setenv("PYTHONHOME", "/host/pythonhome")
    monkeypatch.setenv("VIRTUAL_ENV", "/host/venv")
    monkeypatch.setenv("CONDA_DEFAULT_ENV", "host-conda")
    adapter = _adapter(tmp_path)
    prefix = adapter.python.parent.parent

    environment = adapter._runtime_environment()

    assert environment["PATH"].split(":")[0] == str(prefix / "bin")
    assert environment["LD_LIBRARY_PATH"].split(":")[0] == str(prefix / "lib")
    assert environment["CONDA_PREFIX"] == str(prefix)
    assert environment["PYTHONNOUSERSITE"] == "1"
    assert environment["CUDA_VISIBLE_DEVICES"] == ""
    assert "PYTHONPATH" not in environment
    assert "PYTHONHOME" not in environment
    assert "VIRTUAL_ENV" not in environment
    assert "CONDA_DEFAULT_ENV" not in environment
