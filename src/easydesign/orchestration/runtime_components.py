"""Immutable local scientific components installed from verified offline bundles."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Self

import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict, Field, model_validator

from easydesign.core import ConfigurationError, sha256_file
from easydesign.core.artifacts import SHA256_PATTERN
from easydesign.orchestration.task_tracking import (
    atomic_dump_runtime_model,
    load_latest_runtime_model,
)
from easydesign.workspace_context import WorkspaceContext

from .git_sources import directory_content_sha256
from .profile import (
    OpenFold3Af3JaxRuntime,
    RuntimeBackends,
    RuntimeProfile,
    initialize_runtime_profile,
    load_runtime_profile,
)

COMPONENT_ID = "openfold3-p2-af3-jax"
BACKEND_ID = "openfold3-af3-jax"
MODEL_ID = "of3-p2-155k"
ADAPTER_CONTRACT_VERSION = "openfold3-af3-jax-cli-v1"
SEMVER_PATTERN = r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?$"
RELEASE_ID_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
COMPONENT_STATE_ROOT = Path("state/components") / COMPONENT_ID / "releases"


class OpenFold3EvidenceFile(BaseModel):
    """A file adjacent to a validation receipt, addressed by immutable identity."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    relative_path: Path
    size_bytes: int = Field(ge=0)
    sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_path(self) -> Self:
        if self.relative_path.is_absolute() or ".." in self.relative_path.parts:
            raise ValueError("validation evidence 必须使用 receipt 相邻的安全相对路径")
        return self


class OpenFold3ConversionIdentity(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    conversion_id: Literal["conversion-a", "conversion-b"]
    compressed_size_bytes: int = Field(gt=0)
    compressed_sha256: str = Field(pattern=SHA256_PATTERN)
    uncompressed_size_bytes: int = Field(gt=0)
    uncompressed_sha256: str = Field(pattern=SHA256_PATTERN)
    log: OpenFold3EvidenceFile


class OpenFold3TestReceipt(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    command: tuple[str, ...] = Field(min_length=1)
    collected: int = Field(ge=43)
    passed: int = Field(ge=43)
    return_code: Literal[0]
    log: OpenFold3EvidenceFile

    @model_validator(mode="after")
    def require_all_passed(self) -> Self:
        if self.passed != self.collected:
            raise ValueError("converter tests 必须全部通过")
        return self


class OpenFold3HarnessReceipt(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    harness_id: str = Field(pattern=RELEASE_ID_PATTERN)
    command: tuple[str, ...] = Field(min_length=1)
    return_code: Literal[0]
    tolerance: float = Field(gt=0)
    maximum_relative_error: float = Field(ge=0)
    log: OpenFold3EvidenceFile

    @model_validator(mode="after")
    def within_tolerance(self) -> Self:
        if self.maximum_relative_error > self.tolerance:
            raise ValueError(f"verification harness 超出容差: {self.harness_id}")
        return self


class OpenFold3ConversionValidationReceipt(BaseModel):
    """Typed release evidence; arbitrary user-provided `ok` files are rejected."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["0.2"] = "0.2"
    backend_version: str = Field(pattern=SEMVER_PATTERN)
    runner_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    runner_tree_sha256: str = Field(pattern=SHA256_PATTERN)
    raw_checkpoint_sha256: str = Field(pattern=SHA256_PATTERN)
    conversions: tuple[OpenFold3ConversionIdentity, OpenFold3ConversionIdentity]
    converter_tests: OpenFold3TestReceipt
    verification_harnesses: tuple[OpenFold3HarnessReceipt, ...] = Field(min_length=1)
    python_version: str = Field(min_length=1, max_length=64)
    pytorch_version: str = Field(min_length=1, max_length=64)
    environment_inventory: OpenFold3EvidenceFile
    generated_at: datetime

    @model_validator(mode="after")
    def validate_conversions(self) -> Self:
        if {item.conversion_id for item in self.conversions} != {
            "conversion-a",
            "conversion-b",
        }:
            raise ValueError("validation receipt 必须包含 conversion-a 和 conversion-b")
        first, second = sorted(self.conversions, key=lambda item: item.conversion_id)
        if (
            first.compressed_sha256 != second.compressed_sha256
            or first.compressed_size_bytes != second.compressed_size_bytes
            or first.uncompressed_sha256 != second.uncompressed_sha256
            or first.uncompressed_size_bytes != second.uncompressed_size_bytes
        ):
            raise ValueError("两次转换的压缩与未压缩 identity 必须全部一致")
        identities = [item.harness_id for item in self.verification_harnesses]
        if len(identities) != len(set(identities)):
            raise ValueError("verification harness identity 不能重复")
        return self

    def evidence_files(self) -> tuple[OpenFold3EvidenceFile, ...]:
        return (
            *(item.log for item in self.conversions),
            self.converter_tests.log,
            *(item.log for item in self.verification_harnesses),
            self.environment_inventory,
        )


class OpenFold3BundleFile(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    relative_path: Path
    role: Literal[
        "alphafold-wheel",
        "dependency-wheel",
        "environment-requirements",
        "converted-weight",
        "runner-source",
        "runner-script",
        "license",
        "notice",
        "model-terms",
        "model-card",
        "conversion-manifest",
        "conversion-log",
        "validation-evidence",
        "checksums",
        "smoke-input",
        "validation-receipt",
    ]
    size_bytes: int = Field(ge=0)
    sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_path(self) -> Self:
        if self.relative_path.is_absolute() or ".." in self.relative_path.parts:
            raise ValueError("bundle file 必须是包内相对路径")
        return self


class OpenFold3ReleaseManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["0.2"] = "0.2"
    release_id: str = Field(pattern=RELEASE_ID_PATTERN)
    component_id: Literal["openfold3-p2-af3-jax"] = "openfold3-p2-af3-jax"
    backend_id: Literal["openfold3-af3-jax"] = "openfold3-af3-jax"
    backend_version: str = Field(pattern=SEMVER_PATTERN)
    model_id: Literal["of3-p2-155k"] = "of3-p2-155k"
    adapter_contract_version: Literal["openfold3-af3-jax-cli-v1"] = (
        "openfold3-af3-jax-cli-v1"
    )
    python_version: Literal["3.12"] = "3.12"
    code_license: Literal["Apache-2.0"]
    template_mode: Literal["disabled"]
    raw_checkpoint_sha256: str = Field(pattern=SHA256_PATTERN)
    converted_weight_sha256: str = Field(pattern=SHA256_PATTERN)
    wheel_sha256: str = Field(pattern=SHA256_PATTERN)
    runner_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    runner_tree_sha256: str = Field(pattern=SHA256_PATTERN)
    environment_lock_sha256: str = Field(pattern=SHA256_PATTERN)
    conversion_receipt_sha256: str = Field(pattern=SHA256_PATTERN)
    files: tuple[OpenFold3BundleFile, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_inventory(self) -> Self:
        paths = [item.relative_path for item in self.files]
        if len(paths) != len(set(paths)):
            raise ValueError("bundle inventory 路径不能重复")
        singleton_roles = {
            "alphafold-wheel",
            "environment-requirements",
            "converted-weight",
            "runner-script",
            "license",
            "notice",
            "model-card",
            "conversion-manifest",
            "checksums",
            "smoke-input",
            "validation-receipt",
        }
        for role in singleton_roles:
            if sum(item.role == role for item in self.files) != 1:
                raise ValueError(f"bundle 必须恰好包含一个 {role}")
        if self.require_role("converted-weight").sha256 != self.converted_weight_sha256:
            raise ValueError("converted weight identity 与 inventory 不一致")
        if self.require_role("alphafold-wheel").sha256 != self.wheel_sha256:
            raise ValueError("alphafold wheel identity 与 inventory 不一致")
        if (
            self.require_role("environment-requirements").sha256
            != self.environment_lock_sha256
        ):
            raise ValueError("environment lock identity 与 inventory 不一致")
        if (
            self.require_role("validation-receipt").sha256
            != self.conversion_receipt_sha256
        ):
            raise ValueError("conversion receipt identity 与 inventory 不一致")
        return self

    def require_role(self, role: str) -> OpenFold3BundleFile:
        try:
            return next(item for item in self.files if item.role == role)
        except StopIteration as error:
            raise ConfigurationError(f"OpenFold3 bundle 缺少 {role}") from error


class OpenFold3ComponentReceipt(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["0.2"] = "0.2"
    release_id: str = Field(pattern=RELEASE_ID_PATTERN)
    component_id: Literal["openfold3-p2-af3-jax"] = "openfold3-p2-af3-jax"
    backend_id: Literal["openfold3-af3-jax"] = "openfold3-af3-jax"
    backend_version: str = Field(pattern=SEMVER_PATTERN)
    model_id: Literal["of3-p2-155k"] = "of3-p2-155k"
    adapter_contract_version: Literal["openfold3-af3-jax-cli-v1"] = (
        "openfold3-af3-jax-cli-v1"
    )
    installed_at: datetime
    release_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    environment_lock_sha256: str = Field(pattern=SHA256_PATTERN)
    environment_root: Path
    environment_inventory: Path
    environment_inventory_sha256: str = Field(pattern=SHA256_PATTERN)
    model_root: Path
    converted_weight: Path
    raw_checkpoint_sha256: str = Field(pattern=SHA256_PATTERN)
    converted_weight_sha256: str = Field(pattern=SHA256_PATTERN)
    wheel_sha256: str = Field(pattern=SHA256_PATTERN)
    runner_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    runner_tree_sha256: str = Field(pattern=SHA256_PATTERN)
    conversion_receipt_sha256: str = Field(pattern=SHA256_PATTERN)
    runner: Path
    smoke_receipt: Path
    smoke_receipt_sha256: str = Field(pattern=SHA256_PATTERN)


class OpenFold3InstallResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["installed", "already-installed"]
    component: OpenFold3ComponentReceipt
    profile: Path | None


class RuntimeStatus(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    openfold3: OpenFold3ComponentReceipt | None
    openfold3_installed: tuple[OpenFold3ComponentReceipt, ...] = ()


def _component_path(context: WorkspaceContext, release_id: str) -> Path:
    if re.fullmatch(RELEASE_ID_PATTERN, release_id) is None:
        raise ConfigurationError(f"OpenFold3 release_id 不合法: {release_id}")
    return context.runtime_root / COMPONENT_STATE_ROOT / release_id / "component.json"


def _component_paths(context: WorkspaceContext) -> tuple[Path, ...]:
    root = context.runtime_root / COMPONENT_STATE_ROOT
    return tuple(sorted(root.glob("*/component.json"))) if root.is_dir() else ()


def _bundle_file(bundle: Path, item: OpenFold3BundleFile) -> Path:
    path = (bundle / item.relative_path).resolve(strict=True)
    if not path.is_relative_to(bundle):
        raise ConfigurationError(f"bundle inventory 逃出包边界: {item.relative_path}")
    stat = path.stat()
    if not path.is_file() or stat.st_size != item.size_bytes:
        raise ConfigurationError(f"bundle file 大小不一致: {item.relative_path}")
    if sha256_file(path) != item.sha256:
        raise ConfigurationError(f"bundle file SHA-256 不一致: {item.relative_path}")
    return path


def _validation_evidence_file(
    receipt_path: Path,
    evidence: OpenFold3EvidenceFile,
) -> Path:
    root = receipt_path.parent.resolve(strict=True)
    path = (root / evidence.relative_path).resolve(strict=True)
    if not path.is_relative_to(root):
        raise ConfigurationError(
            f"OpenFold3 validation evidence 逃出 receipt 边界: {evidence.relative_path}"
        )
    if (
        not path.is_file()
        or path.stat().st_size != evidence.size_bytes
        or sha256_file(path) != evidence.sha256
    ):
        raise ConfigurationError(
            f"OpenFold3 validation evidence identity 不一致: {evidence.relative_path}"
        )
    return path


def load_openfold3_validation_receipt(
    receipt_path: Path,
) -> OpenFold3ConversionValidationReceipt:
    try:
        receipt = OpenFold3ConversionValidationReceipt.model_validate_json(
            receipt_path.read_text(encoding="utf-8")
        )
    except (OSError, UnicodeDecodeError, ValueError) as error:
        raise ConfigurationError(
            f"OpenFold3 conversion validation receipt 无法校验: {receipt_path}"
        ) from error
    for evidence in receipt.evidence_files():
        _validation_evidence_file(receipt_path, evidence)
    return receipt


def load_openfold3_bundle(bundle_path: Path) -> tuple[Path, OpenFold3ReleaseManifest]:
    bundle = bundle_path.expanduser().resolve(strict=True)
    manifest_path = bundle / "release-manifest.json"
    try:
        manifest = OpenFold3ReleaseManifest.model_validate_json(
            manifest_path.read_text(encoding="utf-8")
        )
    except (OSError, UnicodeDecodeError, ValueError) as error:
        raise ConfigurationError(
            "OpenFold3 release manifest 无法校验；schema 0.1/3.1.3 bundle "
            f"不得用于新安装: {manifest_path}"
        ) from error
    for item in manifest.files:
        _bundle_file(bundle, item)
    runner_root = (bundle / "runner").resolve(strict=True)
    if directory_content_sha256(runner_root) != manifest.runner_tree_sha256:
        raise ConfigurationError("OpenFold3 runner source tree SHA-256 不一致")
    receipt_path = _bundle_file(bundle, manifest.require_role("validation-receipt"))
    receipt = load_openfold3_validation_receipt(receipt_path)
    if (
        receipt.backend_version != manifest.backend_version
        or receipt.runner_commit != manifest.runner_commit
        or receipt.runner_tree_sha256 != manifest.runner_tree_sha256
        or receipt.raw_checkpoint_sha256 != manifest.raw_checkpoint_sha256
    ):
        raise ConfigurationError("OpenFold3 conversion receipt 与 release manifest 不一致")
    conversion = receipt.conversions[0]
    if conversion.compressed_sha256 != manifest.converted_weight_sha256:
        raise ConfigurationError("OpenFold3 conversion receipt 与 converted weight 不一致")
    return bundle, manifest


def _python312() -> Path:
    configured = os.environ.get("EASYDESIGN_PYTHON312")
    candidates = [Path(configured)] if configured else []
    discovered = shutil.which("python3.12")
    if discovered:
        candidates.append(Path(discovered))
    uv = shutil.which("uv")
    if uv:
        found = subprocess.run(
            [uv, "python", "find", "3.12"],
            check=False,
            capture_output=True,
            text=True,
        )
        if found.returncode == 0 and found.stdout.strip():
            candidates.append(Path(found.stdout.strip()))
    candidates.append(Path("/usr/bin/python3.12"))
    for candidate in candidates:
        if candidate.is_file() or candidate.is_symlink():
            completed = subprocess.run(
                [
                    str(candidate),
                    "-c",
                    "import sys; print('.'.join(map(str, sys.version_info[:2])))",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            if completed.returncode == 0 and completed.stdout.strip() == "3.12":
                return candidate.resolve()
    raise ConfigurationError(
        "安装 OpenFold3 需要 Python 3.12；请设置 EASYDESIGN_PYTHON312 为其绝对路径"
    )


def _profile_revision(context: WorkspaceContext, model: RuntimeProfile) -> Path:
    base = context.profile_path
    if not base.exists():
        destination = base
    else:
        revision_root = base.with_name(f"{base.name}.revisions")
        revision_root.mkdir(parents=True, exist_ok=True)
        sequence = len(tuple(revision_root.glob("revision-*.yaml"))) + 1
        destination = revision_root / f"revision-{sequence:06d}.yaml"
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("x", encoding="utf-8", newline="\n") as handle:
        yaml.safe_dump(
            model.model_dump(mode="json", exclude_none=True),
            handle,
            allow_unicode=True,
            sort_keys=False,
        )
    return destination


def _runtime_from_receipt(
    context: WorkspaceContext,
    receipt: OpenFold3ComponentReceipt,
) -> OpenFold3Af3JaxRuntime:
    return OpenFold3Af3JaxRuntime(
        release_id=receipt.release_id,
        backend_id=receipt.backend_id,
        backend_version=receipt.backend_version,
        model_id=receipt.model_id,
        adapter_contract_version=receipt.adapter_contract_version,
        python=receipt.environment_root / "bin/python",
        runner=receipt.runner,
        model_root=receipt.model_root,
        converted_weight=receipt.converted_weight,
        cache_root=context.runtime_root / "cache/openfold3-p2-af3-jax",
        raw_checkpoint_sha256=receipt.raw_checkpoint_sha256,
        converted_weight_sha256=receipt.converted_weight_sha256,
        release_manifest_sha256=receipt.release_manifest_sha256,
        conversion_receipt_sha256=receipt.conversion_receipt_sha256,
        wheel_sha256=receipt.wheel_sha256,
        runner_commit=receipt.runner_commit,
        runner_tree_sha256=receipt.runner_tree_sha256,
        environment_lock_sha256=receipt.environment_lock_sha256,
    )


def _activate_profile(
    context: WorkspaceContext,
    receipt: OpenFold3ComponentReceipt,
) -> Path:
    revision_root = context.profile_path.with_name(
        f"{context.profile_path.name}.revisions"
    )
    if not context.profile_path.is_file() and not tuple(
        revision_root.glob("revision-*.yaml")
    ):
        initialize_runtime_profile(
            context.profile_path,
            profile_id="workspace-local",
            runs_root=context.runs_root,
        )
    current = load_runtime_profile()
    runtime = _runtime_from_receipt(context, receipt)
    if current.profile.backends.openfold3_af3_jax == runtime:
        return current.path
    backends = current.profile.backends.model_copy(
        update={"openfold3_af3_jax": runtime}
    )
    profile = current.profile.model_copy(
        update={
            "schema_version": "0.2",
            "backends": RuntimeBackends.model_validate(backends),
        }
    )
    return _profile_revision(context, profile)


def active_openfold3_runtime(
    context: WorkspaceContext | None = None,
) -> OpenFold3Af3JaxRuntime | None:
    selected = WorkspaceContext.discover() if context is None else context
    revision_root = selected.profile_path.with_name(
        f"{selected.profile_path.name}.revisions"
    )
    if not selected.profile_path.is_file() and not tuple(
        revision_root.glob("revision-*.yaml")
    ):
        return None
    loaded = load_runtime_profile(selected.profile_path)
    runtime = loaded.profile.backends.openfold3_af3_jax
    if runtime is None:
        return None
    verify_openfold3_component(selected, release_id=runtime.release_id)
    return runtime


def _write_environment_inventory(environment: Path, path: Path) -> Path:
    completed = subprocess.run(
        [str(environment / "bin/python"), "-m", "pip", "freeze", "--all"],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise ConfigurationError(f"OpenFold3 environment inventory 失败: {completed.stderr}")
    path.write_text(completed.stdout, encoding="utf-8")
    return path


def _install_environment(
    *,
    bundle: Path,
    manifest: OpenFold3ReleaseManifest,
    environment: Path,
    child_environment: dict[str, str],
) -> Path:
    python312 = _python312()
    completed = subprocess.run(
        [str(python312), "-m", "venv", "--copies", str(environment)],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, **child_environment},
    )
    if completed.returncode != 0:
        raise ConfigurationError(f"OpenFold3 venv 创建失败: {completed.stderr}")
    requirements = _bundle_file(
        bundle,
        manifest.require_role("environment-requirements"),
    )
    wheelhouse = bundle / "wheelhouse"
    completed = subprocess.run(
        [
            str(environment / "bin/python"),
            "-m",
            "pip",
            "install",
            "--no-index",
            "--no-deps",
            "--find-links",
            str(wheelhouse),
            "--requirement",
            str(requirements),
        ],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, **child_environment},
    )
    if completed.returncode != 0:
        raise ConfigurationError(f"OpenFold3 offline wheel 安装失败: {completed.stderr}")
    build_data = subprocess.run(
        [
            str(environment / "bin/python"),
            "-c",
            "from alphafold3.build_data import build_data; build_data()",
        ],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, **child_environment},
    )
    if build_data.returncode != 0:
        raise ConfigurationError(
            "OpenFold3 chemical component data 构建失败: "
            f"{build_data.stderr or build_data.stdout}"
        )
    probe = subprocess.run(
        [
            str(environment / "bin/python"),
            "-c",
            (
                "from importlib.metadata import version; "
                f"assert version('alphafold3-open') == {manifest.backend_version!r}; "
                "assert version('jax') == '0.10.2'; "
                "assert version('jaxlib') == '0.10.2'; "
                "assert version('dm-haiku') == '0.0.16'; "
                "assert version('rdkit') == '2025.9.4'; "
                "assert version('tokamax') == '0.0.12'; "
                "import importlib.util; assert importlib.util.find_spec('torch') is None"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, **child_environment},
    )
    if probe.returncode != 0:
        raise ConfigurationError(f"OpenFold3 environment probe 失败: {probe.stderr}")
    return environment


def _copy_runner(bundle: Path, manifest: OpenFold3ReleaseManifest, model_root: Path) -> Path:
    runner_source = model_root / "runner"
    runner_source.mkdir(parents=True, exist_ok=False)
    for item in manifest.files:
        if item.role not in {"runner-source", "runner-script"}:
            continue
        source = _bundle_file(bundle, item)
        relative = item.relative_path.relative_to("runner")
        destination = runner_source / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    runner_item = manifest.require_role("runner-script")
    return runner_source / runner_item.relative_path.relative_to("runner")


def _gpu_smoke(
    *,
    bundle: Path,
    manifest: OpenFold3ReleaseManifest,
    environment: Path,
    runner: Path,
    model_root: Path,
    output_root: Path,
    child_environment: dict[str, str],
) -> Path:
    smoke_input = _bundle_file(bundle, manifest.require_role("smoke-input"))
    smoke_device = child_environment.get(
        "EASYDESIGN_OPENFOLD3_SMOKE_DEVICE",
        os.environ.get("EASYDESIGN_OPENFOLD3_SMOKE_DEVICE", "0"),
    )
    inherited_xla_flags = child_environment.get(
        "XLA_FLAGS", os.environ.get("XLA_FLAGS", "")
    )
    triton_gemm_flag = "--xla_gpu_enable_triton_gemm=false"
    xla_flags = (
        inherited_xla_flags
        if triton_gemm_flag in inherited_xla_flags.split()
        else f"{inherited_xla_flags} {triton_gemm_flag}".strip()
    )
    completed = subprocess.run(
        [
            str(environment / "bin/python"),
            str(runner),
            f"--json_path={smoke_input}",
            f"--output_dir={output_root}",
            f"--model_dir={model_root}",
            "--of3_weights=true",
            "--run_data_pipeline=false",
            "--run_inference=true",
            "--use_msa_server=false",
            "--num_diffusion_samples=1",
            "--num_recycles=1",
            "--flash_attention_implementation=xla",
            "--save_terms_of_use=true",
        ],
        check=False,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            **child_environment,
            "CUDA_VISIBLE_DEVICES": smoke_device,
            "XLA_FLAGS": xla_flags,
            "XLA_PYTHON_CLIENT_PREALLOCATE": "false",
        },
        timeout=3600,
    )
    receipt = output_root / "gpu-smoke-receipt.json"
    receipt.write_text(
        json.dumps(
            {
                "schema_version": "0.1",
                "attention_implementation": "xla",
                "physical_gpu": smoke_device,
                "return_code": completed.returncode,
                "stdout": completed.stdout,
                "stderr": completed.stderr,
                "xla_flags": xla_flags,
                "completed_at": datetime.now(UTC).isoformat(),
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    if completed.returncode != 0:
        hardware_hint = (
            "；当前 GPU 的 shared-memory 不足以运行 tokamax 0.0.12 "
            "无补丁 Triton kernel，请改用兼容 GPU 或另行评审 runtime 契约"
            if "Shared memory size limit exceeded" in completed.stderr
            else ""
        )
        raise ConfigurationError(
            f"OpenFold3 GPU smoke 失败{hardware_hint}；receipt={receipt}"
        )
    return receipt


def install_openfold3_component(
    bundle_path: Path,
    *,
    activate: bool = True,
) -> OpenFold3InstallResult:
    """Verify and install one immutable release, optionally activating it."""

    context = WorkspaceContext.discover()
    context.ensure_layout()
    try:
        bundle, manifest = load_openfold3_bundle(bundle_path)
    except Exception as error:
        rejection = (
            context.runtime_root
            / "quarantine"
            / (
                "openfold3-bundle-rejection-"
                f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')}.json"
            )
        )
        with rejection.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(
                {
                    "schema_version": "0.1",
                    "operation": "openfold3-install-preflight",
                    "bundle": str(bundle_path.expanduser()),
                    "reason": str(error),
                    "recorded_at": datetime.now(UTC).isoformat(),
                    "runtime_profile_changed": False,
                },
                handle,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            handle.write("\n")
        raise
    existing_path = _component_path(context, manifest.release_id)
    if existing_path.is_file():
        existing = verify_openfold3_component(context, release_id=manifest.release_id)
        if (
            existing.release_manifest_sha256
            == sha256_file(bundle / "release-manifest.json")
        ):
            profile_path = _activate_profile(context, existing) if activate else None
            return OpenFold3InstallResult(
                status="already-installed",
                component=existing,
                profile=profile_path,
            )
        raise ConfigurationError("同 release_id 已有不同 identity；禁止覆盖")

    environment_root = (
        context.runtime_root
        / "envs/openfold3-p2-af3-jax"
        / manifest.release_id
        / manifest.environment_lock_sha256
    )
    model_root = (
        context.runtime_root
        / "models/openfold3-p2-af3-jax"
        / manifest.release_id
        / manifest.converted_weight_sha256
    )
    if environment_root.exists() or model_root.exists():
        raise ConfigurationError("未激活的 OpenFold3 immutable target 已存在；拒绝覆盖")

    staging_root = Path(
        tempfile.mkdtemp(
            prefix="openfold3-install-",
            dir=context.runtime_root / "tmp",
        )
    )
    context.assert_write_path(staging_root)
    staging_environment = staging_root / "environment"
    staging_model = staging_root / "model"
    staging_model.mkdir()
    validation = staging_root / "validation"
    validation.mkdir()
    child_environment = context.child_environment()
    try:
        _install_environment(
            bundle=bundle,
            manifest=manifest,
            environment=staging_environment,
            child_environment=child_environment,
        )
        weight_item = manifest.require_role("converted-weight")
        weight = staging_model / "of3_ported_weights.bin.zst"
        shutil.copy2(_bundle_file(bundle, weight_item), weight)
        if sha256_file(weight) != manifest.converted_weight_sha256:
            raise ConfigurationError("staging converted weight SHA-256 不一致")
        runner = _copy_runner(bundle, manifest, staging_model)
        smoke_receipt = _gpu_smoke(
            bundle=bundle,
            manifest=manifest,
            environment=staging_environment,
            runner=runner,
            model_root=staging_model,
            output_root=validation,
            child_environment=child_environment,
        )
        inventory = _write_environment_inventory(
            staging_environment,
            staging_environment / "environment-inventory.txt",
        )
        environment_root.parent.mkdir(parents=True, exist_ok=True)
        model_root.parent.mkdir(parents=True, exist_ok=True)
        staging_environment.rename(environment_root)
        try:
            staging_model.rename(model_root)
        except Exception:
            shutil.move(str(environment_root), str(staging_root / "environment-recovered"))
            raise
        final_validation = model_root / "validation"
        validation.rename(final_validation)
        final_smoke = final_validation / smoke_receipt.name
        receipt = OpenFold3ComponentReceipt(
            release_id=manifest.release_id,
            backend_id=manifest.backend_id,
            backend_version=manifest.backend_version,
            model_id=manifest.model_id,
            adapter_contract_version=manifest.adapter_contract_version,
            installed_at=datetime.now(UTC),
            release_manifest_sha256=sha256_file(bundle / "release-manifest.json"),
            environment_lock_sha256=manifest.environment_lock_sha256,
            environment_root=environment_root,
            environment_inventory=environment_root / inventory.name,
            environment_inventory_sha256=sha256_file(environment_root / inventory.name),
            model_root=model_root,
            converted_weight=model_root / weight.name,
            raw_checkpoint_sha256=manifest.raw_checkpoint_sha256,
            converted_weight_sha256=manifest.converted_weight_sha256,
            wheel_sha256=manifest.wheel_sha256,
            runner_commit=manifest.runner_commit,
            runner_tree_sha256=manifest.runner_tree_sha256,
            conversion_receipt_sha256=manifest.conversion_receipt_sha256,
            runner=model_root / runner.relative_to(staging_model),
            smoke_receipt=final_smoke,
            smoke_receipt_sha256=sha256_file(final_smoke),
        )
        atomic_dump_runtime_model(receipt, existing_path)
        profile_path = _activate_profile(context, receipt) if activate else None
        staging_root.rmdir()
        return OpenFold3InstallResult(
            status="installed",
            component=receipt,
            profile=profile_path,
        )
    except Exception as error:
        if staging_root.exists():
            context.quarantine(
                staging_root,
                operation="openfold3-install",
                reason=str(error),
            )
        raise


def verify_openfold3_component(
    context: WorkspaceContext | None = None,
    *,
    release_id: str,
) -> OpenFold3ComponentReceipt:
    selected = WorkspaceContext.discover() if context is None else context
    receipt = load_latest_runtime_model(
        _component_path(selected, release_id), OpenFold3ComponentReceipt
    )
    checks = (
        (receipt.environment_inventory, receipt.environment_inventory_sha256),
        (receipt.converted_weight, receipt.converted_weight_sha256),
        (receipt.smoke_receipt, receipt.smoke_receipt_sha256),
    )
    for path, expected in checks:
        if not path.is_file() or sha256_file(path) != expected:
            raise ConfigurationError(f"OpenFold3 component identity 已变化: {path}")
    if receipt.release_id != release_id:
        raise ConfigurationError("OpenFold3 component receipt release_id 不一致")
    if not receipt.environment_root.is_dir() or not receipt.runner.is_file():
        raise ConfigurationError("OpenFold3 component 环境或 runner 缺失")
    return receipt


def list_openfold3_components(
    context: WorkspaceContext | None = None,
) -> tuple[OpenFold3ComponentReceipt, ...]:
    selected = WorkspaceContext.discover() if context is None else context
    values: list[OpenFold3ComponentReceipt] = []
    for path in _component_paths(selected):
        values.append(
            verify_openfold3_component(selected, release_id=path.parent.name)
        )
    return tuple(sorted(values, key=lambda item: item.release_id))


def activate_openfold3_release(
    release_id: str,
    *,
    context: WorkspaceContext | None = None,
) -> Path:
    selected = WorkspaceContext.discover() if context is None else context
    receipt = verify_openfold3_component(selected, release_id=release_id)
    return _activate_profile(selected, receipt)


def runtime_status() -> RuntimeStatus:
    context = WorkspaceContext.discover()
    installed = list_openfold3_components(context)
    active = active_openfold3_runtime(context)
    component = (
        next(item for item in installed if item.release_id == active.release_id)
        if active is not None
        else None
    )
    return RuntimeStatus(openfold3=component, openfold3_installed=installed)


__all__ = [
    "OpenFold3ComponentReceipt",
    "OpenFold3InstallResult",
    "OpenFold3ReleaseManifest",
    "RuntimeStatus",
    "activate_openfold3_release",
    "active_openfold3_runtime",
    "install_openfold3_component",
    "list_openfold3_components",
    "load_openfold3_bundle",
    "load_openfold3_validation_receipt",
    "runtime_status",
    "verify_openfold3_component",
]
