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
    load_runtime_sources,
    rank_source_candidates,
    rewritten_candidates,
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
    selected_sources: list[str] = []

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
    monkeypatch.setattr(
        source_policy,
        "_curl_candidate",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ConfigurationError("curl unavailable")
        ),
    )
    destination = context.runtime_root / "models" / "fixture.bin"

    result = download_verified_file(
        context,
        artifact_id="fixture",
        candidates=candidates,
        policy="auto",
        destination=destination,
        expected_sha256=expected_sha256,
        expected_size_bytes=len(payload),
        source_callback=lambda selection: selected_sources.append(
            selection.source_id
        ),
    )

    assert calls == ["official", "china-fast"]
    assert selected_sources == [
        "official",
        "official-curl-http1",
        "china-fast",
    ]
    assert result.path.read_bytes() == payload
    assert result.source.source_id == "china-fast"
    assert not tuple((context.runtime_root / "cache" / "downloads").glob("*.part"))


def test_verified_download_falls_back_to_curl_http1_on_same_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _workspace(tmp_path)
    payload = b"locked-artifact-bytes"
    expected_sha256 = hashlib.sha256(payload).hexdigest()
    candidate = _candidates()[0]
    selected_sources: list[str] = []
    monkeypatch.setattr(
        source_policy,
        "rank_source_candidates",
        lambda values, _policy: tuple(values),
    )

    def failed_python_http(
        _candidate: SourceCandidate,
        partial: Path,
        **_kwargs: object,
    ) -> int:
        partial.write_bytes(payload[:8])
        raise OSError("python HTTP stalled")

    def successful_curl(
        _context: WorkspaceContext,
        _candidate: SourceCandidate,
        partial: Path,
        **_kwargs: object,
    ) -> int:
        assert partial.read_bytes() == payload[:8]
        with partial.open("ab") as handle:
            handle.write(payload[8:])
        return len(payload)

    monkeypatch.setattr(source_policy, "_stream_candidate", failed_python_http)
    monkeypatch.setattr(source_policy, "_curl_candidate", successful_curl)

    result = download_verified_file(
        context,
        artifact_id="fixture-curl",
        candidates=(candidate,),
        policy="auto",
        destination=context.runtime_root / "models" / "fixture-curl.bin",
        expected_sha256=expected_sha256,
        expected_size_bytes=len(payload),
        source_callback=lambda selection: selected_sources.append(
            selection.source_id
        ),
    )

    assert result.path.read_bytes() == payload
    assert result.source.source_id == "official-curl-http1"
    assert selected_sources == ["official", "official-curl-http1"]


def test_segmented_download_reuses_prefix_and_publishes_only_verified_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _workspace(tmp_path)
    context.ensure_layout()
    payload = b"0123456789abcdefghijklmnopqrstuvwxyz"
    expected_sha256 = hashlib.sha256(payload).hexdigest()
    artifact_id = "segmented-fixture"
    safe_id = hashlib.sha256(artifact_id.encode("utf-8")).hexdigest()[:16]
    partial = (
        context.runtime_root
        / "cache"
        / "downloads"
        / f"{safe_id}-{expected_sha256[:16]}.part"
    )
    partial.parent.mkdir(parents=True)
    partial.write_bytes(payload[:8])
    monkeypatch.setattr(source_policy, "SEGMENTED_DOWNLOAD_MIN_BYTES", 1)
    monkeypatch.setattr(
        source_policy,
        "rank_source_candidates",
        lambda values, _policy: tuple(values),
    )
    starts: list[int] = []

    def fake_range(
        _candidate: SourceCandidate,
        segment: source_policy._DownloadSegment,
        **_kwargs: object,
    ) -> None:
        starts.append(segment.start)
        segment.path.write_bytes(payload[segment.start : segment.end + 1])

    monkeypatch.setattr(source_policy, "_download_range_segment", fake_range)
    selected_sources: list[str] = []
    result = download_verified_file(
        context,
        artifact_id=artifact_id,
        candidates=(_candidates()[0],),
        policy="official",
        destination=context.runtime_root / "models" / "segmented.bin",
        expected_sha256=expected_sha256,
        expected_size_bytes=len(payload),
        source_callback=lambda selection: selected_sources.append(
            selection.source_id
        ),
    )

    assert min(starts) == 8
    assert result.path.read_bytes() == payload
    assert result.source.source_id == "official-segmented-http1"
    assert selected_sources == ["official-segmented-http1"]
    assert not partial.exists()
    assert not partial.with_name(f"{partial.name}.segments").exists()


def test_segmented_download_preserves_chunks_while_switching_sources(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _workspace(tmp_path)
    payload = b"segmented-equivalent-source-payload"
    expected_sha256 = hashlib.sha256(payload).hexdigest()
    calls: list[str] = []
    monkeypatch.setattr(source_policy, "SEGMENTED_DOWNLOAD_MIN_BYTES", 1)
    monkeypatch.setattr(
        source_policy,
        "rank_source_candidates",
        lambda values, _policy: tuple(values),
    )

    def fake_segmented(
        candidate: SourceCandidate,
        partial: Path,
        **_kwargs: object,
    ) -> int:
        calls.append(candidate.source_id)
        if candidate.source_id == "official":
            segment_root = partial.with_name(f"{partial.name}.segments")
            segment_root.mkdir(parents=True)
            (segment_root / "000.part").write_bytes(payload[:8])
            raise ConfigurationError("sustained low speed")
        assert (
            partial.with_name(f"{partial.name}.segments") / "000.part"
        ).read_bytes()
        partial.write_bytes(payload)
        return len(payload)

    monkeypatch.setattr(source_policy, "_segmented_candidate", fake_segmented)
    result = download_verified_file(
        context,
        artifact_id="segmented-fallback",
        candidates=_candidates()[:2],
        policy="auto",
        destination=context.runtime_root / "models" / "fallback.bin",
        expected_sha256=expected_sha256,
        expected_size_bytes=len(payload),
    )

    assert calls == ["official", "china-fast"]
    assert result.source.source_id == "china-fast-segmented-http1"
    assert result.path.read_bytes() == payload


def test_python_http_uses_bounded_stall_timeout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class FailingClient:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)

        def __enter__(self) -> FailingClient:
            raise OSError("connection stalled")

        def __exit__(self, *_args: object) -> None:
            return None

    monkeypatch.setattr(source_policy.httpx, "Client", FailingClient)

    with pytest.raises(OSError, match="connection stalled"):
        source_policy._stream_candidate(
            _candidates()[0],
            tmp_path / "partial",
            expected_size_bytes=100,
            progress_callback=None,
        )

    timeout = captured["timeout"]
    assert isinstance(timeout, source_policy.httpx.Timeout)
    assert timeout.connect == source_policy.PYTHON_HTTP_CONNECT_TIMEOUT_SECONDS
    assert timeout.read == source_policy.PYTHON_HTTP_READ_TIMEOUT_SECONDS


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


def test_runtime_sources_rewrite_nvidia_packages_to_sustech() -> None:
    repository = Path(__file__).resolve().parents[3]
    context = WorkspaceContext.from_root(repository)
    catalog = load_runtime_sources(context)
    canonical = (
        "https://conda.anaconda.org/nvidia/linux-64/"
        "libcublas-12.6.4.1-0.conda"
    )

    candidates = rewritten_candidates(
        canonical,
        source_id="official-conda",
        rewrites=catalog.conda_rewrites,
    )

    sustech = next(
        candidate
        for candidate in candidates
        if candidate.source_id == "sustech-nvidia"
    )
    assert sustech.region == "china"
    assert sustech.url == (
        "https://mirrors.sustech.edu.cn/anaconda-extra/cloud/nvidia/"
        "linux-64/libcublas-12.6.4.1-0.conda"
    )


def test_protenix_identity_uses_official_url_and_mirror_only_as_transport() -> None:
    repository = Path(__file__).resolve().parents[3]
    context = WorkspaceContext.from_root(repository)
    assets = yaml.safe_load(
        (repository / "config" / "runtime-assets.yaml").read_text(encoding="utf-8")
    )["assets"]
    checkpoint = next(
        asset
        for asset in assets
        if asset["asset_id"] == "protenix-v2-checkpoint"
    )

    assert checkpoint["source"].startswith("https://huggingface.co/")
    candidates = rewritten_candidates(
        checkpoint["source"],
        source_id="official-asset",
        rewrites=load_runtime_sources(context).asset_rewrites,
    )

    assert candidates[0].source_id == "official-asset"
    assert candidates[0].region == "official"
    mirror = next(item for item in candidates if item.source_id == "hf-mirror")
    assert mirror.region == "china"
    assert mirror.url.startswith("https://hf-mirror.com/")
