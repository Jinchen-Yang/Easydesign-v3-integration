from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

from easydesign.backends.target_sources import (
    PYMOL_PYTHON_ENV,
    PseBackendExecutionError,
    PyMOLPseAdapter,
)
from easydesign.core import ExecutionStatus, RunManifest, StageManifest, load_model
from easydesign.orchestration import execute_pse_import, initialize_pse_run
from easydesign.safe_writes import read_last_text_line
from easydesign.stages.s01_target_preparation import (
    PseSourceAnnotations,
    ResidueMapping,
)


def _pymol_python() -> Path:
    value = os.environ.get(PYMOL_PYTHON_ENV)
    if not value:
        pytest.skip(f"{PYMOL_PYTHON_ENV} 未设置，跳过独立 PyMOL 环境集成测试")
    path = Path(value)
    if not path.is_file():
        pytest.skip(f"显式 PyMOL Python 不存在: {path}")
    return path


def _protein_pdb(
    *,
    chains: tuple[str, ...] = ("A",),
    ligand: bool = False,
    residue_name: str = "ALA",
) -> str:
    lines: list[str] = []
    serial = 1
    for chain_index, chain in enumerate(chains):
        for residue_id in range(1, 21):
            base = float((chain_index * 30 + residue_id) * 4)
            for atom_name, element, offset in (
                ("N", "N", 0.0),
                ("CA", "C", 1.2),
                ("C", "C", 2.4),
                ("O", "O", 3.2),
            ):
                lines.append(
                    f"ATOM  {serial:5d} {atom_name:^4s} {residue_name} {chain}{residue_id:4d}"
                    f"    {base + offset:8.3f}{0.0:8.3f}{0.0:8.3f}"
                    f"  1.00 20.00          {element:>2s}"
                )
                serial += 1
        lines.append("TER")
    if ligand:
        lines.append(
            f"HETATM{serial:5d} {'C1':^4s} LIG A{501:4d}"
            f"    {100.0:8.3f}{5.0:8.3f}{0.0:8.3f}"
            f"  1.00 20.00          {'C':>2s}"
        )
    lines.extend(("END", ""))
    return "\n".join(lines)


def _create_session(
    *,
    python: Path,
    directory: Path,
    mode: str,
) -> Path:
    first = directory / "first.pdb"
    second = directory / "second.pdb"
    if mode == "zero-protein":
        first.write_text(
            "HETATM    1  O   HOH A   1       0.000   0.000   0.000"
            "  1.00 20.00           O\nEND\n",
            encoding="utf-8",
        )
    elif mode == "multi-chain":
        first.write_text(_protein_pdb(chains=("A", "B")), encoding="utf-8")
    elif mode == "non-canonical":
        first.write_text(_protein_pdb(residue_name="MSE"), encoding="utf-8")
    else:
        first.write_text(
            _protein_pdb(
                chains=("X",) if mode == "valid" else ("A",),
                ligand=mode == "ligand",
            ),
            encoding="utf-8",
        )
    second.write_text(_protein_pdb(), encoding="utf-8")
    session = directory / f"{mode}.pse"
    code = """
import sys
import pymol
pymol.finish_launching(["pymol", "-cq"])
cmd = pymol.cmd
mode, first, second, output = sys.argv[1:]
cmd.load(first, "TARGET", state=1)
if mode == "multi-object":
    cmd.load(second, "TARGET_2", state=1)
elif mode == "multi-state":
    cmd.load(second, "TARGET", state=2)
if mode == "valid":
    cmd.color("green", "TARGET and polymer.protein")
    cmd.color("red", "TARGET and resi 1-3")
    cmd.color("blue", "TARGET and resi 4-6")
    cmd.color("yellow", "TARGET and resi 7-9")
cmd.save(output)
cmd.quit()
"""
    result = subprocess.run(
        [str(python), "-c", code, mode, str(first), str(second), str(session)],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert session.is_file()
    return session


def _write_config(directory: Path, source: Path) -> Path:
    config = directory / "easydesign.yaml"
    config.write_text(
        f"""
schema_version: "0.1"
project_id: synthetic-pse
target:
  id: synthetic-target
  source: {source.name}
  format: auto
workflow:
  stop_after_stage: 1
""".lstrip(),
        encoding="utf-8",
    )
    return config


def test_synthetic_single_target_pse_publishes_complete_bundle_and_manifests(
    tmp_path: Path,
) -> None:
    python = _pymol_python()
    session = _create_session(python=python, directory=tmp_path, mode="valid")
    adapter = PyMOLPseAdapter(python_executable=python)
    prepared = initialize_pse_run(
        config_path=_write_config(tmp_path, session),
        runs_root=tmp_path / "runs",
        request_writer=adapter,
        code_commit="428e98f",
        easydesign_version="0.1.0.dev0",
        run_id="20260724-synthetic-pse",
        created_at=datetime(2026, 7, 24, 10, 0, tzinfo=UTC),
    )

    completed = execute_pse_import(prepared=prepared, adapter=adapter)

    bundle = completed.built_bundle.bundle
    assert bundle.schema_version == "0.4"
    assert bundle.coordinate_ensemble is not None
    assert bundle.coordinate_ensemble.model_count == 1
    assert bundle.coordinate_ensemble.model_ids == ("1",)
    assert bundle.coordinate_ensemble.representative_model_id == "1"
    assert bundle.origin == "imported"
    assert bundle.sequence_length == 20
    assert bundle.source_annotations is not None
    mapping = load_model(bundle.residue_mapping.verify(prepared.workspace.run_root), ResidueMapping)
    assert [entry.label_seq_id for entry in mapping.entries] == list(range(1, 21))
    assert {entry.label_chain_id for entry in mapping.entries} == {"A"}
    assert {entry.author_chain_id for entry in mapping.entries} == {"A"}
    assert {entry.source_author_chain_id for entry in mapping.entries} == {"X"}
    assert all(entry.reference_position is None for entry in mapping.entries)
    annotations = load_model(
        bundle.source_annotations.verify(prepared.workspace.run_root),
        PseSourceAnnotations,
    )
    assert sorted(group.residue_count for group in annotations.color_counts) == [3, 3, 3, 11]
    assert annotations.interpretation == "uninterpreted"
    assert not list(prepared.workspace.run_root.rglob("protenix-input.json"))
    stage = load_model(completed.stage_manifest, StageManifest)
    assert stage.status == "succeeded"
    assert stage.selected_attempt_id == "attempt-0001"
    run = load_model(completed.run_manifest, RunManifest)
    assert run.revision == 2
    assert run.status == "succeeded"
    assert (
        read_last_text_line(prepared.workspace.latest_manifest_pointer)
        == "run-manifest.v0002.json"
    )
    assert completed.target_viewer.status is ExecutionStatus.SUCCEEDED
    viewer_data = json.loads(
        (completed.target_viewer.report_root / "viewer-data.json").read_text(
            encoding="utf-8"
        )
    )
    assert viewer_data["annotation"]["status"] == "available"
    assert viewer_data["annotation"]["interpretation"] == "uninterpreted"
    assert sorted(
        entry["residue_count"]
        for entry in viewer_data["annotation"]["color_counts"]
    ) == [3, 3, 3, 11]
    assert json.loads(
        bundle.provenance.verify(prepared.workspace.run_root).read_text(encoding="utf-8")
    )["backend_version"] == "3.1.0"


@pytest.mark.parametrize(
    ("mode", "error_code"),
    [
        ("zero-protein", "protein-object-count"),
        ("multi-object", "protein-object-count"),
        ("multi-chain", "protein-chain-count"),
        ("multi-state", "coordinate-state-count"),
        ("ligand", "non-protein-heavy-atoms"),
        ("non-canonical", "non-canonical-residue"),
    ],
)
def test_strict_pse_boundaries_fail_explicitly(
    tmp_path: Path,
    mode: str,
    error_code: str,
) -> None:
    python = _pymol_python()
    session = _create_session(python=python, directory=tmp_path, mode=mode)
    run_root = tmp_path / "run"
    snapshot = run_root / "input-snapshot" / session.name
    snapshot.parent.mkdir(parents=True)
    snapshot.write_bytes(session.read_bytes())
    adapter = PyMOLPseAdapter(python_executable=python)
    request = adapter.build_request(
        run_root=run_root,
        source_path=snapshot,
        target_id="synthetic-target",
    )
    request_path = run_root / "01-target-preparation/attempt-0001/inputs/pse-request.json"
    adapter.write_request(request, request_path)

    with pytest.raises(PseBackendExecutionError) as captured:
        adapter.extract(
            request_path=request_path,
            run_root=run_root,
            output_dir=run_root / "01-target-preparation/attempt-0001/work",
        )
    assert captured.value.error_code == error_code


def test_corrupt_pse_fails_without_fallback(tmp_path: Path) -> None:
    python = _pymol_python()
    run_root = tmp_path / "run"
    snapshot = run_root / "input-snapshot/corrupt.pse"
    snapshot.parent.mkdir(parents=True)
    snapshot.write_bytes(b"not-a-pymol-session")
    adapter = PyMOLPseAdapter(python_executable=python)
    request = adapter.build_request(
        run_root=run_root,
        source_path=snapshot,
        target_id="synthetic-target",
    )
    request_path = run_root / "01-target-preparation/attempt-0001/inputs/pse-request.json"
    adapter.write_request(request, request_path)

    with pytest.raises(PseBackendExecutionError) as captured:
        adapter.extract(
            request_path=request_path,
            run_root=run_root,
            output_dir=run_root / "01-target-preparation/attempt-0001/work",
        )
    assert captured.value.error_code in {"pse-load-failed", "protein-object-count"}
