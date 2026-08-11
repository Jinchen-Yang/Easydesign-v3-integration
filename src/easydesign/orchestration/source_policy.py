"""Transport-source policy independent from pinned runtime identities."""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import signal
import ssl
import subprocess
import time
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from typing import Literal
from urllib.parse import urlparse
from uuid import uuid4

import httpx
import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

from easydesign.core import ConfigurationError, sha256_file
from easydesign.workspace_context import WorkspaceContext

SourcePolicy = Literal["auto", "official", "china"]
SourceRegion = Literal["official", "china"]
SOURCE_POLICIES: tuple[SourcePolicy, ...] = ("auto", "official", "china")
SYSTEM_CA_BUNDLE = Path("/etc/ssl/certs/ca-certificates.crt")
PYTHON_HTTP_CONNECT_TIMEOUT_SECONDS = 15.0
PYTHON_HTTP_READ_TIMEOUT_SECONDS = 30.0
SEGMENTED_DOWNLOAD_MIN_BYTES = 32 * 1024 * 1024
SEGMENTED_DOWNLOAD_PARTS = 4
SEGMENT_LOW_SPEED_WINDOW_SECONDS = 30.0
SEGMENT_LOW_SPEED_BYTES_PER_SECOND = 128 * 1024
_HOST_LATENCY_CACHE: dict[tuple[str, str], float | None] = {}
_CONTENT_RANGE = re.compile(r"^bytes (?P<start>\d+)-(?P<end>\d+)/(?P<total>\d+)$")


def validate_https_url(value: str, *, label: str = "下载源") -> str:
    """Accept only secret-free HTTPS transport endpoints."""

    normalized = value.rstrip("/")
    parsed = urlparse(normalized)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ConfigurationError(
            f"{label}必须是无凭据、无 query/fragment 的 HTTPS URL"
        )
    return normalized


class SourceCandidate(BaseModel):
    """One transport candidate; it does not define artifact identity."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_id: str
    region: SourceRegion
    url: str

    @field_validator("url")
    @classmethod
    def _safe_url(cls, value: str) -> str:
        return validate_https_url(value)


class SourceRewrite(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source_id: str
    region: SourceRegion
    canonical_prefix: str
    transport_prefix: str

    @field_validator("canonical_prefix", "transport_prefix")
    @classmethod
    def _safe_prefix(cls, value: str) -> str:
        return validate_https_url(value)


class RuntimeSourceCatalog(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["0.1"] = "0.1"
    miniforge: tuple[SourceCandidate, ...]
    pip_indexes: tuple[SourceCandidate, ...]
    conda_rewrites: tuple[SourceRewrite, ...] = ()
    asset_rewrites: tuple[SourceRewrite, ...] = ()


class SourceSelection(BaseModel):
    """Auditable transport actually selected for an immutable identity."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_id: str
    url: str


class VerifiedDownload(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    path: Path
    source: SourceSelection
    sha256: str
    size_bytes: int


@dataclass(frozen=True)
class _DownloadSegment:
    start: int
    end: int
    path: Path

    @property
    def expected_size(self) -> int:
        return self.end - self.start + 1


def load_runtime_sources(context: WorkspaceContext) -> RuntimeSourceCatalog:
    path = context.root / "config" / "runtime-sources.yaml"
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        return RuntimeSourceCatalog.model_validate(raw)
    except (OSError, yaml.YAMLError, ValidationError) as error:
        raise ConfigurationError(f"运行时下载源配置无法读取: {path}") from error


def _ssl_verify() -> ssl.SSLContext | bool:
    if SYSTEM_CA_BUNDLE.is_file():
        return ssl.create_default_context(cafile=str(SYSTEM_CA_BUNDLE))
    return True


def _eligible_candidates(
    candidates: Iterable[SourceCandidate],
    policy: SourcePolicy,
) -> tuple[tuple[SourceCandidate, ...], ...]:
    values = tuple(candidates)
    official = tuple(item for item in values if item.region == "official")
    china = tuple(item for item in values if item.region == "china")
    if policy == "official":
        return (official,)
    if policy == "china":
        return (china, official)
    return (values,)


def _probe_latency(candidate: SourceCandidate) -> float | None:
    parsed = urlparse(candidate.url)
    cache_key = (parsed.scheme, parsed.netloc)
    if cache_key in _HOST_LATENCY_CACHE:
        return _HOST_LATENCY_CACHE[cache_key]
    started = time.monotonic()
    try:
        with httpx.Client(
            follow_redirects=True,
            timeout=httpx.Timeout(8.0, connect=4.0),
            verify=_ssl_verify(),
            trust_env=True,
        ) as client:
            response = client.head(candidate.url)
            response.raise_for_status()
            if response.url.scheme != "https":
                raise ConfigurationError(
                    f"下载源 {candidate.source_id} 重定向到非 HTTPS 地址"
                )
    except (ConfigurationError, httpx.HTTPError, OSError):
        _HOST_LATENCY_CACHE[cache_key] = None
        return None
    latency = time.monotonic() - started
    _HOST_LATENCY_CACHE[cache_key] = latency
    return latency


def rank_source_candidates(
    candidates: Iterable[SourceCandidate],
    policy: SourcePolicy,
) -> tuple[SourceCandidate, ...]:
    """Rank viable candidates, preserving an unprobed fallback tail."""

    groups = _eligible_candidates(candidates, policy)
    ranked: list[SourceCandidate] = []
    seen: set[tuple[str, str]] = set()
    for group in groups:
        probes = [(candidate, _probe_latency(candidate)) for candidate in group]
        reachable = sorted(
            (
                (candidate, latency)
                for candidate, latency in probes
                if latency is not None
            ),
            key=lambda item: item[1],
        )
        for candidate, _latency in reachable:
            key = (candidate.source_id, candidate.url)
            if key not in seen:
                ranked.append(candidate)
                seen.add(key)
        for candidate, latency in probes:
            key = (candidate.source_id, candidate.url)
            if latency is None and key not in seen:
                ranked.append(candidate)
                seen.add(key)
    if not ranked:
        raise ConfigurationError(f"下载源策略 {policy} 没有可用候选项")
    return tuple(ranked)


def canonical_candidate(url: str, *, source_id: str) -> SourceCandidate:
    return SourceCandidate(source_id=source_id, region="official", url=url)


def rewritten_candidates(
    canonical_url: str,
    *,
    source_id: str,
    rewrites: Iterable[SourceRewrite],
) -> tuple[SourceCandidate, ...]:
    candidates = [canonical_candidate(canonical_url, source_id=source_id)]
    for rewrite in rewrites:
        prefix = rewrite.canonical_prefix + "/"
        normalized_url = validate_https_url(canonical_url)
        if normalized_url.startswith(prefix):
            suffix = normalized_url[len(prefix) :]
            candidates.append(
                SourceCandidate(
                    source_id=rewrite.source_id,
                    region=rewrite.region,
                    url=f"{rewrite.transport_prefix}/{suffix}",
                )
            )
    return tuple(candidates)


def resolve_pip_index(
    context: WorkspaceContext,
    *,
    policy: SourcePolicy,
    explicit_url: str | None,
) -> SourceSelection:
    selected = pip_index_candidates(
        context,
        policy=policy,
        explicit_url=explicit_url,
    )[0]
    return SourceSelection(source_id=selected.source_id, url=selected.url)


def pip_index_candidates(
    context: WorkspaceContext,
    *,
    policy: SourcePolicy,
    explicit_url: str | None,
) -> tuple[SourceCandidate, ...]:
    if explicit_url is not None:
        return (
            SourceCandidate(
                source_id="explicit-pip-index",
                region="official",
                url=validate_https_url(explicit_url, label="Pip index "),
            ),
        )
    catalog = load_runtime_sources(context)
    return rank_source_candidates(catalog.pip_indexes, policy)


def _quarantine_partial(
    context: WorkspaceContext,
    partial: Path,
    *,
    artifact_id: str,
    reason: str,
) -> None:
    if partial.exists():
        context.quarantine(
            partial,
            operation=f"download-{artifact_id}",
            reason=reason,
        )


def _quarantine_download_state(
    context: WorkspaceContext,
    partial: Path,
    *,
    artifact_id: str,
    reason: str,
) -> None:
    """Preserve every byte that contributed to an identity mismatch."""

    _quarantine_partial(
        context,
        partial,
        artifact_id=artifact_id,
        reason=reason,
    )
    segment_root = partial.with_name(f"{partial.name}.segments")
    if segment_root.exists():
        context.quarantine(
            segment_root,
            operation=f"download-{artifact_id}-segments",
            reason=reason,
        )


def _publish_verified_partial(
    context: WorkspaceContext,
    partial: Path,
    *,
    artifact_id: str,
    destination: Path,
    expected_sha256: str,
    expected_size_bytes: int | None,
    actual_size: int,
    source: SourceSelection,
) -> VerifiedDownload | None:
    """Verify immutable identity and atomically publish one completed partial."""

    if expected_size_bytes is not None and actual_size != expected_size_bytes:
        _quarantine_download_state(
            context,
            partial,
            artifact_id=artifact_id,
            reason=(
                "size mismatch: "
                f"expected={expected_size_bytes}, actual={actual_size}, "
                f"source={source.source_id}"
            ),
        )
        return None
    actual_sha256 = sha256_file(partial)
    if actual_sha256 != expected_sha256:
        _quarantine_download_state(
            context,
            partial,
            artifact_id=artifact_id,
            reason=(
                "SHA-256 mismatch: "
                f"expected={expected_sha256}, actual={actual_sha256}, "
                f"source={source.source_id}"
            ),
        )
        return None
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise ConfigurationError(f"下载发布目标已存在，拒绝覆盖: {destination}")
    partial.rename(destination)
    segment_root = partial.with_name(f"{partial.name}.segments")
    if segment_root.is_dir():
        shutil.rmtree(segment_root)
    return VerifiedDownload(
        path=destination,
        source=source,
        sha256=actual_sha256,
        size_bytes=actual_size,
    )


def _stream_candidate(
    candidate: SourceCandidate,
    partial: Path,
    *,
    expected_size_bytes: int | None,
    progress_callback: Callable[[int, int | None], None] | None,
) -> int:
    offset = partial.stat().st_size if partial.is_file() else 0
    headers = {"Range": f"bytes={offset}-"} if offset else {}
    with httpx.Client(
        follow_redirects=True,
        timeout=httpx.Timeout(
            PYTHON_HTTP_READ_TIMEOUT_SECONDS,
            connect=PYTHON_HTTP_CONNECT_TIMEOUT_SECONDS,
        ),
        verify=_ssl_verify(),
        trust_env=True,
    ) as client:
        with client.stream("GET", candidate.url, headers=headers) as response:
            if offset and response.status_code == 416 and expected_size_bytes == offset:
                return offset
            response.raise_for_status()
            if response.url.scheme != "https":
                raise ConfigurationError(
                    f"下载源 {candidate.source_id} 重定向到非 HTTPS 地址"
                )
            if offset and response.status_code != 206:
                raise ConfigurationError(
                    f"下载源 {candidate.source_id} 不支持安全断点续传"
                )
            response_size = response.headers.get("content-length")
            total_size = expected_size_bytes
            if total_size is None and response_size is not None:
                try:
                    total_size = offset + int(response_size)
                except ValueError:
                    total_size = None
            if progress_callback is not None:
                progress_callback(offset, total_size)
            mode = "ab" if offset else "xb"
            size = offset
            last_progress_at = time.monotonic()
            with partial.open(mode) as handle:
                for chunk in response.iter_bytes():
                    handle.write(chunk)
                    size += len(chunk)
                    now = time.monotonic()
                    if progress_callback is not None and now - last_progress_at >= 0.5:
                        progress_callback(size, total_size)
                        last_progress_at = now
            if progress_callback is not None:
                progress_callback(size, total_size)
            return size


def _segment_plan(
    partial: Path,
    *,
    expected_size_bytes: int,
    part_count: int = SEGMENTED_DOWNLOAD_PARTS,
) -> tuple[_DownloadSegment, ...]:
    """Build stable remaining-byte ranges beside the sequential partial."""

    offset = partial.stat().st_size if partial.is_file() else 0
    if offset > expected_size_bytes:
        raise ConfigurationError("下载 partial 大于锁定文件大小")
    remaining = expected_size_bytes - offset
    if remaining == 0:
        return ()
    count = min(max(part_count, 1), remaining)
    width = (remaining + count - 1) // count
    root = partial.with_name(f"{partial.name}.segments")
    root.mkdir(parents=False, exist_ok=True)
    segments: list[_DownloadSegment] = []
    start = offset
    while start < expected_size_bytes:
        end = min(start + width - 1, expected_size_bytes - 1)
        segments.append(
            _DownloadSegment(
                start=start,
                end=end,
                path=root / f"{start:020d}-{end:020d}.part",
            )
        )
        start = end + 1
    return tuple(segments)


def _download_range_segment(
    candidate: SourceCandidate,
    segment: _DownloadSegment,
    *,
    expected_size_bytes: int,
    stop_event: Event | None = None,
) -> None:
    """Resume one strict HTTPS byte range and reject non-Range responses."""

    existing = segment.path.stat().st_size if segment.path.is_file() else 0
    if existing > segment.expected_size:
        raise ConfigurationError(f"分段 partial 大于锁定范围: {segment.path.name}")
    if existing == segment.expected_size:
        return
    if stop_event is not None and stop_event.is_set():
        raise ConfigurationError("其他下载分段已经失败")
    request_start = segment.start + existing
    with httpx.Client(
        follow_redirects=True,
        timeout=httpx.Timeout(
            PYTHON_HTTP_READ_TIMEOUT_SECONDS,
            connect=PYTHON_HTTP_CONNECT_TIMEOUT_SECONDS,
        ),
        verify=_ssl_verify(),
        trust_env=True,
        http1=True,
        http2=False,
    ) as client:
        with client.stream(
            "GET",
            candidate.url,
            headers={"Range": f"bytes={request_start}-{segment.end}"},
        ) as response:
            response.raise_for_status()
            if response.url.scheme != "https":
                raise ConfigurationError(
                    f"下载源 {candidate.source_id} 重定向到非 HTTPS 地址"
                )
            if response.status_code != 206:
                raise ConfigurationError(
                    f"下载源 {candidate.source_id} 不支持严格 Range 下载"
                )
            content_range = response.headers.get("content-range", "")
            match = _CONTENT_RANGE.fullmatch(content_range)
            if (
                match is None
                or int(match.group("start")) != request_start
                or int(match.group("end")) != segment.end
                or int(match.group("total")) != expected_size_bytes
            ):
                raise ConfigurationError(
                    f"下载源 {candidate.source_id} 返回错误 Content-Range"
                )
            mode = "ab" if existing else "xb"
            window_started = time.monotonic()
            window_bytes = 0
            with segment.path.open(mode) as handle:
                for chunk in response.iter_bytes(chunk_size=256 * 1024):
                    if stop_event is not None and stop_event.is_set():
                        raise ConfigurationError("其他下载分段已经失败")
                    handle.write(chunk)
                    window_bytes += len(chunk)
                    if handle.tell() > segment.expected_size:
                        raise ConfigurationError(
                            f"下载源 {candidate.source_id} 返回超出锁定范围的字节"
                        )
                    elapsed = time.monotonic() - window_started
                    if elapsed >= SEGMENT_LOW_SPEED_WINDOW_SECONDS:
                        if (
                            window_bytes / elapsed
                            < SEGMENT_LOW_SPEED_BYTES_PER_SECOND
                        ):
                            raise ConfigurationError(
                                f"下载源 {candidate.source_id} 分段持续低速"
                            )
                        window_started = time.monotonic()
                        window_bytes = 0
                handle.flush()
                os.fsync(handle.fileno())
    actual = segment.path.stat().st_size
    if actual != segment.expected_size:
        raise ConfigurationError(
            f"下载源 {candidate.source_id} 分段大小不完整: "
            f"expected={segment.expected_size}, actual={actual}"
        )


def _assemble_segments(
    partial: Path,
    segments: tuple[_DownloadSegment, ...],
    *,
    expected_size_bytes: int,
) -> int:
    """Assemble beside the old partial, then atomically replace it."""

    assembly = partial.with_name(f"{partial.name}.assembling-{uuid4().hex}")
    try:
        with assembly.open("xb") as output:
            if partial.is_file():
                with partial.open("rb") as prefix:
                    shutil.copyfileobj(prefix, output)
            for segment in segments:
                if segment.path.stat().st_size != segment.expected_size:
                    raise ConfigurationError(
                        f"下载分段未完成: {segment.path.name}"
                    )
                with segment.path.open("rb") as source:
                    shutil.copyfileobj(source, output)
            output.flush()
            os.fsync(output.fileno())
        actual = assembly.stat().st_size
        if actual != expected_size_bytes:
            raise ConfigurationError(
                f"分段组装大小错误: expected={expected_size_bytes}, actual={actual}"
            )
        os.replace(assembly, partial)
    finally:
        assembly.unlink(missing_ok=True)
    segment_root = partial.with_name(f"{partial.name}.segments")
    if segment_root.is_dir():
        shutil.rmtree(segment_root)
    return expected_size_bytes


def _segmented_candidate(
    candidate: SourceCandidate,
    partial: Path,
    *,
    expected_size_bytes: int,
    progress_callback: Callable[[int, int | None], None] | None,
) -> int:
    """Fetch four resumable ranges concurrently, then atomically assemble."""

    segments = _segment_plan(
        partial,
        expected_size_bytes=expected_size_bytes,
    )
    if not segments:
        if progress_callback is not None:
            progress_callback(expected_size_bytes, expected_size_bytes)
        return expected_size_bytes
    prefix_size = partial.stat().st_size if partial.is_file() else 0
    stop_event = Event()
    failure: BaseException | None = None
    with ThreadPoolExecutor(
        max_workers=len(segments),
        thread_name_prefix="easydesign-download",
    ) as executor:
        futures = {
            executor.submit(
                _download_range_segment,
                candidate,
                segment,
                expected_size_bytes=expected_size_bytes,
                stop_event=stop_event,
            ): segment
            for segment in segments
        }
        pending = set(futures)
        while pending:
            done, pending = wait(pending, timeout=0.5)
            for future in done:
                exception = future.exception()
                if exception is not None and failure is None:
                    failure = exception
                    stop_event.set()
            completed = prefix_size + sum(
                min(
                    segment.path.stat().st_size if segment.path.is_file() else 0,
                    segment.expected_size,
                )
                for segment in segments
            )
            if progress_callback is not None:
                progress_callback(completed, expected_size_bytes)
            if failure is not None:
                for future in pending:
                    future.cancel()
                break
    if failure is not None:
        raise failure
    if progress_callback is not None:
        progress_callback(expected_size_bytes, expected_size_bytes)
    return _assemble_segments(
        partial,
        segments,
        expected_size_bytes=expected_size_bytes,
    )


def _curl_candidate(
    context: WorkspaceContext,
    candidate: SourceCandidate,
    partial: Path,
    *,
    expected_size_bytes: int | None,
    progress_callback: Callable[[int, int | None], None] | None,
) -> int:
    """Fallback to resumable curl HTTP/1.1 with bounded low-speed waits."""

    executable = shutil.which("curl")
    if executable is None:
        raise ConfigurationError("系统 curl 不可用")
    offset = partial.stat().st_size if partial.is_file() else 0
    if expected_size_bytes is not None and offset == expected_size_bytes:
        return offset
    command = [
        executable,
        "--silent",
        "--show-error",
        "--http1.1",
        "--location",
        "--fail",
        "--proto",
        "=https",
        "--proto-redir",
        "=https",
        "--connect-timeout",
        "15",
        "--speed-limit",
        "1024",
        "--speed-time",
        "30",
        "--max-time",
        "600",
        "--retry",
        "2",
        "--retry-delay",
        "2",
        "--retry-all-errors",
        "--continue-at",
        "-",
        "--output",
        str(partial),
        candidate.url,
    ]
    process = subprocess.Popen(
        command,
        cwd=context.root,
        env=context.subprocess_environment(),
        stdout=subprocess.DEVNULL,
        start_new_session=True,
    )
    started = time.monotonic()
    while process.poll() is None:
        size = partial.stat().st_size if partial.is_file() else 0
        if progress_callback is not None:
            progress_callback(size, expected_size_bytes)
        if time.monotonic() - started > 660:
            try:
                os.killpg(process.pid, signal.SIGTERM)
                process.wait(timeout=5)
            except (ProcessLookupError, subprocess.TimeoutExpired):
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()
            raise ConfigurationError(
                f"curl transport 超过硬超时: {candidate.source_id}"
            )
        time.sleep(0.5)
    size = partial.stat().st_size if partial.is_file() else 0
    if progress_callback is not None:
        progress_callback(size, expected_size_bytes)
    if process.returncode != 0:
        raise ConfigurationError(
            f"curl HTTP/1.1 返回 {process.returncode}: {candidate.source_id}"
        )
    return size


def download_verified_file(
    context: WorkspaceContext,
    *,
    artifact_id: str,
    candidates: Iterable[SourceCandidate],
    policy: SourcePolicy,
    destination: Path,
    expected_sha256: str,
    expected_size_bytes: int | None = None,
    progress_callback: Callable[[int, int | None], None] | None = None,
    source_callback: Callable[[SourceSelection], None] | None = None,
) -> VerifiedDownload:
    """Resume across equivalent sources and publish only verified bytes."""

    context.ensure_layout()
    context.assert_write_path(destination)
    if destination.exists():
        actual_sha256 = sha256_file(destination)
        actual_size = destination.stat().st_size
        if actual_sha256 != expected_sha256 or (
            expected_size_bytes is not None and actual_size != expected_size_bytes
        ):
            raise ConfigurationError(f"下载目标已存在但身份不匹配: {destination}")
        selection = SourceSelection(
            source_id="workspace-cache",
            url="workspace-cache://verified",
        )
        if source_callback is not None:
            source_callback(selection)
        if progress_callback is not None:
            progress_callback(actual_size, actual_size)
        return VerifiedDownload(
            path=destination,
            source=selection,
            sha256=actual_sha256,
            size_bytes=actual_size,
        )
    cache_root = context.runtime_root / "cache" / "downloads"
    cache_root.mkdir(parents=True, exist_ok=True)
    safe_id = hashlib.sha256(artifact_id.encode("utf-8")).hexdigest()[:16]
    partial = cache_root / f"{safe_id}-{expected_sha256[:16]}.part"
    context.assert_write_path(partial)
    ordered = rank_source_candidates(candidates, policy)
    failures: list[str] = []
    if (
        expected_size_bytes is not None
        and expected_size_bytes >= SEGMENTED_DOWNLOAD_MIN_BYTES
    ):
        for candidate in ordered:
            selection = SourceSelection(
                source_id=f"{candidate.source_id}-segmented-http1",
                url=candidate.url,
            )
            if source_callback is not None:
                source_callback(selection)
            try:
                size = _segmented_candidate(
                    candidate,
                    partial,
                    expected_size_bytes=expected_size_bytes,
                    progress_callback=progress_callback,
                )
            except (ConfigurationError, httpx.HTTPError, OSError) as error:
                failures.append(f"{selection.source_id}: {error}")
                continue
            verified = _publish_verified_partial(
                context,
                partial,
                artifact_id=artifact_id,
                destination=destination,
                expected_sha256=expected_sha256,
                expected_size_bytes=expected_size_bytes,
                actual_size=size,
                source=selection,
            )
            if verified is not None:
                return verified
            failures.append(f"{selection.source_id}: identity mismatch")
    for candidate in ordered:
        selected_source_id = candidate.source_id
        try:
            if source_callback is not None:
                source_callback(
                    SourceSelection(
                        source_id=candidate.source_id,
                        url=candidate.url,
                    )
                )
            size = _stream_candidate(
                candidate,
                partial,
                expected_size_bytes=expected_size_bytes,
                progress_callback=progress_callback,
            )
        except (ConfigurationError, httpx.HTTPError, OSError) as error:
            failures.append(f"{candidate.source_id}-python-http: {error}")
            selected_source_id = f"{candidate.source_id}-curl-http1"
            try:
                if source_callback is not None:
                    source_callback(
                        SourceSelection(
                            source_id=selected_source_id,
                            url=candidate.url,
                        )
                    )
                size = _curl_candidate(
                    context,
                    candidate,
                    partial,
                    expected_size_bytes=expected_size_bytes,
                    progress_callback=progress_callback,
                )
            except (ConfigurationError, OSError) as curl_error:
                failures.append(f"{selected_source_id}: {curl_error}")
                continue
        selection = SourceSelection(source_id=selected_source_id, url=candidate.url)
        verified = _publish_verified_partial(
            context,
            partial,
            artifact_id=artifact_id,
            destination=destination,
            expected_sha256=expected_sha256,
            expected_size_bytes=expected_size_bytes,
            actual_size=size,
            source=selection,
        )
        if verified is not None:
            return verified
        failures.append(f"{selected_source_id}: identity mismatch")
    detail = "; ".join(failures[-6:])
    raise ConfigurationError(f"所有候选下载源均失败: {artifact_id}; {detail}")
