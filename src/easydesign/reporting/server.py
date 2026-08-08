"""只绑定 localhost、只暴露单个自包含报告目录的静态服务。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit

from pydantic import BaseModel

from easydesign.core import RunManifest, load_model
from easydesign.safe_writes import read_last_text_line

from .evidence_viewer import EvidenceViewerPayload
from .target_viewer import (
    TargetViewerReportError,
    resolve_latest_target_viewer_report,
    verify_target_viewer_report,
)

HOST = "127.0.0.1"
CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-eval'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob:; "
    "font-src 'self' data:; "
    "connect-src 'self'; "
    "worker-src 'self' blob:; "
    "object-src 'none'; "
    "base-uri 'none'; "
    "form-action 'none'; "
    "frame-ancestors 'none'"
)


class _TargetViewerRequestHandler(SimpleHTTPRequestHandler):
    server_version = "EasyDesignTargetViewer/0.1"

    def __init__(
        self,
        *args: object,
        directory: str,
        stage02_overlay: bytes | None = None,
        evidence_overlay: bytes | None = None,
        evidence_files: dict[str, Path] | None = None,
        **kwargs: object,
    ) -> None:
        self._report_root = Path(directory).resolve()
        self._stage02_overlay = stage02_overlay
        self._evidence_overlay = evidence_overlay
        self._evidence_files = evidence_files or {}
        super().__init__(*args, directory=directory, **kwargs)  # type: ignore[arg-type]

    def do_GET(self) -> None:  # noqa: N802
        request_path = unquote(urlsplit(self.path).path)
        if request_path == "/stage02-regions.json":
            if self._stage02_overlay is None:
                self.send_error(404, "Stage 02 overlay unavailable")
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(self._stage02_overlay)))
            self.end_headers()
            self.wfile.write(self._stage02_overlay)
            return
        if request_path == "/evidence.json":
            if self._evidence_overlay is None:
                self.send_error(404, "Evidence overlay unavailable")
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(self._evidence_overlay)))
            self.end_headers()
            self.wfile.write(self._evidence_overlay)
            return
        evidence = self._evidence_files.get(request_path)
        if evidence is not None:
            content = evidence.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "chemical/x-mmcif")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return
        super().do_GET()

    def translate_path(self, path: str) -> str:
        decoded = unquote(urlsplit(path).path)
        relative = PurePosixPath(decoded.lstrip("/"))
        if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
            return str(self._report_root / ".blocked-request")
        candidate = self._report_root.joinpath(*relative.parts)
        try:
            resolved = candidate.resolve()
            resolved.relative_to(self._report_root)
        except (OSError, ValueError):
            return str(self._report_root / ".blocked-request")
        current = candidate
        while current != self._report_root:
            if current.is_symlink():
                return str(self._report_root / ".blocked-request")
            current = current.parent
        return str(resolved)

    def end_headers(self) -> None:
        self.send_header("Content-Security-Policy", CSP)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


@dataclass(slots=True)
class TargetViewerHttpServer:
    report_root: Path
    server: ThreadingHTTPServer

    @property
    def url(self) -> str:
        port = self.server.server_address[1]
        return f"http://{HOST}:{port}/"

    def serve_forever(self) -> None:
        self.server.serve_forever()

    def close(self) -> None:
        self.server.server_close()


def resolve_target_viewer_argument(path: Path) -> Path:
    """Resolve a report directly or through an identical Stage 01 lineage."""

    resolved = path.resolve()
    if (resolved / "report-manifest.json").is_file():
        verify_target_viewer_report(resolved)
        return resolved
    try:
        return resolve_latest_target_viewer_report(resolved)
    except TargetViewerReportError as direct_error:
        try:
            manifest_name = read_last_text_line(resolved / "manifests/LATEST")
            run = load_model(resolved / "manifests" / manifest_name, RunManifest)
            stage01 = next(
                item
                for item in run.stage_manifest_refs
                if item.producer_stage == "01-target-preparation"
            )
        except (OSError, StopIteration, ValueError):
            raise direct_error from None
        matches: list[Path] = []
        for sibling in sorted(resolved.parent.iterdir()):
            if sibling == resolved or not (sibling / "manifests/LATEST").is_file():
                continue
            try:
                sibling_name = read_last_text_line(sibling / "manifests/LATEST")
                sibling_run = load_model(
                    sibling / "manifests" / sibling_name,
                    RunManifest,
                )
                sibling_stage01 = next(
                    item
                    for item in sibling_run.stage_manifest_refs
                    if item.producer_stage == "01-target-preparation"
                )
                if (
                    sibling_run.project_id == run.project_id
                    and sibling_stage01.sha256 == stage01.sha256
                ):
                    matches.append(resolve_latest_target_viewer_report(sibling))
            except (OSError, StopIteration, TargetViewerReportError, ValueError):
                continue
        unique = {item.resolve() for item in matches}
        if len(unique) != 1:
            raise TargetViewerReportError(
                "当前 run 没有自带 Target Viewer，且无法唯一解析相同 Stage 01 lineage"
            ) from direct_error
        return unique.pop()


def create_target_viewer_server(
    report_root: Path,
    *,
    port: int = 0,
    stage02_overlay: BaseModel | None = None,
    evidence: EvidenceViewerPayload | None = None,
) -> TargetViewerHttpServer:
    """验证报告并创建固定绑定 127.0.0.1 的 HTTP server。"""

    if isinstance(port, bool) or port < 0 or port > 65535:
        raise TargetViewerReportError(f"HTTP port 必须在 0..65535: {port}")
    root = report_root.resolve()
    verify_target_viewer_report(root)
    overlay_bytes = (
        None
        if stage02_overlay is None
        else (
            json.dumps(
                stage02_overlay.model_dump(mode="json"),
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
        )
    )
    evidence_bytes = (
        None
        if evidence is None
        else json.dumps(
            evidence.overlay.model_dump(mode="json"),
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
    )
    evidence_files = {} if evidence is None else dict(evidence.files)
    if evidence is not None:
        expected = {item.structure_url for item in evidence.overlay.structures}
        if set(evidence_files) != expected:
            raise TargetViewerReportError("evidence overlay 与文件路由不一致")
        for path in evidence_files.values():
            if not path.is_file() or path.is_symlink():
                raise TargetViewerReportError(f"evidence structure 非普通文件: {path}")
    handler = partial(
        _TargetViewerRequestHandler,
        directory=str(root),
        stage02_overlay=overlay_bytes,
        evidence_overlay=evidence_bytes,
        evidence_files=evidence_files,
    )
    server = ThreadingHTTPServer((HOST, port), handler)
    return TargetViewerHttpServer(report_root=root, server=server)
