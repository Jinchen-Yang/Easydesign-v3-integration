"""验证最新 wheel 的资源、Developer Preview 入口和隔离安装。"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
import tomllib
import venv
from pathlib import Path
from zipfile import BadZipFile, ZipFile

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
PACKAGE_PREFIX = "easydesign/reporting/static/target_viewer"
UI_PREFIX = "easydesign/ui/static"
SCAFFOLD_PREFIX = (
    "easydesign/resources/scaffolds/vhh/official_boltzgen_0_3_2"
)
PML_SKILL_PREFIX = "easydesign/ui/pml_skill_library"
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
EXPECTED_PML_SKILLS = (
    "safe-pml/SKILL.md",
    "chain-coloring/SKILL.md",
    "interface-analysis/SKILL.md",
    "ligand-pocket/SKILL.md",
    "publication-figure/SKILL.md",
    "structure-alignment/SKILL.md",
)


def project_version() -> str:
    with (ROOT / "pyproject.toml").open("rb") as handle:
        value = tomllib.load(handle)["project"]["version"]
    if not isinstance(value, str) or not value:
        raise RuntimeError("pyproject.toml 缺少 project.version")
    return value


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--wheel",
        type=Path,
        help="验证精确 wheel；省略时使用 dist/ 中最后写入的 wheel",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    arguments = parse_args(argv)
    if arguments.wheel is not None:
        wheel = arguments.wheel.resolve()
        if not wheel.is_file():
            print(f"ERROR: wheel 不存在: {wheel}", file=sys.stderr)
            return 1
    else:
        wheels = sorted(
            DIST.glob("easydesign-*.whl"),
            key=lambda path: path.stat().st_mtime_ns,
            reverse=True,
        )
        if not wheels:
            print("ERROR: dist/ 中没有 EasyDesign wheel", file=sys.stderr)
            return 1
        wheel = wheels[0]
    try:
        expected_version = project_version()
    except RuntimeError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    if expected_version not in wheel.name:
        print(
            f"ERROR: wheel 版本与 pyproject.toml 不一致: {wheel.name}",
            file=sys.stderr,
        )
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
            skill_source = ROOT / "src" / PML_SKILL_PREFIX
            for relative in EXPECTED_PML_SKILLS:
                member = f"{PML_SKILL_PREFIX}/{relative}"
                source = skill_source / relative
                if archive.read(member) != source.read_bytes():
                    print(
                        f"ERROR: wheel PML Skill 与源码字节不一致: {relative}",
                        file=sys.stderr,
                    )
                    return 1
            ui_source = ROOT / "src" / UI_PREFIX
            ui_files = tuple(
                sorted(
                    path.relative_to(ui_source).as_posix()
                    for path in ui_source.rglob("*")
                    if path.is_file()
                )
            )
            if not ui_files or "index.html" not in ui_files:
                print("ERROR: UI 构建产物缺少 index.html", file=sys.stderr)
                return 1
            if not any(item.endswith(".js") for item in ui_files) or not any(
                item.endswith(".css") for item in ui_files
            ):
                print("ERROR: UI 构建产物缺少 JS/CSS", file=sys.stderr)
                return 1
            for relative in ui_files:
                member = f"{UI_PREFIX}/{relative}"
                source = ui_source / relative
                if archive.read(member) != source.read_bytes():
                    print(
                        f"ERROR: wheel UI 资源与源码字节不一致: {relative}",
                        file=sys.stderr,
                    )
                    return 1
    except (BadZipFile, KeyError, OSError) as error:
        print(f"ERROR: wheel Target Viewer 资源验证失败: {error}", file=sys.stderr)
        return 1
    uv = os.environ.get("EASYDESIGN_UV")
    if not uv or not Path(uv).is_file():
        print("ERROR: 缺少 EASYDESIGN_UV 精确工具路径", file=sys.stderr)
        return 1
    try:
        stable_temp = Path(tempfile.gettempdir())
        with tempfile.TemporaryDirectory(
            prefix="easydesign-wheel-smoke-",
            dir=stable_temp,
        ) as temporary:
            environment = Path(temporary) / "venv"
            # Some relocatable Conda/bundled Python runtimes cannot execute ensurepip
            # inside a second-level venv.  Use the invoking pip's supported --python
            # target while keeping the smoke environment isolated from source imports.
            venv.EnvBuilder(
                with_pip=False,
                system_site_packages=True,
                symlinks=sys.platform != "win32",
            ).create(environment)
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
            dependency_environment = os.environ.copy()
            installed_site_packages = subprocess.run(
                [
                    str(python),
                    "-c",
                    "import sysconfig; print(sysconfig.get_paths()['purelib'])",
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
            ).stdout.strip()
            dependency_environment["PYTHONPATH"] = os.pathsep.join(
                [
                    installed_site_packages,
                    *[
                        item
                        for item in sys.path
                        if item
                        and "site-packages" in item
                        and Path(item).resolve() != (ROOT / "src").resolve()
                    ],
                ]
            )
            subprocess.run(
                [
                    uv,
                    "pip",
                    "install",
                    "--python",
                    str(python),
                    "--reinstall",
                    "--no-deps",
                    "--offline",
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
                env=dependency_environment,
            ).stdout.strip()
            if version != expected_version:
                raise RuntimeError(f"console-script 版本异常: {version}")
            subprocess.run(
                [str(python), "-m", "easydesign", "--help"],
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
                env=dependency_environment,
            )
            subprocess.run(
                [str(command), "ui", "--help"],
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
                env=dependency_environment,
            )
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"ERROR: wheel 安装或 console-script smoke 失败: {error}", file=sys.stderr)
        return 1
    print(
        f"wheel assets and console script verified: {wheel.name} "
        "(Target Viewer、VHH7、PML Skills、Workbench resources)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
