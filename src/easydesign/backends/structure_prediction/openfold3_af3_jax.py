"""OpenFold3 preview2 weights on a receipt-pinned alphafold3-open JAX runner."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from easydesign.core import (
    BackendContractError,
    ManifestStateError,
    PredictionOutputError,
    RemoteMsaReceipt,
    SerializationError,
    load_model,
    sha256_file,
)

from .contracts import (
    BackendInvocation,
    ComplexConfidenceMetrics,
    ComplexStructurePredictionRequest,
    MsaMode,
    PredictionParameterProfile,
    PredictionRequest,
    ProteinPredictionChain,
    StructurePredictionProduct,
    StructurePredictionRequest,
    TemplateMode,
)

OPENFOLD3_METRIC_DEFINITION_VERSION = (
    "openfold3-p2-af3-jax-complex-confidence-v1"
)


@dataclass(frozen=True, slots=True)
class OpenFold3TemplatePipelineAssets:
    """Receipt-pinned local assets used only by AFO's native DataPipeline."""

    component_receipt: Path
    component_receipt_sha256: str
    hmmbuild: Path
    hmmbuild_sha256: str
    hmmsearch: Path
    hmmsearch_sha256: str
    hmmalign: Path
    hmmalign_sha256: str
    hmmer_version: str
    disabled_msa_search_executable: Path
    disabled_msa_search_executable_sha256: str
    unused_msa_database_sentinel: Path
    unused_msa_database_sentinel_sha256: str
    seqres_database: Path
    seqres_database_sha256: str
    seqres_database_version: str
    mmcif_database: Path
    mmcif_manifest: Path
    mmcif_manifest_sha256: str
    mmcif_database_version: str
    max_template_date: date


class _OpenFold3Summary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="allow")

    ptm: float | None
    iptm: float | None
    ranking_score: float
    fraction_disordered: float
    has_clash: float
    chain_pair_iptm: tuple[tuple[float, ...], ...]
    chain_pair_pae_min: tuple[tuple[float, ...], ...]
    chain_ptm: tuple[float, ...]
    chain_ids: tuple[str, ...] = ()


class _OpenFold3FullConfidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="allow")

    atom_plddts: tuple[float, ...]
    pae: tuple[tuple[float, ...], ...]
    token_chain_ids: tuple[str, ...]


def _read_a3m(path: Path, *, expected_query: str | None = None) -> str:
    if not path.is_absolute() or not path.is_file():
        raise BackendContractError(f"AFO MSA 必须是存在的绝对文件: {path}")
    try:
        value = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise BackendContractError(f"AFO MSA 无法读取: {path}") from error
    if not value.startswith(">") or "\n" not in value:
        raise BackendContractError(f"AFO MSA 不是合法 A3M/FASTA: {path}")
    if expected_query is not None:
        query_parts: list[str] = []
        seen_header = False
        for raw in value.splitlines():
            line = raw.strip()
            if not line:
                continue
            if line.startswith(">"):
                if seen_header:
                    break
                seen_header = True
            elif seen_header:
                query_parts.append(line)
        if "".join(query_parts) != expected_query:
            raise BackendContractError(
                f"AFO MSA query 与 chain sequence 不一致: {path}"
            )
    return value if value.endswith("\n") else value + "\n"


def _read_templates(
    *,
    path: Path,
    expected_sha256: str,
    chain: ProteinPredictionChain,
) -> list[dict[str, Any]]:
    if not path.is_absolute() or not path.is_file():
        raise BackendContractError(
            f"AFO chain={chain.chain_id} template data 必须是存在的绝对文件: {path}"
        )
    if sha256_file(path) != expected_sha256:
        raise BackendContractError(
            f"AFO chain={chain.chain_id} template data SHA-256 不一致"
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise BackendContractError(
            f"AFO chain={chain.chain_id} template data 无法读取"
        ) from error
    if not isinstance(payload, list):
        raise BackendContractError(
            f"AFO chain={chain.chain_id} template data 必须是 JSON list"
        )
    for index, template in enumerate(payload):
        prefix = f"AFO chain={chain.chain_id} template[{index}]"
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
            or any(type(value) is not int for value in (*query_indices, *template_indices))
        ):
            raise BackendContractError(f"{prefix} residue mapping 不合法")
        if (
            len(set(query_indices)) != len(query_indices)
            or any(value < 0 or value >= len(chain.sequence) for value in query_indices)
            or any(value < 0 for value in template_indices)
        ):
            raise BackendContractError(f"{prefix} residue mapping 越界或重复")
    return payload


def _matrix_shape(matrix: tuple[tuple[float, ...], ...]) -> tuple[int, int]:
    if not matrix:
        return (0, 0)
    widths = {len(row) for row in matrix}
    if len(widths) != 1:
        raise PredictionOutputError("AFO confidence matrix 不是矩形")
    return (len(matrix), next(iter(widths)))


class OpenFold3Af3JaxAdapter:
    """File-protocol adapter; never imports JAX or AlphaFold into EasyDesign."""

    backend_name = "openfold3-af3-jax"
    profile_backend_id = "openfold3-af3-jax"

    def __init__(
        self,
        *,
        python: Path,
        runner: Path,
        model_root: Path,
        cache_root: Path,
        release_id: str,
        backend_version: str,
        model_name: str,
        adapter_contract_version: str,
        release_manifest_sha256: str,
        conversion_receipt_sha256: str,
        raw_checkpoint_sha256: str,
        converted_weight_sha256: str,
        wheel_sha256: str,
        environment_lock_sha256: str,
        runner_commit: str,
        runner_tree_sha256: str,
        cuda_visible_devices: str | None = None,
        msa_server_url: str = "https://api.colabfold.com",
        remote_msa_provider: str = "colabfold-public",
        remote_msa_server_mode: str = "colabfold",
        msa_timeout_seconds: int = 3600,
        prediction_timeout_seconds: int = 14_400,
        template_pipeline: OpenFold3TemplatePipelineAssets | None = None,
        extra_environment: tuple[tuple[str, str], ...] = (),
    ) -> None:
        paths = (python, runner, model_root, cache_root)
        if any(not path.is_absolute() for path in paths):
            raise BackendContractError("AFO runtime 必须全部使用绝对路径")
        identities = (
            release_manifest_sha256,
            conversion_receipt_sha256,
            raw_checkpoint_sha256,
            converted_weight_sha256,
            wheel_sha256,
            environment_lock_sha256,
            runner_tree_sha256,
        )
        if any(
            len(value) != 64
            or any(character not in "0123456789abcdef" for character in value)
            for value in identities
        ):
            raise BackendContractError("AFO 资产身份必须是小写 SHA-256")
        if not runner_commit or len(runner_commit) < 7:
            raise BackendContractError("AFO runner commit 不合法")
        if not release_id or not backend_version or not model_name:
            raise BackendContractError("AFO release/version/model identity 不能为空")
        if adapter_contract_version != "openfold3-af3-jax-cli-v1":
            raise BackendContractError(
                f"不支持的 AFO adapter contract: {adapter_contract_version}"
            )
        if min(msa_timeout_seconds, prediction_timeout_seconds) < 1:
            raise BackendContractError("AFO timeout 必须大于 0")
        extra_keys = [key for key, _ in extra_environment]
        reserved = {
            "CUDA_VISIBLE_DEVICES",
            "JAX_PERSISTENT_CACHE_ENABLE_XLA_CACHES",
            "PYTHONDONTWRITEBYTECODE",
            "XLA_FLAGS",
            "XLA_PYTHON_CLIENT_PREALLOCATE",
            "XDG_CACHE_HOME",
        }
        if len(extra_keys) != len(set(extra_keys)) or reserved.intersection(extra_keys):
            raise BackendContractError("AFO extra_environment 重复或覆盖保留变量")
        self.python = python
        self.runner = runner
        self.model_root = model_root
        self.cache_root = cache_root
        self.release_id = release_id
        self.backend_version = backend_version
        self.model_name = model_name
        self.adapter_contract_version = adapter_contract_version
        self.release_manifest_sha256 = release_manifest_sha256
        self.conversion_receipt_sha256 = conversion_receipt_sha256
        self.raw_checkpoint_sha256 = raw_checkpoint_sha256
        self.converted_weight_sha256 = converted_weight_sha256
        self.wheel_sha256 = wheel_sha256
        self.environment_lock_sha256 = environment_lock_sha256
        self.runner_commit = runner_commit
        self.runner_tree_sha256 = runner_tree_sha256
        self.cuda_visible_devices = cuda_visible_devices
        self.msa_server_url = msa_server_url.rstrip("/")
        self.remote_msa_provider = remote_msa_provider
        self.remote_msa_endpoint = self.msa_server_url
        self.remote_msa_server_mode = remote_msa_server_mode
        self.msa_timeout_seconds = msa_timeout_seconds
        self.remote_msa_timeout_seconds = msa_timeout_seconds
        self.prediction_timeout_seconds = prediction_timeout_seconds
        self.template_pipeline = template_pipeline
        self.extra_environment = extra_environment

    def _validated_template_pipeline(self) -> OpenFold3TemplatePipelineAssets:
        assets = self.template_pipeline
        if assets is None:
            raise BackendContractError(
                "AFO frozen template protocol 未注册本地 HMMER/seqres/mmCIF component"
            )
        files = (
            (assets.component_receipt, assets.component_receipt_sha256),
            (assets.hmmbuild, assets.hmmbuild_sha256),
            (assets.hmmsearch, assets.hmmsearch_sha256),
            (assets.hmmalign, assets.hmmalign_sha256),
            (
                assets.disabled_msa_search_executable,
                assets.disabled_msa_search_executable_sha256,
            ),
            (
                assets.unused_msa_database_sentinel,
                assets.unused_msa_database_sentinel_sha256,
            ),
            (assets.seqres_database, assets.seqres_database_sha256),
            (assets.mmcif_manifest, assets.mmcif_manifest_sha256),
        )
        for path, expected in files:
            if not path.is_absolute() or not path.is_file():
                raise BackendContractError(
                    f"AFO template pipeline file 缺失或非绝对路径: {path}"
                )
            if sha256_file(path) != expected:
                raise BackendContractError(
                    f"AFO template pipeline file SHA-256 不一致: {path}"
                )
        if not assets.mmcif_database.is_absolute() or not assets.mmcif_database.is_dir():
            raise BackendContractError(
                f"AFO template mmCIF database 缺失: {assets.mmcif_database}"
            )
        return assets

    def template_pipeline_assets(self) -> OpenFold3TemplatePipelineAssets:
        """Return verified assets for orchestration receipts."""

        return self._validated_template_pipeline()

    def _environment(self) -> tuple[tuple[str, str], ...]:
        values = [
            ("JAX_PERSISTENT_CACHE_ENABLE_XLA_CACHES", "none"),
            ("PYTHONDONTWRITEBYTECODE", "1"),
            ("XLA_FLAGS", "--xla_gpu_enable_triton_gemm=false"),
            ("XLA_PYTHON_CLIENT_PREALLOCATE", "false"),
            ("XDG_CACHE_HOME", str(self.cache_root)),
        ]
        if self.cuda_visible_devices is not None:
            values.append(("CUDA_VISIBLE_DEVICES", self.cuda_visible_devices))
        values.extend(self.extra_environment)
        return tuple(values)

    @staticmethod
    def _protein(
        *,
        chain_id: str,
        sequence: str,
        unpaired_msa_mode: MsaMode,
        paired_msa_mode: MsaMode,
        unpaired_msa_path: Path | None,
        paired_msa_path: Path | None,
        templates: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        protein: dict[str, Any] = {
            "id": chain_id,
            "sequence": sequence,
            "templates": templates or [],
        }
        if unpaired_msa_mode is MsaMode.PRECOMPUTED:
            protein["unpairedMsa"] = (
                _read_a3m(unpaired_msa_path, expected_query=sequence)
                if unpaired_msa_path is not None
                else ""
            )
        elif unpaired_msa_mode is MsaMode.QUERY_ONLY:
            protein["unpairedMsa"] = f">query\n{sequence}\n"
        elif unpaired_msa_mode is MsaMode.DISABLED:
            protein["unpairedMsa"] = ""
        if paired_msa_mode is MsaMode.PRECOMPUTED:
            protein["pairedMsa"] = (
                _read_a3m(paired_msa_path, expected_query=sequence)
                if paired_msa_path is not None
                else ""
            )
        elif paired_msa_mode is MsaMode.QUERY_ONLY:
            protein["pairedMsa"] = f">query\n{sequence}\n"
        elif paired_msa_mode is MsaMode.DISABLED:
            protein["pairedMsa"] = ""
        return {"protein": protein}

    def _legacy_target_templates(
        self,
        request: ComplexStructurePredictionRequest,
    ) -> list[dict[str, Any]]:
        condition = request.target_structure_condition
        if condition is None:
            raise BackendContractError("AFO legacy target template 缺少 condition")
        if sha256_file(condition.snapshot_structure_path) != (
            condition.snapshot_structure_sha256
        ):
            raise BackendContractError("AFO target condition structure SHA-256 不一致")
        if sha256_file(condition.template_data_path) != condition.template_data_sha256:
            raise BackendContractError("AFO target condition template data SHA-256 不一致")
        if sha256_file(condition.template_structure_path) != (
            condition.template_structure_sha256
        ):
            raise BackendContractError(
                "AFO target condition template structure SHA-256 不一致"
            )
        try:
            templates = json.loads(
                condition.template_data_path.read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError) as error:
            raise BackendContractError("AFO target condition template data 无法读取") from error
        if not isinstance(templates, list) or len(templates) != 1:
            raise BackendContractError("AFO target condition 必须恰好一个显式模板")
        template = templates[0]
        if not isinstance(template, dict) or set(template) != {
            "mmcif",
            "queryIndices",
            "templateIndices",
        }:
            raise BackendContractError("AFO target condition template schema 不合法")
        if template["queryIndices"] != list(condition.query_indices) or template[
            "templateIndices"
        ] != list(condition.template_indices):
            raise BackendContractError("AFO target condition residue mapping 不一致")
        if template["mmcif"] != condition.template_structure_path.read_text(
            encoding="utf-8"
        ):
            raise BackendContractError(
                "AFO target condition mmCIF 与 template snapshot 不一致"
            )
        return templates

    def _chain_templates(
        self,
        request: ComplexStructurePredictionRequest,
        chain: ProteinPredictionChain,
    ) -> list[dict[str, Any]]:
        mode = chain.resolved_template_mode(
            request.template_mode,
            legacy_target_condition_available=(
                request.target_structure_condition is not None
            ),
        )
        if mode is TemplateMode.DISABLED:
            return []
        if chain.template_data_path is not None:
            assert chain.template_data_sha256 is not None
            return _read_templates(
                path=chain.template_data_path,
                expected_sha256=chain.template_data_sha256,
                chain=chain,
            )
        if chain.role == "target" and request.target_structure_condition is not None:
            return self._legacy_target_templates(request)
        raise BackendContractError(
            f"AFO chain={chain.chain_id} precomputed template 缺少 data path"
        )

    def _single_templates(
        self,
        request: StructurePredictionRequest,
    ) -> list[dict[str, Any]]:
        if request.template_mode is TemplateMode.DISABLED:
            return []
        path = request.target_template_data_path
        expected_sha256 = request.target_template_data_sha256
        if path is None or expected_sha256 is None:
            raise BackendContractError("AFO Stage 01 precomputed template 缺少 path/SHA")
        chain = ProteinPredictionChain(
            chain_id="A",
            role="target",
            sequence=request.target.sequence,
            template_mode=TemplateMode.PRECOMPUTED,
            template_data_path=path,
            template_data_sha256=expected_sha256,
        )
        return _read_templates(
            path=path,
            expected_sha256=expected_sha256,
            chain=chain,
        )

    @staticmethod
    def _has_remote_msa(request: PredictionRequest) -> bool:
        if not isinstance(request, ComplexStructurePredictionRequest):
            return request.has_remote_msa
        return any(
            mode is MsaMode.REMOTE
            for chain in request.chains
            for mode in (
                chain.resolved_unpaired_msa_mode(request.msa_mode),
                chain.resolved_paired_msa_mode(request.msa_mode),
            )
        )

    @staticmethod
    def _remote_chain_ids(request: PredictionRequest) -> tuple[str, ...]:
        if not isinstance(request, ComplexStructurePredictionRequest):
            return ("A",) if request.has_remote_msa else ()
        return tuple(
            chain.chain_id
            for chain in request.chains
            if MsaMode.REMOTE
            in {
                chain.resolved_unpaired_msa_mode(request.msa_mode),
                chain.resolved_paired_msa_mode(request.msa_mode),
            }
        )

    @staticmethod
    def _chain_feature_metrics(request: PredictionRequest) -> dict[str, str | None]:
        if not isinstance(request, ComplexStructurePredictionRequest):
            return {
                "target_unpaired_msa_mode": str(
                    request.resolved_target_unpaired_msa_mode
                ),
                "target_paired_msa_mode": str(
                    request.resolved_target_paired_msa_mode
                ),
                "binder_unpaired_msa_mode": None,
                "binder_paired_msa_mode": None,
                "target_template_data_sha256": request.target_template_data_sha256,
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

    def render_input(self, request: PredictionRequest) -> dict[str, Any]:
        sequences: list[dict[str, Any]] = []
        if isinstance(request, ComplexStructurePredictionRequest):
            ordered = sorted(
                request.chains,
                key=lambda chain: 0 if chain.role == "target" else 1,
            )
            if [chain.chain_id for chain in ordered] != ["A", "B"]:
                raise BackendContractError("AFO complex 必须固定 target=A、binder=B")
            for chain in ordered:
                sequences.append(
                    self._protein(
                        chain_id=chain.chain_id,
                        sequence=chain.sequence,
                        unpaired_msa_mode=chain.resolved_unpaired_msa_mode(
                            request.msa_mode
                        ),
                        paired_msa_mode=chain.resolved_paired_msa_mode(
                            request.msa_mode
                        ),
                        unpaired_msa_path=chain.unpaired_msa_path,
                        paired_msa_path=chain.paired_msa_path,
                        templates=self._chain_templates(request, chain),
                    )
                )
        else:
            sequences.append(
                self._protein(
                    chain_id="A",
                    sequence=request.target.sequence,
                    unpaired_msa_mode=request.resolved_target_unpaired_msa_mode,
                    paired_msa_mode=request.resolved_target_paired_msa_mode,
                    unpaired_msa_path=request.target_unpaired_msa_path,
                    paired_msa_path=request.target_paired_msa_path,
                    templates=self._single_templates(request),
                )
            )
        return {
            "name": request.job_name,
            "sequences": sequences,
            "modelSeeds": list(request.seeds),
            "dialect": "alphafold3",
            "version": 4,
        }

    def write_input(self, request: PredictionRequest, path: Path) -> Path:
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
            raise ManifestStateError(f"不可覆盖已存在的 AFO 输入: {path}") from error
        return path

    def write_target_template_pipeline_input(
        self,
        *,
        job_name: str,
        target_sequence: str,
        unpaired_msa_path: Path,
        paired_msa_path: Path,
        path: Path,
    ) -> Path:
        """Write the target-only, offline DataPipeline input with templates=null."""

        self._validated_template_pipeline()
        payload = {
            "name": job_name,
            "sequences": [
                {
                    "protein": {
                        "id": "A",
                        "sequence": target_sequence,
                        "unpairedMsa": _read_a3m(
                            unpaired_msa_path,
                            expected_query=target_sequence,
                        ),
                        "pairedMsa": _read_a3m(
                            paired_msa_path,
                            expected_query=target_sequence,
                        ),
                        "templates": None,
                    }
                }
            ],
            "modelSeeds": [101],
            "dialect": "alphafold3",
            "version": 4,
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with path.open("x", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.write("\n")
        except FileExistsError as error:
            raise ManifestStateError(
                f"不可覆盖 AFO target template pipeline 输入: {path}"
            ) from error
        return path

    def target_template_pipeline_invocation(
        self,
        *,
        input_json: Path,
        output_dir: Path,
    ) -> BackendInvocation:
        """Run native AFO DataPipeline locally; inference and network MSA stay off."""

        assets = self._validated_template_pipeline()
        return BackendInvocation(
            backend_name=self.backend_name,
            backend_version=self.backend_version,
            argv=(
                str(self.python),
                str(self.runner),
                f"--json_path={input_json}",
                f"--output_dir={output_dir}",
                f"--model_dir={self.model_root}",
                "--of3_weights=true",
                "--run_data_pipeline=true",
                "--run_inference=false",
                "--use_msa_server=false",
                f"--hmmbuild_binary_path={assets.hmmbuild}",
                f"--hmmsearch_binary_path={assets.hmmsearch}",
                f"--hmmalign_binary_path={assets.hmmalign}",
                "--jackhmmer_binary_path="
                f"{assets.disabled_msa_search_executable}",
                "--nhmmer_binary_path=" f"{assets.disabled_msa_search_executable}",
                "--small_bfd_database_path="
                f"{assets.unused_msa_database_sentinel}",
                "--mgnify_database_path="
                f"{assets.unused_msa_database_sentinel}",
                "--uniprot_cluster_annot_database_path="
                f"{assets.unused_msa_database_sentinel}",
                "--uniref90_database_path="
                f"{assets.unused_msa_database_sentinel}",
                "--ntrna_database_path="
                f"{assets.unused_msa_database_sentinel}",
                "--rfam_database_path="
                f"{assets.unused_msa_database_sentinel}",
                "--rna_central_database_path="
                f"{assets.unused_msa_database_sentinel}",
                f"--seqres_database_path={assets.seqres_database}",
                f"--pdb_database_path={assets.mmcif_database}",
                f"--max_template_date={assets.max_template_date.isoformat()}",
                f"--cache_dir={self.cache_root}",
                "--force_output_dir=true",
            ),
            environment=self._environment(),
            timeout_seconds=self.prediction_timeout_seconds,
        )

    @staticmethod
    def target_template_processed_path(
        *,
        job_name: str,
        output_dir: Path,
    ) -> Path:
        return output_dir / job_name / f"{job_name}_data.json"

    def prepare_precomputed_msa_input(
        self,
        *,
        input_json: Path,
        msa_path: Path,
    ) -> Path:
        try:
            payload = json.loads(input_json.read_text(encoding="utf-8"))
            protein = payload["sequences"][0]["protein"]
            if not isinstance(protein, dict):
                raise TypeError("protein is not a mapping")
        except (OSError, json.JSONDecodeError, KeyError, IndexError, TypeError) as error:
            raise BackendContractError(f"AFO 输入无法更新 MSA: {input_json}") from error
        protein["unpairedMsa"] = _read_a3m(msa_path)
        protein.setdefault("pairedMsa", "")
        updated = input_json.with_name(f"{input_json.stem}-update-msa.json")
        try:
            with updated.open("x", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.write("\n")
        except FileExistsError as error:
            raise ManifestStateError(f"不可覆盖 AFO MSA input: {updated}") from error
        return updated

    def remote_msa_artifacts(
        self,
        *,
        input_json: Path,
        msa_output_dir: Path,
    ) -> tuple[Path, Path]:
        updated, artifacts = self.remote_msa_chain_artifacts(
            input_json=input_json,
            msa_output_dir=msa_output_dir,
            chain_ids=("A",),
        )
        return updated, artifacts["A"]

    def remote_msa_chain_artifacts(
        self,
        *,
        input_json: Path,
        msa_output_dir: Path,
        chain_ids: tuple[str, ...],
    ) -> tuple[Path, dict[str, Path]]:
        if not chain_ids or len(chain_ids) != len(set(chain_ids)):
            raise BackendContractError("AFO remote MSA chain_ids 必须非空且唯一")
        updated = self.updated_msa_input_path(input_json, msa_output_dir)
        sources = {
            chain_id: (
                msa_output_dir
                / input_json.stem
                / f"msas/{chain_id}_unpaired.a3m"
            )
            for chain_id in chain_ids
        }
        missing = [str(path) for path in sources.values() if not path.is_file()]
        if not updated.is_file() or missing:
            raise PredictionOutputError(
                f"AFO MSA 输出缺失: updated={updated}, missing={missing}"
            )
        receipt_path = self.remote_msa_receipt_path(input_json, msa_output_dir)
        try:
            receipt = load_model(receipt_path, RemoteMsaReceipt)
        except (ManifestStateError, SerializationError) as error:
            raise PredictionOutputError("AFO remote MSA receipt 缺失或无效") from error
        if (
            receipt.provider != str(self.remote_msa_provider)
            or receipt.endpoint != self.remote_msa_endpoint
            or receipt.input_json_sha256 != sha256_file(input_json)
            or receipt.processed_json_sha256 != sha256_file(updated)
        ):
            raise PredictionOutputError("AFO remote MSA receipt provider/input identity 不一致")
        receipt_chains = {item.chain_id: item for item in receipt.chains}
        if any(chain_id not in receipt_chains for chain_id in chain_ids):
            raise PredictionOutputError("AFO remote MSA receipt 缺少请求 chain")
        job_root = updated.parent.resolve()
        for chain_id, source in sources.items():
            chain_receipt = receipt_chains[chain_id]
            receipt_source = (job_root / chain_receipt.unpaired_msa_path).resolve()
            if (
                receipt_source != source.resolve()
                or not receipt_source.is_relative_to(job_root)
                or sha256_file(source) != chain_receipt.unpaired_msa_sha256
                or source.stat().st_size != chain_receipt.unpaired_msa_size_bytes
            ):
                raise PredictionOutputError(
                    f"AFO remote MSA receipt chain={chain_id} identity 不一致"
                )
        return updated, sources

    def version_invocation(self) -> BackendInvocation:
        return BackendInvocation(
            backend_name=self.backend_name,
            backend_version=self.backend_version,
            argv=(
                str(self.python),
                "-c",
                "from importlib.metadata import version; print(version('alphafold3-open'))",
            ),
            environment=self._environment(),
            timeout_seconds=30,
        )

    def validate_version_output(self, output: str) -> None:
        if output.strip() != self.backend_version:
            raise BackendContractError(
                "alphafold3-open 版本不匹配: "
                f"expected={self.backend_version}, actual={output.strip()!r}"
            )

    def msa_invocation(
        self,
        request: PredictionRequest,
        *,
        input_json: Path,
        output_dir: Path,
    ) -> BackendInvocation:
        if not self._has_remote_msa(request):
            raise BackendContractError("只有 remote MSA 请求可以调用 ColabFold")
        remote_msa_script = Path(__file__).with_name("openfold3_remote_msa.py").resolve()
        if not remote_msa_script.is_file():
            raise BackendContractError(
                f"AFO remote MSA helper 缺失: {remote_msa_script}"
            )
        return BackendInvocation(
            backend_name=self.backend_name,
            backend_version=self.backend_version,
            argv=(
                str(self.python),
                str(remote_msa_script),
                f"--json_path={input_json}",
                f"--output_dir={output_dir}",
                f"--msa_server_url={self.msa_server_url}",
                f"--provider={self.remote_msa_provider}",
                f"--chain_ids={','.join(self._remote_chain_ids(request))}",
            ),
            environment=self._environment(),
            timeout_seconds=self.msa_timeout_seconds,
        )

    @staticmethod
    def updated_msa_input_path(input_json: Path, msa_output_dir: Path) -> Path:
        return msa_output_dir / input_json.stem / f"{input_json.stem}_data.json"

    @staticmethod
    def remote_msa_receipt_path(input_json: Path, msa_output_dir: Path) -> Path:
        return msa_output_dir / input_json.stem / "remote-msa-receipt.json"

    def prediction_invocation(
        self,
        request: PredictionRequest,
        *,
        input_json: Path,
        output_dir: Path,
    ) -> BackendInvocation:
        if not isinstance(request, ComplexStructurePredictionRequest):
            self._single_templates(request)
        else:
            for chain in request.chains:
                self._chain_templates(request, chain)
        if request.parameter_profile is not PredictionParameterProfile.MODEL_DEFAULT:
            raise BackendContractError("AFO 首版只接受已冻结的 model-default 参数")
        return BackendInvocation(
            backend_name=self.backend_name,
            backend_version=self.backend_version,
            argv=(
                str(self.python),
                str(self.runner),
                f"--json_path={input_json}",
                f"--output_dir={output_dir}",
                f"--model_dir={self.model_root}",
                "--of3_weights=true",
                "--run_data_pipeline=false",
                "--run_inference=true",
                "--use_msa_server=false",
                f"--cache_dir={self.cache_root}",
                f"--num_diffusion_samples={request.sample_count}",
                "--num_recycles=10",
                "--flash_attention_implementation=xla",
                "--save_terms_of_use=true",
                "--force_output_dir=true",
            ),
            environment=self._environment(),
            timeout_seconds=self.prediction_timeout_seconds,
        )

    @staticmethod
    def _complex_confidence(
        summary: _OpenFold3Summary,
        full: _OpenFold3FullConfidence,
    ) -> ComplexConfidenceMetrics:
        chain_count = len(summary.chain_ptm)
        if chain_count != 2:
            raise PredictionOutputError("AFO complex summary 必须恰好包含 A/B 两条链")
        if _matrix_shape(summary.chain_pair_iptm) != (2, 2):
            raise PredictionOutputError("AFO chain_pair_iptm 必须是 2×2")
        token_count = len(full.token_chain_ids)
        if summary.chain_ids:
            summary_chain_order = tuple(dict.fromkeys(summary.chain_ids))
            if summary_chain_order != ("A", "B"):
                raise PredictionOutputError("AFO summary chain 顺序必须为 A/B")
            if len(summary.chain_ids) not in {2, token_count}:
                raise PredictionOutputError(
                    "AFO summary chain_ids 必须是 A/B chain list 或 token-level IDs"
                )
            if (
                len(summary.chain_ids) == token_count
                and summary.chain_ids != full.token_chain_ids
            ):
                raise PredictionOutputError("AFO summary/full token chain IDs 不一致")
        if _matrix_shape(full.pae) != (token_count, token_count):
            raise PredictionOutputError("AFO PAE 必须是 N_token × N_token")
        target_tokens = tuple(
            index for index, chain_id in enumerate(full.token_chain_ids) if chain_id == "A"
        )
        binder_tokens = tuple(
            index for index, chain_id in enumerate(full.token_chain_ids) if chain_id == "B"
        )
        if not target_tokens or not binder_tokens:
            raise PredictionOutputError("AFO full confidence 缺少 A/B token")
        interface_pae = [
            full.pae[first][second]
            for first in target_tokens
            for second in binder_tokens
        ] + [
            full.pae[second][first]
            for first in target_tokens
            for second in binder_tokens
        ]
        values = (
            summary.chain_pair_iptm[0][1],
            summary.chain_ptm[1],
            *interface_pae,
        )
        if any(not math.isfinite(value) for value in values):
            raise PredictionOutputError("AFO complex confidence 包含非有限值")
        return ComplexConfidenceMetrics(
            metric_definition_version=OPENFOLD3_METRIC_DEFINITION_VERSION,
            pairwise_iptm=summary.chain_pair_iptm[0][1],
            minimum_interface_pae_angstrom=min(interface_pae),
            binder_ptm=summary.chain_ptm[1],
            target_token_count=len(target_tokens),
            binder_token_count=len(binder_tokens),
        )

    def collect_products(
        self,
        request: PredictionRequest,
        *,
        output_dir: Path,
    ) -> tuple[StructurePredictionProduct, ...]:
        job_dir = output_dir / request.job_name
        products: list[StructurePredictionProduct] = []
        for seed in request.seeds:
            for sample_index in range(request.sample_count):
                sample_dir = job_dir / f"seed-{seed}_sample-{sample_index}"
                prefix = f"{request.job_name}_seed-{seed}_sample-{sample_index}_"
                structure = sample_dir / f"{prefix}model.cif"
                summary_path = sample_dir / f"{prefix}summary_confidences.json"
                full_path = sample_dir / f"{prefix}confidences.json"
                if not all(path.is_file() for path in (structure, summary_path, full_path)):
                    raise PredictionOutputError(
                        "AFO 正式输出缺失: "
                        f"structure={structure}, summary={summary_path}, full={full_path}"
                    )
                try:
                    summary = _OpenFold3Summary.model_validate_json(
                        summary_path.read_text(encoding="utf-8")
                    )
                    full = _OpenFold3FullConfidence.model_validate_json(
                        full_path.read_text(encoding="utf-8")
                    )
                except (OSError, ValueError) as error:
                    raise SerializationError(
                        f"AFO confidence JSON 无法校验: {sample_dir}"
                    ) from error
                if not full.atom_plddts or any(
                    not math.isfinite(value) for value in full.atom_plddts
                ):
                    raise PredictionOutputError("AFO atom pLDDT 缺失或含非有限值")
                complex_confidence = (
                    self._complex_confidence(summary, full)
                    if isinstance(request, ComplexStructurePredictionRequest)
                    else None
                )
                products.append(
                    StructurePredictionProduct(
                        backend_name=self.backend_name,
                        backend_version=self.backend_version,
                        model_name=self.model_name,
                        seed=seed,
                        sample_index=sample_index,
                        structure_path=structure,
                        structure_sha256=sha256_file(structure),
                        confidence_path=summary_path,
                        confidence_sha256=sha256_file(summary_path),
                        full_confidence_path=full_path,
                        full_confidence_sha256=sha256_file(full_path),
                        plddt=math.fsum(full.atom_plddts) / len(full.atom_plddts),
                        gpde=None,
                        ptm=summary.ptm,
                        iptm=summary.iptm,
                        ranking_score=summary.ranking_score,
                        has_clash=bool(summary.has_clash),
                        recycle_count=10,
                        complex_confidence=complex_confidence,
                        native_metrics={
                            "fraction_disordered": summary.fraction_disordered,
                            "release_id": self.release_id,
                            "backend_id": self.profile_backend_id,
                            "backend_version": self.backend_version,
                            "model_id": self.model_name,
                            "release_manifest_sha256": self.release_manifest_sha256,
                            "adapter_contract_version": self.adapter_contract_version,
                            "conversion_receipt_sha256": self.conversion_receipt_sha256,
                            "raw_checkpoint_sha256": self.raw_checkpoint_sha256,
                            "converted_weight_sha256": self.converted_weight_sha256,
                            "wheel_sha256": self.wheel_sha256,
                            "environment_lock_sha256": self.environment_lock_sha256,
                            "runner_commit": self.runner_commit,
                            "runner_tree_sha256": self.runner_tree_sha256,
                            "msa_provider": (
                                self.remote_msa_provider
                                if self._has_remote_msa(request)
                                else "precomputed"
                            ),
                            "msa_endpoint": (
                                self.remote_msa_endpoint
                                if self._has_remote_msa(request)
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
                            "seeds": ",".join(str(value) for value in request.seeds),
                            "samples_per_seed": request.sample_count,
                            "recycles": 10,
                            "parameter_profile": str(request.parameter_profile),
                        },
                    )
                )
        return tuple(products)


__all__ = [
    "OPENFOLD3_METRIC_DEFINITION_VERSION",
    "OpenFold3Af3JaxAdapter",
]
