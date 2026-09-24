"""Declared artifact capabilities: confined, immutable bytes, no directory serving."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any

from easydesign.core import ArtifactRef

from .contracts import ArtifactView, ProductError


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def immutable_bytes(path: Path, data: bytes) -> None:
    """Publish complete immutable bytes atomically, including concurrent registrations."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".publish-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            if confined_bytes(path.parent, path.name) != data:
                raise ProductError(
                    "immutable_conflict", "An immutable product record changed", 409
                ) from None
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        os.unlink(temporary)


def immutable_json(path: Path, value: Any) -> None:
    immutable_bytes(path, json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2).encode())


def confined_bytes(root: Path, relative: str, *, maximum: int = 128 * 1024**2) -> bytes:
    """Use openat/O_NOFOLLOW for every component, closing the check/use symlink race."""
    parts = PurePosixPath(relative).parts
    if not parts or relative.startswith("/") or any(p in {"..", "."} for p in parts):
        raise ProductError("invalid_artifact", "Invalid artifact identity", 403)
    if "\\" in relative or "\x00" in relative:
        raise ProductError("invalid_artifact", "Invalid artifact identity", 403)
    fd = None
    try:
        fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        for part in parts[:-1]:
            nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = nxt
        file_fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        with os.fdopen(file_fd, "rb") as handle:
            info = os.fstat(handle.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > maximum:
                raise ProductError(
                    "invalid_artifact", "Artifact is not a bounded regular file", 403
                )
            data = handle.read(maximum + 1)
            if len(data) > maximum:
                raise ProductError("artifact_too_large", "Artifact exceeds delivery limit", 413)
            return data
    except OSError as error:
        raise ProductError(
            "artifact_unavailable", "Declared artifact is unavailable", 409
        ) from error
    finally:
        if fd is not None:
            os.close(fd)


class ArtifactCatalog:
    """Persistent capability mapping; identity comes from an already-verified domain ref."""

    def __init__(self, workspace: Path, root: Path) -> None:
        self.workspace, self.root = workspace, root

    def register(
        self,
        *,
        project: str,
        evidence: str,
        root: Path,
        ref: ArtifactRef,
        label: str,
        candidate_id: str | None = None,
    ) -> ArtifactView:
        relative_root = root.relative_to(self.workspace).as_posix()
        record = {
            "project": project,
            "evidence": evidence,
            "root": relative_root,
            "ref": ref.model_dump(mode="json"),
            "candidate_id": candidate_id,
        }
        token = digest(record)
        immutable_json(self.root / (token + ".json"), record)
        return ArtifactView(
            id=token,
            label=label,
            url=f"/api/v1/artifacts/{token}",
            format=ref.file_format,
            size_bytes=ref.size_bytes,
            sha256=ref.sha256,
            candidate_id=candidate_id,
            role=ref.role,
        )

    def document(self, project: str, evidence: str, value: Any, label: str) -> ArtifactView:
        root = self.root.parent / "documents"
        name = digest(value) + ".json"
        immutable_json(root / name, value)
        ref = ArtifactRef.from_file(
            run_root=root,
            relative_path=name,
            artifact_id="product-review-document",
            role="verified-product-projection",
            file_format="json",
        )
        return self.register(project=project, evidence=evidence, root=root, ref=ref, label=label)

    def read(self, token: str) -> tuple[bytes, str]:
        import re

        if not re.fullmatch(r"[0-9a-f]{64}", token):
            raise ProductError("not_found", "Unknown artifact", 404)
        path = self.root / (token + ".json")
        if not path.is_file():
            raise ProductError("not_found", "Unknown artifact", 404)
        record = json.loads(confined_bytes(self.root, path.name))
        if digest(record) != token:
            raise ProductError("integrity_error", "Artifact declaration changed", 409)
        ref = ArtifactRef.model_validate(record["ref"])
        relative = str(PurePosixPath(record["root"]) / ref.relative_path)
        data = confined_bytes(self.workspace, relative)
        if len(data) != ref.size_bytes or hashlib.sha256(data).hexdigest() != ref.sha256:
            raise ProductError("integrity_error", "Artifact checksum or size changed", 409)
        return data, ref.file_format
