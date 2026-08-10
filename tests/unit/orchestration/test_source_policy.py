from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
import yaml

from easydesign.core import ConfigurationError
from easydesign.orchestration import source_policy
from easydesign.orchestration.source_policy import (
    SourceCandidate,
    download_verified_file,
    rank_source_candidates,
)
from easydesign.workspace_context import WorkspaceContext


def _workspace(tmp_path: Path) -> WorkspaceContext:
    (tmp_path / "easydesign-workspace.yaml").write_text(
        yaml.safe_dump(
            {
                "schema_version": "0.1",
                "workspace_id": "source-policy-test",
                "runtime_root": "runtime",
                "projects_root": "projects",
                "runs_root": "runs",
                "archives_root": "archives",
            }
        ),
        encoding="utf-8",
    )
    return WorkspaceContext.from_root(tmp_path)


def _candidates() -> tuple[SourceCandidate, ...]:
    return (
        SourceCandidate(
            source_id="official",
            region="official",
            url="https://official.example.test/file",
        ),
        SourceCandidate(
            source_id="china-fast",
            region="china",
            url="https://fast.example.test/file",
        ),
        SourceCandidate(
            source_id="china-slow",
            region="china",
            url="https://slow.example.test/file",
        ),
    )


def test_source_policy_separates_strict_official_and_china_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    latency = {"official": 0.05, "china-fast": 0.1, "china-slow": 0.3}
    monkeypatch.setattr(
        source_policy,
        "_probe_latency",
        lambda candidate: latency[candidate.source_id],
    )

    assert [item.source_id for item in rank_source_candidates(_candidates(), "official")] == [
        "official"
    ]
    assert [item.source_id for item in rank_source_candidates(_candidates(), "china")] == [
        "china-fast",
        "china-slow",
        "official",
    ]
    assert [item.source_id for item in rank_source_candidates(_candidates(), "auto")] == [
        "official",
        "china-fast",
        "china-slow",
    ]


def test_verified_download_resumes_partial_across_equivalent_sources(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _workspace(tmp_path)
    payload = b"locked-artifact-bytes"
    expected_sha256 = hashlib.sha256(payload).hexdigest()
    candidates = _candidates()[:2]
    calls: list[str] = []

    monkeypatch.setattr(
        source_policy,
        "rank_source_candidates",
        lambda values, _policy: tuple(values),
    )

    def fake_stream(
        candidate: SourceCandidate,
        partial: Path,
        **_kwargs: object,
    ) -> int:
        calls.append(candidate.source_id)
        if candidate.source_id == "official":
            partial.write_bytes(payload[:8])
            raise OSError("connection interrupted")
        assert partial.read_bytes() == payload[:8]
        with partial.open("ab") as handle:
            handle.write(payload[8:])
        return len(payload)

    monkeypatch.setattr(source_policy, "_stream_candidate", fake_stream)
    destination = context.runtime_root / "models" / "fixture.bin"

    result = download_verified_file(
        context,
        artifact_id="fixture",
        candidates=candidates,
        policy="auto",
        destination=destination,
        expected_sha256=expected_sha256,
        expected_size_bytes=len(payload),
    )

    assert calls == ["official", "china-fast"]
    assert result.path.read_bytes() == payload
    assert result.source.source_id == "china-fast"
    assert not tuple((context.runtime_root / "cache" / "downloads").glob("*.part"))


def test_verified_download_quarantines_wrong_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _workspace(tmp_path)
    candidate = _candidates()[0]
    monkeypatch.setattr(
        source_policy,
        "rank_source_candidates",
        lambda values, _policy: tuple(values),
    )

    def fake_stream(
        _candidate: SourceCandidate,
        partial: Path,
        **_kwargs: object,
    ) -> int:
        partial.write_bytes(b"wrong")
        return 5

    monkeypatch.setattr(source_policy, "_stream_candidate", fake_stream)

    with pytest.raises(ConfigurationError, match="所有候选下载源均失败"):
        download_verified_file(
            context,
            artifact_id="fixture",
            candidates=(candidate,),
            policy="official",
            destination=context.runtime_root / "models" / "fixture.bin",
            expected_sha256="0" * 64,
            expected_size_bytes=5,
        )

    metadata = tuple(context.runtime_root.glob("quarantine/*/quarantine.yaml"))
    assert len(metadata) == 1
    assert "SHA-256 mismatch" in metadata[0].read_text(encoding="utf-8")
