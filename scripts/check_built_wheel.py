"""验证 local wheel 的只读资源、console script 和隔离安装。"""

from __future__ import annotations

import argparse
import site
import subprocess
import sys
import tempfile
import tomllib
import venv
from pathlib import Path
from zipfile import BadZipFile, ZipFile

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_PREFIX = "easydesign/reporting/static/target_viewer"
GPCR_REVIEW_PREFIX = "easydesign/reporting/static/gpcr_site_review"
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
EXPECTED_GPCR_REVIEW = (
    "index.html",
    "index.js",
    "report.css",
    "structure.html",
    "structure.js",
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
        help="验证精确 wheel；省略时使用 runtime/builds 中最后写入的 local wheel",
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
            (ROOT / "runtime/builds").glob("**/easydesign_local-*.whl"),
            key=lambda path: path.stat().st_mtime_ns,
            reverse=True,
        )
        if not wheels:
            print("ERROR: runtime/builds 中没有 EasyDesign Local wheel", file=sys.stderr)
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
            gpcr_source = ROOT / "src" / GPCR_REVIEW_PREFIX
            for relative in EXPECTED_GPCR_REVIEW:
                member = f"{GPCR_REVIEW_PREFIX}/{relative}"
                source = gpcr_source / relative
                if archive.read(member) != source.read_bytes():
                    print(
                        f"ERROR: wheel GPCR 审阅资源与源码字节不一致: {relative}",
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
            skill_prefix = "easydesign/agent/skills/binder-strategy"
            gpcr_names = [
                name.replace(".yaml", "-cdr3-50.yaml")
                for name in EXPECTED_SCAFFOLDS
                if name.endswith((".yaml", ".cif"))
            ]
            for relative in [
                "SKILL.md",
                "references/gpcr.md",
                *[f"assets/gpcr-vhh7-v1/{name}" for name in [*gpcr_names, "manifest.json"]],
            ]:
                member = f"{skill_prefix}/{relative}"
                if archive.read(member) != (ROOT / "src" / member).read_bytes():
                    print(f"ERROR: wheel GPCR Skill asset differs: {relative}", file=sys.stderr)
                    return 1
    except (BadZipFile, KeyError, OSError) as error:
        print(f"ERROR: wheel Target Viewer 资源验证失败: {error}", file=sys.stderr)
        return 1
    try:
        stable_temp = Path(tempfile.gettempdir())
        with tempfile.TemporaryDirectory(
            prefix="easydesign-wheel-smoke-",
            dir=stable_temp,
        ) as temporary:
            environment = Path(temporary) / "venv"
            venv.EnvBuilder(
                with_pip=True,
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
            subprocess.run(
                [
                    str(python),
                    "-m",
                    "pip",
                    "install",
                    "--force-reinstall",
                    "--no-deps",
                    "--no-index",
                    str(wheel),
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=180,
            )
            dependency_sites = [
                Path(item).resolve()
                for item in site.getsitepackages()
                if Path(item).is_dir()
            ]
            if not dependency_sites:
                raise RuntimeError("当前验证环境没有可复用的 site-packages")
            purelib = subprocess.run(
                [
                    str(python),
                    "-c",
                    "import sysconfig; print(sysconfig.get_path('purelib'))",
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
            ).stdout.strip()
            Path(purelib, "easydesign-build-dependencies.pth").write_text(
                "".join(f"{item}\n" for item in dependency_sites),
                encoding="utf-8",
            )
            imported_module = Path(
                subprocess.run(
                    [
                        str(python),
                        "-c",
                        (
                            "from pathlib import Path; import easydesign; "
                            "print(Path(easydesign.__file__).resolve())"
                        ),
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=30,
                ).stdout.strip()
            )
            if not imported_module.is_relative_to(environment):
                raise RuntimeError(
                    f"隔离 smoke 未导入刚安装的 wheel: {imported_module}"
                )
            version = subprocess.run(
                [str(command), "--version"],
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
            ).stdout.strip()
            if version != expected_version:
                raise RuntimeError(f"console-script 版本异常: {version}")
            subprocess.run(
                [str(python), "-m", "easydesign", "--help"],
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
            )
            subprocess.run(
                [str(command), "runtime", "--help"],
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
            )
            subprocess.run(
                [
                    str(python),
                    "-c",
                    (
                        "from easydesign.reporting.gpcr_site_review import "
                        "REPORT_RESOURCE_ROOT; "
                        "assert REPORT_RESOURCE_ROOT.joinpath('index.html').is_file()"
                    ),
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
            )
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"ERROR: wheel 安装或 console-script smoke 失败: {error}", file=sys.stderr)
        return 1
    print(
        f"local wheel assets and console script verified: {wheel.name} "
        "(Target Viewer, GPCR review, and VHH7 resources)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
