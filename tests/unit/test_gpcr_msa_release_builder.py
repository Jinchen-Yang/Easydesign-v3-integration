from __future__ import annotations

import hashlib
import io
import json
import tarfile
from pathlib import Path

from scripts.maintainers.gpcr_msa_release_builder import build_stockholm_library


def test_builder_publishes_canonical_sequence_keyed_release(tmp_path: Path) -> None:
    sequence = "ACDE"
    accession = "P12345"
    stockholm = b"# STOCKHOLM 1.0\nP12345 ACDE\nhit AC-E\n//\n"
    source = tmp_path / "source.tar.gz"
    with tarfile.open(source, mode="w:gz") as archive:
        info = tarfile.TarInfo(f"msa_results/{accession}.sto")
        info.size = len(stockholm)
        archive.addfile(info, io.BytesIO(stockholm))
    targets = tmp_path / "targets"
    targets.mkdir()
    (targets / f"{accession}.fasta").write_text(
        f">{accession}\n{sequence}\n",
        encoding="utf-8",
    )
    release_id = "gpcr-msa-test-v1"
    output = tmp_path / release_id

    result = build_stockholm_library(
        source=source,
        targets=targets,
        output_root=output,
        release_id=release_id,
    )

    sequence_sha256 = hashlib.sha256(sequence.encode("ascii")).hexdigest()
    entry = result["entries"][0]
    assert entry["canonical_sequence_sha256"] == sequence_sha256
    assert entry["a3m_path"] == f"entries/{sequence_sha256}.a3m"
    assert (output / entry["a3m_path"]).read_text(encoding="utf-8").startswith(
        ">P12345\nACDE\n"
    )
    manifest = json.loads(
        (output / "library-manifest.json").read_text(encoding="utf-8")
    )
    receipt = json.loads((output / "release-receipt.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "1.0"
    assert receipt["release_id"] == release_id
    assert receipt["entry_count"] == 1
