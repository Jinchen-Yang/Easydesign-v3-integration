#!/usr/bin/env python3
"""Verify byte-identical offline browser PyMOL runtime assets."""

from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "easydesign"
    / "ui"
    / "vendor"
    / "browser_pymol"
)

EXPECTED = {
    "pyodide/pyodide.js": (
        20_757,
        "43a8b5449083ae90c86f457233a4bd595864178d08a8f7c6799288f96e8c9f5d",
    ),
    "pyodide/pyodide.asm.js": (
        1_534_352,
        "fc501342137b8deea3ecca702f54ab0f58196b2cfff8240956ccdef46992dbd3",
    ),
    "pyodide/pyodide.asm.data": (
        5_016_460,
        "49523a53b1a52429622e7e264ce1b313aff9adbe638e9bc22cc40bb625d500b6",
    ),
    "pyodide/pyodide.asm.wasm": (
        7_546_363,
        "0fa411ef7a087911bde6f883b0b162900b225e694ec9b5dd8e724fc637c41394",
    ),
    "pyodide/pyodide_py.tar": (
        163_840,
        "26887852fd5b527b0582a748b2ae3ecab73799832c5d8b03dfd65fe5beb456fb",
    ),
    "pyodide/repodata.json": (
        54_332,
        "7a3163345ac036e7f70d68d5b229943e0b75680dbd59e3e25996ea2348c43ccf",
    ),
    "pyodide/numpy-1.23.5-cp310-cp310-emscripten_3_1_27_wasm32.whl": (
        3_126_204,
        "f790ec2d8cdf394a058d84ba96c36cbc59d3ac6edae1caaab80a8102e57fdcbd",
    ),
    "pymol-wasm/pymol-2.6.0a0-cp39-cp39-emscripten_3_1_46_wasm32.whl": (
        5_143_248,
        "bc6b79c8598ace79aeadd7567881249f523152d1c0f7e9cb35b515e54149b52e",
    ),
    "licenses/CHATPYMOL_MIT.txt": (
        1_079,
        "de580da55399fe982075c27d8a01de1aa1906e74c8449d891935a61b3bd199a4",
    ),
    "licenses/APACHE-2.0.txt": (
        11_357,
        "c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4",
    ),
    "licenses/OPEN_SOURCE_PYMOL.txt": (
        2_227,
        "0afe4207403d50dc602abab563626a4ff9fc2f923cb2d0779dc592c3dba49bce",
    ),
}


def main() -> int:
    for relative, (expected_size, expected_sha256) in EXPECTED.items():
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
    print(f"browser PyMOL assets verified: {len(EXPECTED)} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
