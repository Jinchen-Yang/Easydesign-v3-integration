"""验证最新 EasyDesign wheel 完整携带 Target Viewer 静态资源。"""

from __future__ import annotations

import sys
from pathlib import Path
from zipfile import BadZipFile, ZipFile

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
PACKAGE_PREFIX = "easydesign/reporting/static/target_viewer"
EXPECTED = (
    "index.html",
    "easydesign-viewer.js",
    "easydesign-viewer.css",
    "vendor/molstar/molstar.js",
    "vendor/molstar/molstar.css",
    "vendor/molstar/LICENSE",
)


def main() -> int:
    wheels = sorted(
        DIST.glob("easydesign-*.whl"),
        key=lambda path: path.stat().st_mtime_ns,
        reverse=True,
    )
    if not wheels:
        print("ERROR: dist/ 中没有 EasyDesign wheel", file=sys.stderr)
        return 1
    wheel = wheels[0]
    source_root = ROOT / "src" / PACKAGE_PREFIX
    try:
        with ZipFile(wheel) as archive:
            for relative in EXPECTED:
                member = f"{PACKAGE_PREFIX}/{relative}"
                source = source_root / relative
                if archive.read(member) != source.read_bytes():
                    print(
                        f"ERROR: wheel 静态资源与源码字节不一致: {relative}",
                        file=sys.stderr,
                    )
                    return 1
    except (BadZipFile, KeyError, OSError) as error:
        print(f"ERROR: wheel Target Viewer 资源验证失败: {error}", file=sys.stderr)
        return 1
    print(f"wheel Target Viewer assets verified: {wheel.name} ({len(EXPECTED)}/6)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
