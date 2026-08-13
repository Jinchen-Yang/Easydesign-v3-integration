from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from easydesign.orchestration import afo_releases
from easydesign.orchestration.afo_releases import (
    AfoReleaseCatalog,
    AfoReleaseEntry,
    install_stable_afo_if_available,
    load_afo_release_catalog,
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


def test_committed_314_release_is_approved_stable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _workspace(tmp_path, monkeypatch)
    source = Path(__file__).resolve().parents[3] / "config/afo-releases.yaml"
    (tmp_path / "config").mkdir()
    (tmp_path / "config/afo-releases.yaml").write_bytes(source.read_bytes())

    catalog = load_afo_release_catalog(context)
    release = catalog.resolve(release_id="afo-3-1-4-of3-p2-155k")

    assert release.channel == "stable"
    assert release.backend_version == "3.1.4"
    assert release.runner_commit == "bc32b22ff5902e3daffd5d1f7203d7f2ab6cb997"
    assert release.bundle is not None
    assert release.bundle.sha256 == (
        "83b6d8e895090a0c74d21e495d50b75a7cb031389386f5b7cd9843b6d3501afd"
    )
    assert release.bundle.size_bytes == 5_032_471_381
    assert release.bundle.archive_format == "tar.zst"
    assert release.bundle.sources[0].url == (
        "https://huggingface.co/knitua/Easydesign-afo/resolve/"
        "5d03182f5487c5392236b4fb096875b6f660d902/releases/"
        "afo-3-1-4-of3-p2-155k/afo-3-1-4-of3-p2-155k.tar.zst"
    )
    assert release.validation_report_sha256 == (
        "b645065c5614c95071143c5b44df051b0ea59bc2a3e180abc916f87e69370423"
    )
    assert release.approval_receipt_sha256 == (
        "03cab2913fe97058ee865157cee2d3a7aae88d522d247fecad64716c50c89f8c"
    )
    assert catalog.resolve(channel="stable") == release


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


def test_stable_helper_materializes_installs_and_activates_for_all_jobs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _workspace(tmp_path, monkeypatch)
    release = AfoReleaseEntry(
        release_id="afo-3-1-4-of3-p2-155k",
        channel="stable",
        backend_version="3.1.4",
        runner_commit="1" * 40,
        wheel_sha256="2" * 64,
        raw_checkpoint_sha256="3" * 64,
        bundle={
            "sha256": "4" * 64,
            "size_bytes": 1,
            "sources": [
                {
                    "source_id": "official",
                    "url": "https://example.invalid/afo.tar.zst",
                    "region": "official",
                }
            ],
        },
        validation_report_sha256="5" * 64,
        approval_receipt_sha256="6" * 64,
    )
    bundle = tmp_path / "materialized-bundle"
    sentinel = object()
    install_calls: list[tuple[Path, bool, WorkspaceContext]] = []
    monkeypatch.setattr(
        afo_releases,
        "load_afo_release_catalog",
        lambda _context: AfoReleaseCatalog(releases=(release,)),
    )
    monkeypatch.setattr(
        afo_releases,
        "materialize_afo_bundle",
        lambda *_args, **_kwargs: bundle,
    )

    def fake_install(
        path: Path,
        *,
        activate: bool,
        context: WorkspaceContext,
    ) -> object:
        install_calls.append((path, activate, context))
        return sentinel

    monkeypatch.setattr(afo_releases, "install_openfold3_component", fake_install)

    result = install_stable_afo_if_available(context=context)

    assert result is sentinel
    assert install_calls == [(bundle, True, context)]
