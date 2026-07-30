#!/usr/bin/env python3
"""Verify byte-identical offline browser PyMOL runtime assets."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from easydesign.ui.browser_pymol_assets import BROWSER_PYMOL_ASSETS

ROOT = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "easydesign"
    / "ui"
    / "vendor"
    / "browser_pymol"
)

def main() -> int:
    for relative, (expected_size, expected_sha256) in BROWSER_PYMOL_ASSETS.items():
        path = ROOT / relative
        if not path.is_file():
            raise SystemExit(f"missing browser PyMOL asset: {relative}")
        data = path.read_bytes()
        actual = hashlib.sha256(data).hexdigest()
        if len(data) != expected_size or actual != expected_sha256:
            raise SystemExit(
                f"browser PyMOL asset mismatch: {relative} "
                f"size={len(data)} sha256={actual}"
            )
    print(f"browser PyMOL assets verified: {len(BROWSER_PYMOL_ASSETS)} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
