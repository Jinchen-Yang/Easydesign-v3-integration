from datetime import date
from pathlib import Path

import pytest

from easydesign.core import ManifestStateError
from easydesign.orchestration.complex_prediction_support import (
    _template_ready_mmcif,
)


def test_template_ready_mmcif_preserves_comments_before_data_header(
    tmp_path: Path,
) -> None:
    source = tmp_path / "target.cif"
    source.write_text(
        "# output attribution\n"
        "# model terms\n"
        "data_target\n"
        "_entry.id target\n",
        encoding="utf-8",
    )

    rendered, release_date, source_kind = _template_ready_mmcif(source)

    assert rendered.startswith("# output attribution\n# model terms\ndata_target\n")
    assert (
        "data_target\n_pdbx_audit_revision_history.revision_date 1970-01-01\n"
        in rendered
    )
    assert release_date == date(1970, 1, 1)
    assert source_kind == "synthetic-conservative"


def test_template_ready_mmcif_rejects_invalid_mmcif(tmp_path: Path) -> None:
    source = tmp_path / "target.cif"
    source.write_text("# comments only\n_entry.id target\n", encoding="utf-8")

    with pytest.raises(ManifestStateError, match="无法读取|data_ header"):
        _template_ready_mmcif(source)
