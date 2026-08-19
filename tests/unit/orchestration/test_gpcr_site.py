from __future__ import annotations

from pathlib import Path

import pytest

from easydesign.orchestration.gpcr_site import (
    AnalysisWorkflowError,
    GpcrSiteRequest,
    build_gpcr_site_analysis,
)


def _write_structure(path: Path) -> Path:
    path.write_text(
        """\
ATOM      1  N   ALA A   1       0.000   0.000   0.000  1.00 20.00           N
ATOM      2  CA  ALA A   1       1.450   0.000   0.000  1.00 20.00           C
ATOM      3  C   ALA A   1       2.050   1.400   0.000  1.00 20.00           C
ATOM      4  O   ALA A   1       1.400   2.400   0.000  1.00 20.00           O
ATOM      5  N   GLY A   2       3.300   1.450   0.000  1.00 20.00           N
ATOM      6  CA  GLY A   2       4.000   2.700   0.000  1.00 20.00           C
ATOM      7  C   GLY A   2       5.500   2.500   0.000  1.00 20.00           C
ATOM      8  O   GLY A   2       6.100   1.450   0.000  1.00 20.00           O
ATOM      9  N   SER A   3       6.100   3.600   0.000  1.00 20.00           N
ATOM     10  CA  SER A   3       7.500   3.600   0.000  1.00 20.00           C
ATOM     11  C   SER A   3       8.000   5.000   0.000  1.00 20.00           C
ATOM     12  O   SER A   3       7.300   5.950   0.000  1.00 20.00           O
TER
END
""",
        encoding="utf-8",
    )
    return path


def test_gpcr_orchestration_allows_explicit_geometry_only_dossier(
    tmp_path: Path,
) -> None:
    structure = _write_structure(tmp_path / "receptor.pdb")

    analysis = build_gpcr_site_analysis(
        GpcrSiteRequest(
            evidence_dir=tmp_path / "evidence",
            structure=structure,
            gpcr_entry="adrb2_human",
            receptor_chain="A",
            cache_mode="offline",
            cache_root=tmp_path / "empty-cache",
        )
    )

    assert analysis.structure["sha256"]
    assert analysis.structure["receptor_chain"] == "A"
    assert analysis.identity["entry_name"] == "adrb2_human"
    assert analysis.membrane["status"] == "unresolved"
    assert any(
        isinstance(item, dict)
        and item.get("code") == "gpcrdb_unavailable_geometry_only"
        for item in analysis.warnings
    )
    assert all(
        candidate.classification != "primary"
        for candidate in (*analysis.candidates.inhibit, *analysis.candidates.activate)
    )


def test_gpcr_orchestration_requires_explicit_identity_for_local_filename(
    tmp_path: Path,
) -> None:
    structure = _write_structure(tmp_path / "receptor.pdb")

    with pytest.raises(AnalysisWorkflowError, match="gpcr_entry/accession"):
        build_gpcr_site_analysis(
            GpcrSiteRequest(
                evidence_dir=tmp_path / "evidence",
                structure=structure,
                receptor_chain="A",
                cache_mode="offline",
                cache_root=tmp_path / "empty-cache",
            )
        )
