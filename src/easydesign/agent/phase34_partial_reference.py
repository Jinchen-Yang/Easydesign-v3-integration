"""Keep verified full predictions when the experimental alignment reference is partial.

The protected complete-target RMSD kernel is unchanged. Its unavailable measurements
remain missing; full-prediction confidence and full-target clashes are retained.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, model_validator

from easydesign.backends.structure_prediction import (
    ComplexStructurePredictionRequest,
    MsaMode,
    TemplateMode,
)
from easydesign.core import ArtifactRef, canonical_model_sha256, dump_model, load_model
from easydesign.filtering import extract_complex_confidence, parse_protein_chain
from easydesign.filtering.structure_metrics import (
    MODERATE_CLASH_ANGSTROM,
    SEVERE_CLASH_ANGSTROM,
    _pairwise_distances,
)
from easydesign.orchestration.complex_prediction_support import (
    configured_prediction_chain,
    prediction_release_identity,
    read_fasta_sequence,
)
from easydesign.orchestration.config import PrecomputedComplexMsaConfig
from easydesign.orchestration.stage05 import _TargetMsaState
from easydesign.orchestration.task_tracking import load_latest_runtime_model
from easydesign.stages.s05_pilot_filtering import FullTargetExecutionState

from .contracts import AgentBoundaryError
from .phase34_contracts import FrozenContract
from .session_store import confined


class PartialReferencePrediction(FrozenContract):
    record_kind: Literal["verified-partial-reference-prediction"] = (
        "verified-partial-reference-prediction"
    )
    candidate_id: str
    strategy_id: str
    seed: Literal[101] = 101
    backend_identity: str
    model_identity: str
    confidence_metric_definition_version: str
    release_identity: dict[str, str]
    predicted_structure: ArtifactRef
    summary_confidence: ArtifactRef
    full_confidence: ArtifactRef
    prediction_input: ArtifactRef
    source_task: ArtifactRef
    reference_target: ArtifactRef
    designed_complex: ArtifactRef
    pairwise_iptm: float
    minimum_interface_pae_angstrom: float = Field(ge=0)
    binder_ptm: float
    binder_pose_rmsd_angstrom: None = None
    target_ca_rmsd_angstrom: None = None
    severe_clash_count: int = Field(ge=0)
    moderate_clash_count: int = Field(ge=0)
    expected_target_residues: int = Field(ge=1)
    observed_reference_ca_residues: int = Field(ge=1)
    unavailable_metric_reasons: dict[str, str]
    metric_collection_failed_attempts: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_missing_alignment(self) -> PartialReferencePrediction:
        if self.observed_reference_ca_residues >= self.expected_target_residues:
            raise ValueError("Partial-reference evidence requires an incomplete observed reference")
        if set(self.unavailable_metric_reasons) != {
            "binder_pose_rmsd_angstrom",
            "target_ca_rmsd_angstrom",
        } or not all(self.unavailable_metric_reasons.values()):
            raise ValueError("Each unavailable alignment metric requires an explicit reason")
        if (
            self.backend_identity.startswith("openfold3-af3-jax@")
            and len(self.release_identity) != 13
        ):
            raise ValueError("Verified AFO prediction requires the complete release identity")
        return self


def verified_chain(chain: Any, sequence: str, *, complete: bool) -> dict[int, str]:
    actual = {r.residue_id: r.one_letter for r in chain.residues}
    if len(actual) != len(chain.residues) or not actual:
        raise AgentBoundaryError("Prediction/reference has empty or duplicate residue identities")
    expected = dict(enumerate(sequence, 1))
    if any(expected.get(i) != aa for i, aa in actual.items()):
        raise AgentBoundaryError(
            "Prediction/reference residue identity contradicts the target sequence"
        )
    if complete and (actual != expected or any(r.ca is None for r in chain.residues)):
        raise AgentBoundaryError(
            "Predicted chain must contain the complete requested sequence and CA atoms"
        )
    return actual


def partial_reference_required(root: Path, upstream: Any) -> bool:
    sequence = read_fasta_sequence(upstream.target_sequence_ref.verify(root))
    reference = parse_protein_chain(upstream.target_structure_ref.verify(root), "A")
    identities = verified_chain(reference, sequence, complete=False)
    partial = len(identities) != len(sequence) or any(r.ca is None for r in reference.residues)
    if partial:
        for candidate in upstream.candidate_index.candidates:
            designed = parse_protein_chain(candidate.refolded_structure.verify(root), "A")
            verified_chain(designed, sequence, complete=False)
    return partial


def _ref(root: Path, path: Path, name: str, fmt: str) -> ArtifactRef:
    path = confined(root, path)
    return ArtifactRef.from_file(
        run_root=root,
        relative_path=path.relative_to(root).as_posix(),
        artifact_id=name,
        role="phase34-verified-prediction-evidence",
        file_format=fmt,
    )


def recover_partial_reference_predictions(
    *,
    root: Path,
    work: Path,
    runtime: Path,
    artifacts: Path,
    upstream: Any,
    prediction_config: Any,
    adapter_builder: Any,
    devices: tuple[int, ...],
) -> tuple[tuple[PartialReferencePrediction, ...], tuple[ArtifactRef, ...]]:
    """Re-collect only a journaled, exit-zero backend output; never start a backend.

    Candidate population, wire input, command identity, sequences, confidence and all
    output paths are checked before a valid prediction is projected. Historical kernel
    task records stay unchanged and are preserved as immutable source evidence.
    """
    if not partial_reference_required(root, upstream):
        raise AgentBoundaryError(
            "Partial-reference recovery requires a verified incomplete reference"
        )
    state = load_latest_runtime_model(runtime / "full-target-state.json", FullTargetExecutionState)
    candidates = {c.candidate_id: c for c in upstream.candidate_index.candidates}
    if set(state.selected_candidate_ids) != set(candidates) or {
        t.strategy_id for t in state.tasks
    } != set(candidates):
        raise AgentBoundaryError("Prediction recovery has a foreign candidate population")
    if any(str(t.status) not in {"succeeded", "failed"} for t in state.tasks):
        raise AgentBoundaryError("Prediction recovery requires terminal worker evidence")
    msa = load_model(work / "target-msa/selected-provider.json", _TargetMsaState)
    target_sequence = read_fasta_sequence(upstream.target_sequence_ref.verify(root))
    if msa.target_sequence_sha256 != hashlib.sha256(target_sequence.encode("ascii")).hexdigest():
        raise AgentBoundaryError("Prediction recovery MSA is bound to another target")
    msa_path = confined(root, artifacts / "target-msa.a3m")
    if (
        hashlib.sha256(msa_path.read_bytes()).hexdigest() != msa.a3m_sha256
        or state.target_msa_sha256 != msa.a3m_sha256
    ):
        raise AgentBoundaryError("Prediction recovery MSA checksum changed")
    target_unpaired = PrecomputedComplexMsaConfig(path=msa_path, sha256=msa.a3m_sha256)
    reference = parse_protein_chain(upstream.target_structure_ref.verify(root), "A")
    records: list[PartialReferencePrediction] = []
    refs: list[ArtifactRef] = []
    for task in state.tasks:
        candidate = candidates[task.strategy_id]
        eligible = [
            a
            for a in task.attempts
            if a.return_code == 0
            and a.error
            and (
                a.error.message == "target CA identity 不完整，不能建立 target-aligned frame"
                or a.error.message.startswith("candidate target CA identity 不完整:")
            )
        ]
        if not eligible:
            continue
        attempt = eligible[0]  # deterministic: first complete backend product, no best-of selection
        if attempt.device not in devices:
            raise AgentBoundaryError("Prediction recovery device differs from the bound execution")
        output = confined(root, root / attempt.output_relative_path)
        expected_output = (
            work
            / "full-target"
            / candidate.candidate_id
            / f"attempt-{attempt.attempt_number:04d}"
            / "output"
        )
        if output != expected_output or output.is_symlink():
            raise AgentBoundaryError(
                "Prediction recovery output is outside its declared candidate attempt"
            )
        candidate_root = output.parent
        binder_sequence = candidate.metrics.get("designed_chain_sequence")
        if not isinstance(binder_sequence, str) or not binder_sequence:
            raise AgentBoundaryError("Prediction recovery lost the candidate binder sequence")
        target = configured_prediction_chain(
            chain_id="A",
            role="target",
            sequence=target_sequence,
            unpaired_msa=target_unpaired,
            paired_msa=prediction_config.target_paired_msa,
            templates=prediction_config.target_templates,
            query_only_root=candidate_root,
            target_condition=None,
        )
        binder = configured_prediction_chain(
            chain_id="B",
            role="binder",
            sequence=binder_sequence,
            unpaired_msa=prediction_config.binder_msa,
            paired_msa=prediction_config.binder_paired_msa,
            templates=prediction_config.binder_templates,
            query_only_root=candidate_root,
            target_condition=None,
        )
        request = ComplexStructurePredictionRequest(
            job_name=candidate.candidate_id,
            chains=(target, binder),
            seeds=(101,),
            sample_count=1,
            msa_mode=MsaMode.DISABLED,
            template_mode=TemplateMode.PRECOMPUTED
            if any(c.template_mode is TemplateMode.PRECOMPUTED for c in (target, binder))
            else TemplateMode.DISABLED,
        )
        remote_providers = tuple(
            source.resolved_providers()[0]
            for source in (
                prediction_config.target_paired_msa,
                prediction_config.binder_msa,
                prediction_config.binder_paired_msa,
            )
            if source.resolved_providers()
        )
        if len(set(remote_providers)) > 1:
            raise AgentBoundaryError("Prediction recovery remote feature providers disagree")
        adapter = adapter_builder(
            remote_providers[0] if remote_providers else msa.provider, attempt.device
        )
        input_path = candidate_root / "input.json"
        if json.loads(input_path.read_text()) != adapter.render_input(request):
            raise AgentBoundaryError(
                "Prediction recovery wire input differs from the approved request"
            )
        remote = None
        prediction_input = input_path
        if any(
            mode is MsaMode.REMOTE
            for chain in request.chains
            for mode in (
                chain.resolved_unpaired_msa_mode(request.msa_mode),
                chain.resolved_paired_msa_mode(request.msa_mode),
            )
        ):
            remote = adapter.msa_invocation(
                request, input_json=input_path, output_dir=candidate_root / "msa-output"
            )
            prediction_input = adapter.updated_msa_input_path(
                input_path, candidate_root / "msa-output"
            )
        invocation = adapter.prediction_invocation(
            request, input_json=prediction_input, output_dir=output
        )
        command_sha = hashlib.sha256(
            json.dumps(
                (remote.argv if remote else (), invocation.argv),
                ensure_ascii=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        if command_sha != attempt.command_sha256:
            raise AgentBoundaryError("Prediction recovery backend command identity changed")
        product = adapter.collect_products(request, output_dir=output)[0]
        if product.full_confidence_path is None:
            raise AgentBoundaryError("Prediction recovery lacks full confidence")
        if any(
            not path.resolve().is_relative_to(output)
            for path in (
                product.structure_path,
                product.confidence_path,
                product.full_confidence_path,
            )
        ):
            raise AgentBoundaryError("Prediction product escapes its declared backend output")
        predicted_target = parse_protein_chain(product.structure_path, "A")
        predicted_binder = parse_protein_chain(product.structure_path, "B")
        verified_chain(predicted_target, target_sequence, complete=True)
        verified_chain(predicted_binder, binder_sequence, complete=True)
        verified_chain(
            parse_protein_chain(candidate.refolded_structure.verify(root), "B"),
            binder_sequence,
            complete=True,
        )
        confidence = extract_complex_confidence(product)
        if confidence.target_token_count != len(
            target_sequence
        ) or confidence.binder_token_count != len(binder_sequence):
            raise AgentBoundaryError(
                "Prediction confidence token identities differ from the requested chains"
            )
        distances = _pairwise_distances(predicted_target.atoms, predicted_binder.atoms)
        task_path = artifacts / f"prediction-source-task-{canonical_model_sha256(task)}.json"
        if task_path.exists():
            if load_model(task_path, type(task)) != task:
                raise AgentBoundaryError("Published prediction task source changed")
        else:
            dump_model(task, task_path)
        record = PartialReferencePrediction(
            candidate_id=candidate.candidate_id,
            strategy_id=candidate.strategy_id,
            backend_identity=product.backend_identity,
            model_identity=product.model_identity,
            confidence_metric_definition_version=confidence.metric_definition_version,
            release_identity=prediction_release_identity(product),
            predicted_structure=_ref(
                root,
                product.structure_path,
                candidate.candidate_id + "-verified-full-prediction",
                "mmcif",
            ),
            summary_confidence=_ref(
                root, product.confidence_path, candidate.candidate_id + "-verified-summary", "json"
            ),
            full_confidence=_ref(
                root,
                product.full_confidence_path,
                candidate.candidate_id + "-verified-confidence",
                "json",
            ),
            prediction_input=_ref(
                root, prediction_input, candidate.candidate_id + "-verified-input", "json"
            ),
            source_task=_ref(root, task_path, candidate.candidate_id + "-source-task", "json"),
            reference_target=upstream.target_structure_ref,
            designed_complex=candidate.refolded_structure,
            pairwise_iptm=confidence.pairwise_iptm,
            minimum_interface_pae_angstrom=confidence.minimum_interface_pae_angstrom,
            binder_ptm=confidence.binder_ptm,
            severe_clash_count=int((distances < SEVERE_CLASH_ANGSTROM).sum()),
            moderate_clash_count=int(
                ((distances >= SEVERE_CLASH_ANGSTROM) & (distances < MODERATE_CLASH_ANGSTROM)).sum()
            ),
            expected_target_residues=len(target_sequence),
            observed_reference_ca_residues=sum(r.ca is not None for r in reference.residues),
            unavailable_metric_reasons={
                name: (
                    "Complete-target alignment reference is unavailable: "
                    "the experimental structure resolves only a verified subset of the target. "
                    "No RMSD was inferred or set to zero."
                )
                for name in ("binder_pose_rmsd_angstrom", "target_ca_rmsd_angstrom")
            },
            metric_collection_failed_attempts=len(eligible),
        )
        records.append(record)
        refs.extend(
            (
                record.predicted_structure,
                record.summary_confidence,
                record.full_confidence,
                record.prediction_input,
                record.source_task,
                record.reference_target,
                record.designed_complex,
            )
        )
    return tuple(records), tuple(refs)
