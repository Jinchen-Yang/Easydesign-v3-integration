from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from easydesign.core import ConfigurationError
from easydesign.orchestration.afo_releases import (
    AfoReleaseCatalog,
    AfoReleaseEntry,
    load_afo_release_catalog,
    materialize_afo_bundle,
)
from easydesign.workspace_context import WorkspaceContext


def _workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> WorkspaceContext:
    (tmp_path / "easydesign-workspace.yaml").write_text(
        '\n'.join(
            (
                'schema_version: "0.1"',
                "workspace_id: afo-catalog-test",
                "runtime_root: runtime",
                "projects_root: workspace/projects",
                "runs_root: workspace/runs",
                "archives_root: workspace/archives",
                "",
            )
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("EASYDESIGN_WORKSPACE", str(tmp_path))
    return WorkspaceContext.discover()


def test_committed_314_release_is_candidate_and_not_installable_yet(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _workspace(tmp_path, monkeypatch)
    source = Path(__file__).resolve().parents[3] / "config/afo-releases.yaml"
    (tmp_path / "config").mkdir()
    (tmp_path / "config/afo-releases.yaml").write_bytes(source.read_bytes())

    catalog = load_afo_release_catalog(context)
    release = catalog.resolve(release_id="afo-3-1-4-of3-p2-155k")

    assert release.channel == "candidate"
    assert release.backend_version == "3.1.4"
    assert release.runner_commit == "bc32b22ff5902e3daffd5d1f7203d7f2ab6cb997"
    with pytest.raises(ConfigurationError, match="尚未发布"):
        materialize_afo_bundle(release, context=context)
    with pytest.raises(ConfigurationError, match="无唯一可用 release"):
        catalog.resolve(channel="stable")


def test_stable_release_requires_bundle_panel_and_human_approval() -> None:
    with pytest.raises(ValidationError, match="批准 receipt"):
        AfoReleaseEntry(
            release_id="afo-3-1-4-of3-p2-155k",
            channel="stable",
            backend_version="3.1.4",
            runner_commit="1" * 40,
            wheel_sha256="2" * 64,
            raw_checkpoint_sha256="3" * 64,
        )


def test_catalog_rejects_two_stable_releases() -> None:
    artifact = {
        "sha256": "4" * 64,
        "size_bytes": 1,
        "sources": [
            {
                "source_id": "official",
                "url": "https://example.invalid/afo.tar.zst",
                "region": "official",
            }
        ],
    }
    common = {
        "channel": "stable",
        "backend_version": "3.1.4",
        "runner_commit": "1" * 40,
        "wheel_sha256": "2" * 64,
        "raw_checkpoint_sha256": "3" * 64,
        "bundle": artifact,
        "validation_report_sha256": "5" * 64,
        "approval_receipt_sha256": "6" * 64,
    }
    with pytest.raises(ValidationError, match="一个 stable"):
        AfoReleaseCatalog(
            releases=(
                AfoReleaseEntry(release_id="afo-one", **common),
                AfoReleaseEntry(release_id="afo-two", **common),
            )
        )
