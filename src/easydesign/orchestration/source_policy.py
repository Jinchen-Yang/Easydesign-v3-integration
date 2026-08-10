"""Transport-source policy independent from pinned runtime identities."""

from __future__ import annotations

import hashlib
import ssl
import time
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

import httpx
import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

from easydesign.core import ConfigurationError, sha256_file
from easydesign.workspace_context import WorkspaceContext

SourcePolicy = Literal["auto", "official", "china"]
SourceRegion = Literal["official", "china"]
SOURCE_POLICIES: tuple[SourcePolicy, ...] = ("auto", "official", "china")
SYSTEM_CA_BUNDLE = Path("/etc/ssl/certs/ca-certificates.crt")
_HOST_LATENCY_CACHE: dict[tuple[str, str], float | None] = {}


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
        timeout=httpx.Timeout(1800.0, connect=30.0),
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
        return VerifiedDownload(
            path=destination,
            source=SourceSelection(
                source_id="workspace-cache",
                url="workspace-cache://verified",
            ),
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
    for candidate in ordered:
        try:
            size = _stream_candidate(
                candidate,
                partial,
                expected_size_bytes=expected_size_bytes,
                progress_callback=progress_callback,
            )
        except (ConfigurationError, httpx.HTTPError, OSError) as error:
            failures.append(f"{candidate.source_id}: {error}")
            continue
        actual_sha256 = sha256_file(partial)
        if expected_size_bytes is not None and size != expected_size_bytes:
            _quarantine_partial(
                context,
                partial,
                artifact_id=artifact_id,
                reason=(
                    "size mismatch: "
                    f"expected={expected_size_bytes}, actual={size}, "
                    f"source={candidate.source_id}"
                ),
            )
            failures.append(f"{candidate.source_id}: size mismatch")
            continue
        if actual_sha256 != expected_sha256:
            _quarantine_partial(
                context,
                partial,
                artifact_id=artifact_id,
                reason=(
                    "SHA-256 mismatch: "
                    f"expected={expected_sha256}, actual={actual_sha256}, "
                    f"source={candidate.source_id}"
                ),
            )
            failures.append(f"{candidate.source_id}: SHA-256 mismatch")
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            raise ConfigurationError(f"下载发布目标已存在，拒绝覆盖: {destination}")
        partial.rename(destination)
        return VerifiedDownload(
            path=destination,
            source=SourceSelection(source_id=candidate.source_id, url=candidate.url),
            sha256=actual_sha256,
            size_bytes=size,
        )
    detail = "; ".join(failures[-6:])
    raise ConfigurationError(f"所有候选下载源均失败: {artifact_id}; {detail}")
