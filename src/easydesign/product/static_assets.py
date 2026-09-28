"""Explicit release assets: no directory guessing and no old HTML fallback."""

from __future__ import annotations

import gzip
import hashlib
import re
import threading
from collections import OrderedDict
from pathlib import Path

from easydesign.agent.session_store import confined

from .artifacts import confined_bytes
from .contracts import ProductError

HASHED_BUILD_ASSET = re.compile(r"assets/[^/]+-[A-Za-z0-9_-]{8,}\.(?:js|css|woff2?|ttf|otf)")


def accepts_gzip(value: str) -> bool:
    choices: dict[str, list[float]] = {}
    for item in value.lower().split(","):
        name, *parameters = item.strip().split(";")
        quality = 1.0
        for parameter in parameters:
            key, separator, raw = parameter.strip().partition("=")
            if (
                key != "q"
                or not separator
                or not re.fullmatch(r"(?:0(?:\.\d{0,3})?|1(?:\.0{0,3})?)", raw)
            ):
                quality = 0.0
                break
            quality = float(raw)
        choices.setdefault(name, []).append(quality)
    return min(choices.get("gzip", choices.get("*", [0.0]))) > 0


class GzipCache:
    """Bounded content-keyed cache; parallel misses compress a bundle only once."""

    def __init__(self, maximum_bytes: int = 16 * 1024**2, maximum_entries: int = 256):
        self.maximum_bytes, self.maximum_entries = maximum_bytes, maximum_entries
        self._entries: OrderedDict[bytes, bytes] = OrderedDict()
        self._size = 0
        self._lock = threading.Lock()

    def encode(self, body: bytes) -> bytes:
        key = hashlib.sha256(body).digest()
        with self._lock:
            if key in self._entries:
                self._entries.move_to_end(key)
                return self._entries[key]
            encoded = gzip.compress(body, compresslevel=6, mtime=0)
            if len(encoded) <= self.maximum_bytes:
                while self._entries and (
                    self._size + len(encoded) > self.maximum_bytes
                    or len(self._entries) >= self.maximum_entries
                ):
                    self._size -= len(self._entries.popitem(last=False)[1])
                self._entries[key] = encoded
                self._size += len(encoded)
            return encoded


class StaticAssets:
    def __init__(self, workspace: Path, current: Path | None, history: tuple[Path, ...] = ()):
        self.current = confined(workspace, current) if current is not None else None
        if len(history) > 16 or (history and self.current is None):
            raise ValueError("Historical builds require a current build and at most 16 roots")
        self.history = tuple(confined(workspace, root) for root in history)
        self._known: dict[str, tuple[str, Path]] = {}
        for root in self.history:
            if not root.is_dir():
                raise ValueError("Explicit historical build is unavailable")
        # Only the declared roots' assets directories are enumerated. Neither
        # surrounding releases nor arbitrary workspace paths are discovered.
        if self.history:
            assert self.current is not None
            for root in (self.current, *self.history):
                assets = confined(workspace, root / "assets")
                if not assets.exists():
                    continue
                for entry in assets.iterdir():
                    relative = "assets/" + entry.name
                    if not HASHED_BUILD_ASSET.fullmatch(relative):
                        continue
                    data = confined_bytes(root, relative, maximum=32 * 1024**2)
                    digest = hashlib.sha256(data).hexdigest()
                    prior = self._known.get(relative)
                    if prior is not None and prior[0] != digest:
                        raise ValueError("Immutable asset name conflict: " + relative)
                    self._known.setdefault(relative, (digest, root))
                    if len(self._known) > 20000:
                        raise ValueError("Explicit asset index exceeds its bound")

    def read(self, relative: str) -> bytes:
        if self.current is None:
            raise ProductError("not_found", "Workbench build is not available", 404)
        known = self._known.get(relative) if HASHED_BUILD_ASSET.fullmatch(relative) else None
        try:
            data = confined_bytes(self.current, relative, maximum=32 * 1024**2)
        except ProductError as error:
            if known is None or not isinstance(error.__cause__, FileNotFoundError):
                raise
            data = confined_bytes(known[1], relative, maximum=32 * 1024**2)
        if known is not None and hashlib.sha256(data).hexdigest() != known[0]:
            raise ProductError("immutable_conflict", "Published asset content changed", 409)
        return data
