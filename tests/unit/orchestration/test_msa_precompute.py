from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from easydesign.core import (
    MsaLibraryEntry,
    MsaLibraryManifest,
    MsaLibraryProducer,
    MsaLibrarySource,
    MsaReleaseReceipt,
    dump_model,
    sha256_file,
)
from easydesign.orchestration.msa_precompute import (
    MsaArtifactError,
    resolve_explicit_a3m,
    resolve_library_entry,
    snapshot_msa_artifact,
    validate_library_release,
)
from easydesign.workspace_context import WorkspaceContext, WorkspaceDeclaration


def _context(tmp_path: Path) -> WorkspaceContext:
    declaration_path = tmp_path / "easydesign-workspace.yaml"
    declaration_path.write_text('schema_version: "0.1"\n', encoding="utf-8")
    context = WorkspaceContext(
        root=tmp_path,
        declaration_path=declaration_path,
        declaration=WorkspaceDeclaration(),
    )
    context.ensure_layout()
    return context


def _a3m(path: Path, sequence: str = "ACDE") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f">query\n{sequence}\n>homolog\nAC-E\n", encoding="utf-8")
    return path


def _release(context: WorkspaceContext, sequence: str = "ACDE") -> tuple[str, Path]:
    release_id = "gpcr-msa-test-v1"
    sequence_sha256 = hashlib.sha256(sequence.encode("ascii")).hexdigest()
    root = context.runtime_root / "databases/gpcr-msa" / release_id
    a3m = _a3m(root / "entries" / f"{sequence_sha256}.a3m", sequence)
    manifest = MsaLibraryManifest(
        release_id=release_id,
        created_at=datetime(2026, 9, 4, tzinfo=UTC),
        producer=MsaLibraryProducer(
            name="gpcr-msa-release-builder",
            version="1.0",
        ),
        source=MsaLibrarySource(
            kind="stockholm-archive",
            label="gpcr-source.tar.gz",
            sha256="a" * 64,
            size_bytes=123,
        ),
        entries=(
            MsaLibraryEntry(
                canonical_sequence_sha256=sequence_sha256,
                a3m_path=f"entries/{sequence_sha256}.a3m",
                a3m_sha256=sha256_file(a3m),
                a3m_size_bytes=a3m.stat().st_size,
                depth=2,
                query_name="query",
                accessions=("P00001",),
                source_member="msa_results/P00001.sto",
                source_member_sha256="b" * 64,
            ),
        ),
    )
    manifest_path = dump_model(manifest, root / "library-manifest.json")
    dump_model(
        MsaReleaseReceipt(
            release_id=release_id,
            created_at=manifest.created_at,
            library_manifest_sha256=sha256_file(manifest_path),
            entry_count=1,
        ),
        root / "release-receipt.json",
    )
    return release_id, a3m


def test_resolves_new_library_by_canonical_sequence_sha_and_snapshots_receipt(
    tmp_path: Path,
) -> None:
    context = _context(tmp_path)
    release_id, source = _release(context)

    artifact = resolve_library_entry(
        context=context,
        release_id=release_id,
        canonical_sequence="ACDE",
    )
    snapshot = snapshot_msa_artifact(
        context=context,
        artifact=artifact,
        destination_parent=context.projects_root / "project-one/inputs/msa-selections",
    )

    assert artifact.source_path == source
    assert artifact.receipt.release_id == release_id
    assert artifact.receipt.query_match == "exact"
    assert artifact.receipt.paired_msa == "empty"
    assert snapshot.a3m_path.read_bytes() == source.read_bytes()
    receipt = json.loads(snapshot.receipt_path.read_text(encoding="utf-8"))
    assert receipt["type"] == "precomputed-library"
    assert receipt["fallback_policy"] == "fail-closed"
    assert snapshot_msa_artifact(
        context=context,
        artifact=artifact,
        destination_parent=context.projects_root / "project-one/inputs/msa-selections",
    ) == snapshot


def test_library_resolution_fails_closed_on_sequence_or_release_receipt_mismatch(
    tmp_path: Path,
) -> None:
    context = _context(tmp_path)
    release_id, _source = _release(context)

    with pytest.raises(MsaArtifactError, match="唯一匹配"):
        resolve_library_entry(
            context=context,
            release_id=release_id,
            canonical_sequence="AAAA",
        )

    receipt_path = (
        context.runtime_root
        / "databases/gpcr-msa"
        / release_id
        / "release-receipt.json"
    )
    payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    payload["library_manifest_sha256"] = "0" * 64
    receipt_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(MsaArtifactError, match="未绑定"):
        validate_library_release(context=context, release_id=release_id)


def test_explicit_a3m_records_file_provenance_without_fake_release(
    tmp_path: Path,
) -> None:
    source = _a3m(tmp_path / "target.a3m")

    artifact = resolve_explicit_a3m(source=source, canonical_sequence="ACDE")

    assert artifact.receipt.source_type == "precomputed-file"
    assert artifact.receipt.source_name == "target.a3m"
    assert artifact.receipt.release_id is None
    assert artifact.receipt.release_receipt_sha256 is None


def test_legacy_source_library_is_read_only_compatible_but_not_promoted(
    tmp_path: Path,
) -> None:
    context = _context(tmp_path)
    release_id = "gpcr-msa-source-test-v3"
    root = context.runtime_root / "databases" / release_id
    a3m = _a3m(root / "a3m/P00001.a3m")
    sequence_sha256 = hashlib.sha256(b"ACDE").hexdigest()
    (root / "library-manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "0.2",
                "status": "ready",
                "entries": [
                    {
                        "status": "converted",
                        "accession": "P00001",
                        "query_sequence_sha256": sequence_sha256,
                        "a3m_path": "a3m/P00001.a3m",
                        "a3m_sha256": sha256_file(a3m),
                        "a3m_size_bytes": a3m.stat().st_size,
                        "depth": 2,
                    }
                ],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    artifact = resolve_library_entry(
        context=context,
        release_id=release_id,
        canonical_sequence="ACDE",
    )

    assert artifact.receipt.library_schema_version == "0.2"
    assert artifact.receipt.release_receipt_sha256 is None
    assert artifact.receipt.library_entry_path == "a3m/P00001.a3m"
