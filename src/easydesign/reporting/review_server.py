"""Loopback-only serving and portable export for review dashboards."""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from os import PathLike
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit

from easydesign.core import ArtifactRef, dump_model, load_model, sha256_file

from .review_dashboard import ReviewDashboardError, verify_review_dashboard
from .review_models import (
    ReviewDashboardExportManifest,
    ReviewDashboardReport,
    ReviewStructureRoute,
)

HOST = "127.0.0.1"
CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-eval'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob:; "
    "connect-src 'self'; "
    "font-src 'self'; "
    "worker-src 'self' blob:; "
    "object-src 'none'; "
    "base-uri 'none'; "
    "form-action 'none'; "
    "frame-ancestors 'none'"
)


def _has_symlink(path: Path, root: Path) -> bool:
    current = path
    while current != root:
        if current.is_symlink():
            return True
        current = current.parent
    return False


class _ReviewDashboardHandler(SimpleHTTPRequestHandler):
    server_version = "EasyDesignReviewDashboard/0.1"

    def __init__(
        self,
        *args: object,
        directory: str,
        run_root: Path,
        structures: dict[str, ReviewStructureRoute],
        **kwargs: object,
    ) -> None:
        self._report_root = Path(directory).resolve()
        self._run_root = run_root.resolve()
        self._structures = structures
        super().__init__(*args, directory=directory, **kwargs)  # type: ignore[arg-type]

    def _valid_host(self) -> bool:
        host = self.headers.get("Host", "")
        hostname = host.rsplit(":", 1)[0].strip("[]").lower()
        return hostname in {"127.0.0.1", "localhost", "::1"}

    def _serve_structure(self, route: ReviewStructureRoute) -> None:
        original = self._run_root / route.artifact.relative_path
        if _has_symlink(original, self._run_root):
            self.send_error(403, "Symlink structures are forbidden")
            return
        try:
            path = route.artifact.verify(self._run_root)
        except Exception:
            self.send_error(409, "Structure integrity verification failed")
            return
        size = route.artifact.size_bytes
        start, end = 0, size - 1
        status = 200
        range_header = self.headers.get("Range")
        if range_header:
            if not range_header.startswith("bytes=") or "," in range_header:
                self.send_error(416, "Only one byte range is supported")
                return
            value = range_header[6:]
            try:
                first, last = value.split("-", 1)
                if first:
                    start = int(first)
                    end = int(last) if last else end
                elif last:
                    length = int(last)
                    start = max(0, size - length)
                else:
                    raise ValueError
            except ValueError:
                self.send_error(416, "Invalid byte range")
                return
            if start < 0 or end < start or start >= size:
                self.send_error(416, "Byte range outside artifact")
                return
            end = min(end, size - 1)
            status = 206
        length = max(0, end - start + 1)
        self.send_response(status)
        self.send_header("Content-Type", route.mime_type)
        self.send_header("Content-Length", str(length))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("ETag", f'"sha256-{route.artifact.sha256}"')
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        if length:
            with path.open("rb") as handle:
                handle.seek(start)
                self.wfile.write(handle.read(length))

    def do_GET(self) -> None:  # noqa: N802
        if not self._valid_host():
            self.send_error(421, "Review dashboard only accepts localhost requests")
            return
        request_path = unquote(urlsplit(self.path).path)
        prefix = "/structures/"
        if request_path.startswith(prefix):
            token = request_path[len(prefix) :]
            if "/" in token or token not in self._structures:
                self.send_error(404, "Unknown structure route")
                return
            self._serve_structure(self._structures[token])
            return
        super().do_GET()

    def translate_path(self, path: str) -> str:
        decoded = unquote(urlsplit(path).path)
        relative = PurePosixPath(decoded.lstrip("/"))
        if relative.is_absolute() or any(
            part in {"", ".", ".."} for part in relative.parts
        ):
            return str(self._report_root / ".blocked-request")
        candidate = self._report_root.joinpath(*relative.parts)
        try:
            resolved = candidate.resolve()
            resolved.relative_to(self._report_root)
        except (OSError, ValueError):
            return str(self._report_root / ".blocked-request")
        if _has_symlink(candidate, self._report_root):
            return str(self._report_root / ".blocked-request")
        return str(resolved)

    def guess_type(self, path: str | PathLike[str]) -> str:
        suffix = Path(path).suffix.lower()
        return {
            ".html": "text/html; charset=utf-8",
            ".js": "text/javascript; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".json": "application/json; charset=utf-8",
            ".txt": "text/plain; charset=utf-8",
        }.get(suffix, "application/octet-stream")

    def end_headers(self) -> None:
        self.send_header("Content-Security-Policy", CSP)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


@dataclass(slots=True)
class ReviewDashboardHttpServer:
    report_root: Path
    server: ThreadingHTTPServer

    @property
    def url(self) -> str:
        return f"http://{HOST}:{self.server.server_address[1]}/"

    def serve_forever(self) -> None:
        self.server.serve_forever()

    def close(self) -> None:
        self.server.server_close()


def create_review_dashboard_server(
    report_root: Path,
    *,
    run_root: Path | None = None,
    port: int = 0,
) -> ReviewDashboardHttpServer:
    if isinstance(port, bool) or port < 0 or port > 65535:
        raise ReviewDashboardError("HTTP port 必须在 0..65535")
    root = report_root.resolve()
    verify_review_dashboard(root)
    report = load_model(root / "report.json", ReviewDashboardReport)
    source_root = (run_root or root).resolve()
    structures = {item.token: item for item in report.structure_routes}
    for route in structures.values():
        original = source_root / route.artifact.relative_path
        if _has_symlink(original, source_root):
            raise ReviewDashboardError(f"结构 route 是 symlink: {original}")
        route.artifact.verify(source_root)
    handler = partial(
        _ReviewDashboardHandler,
        directory=str(root),
        run_root=source_root,
        structures=structures,
    )
    return ReviewDashboardHttpServer(
        report_root=root,
        server=ThreadingHTTPServer((HOST, port), handler),
    )


def _copy_exclusive(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with source.open("rb") as read, destination.open("xb") as write:
        shutil.copyfileobj(read, write)


def export_review_dashboard(
    report_root: Path,
    *,
    run_root: Path,
    output: Path,
    created_at: datetime | None = None,
) -> Path:
    """Create a new portable report; output must not already exist."""

    source = report_root.resolve()
    manifest = verify_review_dashboard(source)
    report = load_model(source / "report.json", ReviewDashboardReport)
    destination = output.resolve()
    if destination.exists():
        raise ReviewDashboardError(f"export output 已存在，拒绝覆盖: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.creating-", dir=destination.parent)
    )
    try:
        for relative in (
            "index.html",
            "assets/review-dashboard.css",
            "assets/review-dashboard.js",
            "assets/3Dmol-min.js",
            "assets/3DMOL_LICENSE.txt",
        ):
            _copy_exclusive(source / relative, staging / relative)
        portable_routes: list[ReviewStructureRoute] = []
        copied: list[ArtifactRef] = []
        run = run_root.resolve()
        for index, route in enumerate(report.structure_routes, start=1):
            original = run / route.artifact.relative_path
            if _has_symlink(original, run):
                raise ReviewDashboardError(f"export 禁止 symlink structure: {original}")
            verified = route.artifact.verify(run)
            suffix = ".pdb" if route.mime_type == "chemical/x-pdb" else ".cif"
            relative = f"structures/{route.token}{suffix}"
            _copy_exclusive(verified, staging / relative)
            reference = ArtifactRef.from_file(
                run_root=staging,
                relative_path=relative,
                artifact_id=f"portable-structure-{index:04d}",
                role="portable-review-structure",
                file_format="pdb" if suffix == ".pdb" else "mmcif",
            )
            copied.append(reference)
            portable_routes.append(
                ReviewStructureRoute(
                    token=route.token,
                    artifact=reference,
                    mime_type=route.mime_type,
                )
            )
        portable_report = report.model_copy(
            update={"structure_routes": tuple(portable_routes)}
        )
        dump_model(portable_report, staging / "report.json")
        standard = tuple(
            ArtifactRef.from_file(
                run_root=staging,
                relative_path=relative,
                artifact_id=artifact_id,
                role="portable-review-dashboard",
                file_format=file_format,
            )
            for relative, artifact_id, file_format in (
                ("index.html", "review-dashboard-html", "html"),
                ("report.json", "review-dashboard-data", "json"),
                ("assets/review-dashboard.css", "review-dashboard-css", "css"),
                ("assets/review-dashboard.js", "review-dashboard-js", "javascript"),
                ("assets/3Dmol-min.js", "review-dashboard-3dmol-js", "javascript"),
                ("assets/3DMOL_LICENSE.txt", "review-dashboard-3dmol-license", "text"),
            )
        )
        portable_manifest = manifest.model_copy(
            update={
                "created_at": created_at or datetime.now(UTC),
                "completed_at": datetime.now(UTC),
                "output_artifacts": standard,
            }
        )
        dump_model(portable_manifest, staging / "report-manifest.json")
        export_manifest = ReviewDashboardExportManifest(
            created_at=created_at or datetime.now(UTC),
            source_report_manifest_sha256=sha256_file(source / "report-manifest.json"),
            report_kind=report.report_kind,
            copied_structures=tuple(copied),
            output_artifacts=standard,
        )
        dump_model(export_manifest, staging / "export-manifest.json")
        destination.parent.mkdir(parents=True, exist_ok=True)
        staging.rename(destination)
        return destination
    except Exception:
        if staging.exists():
            # A quarantined staging directory is intentionally recoverable and auditable.
            quarantine = staging.with_name(staging.name + ".quarantine")
            if not quarantine.exists():
                staging.rename(quarantine)
        raise
