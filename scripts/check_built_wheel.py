"""验证最新 wheel 的资源、Developer Preview 入口和隔离安装。"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import venv
from pathlib import Path
from zipfile import BadZipFile, ZipFile

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
PACKAGE_PREFIX = "easydesign/reporting/static/target_viewer"
SCAFFOLD_PREFIX = (
    "easydesign/resources/scaffolds/vhh/official_boltzgen_0_3_2"
)
EXPECTED_VIEWER = (
    "index.html",
    "easydesign-viewer.js",
    "easydesign-viewer.css",
    "vendor/molstar/molstar.js",
    "vendor/molstar/molstar.css",
    "vendor/molstar/LICENSE",
)
EXPECTED_SCAFFOLDS = (
    "7eow.yaml",
    "7eow.cif",
    "7xl0.yaml",
    "7xl0.cif",
    "8coh.yaml",
    "8coh.cif",
    "8z8v.yaml",
    "8z8v.cif",
    "gontivimab.yaml",
    "gontivimab.cif",
    "isecarosmab.yaml",
    "isecarosmab.cif",
    "sonelokimab.yaml",
    "sonelokimab.cif",
    "BOLTZGEN_LICENSE.txt",
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
    if "0.1.0.dev5" not in wheel.name:
        print(f"ERROR: 最新 wheel 版本不是 0.1.0.dev5: {wheel.name}", file=sys.stderr)
        return 1
    source_root = ROOT / "src" / PACKAGE_PREFIX
    try:
        with ZipFile(wheel) as archive:
            for relative in EXPECTED_VIEWER:
                member = f"{PACKAGE_PREFIX}/{relative}"
                source = source_root / relative
                if archive.read(member) != source.read_bytes():
                    print(
                        f"ERROR: wheel 静态资源与源码字节不一致: {relative}",
                        file=sys.stderr,
                    )
                    return 1
            scaffold_source = ROOT / "src" / SCAFFOLD_PREFIX
            for relative in EXPECTED_SCAFFOLDS:
                member = f"{SCAFFOLD_PREFIX}/{relative}"
                source = scaffold_source / relative
                if archive.read(member) != source.read_bytes():
                    print(
                        f"ERROR: wheel scaffold 资产与源码字节不一致: {relative}",
                        file=sys.stderr,
                    )
                    return 1
    except (BadZipFile, KeyError, OSError) as error:
        print(f"ERROR: wheel Target Viewer 资源验证失败: {error}", file=sys.stderr)
        return 1
    try:
        with tempfile.TemporaryDirectory(prefix="easydesign-wheel-smoke-") as temporary:
            environment = Path(temporary) / "venv"
            venv.EnvBuilder(with_pip=True, system_site_packages=True).create(environment)
            python = (
                environment / "Scripts" / "python.exe"
                if sys.platform == "win32"
                else environment / "bin" / "python"
            )
            command = (
                environment / "Scripts" / "easydesign.exe"
                if sys.platform == "win32"
                else environment / "bin" / "easydesign"
            )
            subprocess.run(
                [
                    str(python),
                    "-m",
                    "pip",
                    "install",
                    "--force-reinstall",
                    "--no-deps",
                    str(wheel),
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=180,
            )
            version = subprocess.run(
                [str(command), "--version"],
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
            ).stdout.strip()
            if version != "0.1.0.dev5":
                raise RuntimeError(f"console-script 版本异常: {version}")
            subprocess.run(
                [str(python), "-m", "easydesign", "--help"],
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
            )
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"ERROR: wheel 安装或 console-script smoke 失败: {error}", file=sys.stderr)
        return 1
    print(
        f"wheel assets and console script verified: {wheel.name} "
        f"({len(EXPECTED_VIEWER) + len(EXPECTED_SCAFFOLDS)}/"
        f"{len(EXPECTED_VIEWER) + len(EXPECTED_SCAFFOLDS)})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
