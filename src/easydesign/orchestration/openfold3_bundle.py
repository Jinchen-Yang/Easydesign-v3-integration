"""Reproducibly assemble a self-contained, provenance-checked AFO release."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tarfile
import tempfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from easydesign.core import ConfigurationError, sha256_file

from .git_sources import directory_content_sha256
from .runtime_components import (
    OpenFold3BundleFile,
    OpenFold3ConversionValidationReceipt,
    OpenFold3ReleaseManifest,
    load_openfold3_bundle,
    load_openfold3_validation_receipt,
)

RAW_CHECKPOINT_SHA256 = (
    "af09eac4f29cef856633af07558cb143226fe95ebbef2c20921769d4a5f4bee4"
)
ALPHAFOLD_WHEEL_SHA256 = (
    "91b13810c3d51c18b75d0ad27b95b7448dee60933fa3688363c861dded0f7bf0"
)
RUNNER_COMMIT = "bc32b22ff5902e3daffd5d1f7203d7f2ab6cb997"
BACKEND_VERSION = "3.1.4"
RELEASE_ID = "afo-3-1-4-of3-p2-155k"


def _copy(source: Path, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return destination


def _write(path: Path, value: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(value if value.endswith("\n") else value + "\n")
    return path


def _git(repository: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise ConfigurationError(
            f"runner Git 校验失败: git {' '.join(arguments)}: {completed.stderr.strip()}"
        )
    return completed.stdout.strip()


def _safe_extract_git_archive(archive: Path, destination: Path) -> Path:
    destination.mkdir(parents=False, exist_ok=False)
    with tarfile.open(archive, mode="r:") as handle:
        for member in handle.getmembers():
            pure = PurePosixPath(member.name)
            if pure.is_absolute() or ".." in pure.parts or not pure.parts:
                raise ConfigurationError("runner git archive 含不安全路径")
            target = destination.joinpath(*pure.parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if not member.isfile():
                raise ConfigurationError(
                    f"runner git archive 含链接或设备条目: {member.name}"
                )
            target.parent.mkdir(parents=True, exist_ok=True)
            extracted = handle.extractfile(member)
            if extracted is None:
                raise ConfigurationError(f"runner git archive 无法读取: {member.name}")
            with extracted, target.open("xb") as output:
                shutil.copyfileobj(extracted, output)
            target.chmod(0o755 if member.mode & 0o111 else 0o644)
    return destination


def _export_runner_source(
    repository: Path,
    *,
    runner_commit: str,
    workspace: Path,
) -> tuple[Path, str]:
    head = _git(repository, "rev-parse", "HEAD")
    if head != runner_commit:
        raise ConfigurationError(
            f"runner HEAD 与声明 commit 不一致: expected={runner_commit}, actual={head}"
        )
    tracked_status = _git(repository, "status", "--porcelain", "--untracked-files=no")
    if tracked_status:
        raise ConfigurationError("runner tracked worktree 含本地修改，拒绝发布")
    _git(repository, "cat-file", "-e", f"{runner_commit}^{{commit}}")
    archive = workspace / "runner-source.tar"
    with archive.open("xb") as output:
        completed = subprocess.run(
            ["git", "-C", str(repository), "archive", "--format=tar", runner_commit],
            check=False,
            stdout=output,
            stderr=subprocess.PIPE,
        )
    if completed.returncode != 0:
        raise ConfigurationError(
            "无法从 runner commit object 导出源码: "
            + completed.stderr.decode("utf-8", errors="replace")
        )
    exported = _safe_extract_git_archive(archive, workspace / "runner-export")
    if not (exported / "run_alphafold.py").is_file():
        raise ConfigurationError("runner commit archive 缺少 run_alphafold.py")
    return exported, directory_content_sha256(exported)


def _zstd_content_identity(path: Path) -> tuple[int, str]:
    executable = shutil.which("zstd")
    if executable is None:
        raise ConfigurationError("发布 AFO bundle 需要 zstd executable")
    process = subprocess.Popen(
        [executable, "--decompress", "--stdout", str(path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    stdout = process.stdout
    if stdout is None:
        raise ConfigurationError("无法读取 zstd 解压输出")
    digest = hashlib.sha256()
    size = 0
    for chunk in iter(lambda: stdout.read(1024 * 1024), b""):
        digest.update(chunk)
        size += len(chunk)
    _, stderr = process.communicate()
    if process.returncode != 0:
        raise ConfigurationError(
            "converted weight zstd 校验失败: "
            + (b"" if stderr is None else stderr).decode(errors="replace")
        )
    return size, digest.hexdigest()


def _verify_conversion_receipt(
    receipt_path: Path,
    *,
    receipt: OpenFold3ConversionValidationReceipt,
    backend_version: str,
    runner_commit: str,
    runner_tree_sha256: str,
    raw_checkpoint_sha256: str,
    first_conversion: Path,
    second_conversion: Path,
) -> None:
    if (
        receipt.backend_version != backend_version
        or receipt.runner_commit != runner_commit
        or receipt.runner_tree_sha256 != runner_tree_sha256
        or receipt.raw_checkpoint_sha256 != raw_checkpoint_sha256
    ):
        raise ConfigurationError("conversion validation receipt 的 runner/checkpoint 身份不一致")
    actual: dict[str, tuple[int, str, int, str]] = {}
    for conversion_id, path in (
        ("conversion-a", first_conversion),
        ("conversion-b", second_conversion),
    ):
        uncompressed_size, uncompressed_sha = _zstd_content_identity(path)
        actual[conversion_id] = (
            path.stat().st_size,
            sha256_file(path),
            uncompressed_size,
            uncompressed_sha,
        )
    if actual["conversion-a"] != actual["conversion-b"]:
        raise ConfigurationError("两次转换的压缩或未压缩内容不一致")
    for declared in receipt.conversions:
        expected = (
            declared.compressed_size_bytes,
            declared.compressed_sha256,
            declared.uncompressed_size_bytes,
            declared.uncompressed_sha256,
        )
        if actual[declared.conversion_id] != expected:
            raise ConfigurationError(
                f"conversion validation receipt 与实际文件不一致: {declared.conversion_id}"
            )
    # Loading already verifies all referenced logs and the environment inventory.
    load_openfold3_validation_receipt(receipt_path)


def build_openfold3_release_bundle(
    *,
    output: Path,
    source: Path,
    wheelhouse: Path,
    requirements: Path,
    raw_checkpoint: Path,
    first_conversion: Path,
    second_conversion: Path,
    validation_receipt: Path,
    backend_version: str = BACKEND_VERSION,
    runner_commit: str = RUNNER_COMMIT,
    alphafold_wheel_sha256: str = ALPHAFOLD_WHEEL_SHA256,
    release_id: str = RELEASE_ID,
) -> Path:
    """Build a release only from a clean, exact commit and typed validation evidence."""

    publication = output.expanduser().resolve()
    if publication.exists():
        raise ConfigurationError(f"release bundle 已存在，禁止覆盖: {publication}")
    publication.parent.mkdir(parents=True, exist_ok=True)
    selected_source = source.expanduser().resolve(strict=True)
    selected_wheelhouse = wheelhouse.expanduser().resolve(strict=True)
    selected_requirements = requirements.expanduser().resolve(strict=True)
    selected_raw = raw_checkpoint.expanduser().resolve(strict=True)
    first_weight = first_conversion.expanduser().resolve(strict=True)
    second_weight = second_conversion.expanduser().resolve(strict=True)
    selected_receipt = validation_receipt.expanduser().resolve(strict=True)
    if sha256_file(selected_raw) != RAW_CHECKPOINT_SHA256:
        raise ConfigurationError("raw OpenFold3 checkpoint SHA-256 不一致")

    with tempfile.TemporaryDirectory(
        prefix=f".{publication.name}.staging-",
        dir=publication.parent,
    ) as temporary:
        selected_output = Path(temporary) / "bundle"
        exported, runner_tree_sha = _export_runner_source(
            selected_source,
            runner_commit=runner_commit,
            workspace=Path(temporary),
        )
        receipt = load_openfold3_validation_receipt(selected_receipt)
        _verify_conversion_receipt(
            selected_receipt,
            receipt=receipt,
            backend_version=backend_version,
            runner_commit=runner_commit,
            runner_tree_sha256=runner_tree_sha,
            raw_checkpoint_sha256=RAW_CHECKPOINT_SHA256,
            first_conversion=first_weight,
            second_conversion=second_weight,
        )

        wheels = tuple(sorted(selected_wheelhouse.glob("*.whl")))
        official = tuple(
            item for item in wheels if sha256_file(item) == alphafold_wheel_sha256
        )
        if len(official) != 1:
            raise ConfigurationError(
                f"wheelhouse 缺少唯一 alphafold3-open {backend_version} wheel"
            )

        selected_output.mkdir(parents=True, exist_ok=False)
        records: list[OpenFold3BundleFile] = []

        def add(path: Path, *, role: str) -> None:
            records.append(
                OpenFold3BundleFile(
                    relative_path=path.relative_to(selected_output),
                    role=role,  # type: ignore[arg-type]
                    size_bytes=path.stat().st_size,
                    sha256=sha256_file(path),
                )
            )

        for wheel in wheels:
            copied = _copy(wheel, selected_output / "wheelhouse" / wheel.name)
            add(
                copied,
                role=(
                    "alphafold-wheel"
                    if sha256_file(wheel) == alphafold_wheel_sha256
                    else "dependency-wheel"
                ),
            )
        requirement_copy = _copy(
            selected_requirements,
            selected_output / "environment/requirements.txt",
        )
        add(requirement_copy, role="environment-requirements")
        weight_copy = _copy(
            first_weight,
            selected_output / "model/of3_ported_weights.bin.zst",
        )
        add(weight_copy, role="converted-weight")

        for tracked in sorted(item for item in exported.rglob("*") if item.is_file()):
            relative = tracked.relative_to(exported)
            copied = _copy(tracked, selected_output / "runner" / relative)
            add(
                copied,
                role=(
                    "runner-script"
                    if relative == Path("run_alphafold.py")
                    else "runner-source"
                ),
            )

        add(_copy(exported / "LICENSE", selected_output / "licenses/LICENSE"), role="license")
        notice = _write(
            selected_output / "licenses/NOTICE",
            (
                f"OpenFold3 preview2 / alphafold3-open {backend_version} release bundle.\n"
                f"Runner source commit: {runner_commit}.\n"
                "Code license: Apache-2.0. Model weights remain subject to the "
                "included OpenFold3 weight terms."
            ),
        )
        add(notice, role="notice")
        for name in ("WEIGHTS_TERMS_OF_USE.md", "WEIGHTS_PROHIBITED_USE_POLICY.md"):
            add(_copy(exported / name, selected_output / "licenses" / name), role="model-terms")
        model_card = _write(
            selected_output / "MODEL_CARD.md",
            (
                "# OpenFold3 preview2 on alphafold3-open\n\n"
                "- Backend ID: `openfold3-af3-jax`\n"
                "- Model: `of3-p2-155k` (OpenFold3 preview2)\n"
                f"- Runner: `alphafold3-open {backend_version}`\n"
                f"- Runner commit: `{runner_commit}`\n"
                "- Templates: disabled in EasyDesign Local phase 1\n"
                "- This is not Google AlphaFold 3 and contains no Google AF3 weights."
            ),
        )
        add(model_card, role="model-card")

        validation_root = selected_output / "metadata/validation"
        validation_copy = _copy(selected_receipt, validation_root / "receipt.json")
        add(validation_copy, role="validation-receipt")
        for evidence in receipt.evidence_files():
            source_evidence = selected_receipt.parent / evidence.relative_path
            copied = _copy(source_evidence, validation_root / evidence.relative_path)
            add(copied, role="validation-evidence")

        conversion = receipt.conversions[0]
        conversion_manifest = _write(
            selected_output / "metadata/conversion-manifest.json",
            json.dumps(
                {
                    "schema_version": "0.2",
                    "generated_at": datetime.now(UTC).isoformat(),
                    "raw_checkpoint_sha256": RAW_CHECKPOINT_SHA256,
                    "converted_weight_sha256": conversion.compressed_sha256,
                    "converted_weight_uncompressed_sha256": (
                        conversion.uncompressed_sha256
                    ),
                    "two_independent_conversions_byte_identical": True,
                    "runner_commit": runner_commit,
                    "runner_tree_sha256": runner_tree_sha,
                    "alphafold_wheel_sha256": alphafold_wheel_sha256,
                    "conversion_receipt_sha256": sha256_file(validation_copy),
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
        )
        add(conversion_manifest, role="conversion-manifest")

        smoke = _write(
            selected_output / "validation/minimal-no-msa.json",
            json.dumps(
                {
                    "name": "openfold3-minimal-smoke",
                    "sequences": [
                        {
                            "protein": {
                                "id": "A",
                                "sequence": "MKTAYIAKQRQISFVKSHFSRQDILDLWQ",
                                "unpairedMsa": "",
                                "pairedMsa": "",
                                "templates": [],
                            }
                        }
                    ],
                    "modelSeeds": [101],
                    "dialect": "alphafold3",
                    "version": 4,
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
        )
        add(smoke, role="smoke-input")
        checksum_lines = [
            f"{item.sha256}  {item.relative_path.as_posix()}"
            for item in sorted(records, key=lambda value: value.relative_path.as_posix())
        ]
        checksums = _write(selected_output / "SHA256SUMS", "\n".join(checksum_lines))
        add(checksums, role="checksums")
        manifest = OpenFold3ReleaseManifest(
            release_id=release_id,
            backend_version=backend_version,
            code_license="Apache-2.0",
            template_mode="disabled",
            raw_checkpoint_sha256=RAW_CHECKPOINT_SHA256,
            converted_weight_sha256=conversion.compressed_sha256,
            wheel_sha256=alphafold_wheel_sha256,
            runner_commit=runner_commit,
            runner_tree_sha256=runner_tree_sha,
            environment_lock_sha256=sha256_file(requirement_copy),
            conversion_receipt_sha256=sha256_file(validation_copy),
            files=tuple(records),
        )
        _write(
            selected_output / "release-manifest.json",
            manifest.model_dump_json(indent=2),
        )
        load_openfold3_bundle(selected_output)
        selected_output.rename(publication)
    load_openfold3_bundle(publication)
    return publication


__all__ = ["build_openfold3_release_bundle"]
