"""Protenix 2.0.0 / protenix-v2 的文件协议 adapter。"""

from __future__ import annotations

import json
import os
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
    ProteinPredictionChain,
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
    """只生成/解释文件协议，不在主 ``.venv`` 中导入 Protenix。"""

    backend_name = "protenix"
    profile_backend_id = "protenix-v2"
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
        kalign_binary_path: Path | None = None,
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
        self.kalign_binary_path = kalign_binary_path or (
            self.executable.parent / "kalign"
        )
        if not self.kalign_binary_path.is_absolute():
            raise BackendContractError("kalign binary 必须是绝对路径")
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
                template_path = self._chain_template_path(request, chain)
                if template_path is not None:
                    protein_chain["templatesPath"] = str(template_path)
                sequences.append({"proteinChain": protein_chain})
            return [{"name": request.job_name, "sequences": sequences}]
        if request.template_mode is not TemplateMode.DISABLED:
            raise BackendContractError("Protenix 单链 Stage 01 暂不接受模板")
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

    def _chain_template_path(
        self,
        request: ComplexStructurePredictionRequest,
        chain: ProteinPredictionChain,
    ) -> Path | None:
        mode = chain.resolved_template_mode(
            request.template_mode,
            legacy_target_condition_available=(
                request.target_structure_condition is not None
            ),
        )
        if mode is TemplateMode.DISABLED:
            return None
        if chain.template_data_path is not None:
            assert chain.template_data_sha256 is not None
            self._validate_chain_templates(chain)
            return chain.template_data_path
        if chain.role == "target" and request.target_structure_condition is not None:
            self._validate_target_condition(request)
            return request.target_structure_condition.template_data_path
        raise BackendContractError(
            f"Protenix chain={chain.chain_id} precomputed template 缺少 data path"
        )

    @staticmethod
    def _validate_chain_templates(chain: ProteinPredictionChain) -> None:
        path = chain.template_data_path
        expected_sha256 = chain.template_data_sha256
        if path is None or expected_sha256 is None:
            raise BackendContractError(
                f"Protenix chain={chain.chain_id} template path/SHA 缺失"
            )
        if not path.is_file() or sha256_file(path) != expected_sha256:
            raise BackendContractError(
                f"Protenix chain={chain.chain_id} template data 缺失或 SHA-256 不一致"
            )
        try:
            templates = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise BackendContractError(
                f"Protenix chain={chain.chain_id} template data 无法读取"
            ) from error
        if not isinstance(templates, list):
            raise BackendContractError(
                f"Protenix chain={chain.chain_id} template data 必须是 JSON list"
            )
        for index, template in enumerate(templates):
            prefix = f"Protenix chain={chain.chain_id} template[{index}]"
            if not isinstance(template, dict) or set(template) != {
                "mmcif",
                "queryIndices",
                "templateIndices",
            }:
                raise BackendContractError(f"{prefix} schema 不合法")
            mmcif = template["mmcif"]
            query_indices = template["queryIndices"]
            template_indices = template["templateIndices"]
            if not isinstance(mmcif, str) or not mmcif.strip():
                raise BackendContractError(f"{prefix} mmCIF 不能为空")
            if (
                not isinstance(query_indices, list)
                or not isinstance(template_indices, list)
                or not query_indices
                or len(query_indices) != len(template_indices)
                or any(
                    type(value) is not int
                    for value in (*query_indices, *template_indices)
                )
            ):
                raise BackendContractError(f"{prefix} residue mapping 不合法")
            if (
                len(set(query_indices)) != len(query_indices)
                or any(
                    value < 0 or value >= len(chain.sequence)
                    for value in query_indices
                )
                or any(value < 0 for value in template_indices)
            ):
                raise BackendContractError(f"{prefix} residue mapping 越界或重复")

    def _validate_target_condition(
        self,
        request: ComplexStructurePredictionRequest,
    ) -> None:
        condition = request.target_structure_condition
        if condition is None:
            raise BackendContractError("Protenix target-conditioned 请求缺少 condition")
        if sha256_file(condition.snapshot_structure_path) != (
            condition.snapshot_structure_sha256
        ):
            raise BackendContractError(
                "Protenix target condition structure SHA-256 不一致"
            )
        if sha256_file(condition.template_data_path) != condition.template_data_sha256:
            raise BackendContractError(
                "Protenix target condition template data SHA-256 不一致"
            )
        if sha256_file(condition.template_structure_path) != (
            condition.template_structure_sha256
        ):
            raise BackendContractError(
                "Protenix target condition template structure SHA-256 不一致"
            )
        try:
            templates = json.loads(
                condition.template_data_path.read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError) as error:
            raise BackendContractError(
                "Protenix target condition template data 无法读取"
            ) from error
        if not isinstance(templates, list) or len(templates) != 1:
            raise BackendContractError(
                "Protenix target condition 必须恰好一个显式模板"
            )
        template = templates[0]
        if not isinstance(template, dict) or set(template) != {
            "mmcif",
            "queryIndices",
            "templateIndices",
        }:
            raise BackendContractError("Protenix target condition template schema 不合法")
        if template["queryIndices"] != list(condition.query_indices) or template[
            "templateIndices"
        ] != list(condition.template_indices):
            raise BackendContractError(
                "Protenix target condition residue mapping 不一致"
            )
        if template["mmcif"] != condition.template_structure_path.read_text(
            encoding="utf-8"
        ):
            raise BackendContractError(
                "Protenix target condition mmCIF 与 template snapshot 不一致"
            )

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

    def prepare_precomputed_msa_input(
        self,
        *,
        input_json: Path,
        msa_path: Path,
    ) -> Path:
        """Publish a new Protenix input revision that points at an approved A3M."""

        try:
            payload = json.loads(input_json.read_text(encoding="utf-8"))
            chain = payload[0]["sequences"][0]["proteinChain"]
            if not isinstance(chain, dict):
                raise TypeError("proteinChain is not a mapping")
        except (OSError, json.JSONDecodeError, KeyError, IndexError, TypeError) as error:
            raise BackendContractError(f"Protenix 输入无法更新 MSA: {input_json}") from error
        chain["unpairedMsaPath"] = str(msa_path.resolve())
        updated = input_json.with_name(f"{input_json.stem}-update-msa.json")
        try:
            with updated.open("x", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.write("\n")
        except FileExistsError as error:
            raise ManifestStateError(f"不可覆盖 Protenix MSA input: {updated}") from error
        return updated

    def remote_msa_artifacts(
        self,
        *,
        input_json: Path,
        msa_output_dir: Path,
    ) -> tuple[Path, Path]:
        updated = self.updated_msa_input_path(input_json, msa_output_dir)
        try:
            payload = json.loads(updated.read_text(encoding="utf-8"))
            value = payload[0]["sequences"][0]["proteinChain"]["unpairedMsaPath"]
            if not isinstance(value, str) or not value:
                raise TypeError("unpairedMsaPath is missing")
        except (OSError, json.JSONDecodeError, KeyError, IndexError, TypeError) as error:
            raise PredictionOutputError(f"Protenix MSA updated input 无效: {updated}") from error
        source = Path(value).resolve()
        root = msa_output_dir.resolve()
        if not source.is_relative_to(root) or not source.is_file():
            raise PredictionOutputError(f"Protenix MSA 路径逃出当前输出: {source}")
        return updated, source

    def _environment(self) -> tuple[tuple[str, str], ...]:
        extra_environment = dict(self.extra_environment)
        extra_path = extra_environment.pop("PATH", "")
        path_parts = [str(self.executable.parent)]
        if extra_path:
            path_parts.append(extra_path)
        path_parts.append(os.environ.get("PATH", os.defpath))
        values = [
            ("PROTENIX_ROOT_DIR", str(self.model_root)),
            ("PATH", os.pathsep.join(path_parts)),
        ]
        if self.cuda_visible_devices is not None:
            values.append(("CUDA_VISIBLE_DEVICES", self.cuda_visible_devices))
        values.extend(extra_environment.items())
        return tuple(values)

    def _msa_environment(self) -> tuple[tuple[str, str], ...]:
        return self._environment() + (
            ("MMSEQS_SERVICE_HOST_URL", self.remote_msa_endpoint),
        )

    def validate_version_output(self, output: str) -> None:
        expected = f"protenix, version {self.backend_version}"
        if output.strip() not in {self.backend_version, expected}:
            raise BackendContractError(
                f"Protenix 版本不匹配: expected={expected!r}, actual={output.strip()!r}"
            )

    def version_invocation(self) -> BackendInvocation:
        return BackendInvocation(
            backend_name=self.backend_name,
            backend_version=self.backend_version,
            argv=(
                str(self.executable.parent / "python"),
                "-c",
                (
                    "from importlib.metadata import version; "
                    "print(version('protenix'))"
                ),
            ),
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
        if not self._uses_remote_msa(request):
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
        if not isinstance(request, ComplexStructurePredictionRequest):
            if request.template_mode is not TemplateMode.DISABLED:
                raise BackendContractError("Protenix 单链 Stage 01 禁止模板")
        else:
            for chain in request.chains:
                self._chain_template_path(request, chain)
        uses_msa = self._uses_msa(request)
        uses_templates = self._uses_templates(request)
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
            str(uses_msa).lower(),
            "--use_template",
            str(uses_templates).lower(),
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
        if uses_templates:
            argv.extend(("--kalign_binary_path", str(self.kalign_binary_path)))
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

    @staticmethod
    def _uses_remote_msa(request: PredictionRequest) -> bool:
        if not isinstance(request, ComplexStructurePredictionRequest):
            return request.msa_mode is MsaMode.REMOTE
        return any(
            mode is MsaMode.REMOTE
            for chain in request.chains
            for mode in (
                chain.resolved_unpaired_msa_mode(request.msa_mode),
                chain.resolved_paired_msa_mode(request.msa_mode),
            )
        )

    @staticmethod
    def _uses_msa(request: PredictionRequest) -> bool:
        if not isinstance(request, ComplexStructurePredictionRequest):
            return request.msa_mode is not MsaMode.DISABLED
        return any(
            mode is not MsaMode.DISABLED
            for chain in request.chains
            for mode in (
                chain.resolved_unpaired_msa_mode(request.msa_mode),
                chain.resolved_paired_msa_mode(request.msa_mode),
            )
        )

    @staticmethod
    def _uses_templates(request: PredictionRequest) -> bool:
        if not isinstance(request, ComplexStructurePredictionRequest):
            return request.template_mode is not TemplateMode.DISABLED
        return any(
            chain.resolved_template_mode(
                request.template_mode,
                legacy_target_condition_available=(
                    request.target_structure_condition is not None
                ),
            )
            is not TemplateMode.DISABLED
            for chain in request.chains
        )

    @staticmethod
    def _chain_feature_metrics(request: PredictionRequest) -> dict[str, str | None]:
        if not isinstance(request, ComplexStructurePredictionRequest):
            return {
                "target_unpaired_msa_mode": str(request.msa_mode),
                "target_paired_msa_mode": str(request.msa_mode),
                "binder_unpaired_msa_mode": None,
                "binder_paired_msa_mode": None,
                "target_template_data_sha256": None,
                "binder_template_data_sha256": None,
            }
        target = request.require_role("target")
        binder = request.require_role("binder")
        return {
            "target_unpaired_msa_mode": str(
                target.resolved_unpaired_msa_mode(request.msa_mode)
            ),
            "target_paired_msa_mode": str(
                target.resolved_paired_msa_mode(request.msa_mode)
            ),
            "binder_unpaired_msa_mode": str(
                binder.resolved_unpaired_msa_mode(request.msa_mode)
            ),
            "binder_paired_msa_mode": str(
                binder.resolved_paired_msa_mode(request.msa_mode)
            ),
            "target_template_data_sha256": target.template_data_sha256,
            "binder_template_data_sha256": binder.template_data_sha256,
        }

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
                        native_metrics={
                            "msa_provider": (
                                str(self.remote_msa_provider)
                                if self._uses_remote_msa(request)
                                else "precomputed"
                            ),
                            "msa_endpoint": (
                                self.remote_msa_endpoint
                                if self._uses_remote_msa(request)
                                else None
                            ),
                            "template_mode": str(request.template_mode),
                            "scientific_mode": (
                                str(request.scientific_mode)
                                if isinstance(request, ComplexStructurePredictionRequest)
                                else "de-novo"
                            ),
                            "target_condition_sha256": (
                                request.target_structure_condition.template_data_sha256
                                if isinstance(request, ComplexStructurePredictionRequest)
                                and request.target_structure_condition is not None
                                else None
                            ),
                            "target_condition_source_origin": (
                                request.target_structure_condition.source_origin
                                if isinstance(request, ComplexStructurePredictionRequest)
                                and request.target_structure_condition is not None
                                else None
                            ),
                            "target_condition_self_conditioned": (
                                request.target_structure_condition.is_self_conditioned_for(
                                    self.backend_name
                                )
                                if isinstance(request, ComplexStructurePredictionRequest)
                                and request.target_structure_condition is not None
                                else False
                            ),
                            **self._chain_feature_metrics(request),
                        },
                    )
                )
        return tuple(products)
