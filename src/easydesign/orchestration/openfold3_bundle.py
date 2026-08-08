"""Reproducibly assemble a self-contained OpenFold3 offline release bundle."""

from __future__ import annotations

import json
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from easydesign.core import ConfigurationError, sha256_file

from .runtime_components import (
    OpenFold3BundleFile,
    OpenFold3ReleaseManifest,
    load_openfold3_bundle,
)

RAW_CHECKPOINT_SHA256 = (
    "af09eac4f29cef856633af07558cb143226fe95ebbef2c20921769d4a5f4bee4"
)
ALPHAFOLD_WHEEL_SHA256 = (
    "d8a54a63627542cbbad4d0df98d2c6f10ecb716955da110c4f4415e01383a942"
)
RUNNER_COMMIT = "b811498caf10001eab4029e7b903453ef48f4d37"


def _copy(source: Path, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return destination


def _write(path: Path, value: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(value if value.endswith("\n") else value + "\n")
    return path


def _git_files(source: Path) -> tuple[Path, ...]:
    completed = subprocess.run(
        ["git", "-C", str(source), "ls-files", "-z"],
        check=False,
        capture_output=True,
    )
    if completed.returncode != 0:
        raise ConfigurationError("runner source 必须是 runner commit 的 Git worktree")
    return tuple(
        source / value.decode("utf-8")
        for value in completed.stdout.split(b"\0")
        if value
    )


def build_openfold3_release_bundle(
    *,
    output: Path,
    source: Path,
    wheelhouse: Path,
    requirements: Path,
    raw_checkpoint: Path,
    first_conversion: Path,
    second_conversion: Path,
    first_log: Path,
    second_log: Path,
    validation_receipt: Path,
) -> Path:
    """Build a future-upload bundle; it deliberately contains no download URL."""

    selected_output = output.expanduser().resolve()
    if selected_output.exists():
        raise ConfigurationError(f"release bundle 已存在，禁止覆盖: {selected_output}")
    selected_source = source.expanduser().resolve(strict=True)
    selected_wheelhouse = wheelhouse.expanduser().resolve(strict=True)
    selected_requirements = requirements.expanduser().resolve(strict=True)
    selected_raw = raw_checkpoint.expanduser().resolve(strict=True)
    first_weight = first_conversion.expanduser().resolve(strict=True)
    second_weight = second_conversion.expanduser().resolve(strict=True)
    if sha256_file(selected_raw) != RAW_CHECKPOINT_SHA256:
        raise ConfigurationError("raw OpenFold3 checkpoint SHA-256 不一致")
    converted_sha = sha256_file(first_weight)
    if sha256_file(second_weight) != converted_sha or (
        first_weight.stat().st_size != second_weight.stat().st_size
    ):
        raise ConfigurationError("两次独立转换结果不一致")
    wheels = tuple(sorted(selected_wheelhouse.glob("*.whl")))
    official = tuple(
        item for item in wheels if sha256_file(item) == ALPHAFOLD_WHEEL_SHA256
    )
    if len(official) != 1:
        raise ConfigurationError("wheelhouse 缺少唯一官方 alphafold3-open 3.1.3 wheel")

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
                if sha256_file(wheel) == ALPHAFOLD_WHEEL_SHA256
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

    for tracked in _git_files(selected_source):
        relative = tracked.relative_to(selected_source)
        copied = _copy(tracked, selected_output / "runner" / relative)
        add(
            copied,
            role=("runner-script" if relative == Path("run_alphafold.py") else "runner-source"),
        )
    license_copy = selected_output / "licenses/LICENSE"
    if license_copy.exists():
        # The tracked runner LICENSE is also copied under runner/; release metadata
        # gets one explicit canonical license role.
        raise ConfigurationError("unexpected pre-existing release license")
    add(_copy(selected_source / "LICENSE", license_copy), role="license")
    notice = _write(
        selected_output / "licenses/NOTICE",
        (
            "OpenFold3 preview2 / alphafold3-open 3.1.3 release bundle.\n"
            f"Runner source commit: {RUNNER_COMMIT}.\n"
            "Code license: Apache-2.0. Model weights remain subject to the "
            "included OpenFold3 weight terms."
        ),
    )
    add(notice, role="notice")
    for name in ("WEIGHTS_TERMS_OF_USE.md", "WEIGHTS_PROHIBITED_USE_POLICY.md"):
        add(_copy(selected_source / name, selected_output / "licenses" / name), role="model-terms")
    model_card = _write(
        selected_output / "MODEL_CARD.md",
        (
            "# OpenFold3 preview2 on alphafold3-open\n\n"
            "- Backend ID: `openfold3-af3-jax`\n"
            "- Model: `of3-p2-155k` (OpenFold3 preview2)\n"
            "- Runner: `alphafold3-open 3.1.3`\n"
            "- Templates: disabled in EasyDesign Local phase 1\n"
            "- This is not Google AlphaFold 3 and contains no Google AF3 weights.\n"
            "- Distribution URL: intentionally unset until a researcher publishes the bundle."
        ),
    )
    add(model_card, role="model-card")
    conversion_manifest = _write(
        selected_output / "metadata/conversion-manifest.json",
        json.dumps(
            {
                "schema_version": "0.1",
                "generated_at": datetime.now(UTC).isoformat(),
                "raw_checkpoint_sha256": RAW_CHECKPOINT_SHA256,
                "converted_weight_sha256": converted_sha,
                "converted_weight_size_bytes": first_weight.stat().st_size,
                "two_independent_conversions_byte_identical": True,
                "runner_commit": RUNNER_COMMIT,
                "alphafold_wheel_sha256": ALPHAFOLD_WHEEL_SHA256,
                "converter_python": "3.12",
                "converter_torch": "2.8.0+cpu",
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
    )
    add(conversion_manifest, role="conversion-manifest")
    for label, log in (("conversion-a", first_log), ("conversion-b", second_log)):
        add(
            _copy(
                log.resolve(strict=True),
                selected_output / f"metadata/{label}.log",
            ),
            role="conversion-log",
        )
    validation_copy = _copy(
        validation_receipt.resolve(strict=True),
        selected_output / "metadata/conversion-validation-receipt.json",
    )
    add(validation_copy, role="validation-receipt")
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
        code_license="Apache-2.0",
        template_mode="disabled",
        raw_checkpoint_sha256=RAW_CHECKPOINT_SHA256,
        converted_weight_sha256=converted_sha,
        wheel_sha256=ALPHAFOLD_WHEEL_SHA256,
        runner_commit=RUNNER_COMMIT,
        environment_lock_sha256=sha256_file(requirement_copy),
        files=tuple(records),
    )
    _write(
        selected_output / "release-manifest.json",
        manifest.model_dump_json(indent=2),
    )
    load_openfold3_bundle(selected_output)
    return selected_output


__all__ = ["build_openfold3_release_bundle"]
