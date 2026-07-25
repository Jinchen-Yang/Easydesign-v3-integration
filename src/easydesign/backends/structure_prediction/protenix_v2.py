"""Protenix 2.0.0 / protenix-v2 的文件协议 adapter。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field

from easydesign.core import (
    BackendContractError,
    ManifestStateError,
    PredictionOutputError,
    SerializationError,
    sha256_file,
)

from .contracts import (
    BackendInvocation,
    ComplexStructurePredictionRequest,
    MsaMode,
    PredictionParameterProfile,
    PredictionRequest,
    StructurePredictionProduct,
    TemplateMode,
)


class ProtenixMsaProvider(StrEnum):
    """Protenix 2.0.0 remote-MSA 服务身份；名称不能代替实际 endpoint。"""

    COLABFOLD_PUBLIC = "colabfold-public"
    PROTENIX_OFFICIAL = "protenix-official"
    CUSTOM_COLABFOLD = "custom-colabfold"


@dataclass(frozen=True, slots=True)
class ResolvedProtenixMsaProvider:
    provider: ProtenixMsaProvider
    endpoint: str
    server_mode: str


_COLABFOLD_PUBLIC_ENDPOINT = "https://api.colabfold.com"
_PROTENIX_OFFICIAL_ENDPOINT = "https://protenix-server.com/api/msa"


def resolve_protenix_msa_provider(
    provider: ProtenixMsaProvider,
    *,
    custom_endpoint: str | None = None,
) -> ResolvedProtenixMsaProvider:
    """把 provider preset 解析成不可含糊的 endpoint 与 Protenix parser mode。"""

    if provider is ProtenixMsaProvider.COLABFOLD_PUBLIC:
        if custom_endpoint is not None:
            raise BackendContractError("colabfold-public 使用固定 endpoint，不能覆盖")
        endpoint = _COLABFOLD_PUBLIC_ENDPOINT
        server_mode = "colabfold"
    elif provider is ProtenixMsaProvider.PROTENIX_OFFICIAL:
        if custom_endpoint is not None:
            raise BackendContractError("protenix-official 使用固定 endpoint，不能覆盖")
        endpoint = _PROTENIX_OFFICIAL_ENDPOINT
        server_mode = "protenix"
    else:
        if custom_endpoint is None:
            raise BackendContractError("custom-colabfold 必须显式提供 endpoint")
        parsed = urlsplit(custom_endpoint)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise BackendContractError(
                "custom-colabfold endpoint 必须是完整 http/https URL"
            )
        if (
            parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise BackendContractError(
                "custom-colabfold endpoint 不能内嵌凭据、query 或 fragment"
            )
        endpoint = custom_endpoint.rstrip("/")
        server_mode = "colabfold"
    return ResolvedProtenixMsaProvider(
        provider=provider,
        endpoint=endpoint,
        server_mode=server_mode,
    )


class _ProtenixConfidence(BaseModel):
    model_config = ConfigDict(extra="ignore")

    plddt: float
    gpde: float
    ptm: float
    iptm: float
    ranking_score: float
    has_clash: bool
    num_recycles: int = Field(ge=0)


class ProtenixV2Adapter:
    """只生成/解释文件协议，不在 easydesign-core 中导入 Protenix。"""

    backend_name = "protenix"
    backend_version = "2.0.0"
    model_name = "protenix-v2"

    def __init__(
        self,
        *,
        executable: Path,
        model_root: Path,
        cuda_visible_devices: str | None = None,
        remote_msa_provider: ProtenixMsaProvider = (
            ProtenixMsaProvider.COLABFOLD_PUBLIC
        ),
        remote_msa_endpoint: str | None = None,
        remote_msa_timeout_seconds: int = 1800,
        prediction_timeout_seconds: int = 7200,
        extra_environment: tuple[tuple[str, str], ...] = (),
    ) -> None:
        if not executable.is_absolute() or not model_root.is_absolute():
            raise BackendContractError("executable 和 model_root 必须由 profile 提供绝对路径")
        if remote_msa_timeout_seconds < 1:
            raise BackendContractError("remote MSA timeout 必须大于 0")
        if prediction_timeout_seconds < 1:
            raise BackendContractError("prediction timeout 必须大于 0")
        resolved_msa = resolve_protenix_msa_provider(
            remote_msa_provider,
            custom_endpoint=remote_msa_endpoint,
        )
        reserved = {
            "PROTENIX_ROOT_DIR",
            "CUDA_VISIBLE_DEVICES",
            "MMSEQS_SERVICE_HOST_URL",
        }
        extra_keys = [key for key, _ in extra_environment]
        if len(extra_keys) != len(set(extra_keys)):
            raise BackendContractError("extra_environment 变量名不能重复")
        if reserved.intersection(extra_keys):
            raise BackendContractError(
                "extra_environment 不能覆盖 PROTENIX_ROOT_DIR、CUDA_VISIBLE_DEVICES "
                "或 MMSEQS_SERVICE_HOST_URL"
            )
        self.executable = executable
        self.model_root = model_root
        self.cuda_visible_devices = cuda_visible_devices
        self.remote_msa_provider = resolved_msa.provider
        self.remote_msa_endpoint = resolved_msa.endpoint
        self.remote_msa_server_mode = resolved_msa.server_mode
        self.remote_msa_timeout_seconds = remote_msa_timeout_seconds
        self.prediction_timeout_seconds = prediction_timeout_seconds
        self.extra_environment = extra_environment

    def render_input(self, request: PredictionRequest) -> list[dict[str, Any]]:
        if isinstance(request, ComplexStructurePredictionRequest):
            sequences: list[dict[str, Any]] = []
            for chain in request.chains:
                protein_chain: dict[str, Any] = {
                    "sequence": chain.sequence,
                    "count": 1,
                }
                if chain.paired_msa_path is not None:
                    protein_chain["pairedMsaPath"] = str(chain.paired_msa_path)
                if chain.unpaired_msa_path is not None:
                    protein_chain["unpairedMsaPath"] = str(
                        chain.unpaired_msa_path
                    )
                sequences.append({"proteinChain": protein_chain})
            return [{"name": request.job_name, "sequences": sequences}]
        return [
            {
                "name": request.job_name,
                "sequences": [
                    {
                        "proteinChain": {
                            "sequence": request.target.sequence,
                            "count": 1,
                        }
                    }
                ],
            }
        ]

    def write_input(self, request: PredictionRequest, path: Path) -> Path:
        """排他写入 Protenix JSON；已有请求不可覆盖。"""

        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with path.open("x", encoding="utf-8") as handle:
                json.dump(
                    self.render_input(request),
                    handle,
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
                handle.write("\n")
        except FileExistsError as error:
            raise ManifestStateError(f"不可覆盖已存在的 Protenix 输入: {path}") from error
        return path

    def _environment(self) -> tuple[tuple[str, str], ...]:
        values = [("PROTENIX_ROOT_DIR", str(self.model_root))]
        if self.cuda_visible_devices is not None:
            values.append(("CUDA_VISIBLE_DEVICES", self.cuda_visible_devices))
        values.extend(self.extra_environment)
        return tuple(values)

    def _msa_environment(self) -> tuple[tuple[str, str], ...]:
        return self._environment() + (
            ("MMSEQS_SERVICE_HOST_URL", self.remote_msa_endpoint),
        )

    def validate_version_output(self, output: str) -> None:
        expected = f"protenix, version {self.backend_version}"
        if expected not in output.strip():
            raise BackendContractError(
                f"Protenix 版本不匹配: expected={expected!r}, actual={output.strip()!r}"
            )

    def version_invocation(self) -> BackendInvocation:
        return BackendInvocation(
            backend_name=self.backend_name,
            backend_version=self.backend_version,
            argv=(str(self.executable), "--version"),
            environment=self._environment(),
            timeout_seconds=30,
        )

    def msa_invocation(
        self,
        request: PredictionRequest,
        *,
        input_json: Path,
        output_dir: Path,
    ) -> BackendInvocation:
        if request.msa_mode is not MsaMode.REMOTE:
            raise BackendContractError("只有 remote MSA 请求可以创建远程 MSA 调用")
        return BackendInvocation(
            backend_name=self.backend_name,
            backend_version=self.backend_version,
            argv=(
                str(self.executable),
                "msa",
                "--input",
                str(input_json),
                "--out_dir",
                str(output_dir),
                "--msa_server_mode",
                self.remote_msa_server_mode,
            ),
            environment=self._msa_environment(),
            timeout_seconds=self.remote_msa_timeout_seconds,
        )

    @staticmethod
    def updated_msa_input_path(input_json: Path, msa_output_dir: Path) -> Path:
        del msa_output_dir
        return input_json.with_name(f"{input_json.stem}-update-msa.json")

    def prediction_invocation(
        self,
        request: PredictionRequest,
        *,
        input_json: Path,
        output_dir: Path,
    ) -> BackendInvocation:
        if request.template_mode is not TemplateMode.DISABLED:
            raise BackendContractError(
                "Protenix-v2 首个 EasyDesign adapter 只实现 template disabled"
            )
        argv = [
            str(self.executable),
            "pred",
            "--input",
            str(input_json),
            "--out_dir",
            str(output_dir),
            "--seeds",
            ",".join(str(seed) for seed in request.seeds),
            "--sample",
            str(request.sample_count),
            "--dtype",
            "bf16",
            "--model_name",
            self.model_name,
            "--use_msa",
            str(request.msa_mode is not MsaMode.DISABLED).lower(),
            "--use_template",
            str(request.template_mode is not TemplateMode.DISABLED).lower(),
            "--use_rna_msa",
            "false",
            "--trimul_kernel",
            "cuequivariance",
            "--triatt_kernel",
            "cuequivariance",
            "--enable_cache",
            "true",
            "--enable_fusion",
            "true",
            "--enable_tf32",
            "true",
            "--need_atom_confidence",
            str(request.require_full_confidence).lower(),
        ]
        if request.parameter_profile is PredictionParameterProfile.MODEL_DEFAULT:
            argv.extend(("--use_default_params", "true"))
        else:
            argv.extend(
                (
                    "--use_default_params",
                    "false",
                    "--cycle",
                    str(request.cycle_count),
                    "--step",
                    str(request.diffusion_step_count),
                )
            )
        return BackendInvocation(
            backend_name=self.backend_name,
            backend_version=self.backend_version,
            argv=tuple(argv),
            environment=self._environment(),
            timeout_seconds=self.prediction_timeout_seconds,
        )

    def collect_products(
        self,
        request: PredictionRequest,
        *,
        output_dir: Path,
    ) -> tuple[StructurePredictionProduct, ...]:
        """按 Protenix 2.0.0 的确定性目录协议收集全部 seed/sample。"""

        error_dir = output_dir / "ERR"
        if error_dir.is_dir() and any(error_dir.iterdir()):
            raise PredictionOutputError(f"Protenix ERR 目录非空: {error_dir}")

        products: list[StructurePredictionProduct] = []
        for seed in request.seeds:
            prediction_dir = (
                output_dir / request.job_name / f"seed_{seed}" / "predictions"
            )
            for sample_index in range(request.sample_count):
                prefix = f"{request.job_name}_sample_{sample_index}"
                structure_path = prediction_dir / f"{prefix}.cif"
                confidence_path = (
                    prediction_dir
                    / f"{request.job_name}_summary_confidence_sample_{sample_index}.json"
                )
                full_confidence_path = (
                    prediction_dir
                    / f"{request.job_name}_full_data_sample_{sample_index}.json"
                )
                if not structure_path.is_file() or not confidence_path.is_file():
                    raise PredictionOutputError(
                        "Protenix 正式输出缺失: "
                        f"structure={structure_path}, confidence={confidence_path}"
                    )
                if request.require_full_confidence and not full_confidence_path.is_file():
                    raise PredictionOutputError(
                        "Protenix full confidence 正式输出缺失: "
                        f"{full_confidence_path}"
                    )
                try:
                    confidence = _ProtenixConfidence.model_validate_json(
                        confidence_path.read_text(encoding="utf-8")
                    )
                except (OSError, ValueError) as error:
                    raise SerializationError(
                        f"Protenix confidence JSON 无法校验: {confidence_path}"
                    ) from error
                products.append(
                    StructurePredictionProduct(
                        backend_name=self.backend_name,
                        backend_version=self.backend_version,
                        model_name=self.model_name,
                        seed=seed,
                        sample_index=sample_index,
                        structure_path=structure_path,
                        structure_sha256=sha256_file(structure_path),
                        confidence_path=confidence_path,
                        confidence_sha256=sha256_file(confidence_path),
                        full_confidence_path=(
                            full_confidence_path
                            if request.require_full_confidence
                            else None
                        ),
                        full_confidence_sha256=(
                            sha256_file(full_confidence_path)
                            if request.require_full_confidence
                            else None
                        ),
                        plddt=confidence.plddt,
                        gpde=confidence.gpde,
                        ptm=confidence.ptm,
                        iptm=confidence.iptm,
                        ranking_score=confidence.ranking_score,
                        has_clash=confidence.has_clash,
                        recycle_count=confidence.num_recycles,
                    )
                )
        return tuple(products)
