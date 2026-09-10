"""Synthetic geometry fixtures, not biological validation or a design benchmark."""

from __future__ import annotations

import math
from typing import Any


def gpcr_like_structure() -> tuple[str, dict[str, Any]]:
    rows: list[str] = []
    topology: list[dict[str, Any]] = []
    serial = 1
    residue_id = 0
    glycan_labels: list[int] = []
    for helix in range(1, 8):
        angle = (helix - 1) * 2 * math.pi / 7
        x, y = 12 * math.cos(angle), 12 * math.sin(angle)
        segments = [(f"TM{helix}", 10)]
        if helix < 7:
            segments.append((f"ICL{(helix + 1) // 2}" if helix % 2 else f"ECL{helix // 2}", 5))
        for segment, count in segments:
            for index in range(count):
                residue_id += 1
                if segment.startswith("TM"):
                    z = 13.5 - index * 3 if helix % 2 else -13.5 + index * 3
                    px, py = x, y
                else:
                    z = -20.0 if segment.startswith("ICL") else 20.0
                    px, py = x + index * 1.0, y + math.sin(index)
                residue = "ALA"
                if segment == "ECL1" and index in {1, 2, 3}:
                    residue = {1: "ASN", 2: "GLY", 3: "THR"}[index]
                    glycan_labels.append(residue_id)
                topology.append({"label_seq_id": residue_id, "segment": segment})
                for atom, dx, dy, dz, element in (
                    ("N", -1.0, 0, 0, "N"),
                    ("CA", 0, 0, 0, "C"),
                    ("C", 1.0, 0, 0, "C"),
                    ("O", 1.7, 0, 0, "O"),
                    ("CB", 0, 1.5, 0.3, "C"),
                ):
                    rows.append(
                        f"ATOM  {serial:5d} {atom:^4s} {residue} A{residue_id:4d}    "
                        f"{px + dx:8.3f}{py + dy:8.3f}{z + dz:8.3f}  "
                        f"1.00 20.00          {element:>2s}"
                    )
                    serial += 1
    context = {
        "target_auth_chain": "A",
        "target_kind": "gpcr",
        "structural_state": "active-like hypothesis, not established",
        "state_source": (
            "synthetic regression annotation; no independent biological state evidence"
        ),
        "topology_source": "synthetic seven-helix coordinate fixture",
        "topology": topology,
        "features": [
            {
                "kind": "glycan",
                "label_seq_ids": glycan_labels,
                "description": "Supplied candidate glycosylation region; occupancy not observed",
                "source": "synthetic annotation for limitation testing",
            }
        ],
        "limitations": [
            ("Synthetic geometry tests tool semantics, not native GPCR topology or binding.")
        ],
    }
    return "\n".join(rows) + "\nTER\nEND\n", context


def configure_offline_validation(monkeypatch, tmp_path):
    """Only the backend process is mocked; original compiler and validation service still run."""
    import subprocess

    from easydesign.backends.boltzgen.check import BoltzGenCheckAdapter
    from easydesign.core import dump_model
    from easydesign.orchestration.profile import BoltzGenRuntime, RuntimeBackends, RuntimeProfile
    from easydesign.stages.s03_boltzgen_configuration.models import (
        BOLTZGEN_COMMIT,
        BOLTZGEN_VERSION,
    )
    from easydesign.workspace_context import WorkspaceContext

    context = WorkspaceContext.discover()
    local = context.runtime_root / "offline-validator"
    local.mkdir()
    profile = RuntimeProfile(
        profile_id="offline-compiler-test",
        runs_root=context.runs_root,
        backends=RuntimeBackends(
            boltzgen_validation=BoltzGenRuntime(
                executable=local / "boltzgen",
                repository_root=local / "source",
                cache_root=local / "cache",
            )
        ),
    )
    revision = context.profile_path.with_name(context.profile_path.name + ".revisions")
    dump_model(profile, revision / "revision-000001.yaml")
    calls = []
    monkeypatch.setattr(
        BoltzGenCheckAdapter,
        "probe",
        lambda self: {
            "version": BOLTZGEN_VERSION,
            "commit": BOLTZGEN_COMMIT,
        },
    )

    def run(self, argv, *, cwd=None):
        calls.append((argv, cwd))
        assert argv[1] == "check"
        assert (cwd / argv[2]).is_file()
        return subprocess.CompletedProcess(
            argv, 0, stdout="OFFLINE MOCK: no backend execution", stderr=""
        )

    monkeypatch.setattr(BoltzGenCheckAdapter, "_run", run)
    return calls


def configure_live_validation():
    """Use the real installed BoltzGen interpreter with isolated source/cache/profile paths."""
    import json
    import os
    import shutil
    from pathlib import Path

    from easydesign.backends.boltzgen.check import BoltzGenCheckAdapter
    from easydesign.core import dump_model
    from easydesign.orchestration.profile import BoltzGenRuntime, RuntimeBackends, RuntimeProfile
    from easydesign.workspace_context import WorkspaceContext

    path = os.environ.get("EASYDESIGN_AGENT_BOLTZGEN_RUNTIME")
    assert path, (
        "Provide a JSON file naming executable, repository_root and "
        "cache_root for a real BoltzGen installation"
    )
    supplied = json.loads(Path(path).read_text())
    adapter = BoltzGenCheckAdapter(
        executable=Path(supplied["executable"]),
        repository_root=Path(supplied["repository_root"]),
        cache_root=Path(supplied["cache_root"]),
        require_generation_assets=False,
    )
    from easydesign.agent.tools import scientific_environment

    with scientific_environment():
        adapter.probe()
    context = WorkspaceContext.discover()
    local = context.runtime_root / "live-boltzgen-validation"
    local.mkdir()
    executable = local / "boltzgen"
    # Byte-identical console entry point retains its real installed interpreter.
    # No model or validator is mocked; all writable check/cache output is fixture-local.
    shutil.copy2(adapter.executable, executable)
    source = local / "source"
    shutil.copytree(adapter.repository_root, source)
    cache = local / "cache"
    molecule_source = adapter.artifact_paths().molecule_dataset
    molecule = cache / molecule_source.relative_to(adapter.cache_root)
    molecule.parent.mkdir(parents=True)
    try:
        os.link(molecule_source, molecule)
    except OSError:
        shutil.copy2(molecule_source, molecule)
    runtime = BoltzGenRuntime(
        executable=executable,
        repository_root=source,
        cache_root=cache,
        timeout_seconds=300,
        validation_workers=2,
        offline_mode=True,
    )
    profile = RuntimeProfile(
        profile_id="real-boltzgen-validation",
        runs_root=context.runs_root,
        backends=RuntimeBackends(boltzgen_validation=runtime),
    )
    revision = context.profile_path.with_name(context.profile_path.name + ".revisions")
    dump_model(profile, revision / "revision-000001.yaml")
    return {
        "backend": "boltzgen",
        "version": "0.3.2",
        "mocked": False,
        "generation_assets_required": False,
        "cache_isolated": True,
    }
