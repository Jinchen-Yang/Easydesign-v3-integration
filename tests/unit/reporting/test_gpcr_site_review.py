from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from easydesign.reporting.gpcr_site_review import (
    generate_review_report,
    resolve_latest_review_report,
    validate_review_report,
)


def test_report_is_generated_from_packaged_assets(tmp_path: Path) -> None:
    input_root = tmp_path / "input"
    input_root.mkdir()
    structure = input_root / "target.pdb"
    structure.write_text(
        "ATOM      1  CA  ALA A   1       0.000   0.000   0.000  1.00 20.00           C\n"
        "END\n",
        encoding="ascii",
    )
    analysis = input_root / "gpcr-hotspot-analysis.json"
    analysis.write_text(
        json.dumps(
            {
                "identity": {
                    "structure_id": "adrb2-inactive",
                    "entry": "adrb2_human",
                    "family": "class-a",
                    "state": "inactive",
                },
                "structure": {"path": structure.name},
                "topology": {"residues": []},
                "candidates": {"inhibit": [], "activate": []},
                "membrane": {"status": "unresolved"},
            }
        ),
        encoding="utf-8",
    )

    output = tmp_path / "review"
    outcome = generate_review_report(
        analysis,
        output,
        repository_root=tmp_path / "intentionally-absent-checkout",
        generated_at=datetime(2026, 8, 19, tzinfo=UTC),
    )

    assert outcome.structure_count == 1
    assert resolve_latest_review_report(output) == outcome.report_root
    manifest = validate_review_report(outcome.report_root)
    assert manifest["viewer"]["version"] == "5.11.0"
    assert manifest["entries"][0]["identity"]["entry"] == "adrb2_human"
    assert (outcome.report_root / "assets" / "molstar.js").is_file()
    assert (outcome.report_root / "structures" / "adrb2-inactive.html").is_file()
