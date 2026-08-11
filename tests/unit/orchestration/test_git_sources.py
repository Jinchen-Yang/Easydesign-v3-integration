from __future__ import annotations

import hashlib
import io
import shutil
import tarfile
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from easydesign.core import ConfigurationError
from easydesign.orchestration import git_sources
from easydesign.orchestration.git_sources import (
    GitArchiveLock,
    GitSourceResult,
    materialize_git_source,
    verify_existing_git_source,
    verify_git_source_identity,
)
from easydesign.orchestration.source_policy import (
    SourceCandidate,
    SourceSelection,
    VerifiedDownload,
)
from easydesign.workspace_context import WorkspaceContext


def _workspace(tmp_path: Path) -> WorkspaceContext:
    (tmp_path / "easydesign-workspace.yaml").write_text(
        yaml.safe_dump(
            {
                "schema_version": "0.1",
                "workspace_id": "git-source-test",
                "runtime_root": "runtime",
                "projects_root": "projects",
                "runs_root": "runs",
                "archives_root": "archives",
            }
        ),
        encoding="utf-8",
    )
    return WorkspaceContext.from_root(tmp_path)


def _archive(tmp_path: Path) -> Path:
    source = tmp_path / "archive-input" / "fixture-abc123"
    source.mkdir(parents=True)
    (source / "pyproject.toml").write_text(
        "[project]\nname = 'fixture'\nversion = '1.0'\n",
        encoding="utf-8",
    )
    archive = tmp_path / "fixture.tar.gz"
    with tarfile.open(archive, mode="w:gz") as handle:
        handle.add(source, arcname=source.name)
    return archive


def test_archive_materialization_is_verified_and_reused(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _workspace(tmp_path)
    archive = _archive(tmp_path)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    candidate = SourceCandidate(
        source_id="fixture-archive",
        region="official",
        url="https://example.test/fixture.tar.gz",
    )
    lock = GitArchiveLock(
        sha256=digest,
        expected_size_bytes=archive.stat().st_size,
        sources=(candidate,),
    )
    calls = 0

    def fake_download(
        _context: WorkspaceContext,
        **kwargs: object,
    ) -> VerifiedDownload:
        nonlocal calls
        calls += 1
        destination = kwargs["destination"]
        assert isinstance(destination, Path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(archive, destination)
        selection = SourceSelection(source_id=candidate.source_id, url=candidate.url)
        source_callback = kwargs["source_callback"]
        assert callable(source_callback)
        source_callback(selection)
        return VerifiedDownload(
            path=destination,
            source=selection,
            sha256=digest,
            size_bytes=archive.stat().st_size,
        )

    monkeypatch.setattr(git_sources, "download_verified_file", fake_download)
    destination = context.runtime_root / "models" / "fixture/source"
    statuses: list[str] = []

    first = materialize_git_source(
        context,
        asset_id="fixture-source",
        source="https://example.test/fixture.git",
        revision="a" * 40,
        archive_lock=lock,
        destination=destination,
        source_policy="auto",
        status_callback=statuses.append,
    )
    second = materialize_git_source(
        context,
        asset_id="fixture-source",
        source="https://example.test/fixture.git",
        revision="a" * 40,
        archive_lock=lock,
        destination=destination,
        source_policy="auto",
    )

    assert calls == 1
    assert first.content_sha256 == second.content_sha256
    assert (destination / "pyproject.toml").is_file()
    assert (destination / git_sources.SOURCE_RECEIPT_NAME).is_file()
    assert "fixture-archive" in statuses[-1]
    (destination / "pyproject.toml").write_text("changed\n", encoding="utf-8")
    with pytest.raises(ConfigurationError, match="receipt 与现有内容不一致"):
        verify_existing_git_source(
            context,
            source="https://example.test/fixture.git",
            revision="a" * 40,
            destination=destination,
        )


def test_archive_failure_switches_to_git_transport(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _workspace(tmp_path)
    lock = GitArchiveLock(
        sha256="a" * 64,
        expected_size_bytes=10,
        sources=(
            SourceCandidate(
                source_id="fixture-archive",
                region="official",
                url="https://example.test/fixture.tar.gz",
            ),
        ),
    )
    destination = context.runtime_root / "models" / "fixture/source"
    statuses: list[str] = []
    expected = GitSourceResult(
        path=destination,
        revision="b" * 40,
        content_sha256="c" * 64,
        size_bytes=100,
        source=SourceSelection(
            source_id="official-git-http1",
            url="https://example.test/fixture.git",
        ),
    )
    monkeypatch.setattr(
        git_sources,
        "_publish_archive_source",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("archive down")),
    )
    monkeypatch.setattr(
        git_sources,
        "_publish_git_source",
        lambda *_args, **_kwargs: expected,
    )

    result = materialize_git_source(
        context,
        asset_id="fixture-source",
        source="https://example.test/fixture.git",
        revision="b" * 40,
        archive_lock=lock,
        destination=destination,
        source_policy="auto",
        status_callback=statuses.append,
    )

    assert result == expected
    assert "自动切换 Git transport" in statuses[-1]


def test_source_without_receipt_cannot_discover_parent_git_checkout(
    tmp_path: Path,
) -> None:
    parent = tmp_path / "parent-checkout"
    source = parent / "runtime" / "models" / "source"
    source.mkdir(parents=True)
    (parent / ".git").mkdir()
    (source / "model.py").write_text("VERSION = 'fixed'\n", encoding="utf-8")

    with pytest.raises(ConfigurationError, match="自身 .git"):
        verify_git_source_identity(
            source,
            source="https://example.test/source.git",
            revision="a" * 40,
        )


def test_git_transport_tries_http1_before_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _workspace(tmp_path)
    destination = context.runtime_root / "models" / "fixture/source"
    revision = "d" * 40
    fetches: list[tuple[str, ...]] = []

    def fake_fetch(
        command: list[str],
        **_kwargs: object,
    ) -> int:
        fetches.append(tuple(command))
        if len(fetches) == 1:
            return 1
        staging = Path(command[command.index("-C") + 1])
        (staging / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
        return 0

    def fake_run(command: list[str], **_kwargs: object) -> SimpleNamespace:
        if command[:3] == ["git", "init", "--quiet"]:
            Path(command[-1]).mkdir(parents=True)
            return SimpleNamespace(returncode=0)
        if command[-2:] == ["rev-parse", "HEAD"]:
            return SimpleNamespace(returncode=0, stdout=revision + "\n")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(git_sources, "_git_fetch", fake_fetch)
    monkeypatch.setattr(git_sources.subprocess, "run", fake_run)
    monkeypatch.setattr(
        git_sources,
        "load_runtime_sources",
        lambda _context: SimpleNamespace(asset_rewrites=()),
    )
    monkeypatch.setattr(
        git_sources,
        "rank_source_candidates",
        lambda candidates, _policy: tuple(candidates),
    )

    result = git_sources._publish_git_source(
        context,
        asset_id="fixture-source",
        source="https://example.test/fixture.git",
        revision=revision,
        destination=destination,
        source_policy="auto",
        status_callback=None,
    )

    assert "http.version=HTTP/1.1" in fetches[0]
    assert not any("http.version=" in item for item in fetches[1])
    assert result.revision == revision


def test_archive_rejects_link_entries(
    tmp_path: Path,
) -> None:
    archive = tmp_path / "unsafe.tar.gz"
    with tarfile.open(archive, mode="w:gz") as handle:
        directory = tarfile.TarInfo("fixture-root/")
        directory.type = tarfile.DIRTYPE
        handle.addfile(directory)
        link = tarfile.TarInfo("fixture-root/outside")
        link.type = tarfile.SYMTYPE
        link.linkname = "../../outside"
        handle.addfile(link, io.BytesIO())

    with pytest.raises(ConfigurationError, match="不允许的链接"):
        git_sources._safe_extract_archive(archive, tmp_path / "extracted")
