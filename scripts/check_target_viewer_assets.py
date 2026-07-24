#!/usr/bin/env python3
"""验证 vendored Mol* 资产仍是已审计的 5.11.0 官方字节。"""

from __future__ import annotations

from pathlib import Path

from easydesign.core import sha256_file

ROOT = Path(__file__).resolve().parents[1]
MOLSTAR_ROOT = (
    ROOT
    / "src"
    / "easydesign"
    / "reporting"
    / "static"
    / "target_viewer"
    / "vendor"
    / "molstar"
)
EXPECTED = {
    "LICENSE": (
        1_108,
        "eabd1831ed605a29cf9d7e60221c019c1bc026add81e3c0686ce5f24b3d4d500",
    ),
    "molstar.css": (
        72_842,
        "5b68ceb6d3642549b4e9b2c071e58e41b98a5350ae269180587b39da86925d55",
    ),
    "molstar.js": (
        5_027_864,
        "7fad5561c74bc900930fb57d6ab028d1aafdda82223a901bf932b1098e84f1f3",
    ),
}


def main() -> int:
    actual_names = {path.name for path in MOLSTAR_ROOT.iterdir() if path.is_file()}
    if actual_names != set(EXPECTED):
        raise SystemExit(
            "Mol* vendored 文件集合不符合审计清单："
            f"expected={sorted(EXPECTED)}, actual={sorted(actual_names)}"
        )
    for name, (expected_size, expected_sha256) in EXPECTED.items():
        path = MOLSTAR_ROOT / name
        actual_size = path.stat().st_size
        if actual_size != expected_size:
            raise SystemExit(
                f"Mol* {name} 大小错误：expected={expected_size}, actual={actual_size}"
            )
        actual_sha256 = sha256_file(path)
        if actual_sha256 != expected_sha256:
            raise SystemExit(
                f"Mol* {name} SHA-256 错误："
                f"expected={expected_sha256}, actual={actual_sha256}"
            )
    print("Mol* 5.11.0 vendored assets verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
