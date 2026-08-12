"""Shared file-protocol helpers for Stage 05/07 complex prediction."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from datetime import date
from pathlib import Path
from typing import Literal, cast

from Bio.PDB.MMCIF2Dict import MMCIF2Dict

from easydesign.backends.structure_prediction import (
    BackendInvocation,
    StructurePredictionProduct,
    TargetResidueNumbering,
    TargetStructureCondition,
)
from easydesign.core import (
    ManifestStateError,
    dump_model,
    load_model,
    sha256_file,
)
from easydesign.stages.s01_target_preparation import ResidueMapping, TargetBundle

AFO_RELEASE_IDENTITY_KEYS = (
    "release_id",
    "backend_id",
    "backend_version",
    "model_id",
    "adapter_contract_version",
    "release_manifest_sha256",
    "conversion_receipt_sha256",
    "raw_checkpoint_sha256",
    "converted_weight_sha256",
    "wheel_sha256",
    "environment_lock_sha256",
    "runner_commit",
    "runner_tree_sha256",
)

_TEMPLATE_RELEASE_DATE_FIELD = (
    "_pdbx_audit_revision_history.revision_date"
)
_CONSERVATIVE_TEMPLATE_RELEASE_DATE = date(1970, 1, 1)


def _exclusive_copy_or_verify(source: Path, destination: Path, digest: str) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if not destination.is_file() or sha256_file(destination) != digest:
            raise ManifestStateError(
                f"target condition snapshot 已存在但身份不一致: {destination}"
            )
        return
    temporary = destination.with_name(f".{destination.name}.tmp-{os.getpid()}")
    try:
        with source.open("rb") as source_handle, temporary.open("xb") as output_handle:
            shutil.copyfileobj(source_handle, output_handle)
            output_handle.flush()
            os.fsync(output_handle.fileno())
        if sha256_file(temporary) != digest:
            raise ManifestStateError("target condition snapshot copy SHA-256 不一致")
        temporary.rename(destination)
    finally:
        if temporary.exists():
            temporary.unlink()


def _exclusive_write_or_verify(
    destination: Path,
    content: str,
) -> str:
    """Write a derived snapshot once, or verify the exact existing bytes."""

    encoded = content.encode("utf-8")
    expected = hashlib.sha256(encoded).hexdigest()
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if not destination.is_file() or sha256_file(destination) != expected:
            raise ManifestStateError(
                f"target condition derived snapshot 已存在但身份不一致: {destination}"
            )
        return expected
    temporary = destination.with_name(f".{destination.name}.tmp-{os.getpid()}")
    try:
        with temporary.open("xb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        if sha256_file(temporary) != expected:
            raise ManifestStateError("target condition derived snapshot SHA-256 不一致")
        temporary.rename(destination)
    finally:
        if temporary.exists():
            temporary.unlink()
    return expected


def _template_ready_mmcif(
    source_path: Path,
) -> tuple[str, date, Literal["source-mmcif", "synthetic-conservative"]]:
    """Return a template view with the release-date field required by AF3.

    The canonical Stage 01 structure is never changed.  Imported/generated CIFs
    frequently omit the audit category, so the derived template view receives a
    fixed, deliberately old date that cannot make a structure appear newer than
    it is.  The transformation is explicit in TargetStructureCondition.
    """

    try:
        raw = MMCIF2Dict(str(source_path))  # type: ignore[no-untyped-call]
        source_text = source_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError, ValueError) as error:
        raise ManifestStateError("Stage 01 target mmCIF 无法读取") from error
    observed = raw.get(_TEMPLATE_RELEASE_DATE_FIELD)
    values = [observed] if isinstance(observed, str) else list(observed or ())
    parsed: list[date] = []
    for value in values:
        try:
            parsed.append(date.fromisoformat(str(value)))
        except ValueError:
            continue
    if parsed:
        return source_text, min(parsed), "source-mmcif"
    lines = source_text.splitlines(keepends=True)
    header_index = next(
        (index for index, line in enumerate(lines) if line.startswith("data_")),
        None,
    )
    if header_index is None:
        raise ManifestStateError("Stage 01 target mmCIF 缺少 data_ header")
    release_date = _CONSERVATIVE_TEMPLATE_RELEASE_DATE.isoformat()
    lines.insert(
        header_index + 1,
        f"{_TEMPLATE_RELEASE_DATE_FIELD} {release_date}\n",
    )
    return "".join(lines), _CONSERVATIVE_TEMPLATE_RELEASE_DATE, (
        "synthetic-conservative"
    )


def snapshot_target_structure_condition(
    *,
    run_root: Path,
    snapshot_root: Path,
    target_bundle: TargetBundle,
) -> TargetStructureCondition:
    """Freeze the Stage 01 target and residue mapping for exact resume."""

    resolved_run = run_root.resolve()
    resolved_snapshot = snapshot_root.resolve()
    if not resolved_snapshot.is_relative_to(resolved_run):
        raise ManifestStateError("target condition snapshot 必须位于当前 run 内")
    condition_path = resolved_snapshot / "condition.json"
    source_structure = target_bundle.target_structure.verify(resolved_run)
    source_mapping = target_bundle.residue_mapping.verify(resolved_run)
    source_provenance = target_bundle.provenance.verify(resolved_run)
    if condition_path.exists():
        condition = load_model(condition_path, TargetStructureCondition)
        if (
            condition.source_structure_sha256 != target_bundle.target_structure.sha256
            or condition.snapshot_structure_sha256
            != target_bundle.target_structure.sha256
        ):
            raise ManifestStateError("resume target condition 与 Stage 01 structure 不一致")
        if sha256_file(condition.snapshot_structure_path) != (
            condition.snapshot_structure_sha256
        ):
            raise ManifestStateError("resume target condition structure 已损坏")
        if sha256_file(condition.template_data_path) != condition.template_data_sha256:
            raise ManifestStateError("resume target condition template data 已损坏")
        if sha256_file(condition.template_structure_path) != (
            condition.template_structure_sha256
        ):
            raise ManifestStateError("resume target condition template structure 已损坏")
        if sha256_file(condition.binder_template_data_path) != (
            condition.binder_template_data_sha256
        ):
            raise ManifestStateError("resume binder empty-template data 已损坏")
        if (
            condition.snapshot_pdb_path is not None
            and condition.snapshot_pdb_sha256 is not None
            and sha256_file(condition.snapshot_pdb_path)
            != condition.snapshot_pdb_sha256
        ):
            raise ManifestStateError("resume target condition PDB snapshot 已损坏")
        return condition

    mapping = load_model(source_mapping, ResidueMapping)
    representative = (
        target_bundle.coordinate_ensemble.representative_model_id
        if target_bundle.coordinate_ensemble is not None
        else "1"
    )
    present = tuple(
        entry
        for entry in mapping.entries
        if not entry.model_presence or representative in entry.model_presence
    )
    if not present:
        raise ManifestStateError("Stage 01 target condition 没有可映射残基")
    chain_ids = {entry.label_chain_id for entry in present}
    if len(chain_ids) != 1:
        raise ManifestStateError(
            f"target condition 需要恰好一条 template chain: {sorted(chain_ids)}"
        )
    template_chain_id = next(iter(chain_ids))
    query_indices = tuple(entry.sequence_index - 1 for entry in present)
    template_indices = tuple(entry.label_seq_id - 1 for entry in present)
    mapped = set(query_indices)
    missing_query_indices = tuple(
        index for index in range(target_bundle.sequence_length) if index not in mapped
    )
    numbering = tuple(
        TargetResidueNumbering(
            sequence_index=entry.sequence_index,
            query_index=entry.sequence_index - 1,
            template_index=entry.label_seq_id - 1,
            label_seq_id=entry.label_seq_id,
            author_chain_id=entry.author_chain_id,
            author_residue_id=entry.author_residue_id,
            insertion_code=entry.insertion_code,
        )
        for entry in present
    )
    snapshot_structure = resolved_snapshot / "target.cif"
    _exclusive_copy_or_verify(
        source_structure,
        snapshot_structure,
        target_bundle.target_structure.sha256,
    )
    snapshot_pdb: Path | None = None
    snapshot_pdb_sha256: str | None = None
    if target_bundle.target_pdb is not None:
        source_pdb = target_bundle.target_pdb.verify(resolved_run)
        snapshot_pdb = resolved_snapshot / "target.pdb"
        _exclusive_copy_or_verify(
            source_pdb,
            snapshot_pdb,
            target_bundle.target_pdb.sha256,
        )
        snapshot_pdb_sha256 = target_bundle.target_pdb.sha256
    try:
        provenance_payload = json.loads(source_provenance.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ManifestStateError("Stage 01 target provenance 无法读取") from error
    source_backend_name: str | None = None
    if str(target_bundle.origin) == "predicted":
        value = provenance_payload.get("backend_name")
        if not isinstance(value, str) or not value:
            raise ManifestStateError("predicted Stage 01 target 缺少 backend provenance")
        source_backend_name = value
    template_mmcif, template_release_date, template_release_date_source = (
        _template_ready_mmcif(snapshot_structure)
    )
    template_structure = resolved_snapshot / "target-template.cif"
    template_structure_sha256 = _exclusive_write_or_verify(
        template_structure,
        template_mmcif,
    )
    template_data = resolved_snapshot / "target-template.json"
    template_payload = [
        {
            "mmcif": template_mmcif,
            "queryIndices": list(query_indices),
            "templateIndices": list(template_indices),
        }
    ]
    template_data.parent.mkdir(parents=True, exist_ok=True)
    try:
        with template_data.open("x", encoding="utf-8") as handle:
            json.dump(
                template_payload,
                handle,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as error:
        raise ManifestStateError(
            f"不可覆盖 target condition template data: {template_data}"
        ) from error
    binder_template_data = resolved_snapshot / "binder-no-templates.json"
    binder_template_data_sha256 = _exclusive_write_or_verify(
        binder_template_data,
        "[]\n",
    )
    condition = TargetStructureCondition(
        source_origin=cast(
            Literal["experimental", "imported", "predicted"],
            str(target_bundle.origin),
        ),
        source_structure_kind=cast(
            Literal["experimental", "predicted", "imported-unknown"],
            {
                "experimental": "experimental",
                "predicted": "predicted",
                "imported": "imported-unknown",
            }[str(target_bundle.origin)],
        ),
        source_backend_name=source_backend_name,
        source_structure_sha256=target_bundle.target_structure.sha256,
        snapshot_structure_path=snapshot_structure,
        snapshot_structure_sha256=sha256_file(snapshot_structure),
        snapshot_pdb_path=snapshot_pdb,
        snapshot_pdb_sha256=snapshot_pdb_sha256,
        template_structure_path=template_structure,
        template_structure_sha256=template_structure_sha256,
        template_release_date=template_release_date,
        template_release_date_source=template_release_date_source,
        template_data_path=template_data,
        template_data_sha256=sha256_file(template_data),
        binder_template_data_path=binder_template_data,
        binder_template_data_sha256=binder_template_data_sha256,
        run_snapshot_relative_path=resolved_snapshot.relative_to(resolved_run).as_posix(),
        template_chain_id=template_chain_id,
        query_indices=query_indices,
        template_indices=template_indices,
        missing_query_indices=missing_query_indices,
        residue_numbering=numbering,
    )
    dump_model(condition, condition_path)
    return condition


def prediction_release_identity(product: StructurePredictionProduct) -> dict[str, str]:
    """Extract the complete immutable AFO identity; Protenix returns an empty mapping."""

    values = {
        key: str(product.native_metrics[key])
        for key in AFO_RELEASE_IDENTITY_KEYS
        if isinstance(product.native_metrics.get(key), str)
    }
    if product.backend_name == "openfold3-af3-jax" and set(values) != set(
        AFO_RELEASE_IDENTITY_KEYS
    ):
        missing = sorted(set(AFO_RELEASE_IDENTITY_KEYS) - set(values))
        raise ManifestStateError(f"AFO prediction 缺少完整 release identity: {missing}")
    return values


def read_fasta_sequence(path: Path) -> str:
    lines = [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith(">")
    ]
    sequence = "".join(lines).upper()
    if not sequence:
        raise ManifestStateError("target sequence artifact 为空")
    return sequence


def prepare_query_only_a3m(sequence: str, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    expected = f">query\n{sequence}\n"
    if path.exists():
        if path.read_text(encoding="ascii") != expected:
            raise ManifestStateError(f"query-only MSA 已存在但 sequence 不一致: {path}")
    else:
        path.write_text(expected, encoding="ascii")
    return path.resolve()


def run_checked_backend_invocation(
    invocation: BackendInvocation,
) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment.update(dict(invocation.environment))
    try:
        completed = subprocess.run(
            list(invocation.argv),
            check=False,
            capture_output=True,
            text=True,
            timeout=invocation.timeout_seconds,
            env=environment,
        )
    except subprocess.TimeoutExpired as error:
        raise ManifestStateError(
            f"backend invocation timeout: {invocation.backend_name}"
        ) from error
    if completed.returncode != 0:
        raise ManifestStateError(
            f"backend invocation failed: {invocation.backend_name}, "
            f"returncode={completed.returncode}, stderr={completed.stderr[-2048:]}"
        )
    return completed
