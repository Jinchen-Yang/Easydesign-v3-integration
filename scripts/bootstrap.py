#!/usr/bin/env python3
"""Install the locked EasyDesign development environment through a measured index.

This file intentionally uses only the Python 3.10 standard library: it must run
before the repository virtual environment or EasyDesign itself exists.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "bootstrap-indexes.json"
LOCK_PATH = ROOT / "uv.lock"
PROJECT_PATH = ROOT / "pyproject.toml"
STATE_ROOT = ROOT / "runtime" / "state" / "bootstrap"
CACHE_ROOT = ROOT / "runtime" / "cache" / "uv"
TMP_ROOT = ROOT / "runtime" / "tmp"
VENV_PYTHON = ROOT / ".venv" / "bin" / "python"
VENV_ENTRYPOINT = ROOT / ".venv" / "bin" / "easydesign"
USER_AGENT = "EasyDesign-bootstrap/0.1"


class BootstrapError(RuntimeError):
    """Raised when a bootstrap safety or installation check fails."""


@dataclass(frozen=True)
class IndexSource:
    name: str
    display_name: str
    index_url: str


@dataclass(frozen=True)
class ProbeResult:
    name: str
    display_name: str
    index_url: str
    available: bool
    latency_ms: int | None
    artifact_bytes: int
    throughput_mib_s: float | None
    error: str | None


class _LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        if tag.lower() != "a":
            return
        href = dict(attrs).get("href")
        if href:
            self.links.append(href)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")  # noqa: UP017


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_index_url(value: str) -> str:
    parsed = urllib.parse.urlsplit(value.strip())
    if parsed.scheme != "https":
        raise BootstrapError("package index 必须使用 https")
    if not parsed.hostname or parsed.username or parsed.password:
        raise BootstrapError("package index URL 必须有主机且不能包含凭据")
    if parsed.query or parsed.fragment:
        raise BootstrapError("package index URL 不能包含 query 或 fragment")
    return urllib.parse.urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", "")
    )


def _load_config() -> tuple[dict[str, Any], tuple[IndexSource, ...]]:
    try:
        payload = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise BootstrapError(f"无法读取 bootstrap source 配置: {error}") from error
    if payload.get("schema_version") != "0.1":
        raise BootstrapError("bootstrap source 配置 schema 必须为 0.1")
    sources = tuple(
        IndexSource(
            name=str(item["name"]),
            display_name=str(item["display_name"]),
            index_url=_safe_index_url(str(item["index_url"])),
        )
        for item in payload.get("sources", [])
    )
    if not sources or len({source.name for source in sources}) != len(sources):
        raise BootstrapError("bootstrap source 配置必须包含唯一命名的 source")
    return payload, sources


def _validate_repository() -> None:
    if sys.version_info < (3, 10):  # noqa: UP036 -- bootstrap deliberately supports system 3.10
        raise BootstrapError("bootstrap 需要系统 Python 3.10 或更高版本")
    for path in (LOCK_PATH, PROJECT_PATH, CONFIG_PATH):
        if not path.is_file():
            raise BootstrapError(f"仓库文件缺失: {path.relative_to(ROOT)}")
    if not (ROOT / "easydesign-workspace.yaml").is_file():
        raise BootstrapError("请从 EasyDesign 仓库根目录运行 bootstrap")


def _find_uv() -> str:
    candidates = [shutil.which("uv"), str(Path.home() / ".local" / "bin" / "uv")]
    for candidate in candidates:
        if candidate and Path(candidate).is_file() and os.access(candidate, os.X_OK):
            return str(Path(candidate).resolve())
    raise BootstrapError(
        "未找到 uv；请先运行 curl -LsSf https://astral.sh/uv/install.sh | sh，"
        "然后重新执行 bootstrap"
    )


def _request(url: str, *, timeout: float, headers: dict[str, str] | None = None) -> Any:
    selected_headers = {"User-Agent": USER_AGENT, "Accept": "text/html,*/*"}
    if headers:
        selected_headers.update(headers)
    return urllib.request.urlopen(
        urllib.request.Request(url, headers=selected_headers), timeout=timeout
    )


def _fetch_bytes(
    url: str,
    *,
    timeout: float,
    byte_range: tuple[int, int] | None = None,
) -> bytes:
    curl = shutil.which("curl")
    if curl:
        command = [
            curl,
            "--fail",
            "--location",
            "--silent",
            "--show-error",
            "--proto",
            "=https",
            "--proto-redir",
            "=https",
            "--max-time",
            str(timeout),
            "--user-agent",
            USER_AGENT,
        ]
        if byte_range is not None:
            command.extend(["--range", f"{byte_range[0]}-{byte_range[1]}"])
        command.append(url)
        completed = subprocess.run(command, check=False, capture_output=True)
        if completed.returncode != 0:
            detail = completed.stderr.decode("utf-8", errors="replace").strip()
            raise BootstrapError(f"curl rc={completed.returncode}: {detail}")
        return completed.stdout
    headers = None
    if byte_range is not None:
        headers = {"Range": f"bytes={byte_range[0]}-{byte_range[1]}"}
    with _request(url, timeout=timeout, headers=headers) as response:
        maximum = 2 * 1024 * 1024 if byte_range is None else byte_range[1] - byte_range[0] + 1
        return response.read(maximum)


def _artifact_url(index_url: str, package: str, body: bytes) -> str:
    parser = _LinkParser()
    parser.feed(body.decode("utf-8", errors="replace"))
    links = [urllib.parse.urljoin(f"{index_url}/{package}/", link) for link in parser.links]
    wheels = [link for link in links if ".whl" in urllib.parse.urlsplit(link).path]
    preferred = [
        link
        for link in wheels
        if "manylinux" in link and "x86_64" in link and "cp311" in link
    ]
    candidates = preferred or wheels
    if not candidates:
        raise BootstrapError(f"{package} simple page 没有可探测 wheel")
    return urllib.parse.urldefrag(candidates[-1]).url


def probe_source(
    source: IndexSource,
    *,
    package: str,
    probe_bytes: int,
    timeout: float,
) -> ProbeResult:
    started = time.monotonic()
    try:
        page_url = f"{source.index_url}/{package}/"
        body = _fetch_bytes(page_url, timeout=timeout)
        latency = max(time.monotonic() - started, 0.000001)
        artifact_url = _artifact_url(source.index_url, package, body)
        artifact_started = time.monotonic()
        sample = _fetch_bytes(
            artifact_url, timeout=timeout, byte_range=(0, probe_bytes - 1)
        )[:probe_bytes]
        artifact_duration = max(time.monotonic() - artifact_started, 0.000001)
        if not sample:
            raise BootstrapError("representative artifact 返回空响应")
        return ProbeResult(
            name=source.name,
            display_name=source.display_name,
            index_url=source.index_url,
            available=True,
            latency_ms=round(latency * 1000),
            artifact_bytes=len(sample),
            throughput_mib_s=round(len(sample) / artifact_duration / 1024 / 1024, 3),
            error=None,
        )
    except (BootstrapError, OSError, TimeoutError, urllib.error.URLError) as error:
        return ProbeResult(
            name=source.name,
            display_name=source.display_name,
            index_url=source.index_url,
            available=False,
            latency_ms=None,
            artifact_bytes=0,
            throughput_mib_s=None,
            error=f"{type(error).__name__}: {error}"[:500],
        )


def rank_probes(probes: Sequence[ProbeResult]) -> list[ProbeResult]:
    available = [probe for probe in probes if probe.available]
    return sorted(
        available,
        key=lambda probe: (
            -(probe.throughput_mib_s or 0.0),
            probe.latency_ms if probe.latency_ms is not None else 10**9,
            probe.name,
        ),
    )


def _run(
    command: Sequence[str],
    *,
    environment: dict[str, str],
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    print(f"+ {' '.join(command)}", file=sys.stderr, flush=True)
    completed = subprocess.run(
        list(command),
        cwd=ROOT,
        env=environment,
        check=False,
        text=True,
    )
    if check and completed.returncode != 0:
        raise BootstrapError(
            f"命令失败 (rc={completed.returncode}): {' '.join(command)}"
        )
    return completed


def _capture(command: Sequence[str], *, environment: dict[str, str]) -> str:
    completed = subprocess.run(
        list(command),
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise BootstrapError(
            f"命令失败 (rc={completed.returncode}): {' '.join(command)}: "
            f"{completed.stderr.strip()}"
        )
    return completed.stdout.strip()


def _environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment.update(
        {
            "UV_CACHE_DIR": str(CACHE_ROOT),
            "PIP_CACHE_DIR": str(ROOT / "runtime" / "cache" / "pip"),
            "TMPDIR": str(TMP_ROOT),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPYCACHEPREFIX": str(ROOT / "runtime" / "cache" / "bootstrap-pycache"),
        }
    )
    return environment


def _ensure_venv(uv: str, environment: dict[str, str]) -> None:
    expected = (ROOT / ".python-version").read_text(encoding="utf-8").strip()
    if not VENV_PYTHON.is_file():
        _run([uv, "venv", "--python", expected, ".venv"], environment=environment)
    version = _capture(
        [
            str(VENV_PYTHON),
            "-c",
            "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')",
        ],
        environment=environment,
    )
    if version != expected:
        raise BootstrapError(
            f"现有 .venv Python={version}，但 .python-version={expected}；"
            "为避免覆盖请先人工检查该环境"
        )


def _git_head(environment: dict[str, str]) -> str | None:
    completed = subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "--show-toplevel", "HEAD"],
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    lines = completed.stdout.splitlines()
    if completed.returncode != 0 or len(lines) != 2:
        return None
    try:
        top_level = Path(lines[0]).resolve()
    except OSError:
        return None
    return lines[1] if top_level == ROOT.resolve() else None


def _write_receipt(payload: dict[str, Any]) -> Path:
    STATE_ROOT.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")  # noqa: UP017
    receipt = STATE_ROOT / f"bootstrap-{stamp}-{uuid.uuid4().hex[:12]}.json"
    encoded = (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
    descriptor = os.open(receipt, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())
    pointer_temp = STATE_ROOT / f".BOOTSTRAP_CURRENT.{uuid.uuid4().hex}.tmp"
    pointer_temp.write_text(f"{receipt.name}\n", encoding="utf-8")
    os.replace(pointer_temp, STATE_ROOT / "BOOTSTRAP_CURRENT")
    return receipt


def _print_probes(probes: Sequence[ProbeResult]) -> None:
    print("Package index probe:", file=sys.stderr)
    for probe in probes:
        if probe.available:
            print(
                f"  {probe.name:9} available latency={probe.latency_ms}ms "
                f"sample={probe.artifact_bytes}B throughput={probe.throughput_mib_s}MiB/s",
                file=sys.stderr,
            )
        else:
            print(f"  {probe.name:9} unavailable {probe.error}", file=sys.stderr)


def _probe_sources(
    config: dict[str, Any],
    sources: Sequence[IndexSource],
    *,
    timeout: float,
) -> list[ProbeResult]:
    probes = [
        probe_source(
            source,
            package=str(config["probe_package"]),
            probe_bytes=int(config["probe_bytes"]),
            timeout=timeout,
        )
        for source in sources
    ]
    _print_probes(probes)
    return probes


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Install the frozen EasyDesign environment from a measured package index."
    )
    group = result.add_mutually_exclusive_group()
    group.add_argument(
        "--index",
        default="auto",
        choices=("auto", "official", "aliyun", "tsinghua"),
        help="Named source or measured automatic selection (default: auto).",
    )
    group.add_argument("--index-url", help="Explicit HTTPS PEP 503 package index URL.")
    result.add_argument("--timeout", type=float, default=10.0, help="Probe timeout in seconds.")
    result.add_argument("--dry-run", action="store_true", help="Probe and plan without writing.")
    result.add_argument("--json", action="store_true", help="Print the result as JSON.")
    return result


def bootstrap(arguments: argparse.Namespace) -> dict[str, Any]:
    _validate_repository()
    if arguments.timeout <= 0:
        raise BootstrapError("--timeout 必须大于 0")
    config, configured_sources = _load_config()
    if arguments.index_url:
        requested = "custom"
        selected_sources = (
            IndexSource("custom", "Custom", _safe_index_url(arguments.index_url)),
        )
    else:
        requested = arguments.index
        selected_sources = (
            configured_sources
            if requested == "auto"
            else tuple(source for source in configured_sources if source.name == requested)
        )
    if not selected_sources:
        raise BootstrapError(f"未知 package index: {requested}")

    if arguments.dry_run:
        probes = _probe_sources(config, selected_sources, timeout=arguments.timeout)
        ranked = rank_probes(probes)
        if not ranked:
            raise BootstrapError("没有可用的 package index；未修改环境")
        return {
            "schema_version": "0.1",
            "status": "dry-run",
            "requested_source": requested,
            "selected_source": ranked[0].name,
            "probes": [asdict(probe) for probe in probes],
            "uv_lock_sha256": _sha256(LOCK_PATH),
            "would_write": False,
        }

    started = time.monotonic()
    started_at = _now()
    before = {"uv.lock": _sha256(LOCK_PATH), "pyproject.toml": _sha256(PROJECT_PATH)}
    receipt: dict[str, Any] = {
        "schema_version": "0.1",
        "status": "running",
        "started_at": started_at,
        "completed_at": None,
        "duration_seconds": None,
        "requested_source": requested,
        "selected_source": None,
        "selected_index_url": None,
        "probes": [],
        "install_attempts": [],
        "git_sha": None,
        "bootstrap_python": platform.python_version(),
        "uv_version": None,
        "input_sha256": before,
        "requirements_sha256": None,
        "verification": {},
        "error": None,
    }
    try:
        probes = _probe_sources(config, selected_sources, timeout=arguments.timeout)
        receipt["probes"] = [asdict(probe) for probe in probes]
        ranked = rank_probes(probes)
        if not ranked:
            raise BootstrapError("没有可用的 package index；未修改环境")
        if requested != "auto" and len(ranked) != 1:
            raise BootstrapError(
                f"显式 package index {requested} 不可用；不会静默 fallback"
            )
        environment = _environment()
        CACHE_ROOT.mkdir(parents=True, exist_ok=True)
        TMP_ROOT.mkdir(parents=True, exist_ok=True)
        uv = _find_uv()
        receipt["uv_version"] = _capture([uv, "--version"], environment=environment)
        receipt["git_sha"] = _git_head(environment)
        _ensure_venv(uv, environment)
        with tempfile.TemporaryDirectory(prefix="bootstrap-", dir=TMP_ROOT) as temp_value:
            requirements = Path(temp_value) / "dev-requirements.txt"
            _run(
                [
                    uv,
                    "export",
                    "--quiet",
                    "--frozen",
                    "--extra",
                    "dev",
                    "--no-emit-project",
                    "--format",
                    "requirements-txt",
                    "--output-file",
                    str(requirements),
                ],
                environment=environment,
            )
            receipt["requirements_sha256"] = _sha256(requirements)
            installed: ProbeResult | None = None
            for candidate in ranked:
                completed = _run(
                    [
                        uv,
                        "pip",
                        "sync",
                        "--python",
                        str(VENV_PYTHON),
                        "--require-hashes",
                        "--default-index",
                        candidate.index_url,
                        str(requirements),
                    ],
                    environment=environment,
                    check=False,
                )
                receipt["install_attempts"].append(
                    {"source": candidate.name, "returncode": completed.returncode}
                )
                if completed.returncode == 0:
                    installed = candidate
                    break
                if requested != "auto":
                    break
            if installed is None:
                raise BootstrapError("hash-locked dependency install failed")
            receipt["selected_source"] = installed.name
            receipt["selected_index_url"] = installed.index_url

        _run(
            [
                uv,
                "pip",
                "install",
                "--python",
                str(VENV_PYTHON),
                "--no-deps",
                "--no-build-isolation",
                "--editable",
                ".",
            ],
            environment=environment,
        )
        _run([uv, "sync", "--frozen", "--extra", "dev", "--check"], environment=environment)
        version = _capture([str(VENV_ENTRYPOINT), "--version"], environment=environment)
        after = {"uv.lock": _sha256(LOCK_PATH), "pyproject.toml": _sha256(PROJECT_PATH)}
        if after != before:
            raise BootstrapError("bootstrap 期间 uv.lock 或 pyproject.toml 发生变化")
        receipt["verification"] = {
            "uv_sync_check": "passed",
            "easydesign_version": version,
            "input_sha256_after": after,
        }
        receipt["status"] = "success"
    except KeyboardInterrupt:
        receipt["status"] = "interrupted"
        receipt["error"] = "KeyboardInterrupt"
        raise
    except Exception as error:
        receipt["status"] = "failed"
        receipt["error"] = f"{type(error).__name__}: {error}"[:1000]
        if isinstance(error, BootstrapError):
            raise
        raise BootstrapError(receipt["error"]) from error
    finally:
        receipt["completed_at"] = _now()
        receipt["duration_seconds"] = round(time.monotonic() - started, 3)
        receipt_path = _write_receipt(receipt)
        receipt["receipt"] = str(receipt_path.relative_to(ROOT))
        print(f"bootstrap receipt: {receipt['receipt']}", file=sys.stderr)
    return receipt


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    try:
        result = bootstrap(arguments)
    except KeyboardInterrupt:
        print("bootstrap interrupted; rerun the same command to resume safely", file=sys.stderr)
        return 130
    except BootstrapError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    if arguments.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"bootstrap status: {result['status']}")
        print(f"selected source: {result['selected_source']}")
        if result.get("receipt"):
            print(f"receipt: {result['receipt']}")
        if result["status"] == "success":
            print("next: source .venv/bin/activate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
