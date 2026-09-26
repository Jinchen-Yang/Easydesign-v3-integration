"""Partial experimental references retain full predictions without inventing RMSDs."""

import hashlib
import json
from datetime import UTC, datetime
from types import SimpleNamespace

import gemmi
import pytest
from pydantic import ValidationError

from easydesign.agent.contracts import AgentBoundaryError
from easydesign.agent.phase34_contracts import PilotArmDenominator
from easydesign.agent.phase34_partial_reference import (
    partial_reference_required,
    recover_partial_reference_predictions,
    verified_chain,
)
from easydesign.backends.structure_prediction import ComplexConfidenceMetrics
from easydesign.core import (
    ArtifactRef,
    ProgressSnapshot,
    TaskRecord,
    TaskStatus,
    dump_model,
    sha256_file,
)
from easydesign.orchestration.afo_template_protocol import (
    PROTOCOL_ID,
    AfoBinderTemplateReceipt,
    AfoTargetTemplateReceipt,
    AfoTemplateMappingAudit,
)
from easydesign.orchestration.config import stage05_config_for_backend
from easydesign.orchestration.stage05 import _TargetMsaState
from easydesign.stages.s05_pilot_filtering import FullTargetExecutionState


def cif(rows):
    text = (
        "".join(
            f"ATOM  {n:5d}  CA  ALA {chain}{residue:4d}    "
            f"{x:8.3f}{0:8.3f}{0:8.3f}  1.00 20.00           C\n"
            for n, (chain, residue, x) in enumerate(rows, 1)
        )
        + "END\n"
    )
    structure = gemmi.read_pdb_string(text)
    for chain in structure[0]:
        for residue in chain:
            residue.label_seq = residue.seqid.num
    return structure.make_mmcif_document().as_string()


def setup_partial(tmp_path, *, template_protocol=False):
    runtime, artifacts, work = (tmp_path / name for name in ("runtime", "artifacts", "work"))
    for path in (runtime, artifacts, work):
        path.mkdir()
    reference = tmp_path / "reference.cif"
    reference.write_text(cif([("A", i, 10 * i) for i in (2, 3, 4)]))
    designed = tmp_path / "designed.cif"
    designed.write_text(
        cif([("A", i, 10 * i) for i in (2, 3, 4)] + [("B", 1, 0.5), ("B", 2, 100), ("B", 3, 200)])
    )
    predicted = tmp_path / "predicted.cif"
    predicted.write_text(
        cif(
            [("A", i, 0 if i == 1 else 10 * i) for i in range(1, 6)]
            + [("B", 1, 0.5), ("B", 2, 100), ("B", 3, 200)]
        )
    )
    fasta = tmp_path / "target.fasta"
    fasta.write_text(">target\nAAAAA\n")
    summary, full = tmp_path / "summary.json", tmp_path / "full.json"
    summary.write_text("{}")
    full.write_text("{}")

    def ref(path):
        return ArtifactRef.from_file(
            run_root=tmp_path,
            relative_path=path.name,
            artifact_id=path.stem,
            role="synthetic-test",
            file_format=path.suffix[1:],
        )

    candidate = SimpleNamespace(
        candidate_id="candidate-a",
        strategy_id="arm-a",
        refolded_structure=ref(designed),
        metrics={"designed_chain_sequence": "AAA"},
    )
    upstream = SimpleNamespace(
        target_structure_ref=ref(reference),
        target_sequence_ref=ref(fasta),
        candidate_index=SimpleNamespace(candidates=(candidate,)),
    )
    msa = artifacts / "target-msa.a3m"
    msa.write_text(">query\nAAAAA\n>homolog\nAAAAA\n")
    msa_sha = hashlib.sha256(msa.read_bytes()).hexdigest()
    config = stage05_config_for_backend("openfold3-af3-jax").full_target_prediction
    if not template_protocol:
        config = config.model_copy(update={"template_protocol": "disabled"})
    provider = config.target_msa.resolved_providers()[0]
    dump_model(
        _TargetMsaState(
            provider=provider,
            source_relative_path="declared-test-msa.a3m",
            target_sequence_sha256=hashlib.sha256(b"AAAAA").hexdigest(),
            a3m_sha256=msa_sha,
            depth=2,
        ),
        work / "target-msa/selected-provider.json",
    )
    candidate_root = work / "full-target/candidate-a/attempt-0001"
    candidate_root.mkdir(parents=True)
    output = candidate_root / "output"
    output.mkdir()
    for source in (predicted, summary, full):
        (output / source.name).write_text(source.read_text())
    predicted, summary, full = (output / p.name for p in (predicted, summary, full))
    input_path = candidate_root / "input.json"
    input_path.write_text(json.dumps({"candidate": "candidate-a"}))
    target_receipt_sha256 = None
    if template_protocol:
        target_root = work / "afo-template-protocol/de-novo/target"
        target_root.mkdir(parents=True)
        target_data = target_root / "target-templates.json"
        target_data.write_text('[{"queryIndices":[0]}]\n')
        target_receipt = AfoTargetTemplateReceipt(
            target_sequence_sha256=hashlib.sha256(b"AAAAA").hexdigest(),
            target_unpaired_a3m_sha256=msa_sha,
            target_paired_a3m_sha256="a" * 64,
            source_input_json_sha256="b" * 64,
            processed_json_sha256="c" * 64,
            template_data_sha256=sha256_file(target_data),
            template_count=1,
            templates=(
                AfoTemplateMappingAudit(
                    template_index=0,
                    inline_mmcif_sha256="d" * 64,
                    mapped_residues=1,
                    minimum_query_index=0,
                    maximum_query_index=0,
                ),
            ),
            component_receipt_sha256="e" * 64,
            hmmer_version="3.4",
            hmmbuild_sha256="f" * 64,
            hmmsearch_sha256="1" * 64,
            hmmalign_sha256="2" * 64,
            seqres_database_version="test",
            seqres_database_sha256="3" * 64,
            mmcif_database_version="test",
            mmcif_manifest_sha256="4" * 64,
            max_template_date="2022-09-28",
        )
        target_receipt_path = target_root / "target-template-receipt.json"
        dump_model(target_receipt, target_receipt_path)
        target_receipt_sha256 = sha256_file(target_receipt_path)
        binder_root = candidate_root / "binder-template-protocol"
        binder_root.mkdir()
        binder_data = binder_root / "binder-template.json"
        binder_data.write_text('[{"queryIndices":[0,1,2]}]\n')
        dump_model(
            AfoBinderTemplateReceipt(
                source_stage1_complex_sha256="5" * 64,
                source_chain_id="B",
                binder_sequence_sha256=hashlib.sha256(b"AAA").hexdigest(),
                binder_length=3,
                binder_template_mmcif_sha256="6" * 64,
                binder_template_data_sha256=sha256_file(binder_data),
                mapped_residues=3,
            ),
            binder_root / "binder-template-receipt.json",
        )
    command = ("synthetic-prediction", str(input_path), str(output))
    command_sha = hashlib.sha256(
        json.dumps(((), command), ensure_ascii=True, separators=(",", ":")).encode()
    ).hexdigest()
    now = datetime.now(UTC)
    task = TaskRecord(
        task_id="predict-a",
        strategy_id="candidate-a",
        status=TaskStatus.FAILED,
        requested_candidates=1,
        attempts=(
            {
                "attempt_number": 1,
                "status": "failed",
                "requested_candidates": 1,
                "device": 0,
                "command_sha256": command_sha,
                "output_relative_path": output.relative_to(tmp_path).as_posix(),
                "started_at": now,
                "ended_at": now,
                "return_code": 0,
                "error": {
                    "code": "structure-full-target-failed",
                    "message": "target CA identity 不完整，不能建立 target-aligned frame",
                    "retryable": True,
                },
            },
        ),
    )
    state = FullTargetExecutionState(
        created_at=now,
        updated_at=now,
        target_msa_sha256=msa_sha,
        selected_candidate_ids=("candidate-a",),
        template_protocol_id=PROTOCOL_ID if template_protocol else None,
        target_template_receipt_sha256=target_receipt_sha256,
        tasks=(task,),
        predictions=(),
        progress=ProgressSnapshot(
            stage_id="05-pilot-filtering",
            updated_at=now,
            status="incomplete",
            total_tasks=1,
            pending_tasks=0,
            waiting_tasks=0,
            running_tasks=0,
            succeeded_tasks=0,
            failed_tasks=1,
            planned_candidates=1,
            collected_candidates=0,
        ),
    )
    dump_model(state, runtime / "full-target-state.json")
    product = SimpleNamespace(
        structure_path=predicted,
        confidence_path=summary,
        full_confidence_path=full,
        backend_name="synthetic",
        backend_identity="synthetic@1",
        model_identity="synthetic",
        native_metrics={},
        complex_confidence=ComplexConfidenceMetrics(
            metric_definition_version="synthetic-confidence-v1",
            pairwise_iptm=0.4,
            minimum_interface_pae_angstrom=8.0,
            binder_ptm=0.5,
            target_token_count=5,
            binder_token_count=3,
        ),
    )
    def render_input(request):
        if template_protocol:
            assert request.require_role("target").template_data_sha256 == sha256_file(
                work / "afo-template-protocol/de-novo/target/target-templates.json"
            )
            assert request.require_role("binder").template_data_sha256 == sha256_file(
                candidate_root / "binder-template-protocol/binder-template.json"
            )
        return {"candidate": request.job_name}

    adapter = SimpleNamespace(
        render_input=render_input,
        prediction_invocation=lambda request, **kwargs: SimpleNamespace(argv=command),
        collect_products=lambda request, **kwargs: (product,),
    )
    return (
        dict(
            root=tmp_path,
            work=work,
            runtime=runtime,
            artifacts=artifacts,
            upstream=upstream,
            prediction_config=config,
            adapter_builder=lambda *args: adapter,
            devices=(0,),
        ),
        predicted,
        input_path,
        state,
    )


def test_partial_reference_retains_full_target_clashes_and_missing_rmsd(tmp_path):
    kwargs, _, _, state = setup_partial(tmp_path)
    assert partial_reference_required(tmp_path, kwargs["upstream"])
    records, refs = recover_partial_reference_predictions(**kwargs)
    assert len(records) == 1
    record = records[0]
    assert record.expected_target_residues == 5 and record.observed_reference_ca_residues == 3
    assert record.binder_pose_rmsd_angstrom is None and record.target_ca_rmsd_angstrom is None
    # The sole clash is at target residue 1, absent from the experimental reference.
    assert record.severe_clash_count == 1
    assert record.pairwise_iptm == 0.4 and record.binder_ptm == 0.5
    assert record.metric_collection_failed_attempts == 1
    assert all(ref.verify(tmp_path).is_file() for ref in refs)
    assert recover_partial_reference_predictions(**kwargs) == (records, refs)
    assert (
        json.loads((kwargs["runtime"] / "full-target-state.json").read_text())["tasks"][0]["status"]
        == state.tasks[0].status
    )


def test_partial_reference_recovery_preserves_frozen_template_protocol(tmp_path):
    kwargs, _, _, _ = setup_partial(tmp_path, template_protocol=True)

    records, _ = recover_partial_reference_predictions(**kwargs)

    assert len(records) == 1


def test_recollection_rejects_changed_wire_input_and_true_sequence_conflict(tmp_path):
    kwargs, predicted, input_path, _ = setup_partial(tmp_path)
    input_path.write_text('{"candidate":"foreign"}')
    with pytest.raises(AgentBoundaryError, match="wire input"):
        recover_partial_reference_predictions(**kwargs)
    input_path.write_text('{"candidate":"candidate-a"}')
    structure = gemmi.read_structure(str(predicted))
    structure[0]["A"][0].name = "GLY"
    structure.make_mmcif_document().write_file(str(predicted))
    with pytest.raises(AgentBoundaryError, match="residue identity"):
        recover_partial_reference_predictions(**kwargs)


def test_complete_prediction_requires_all_ca_and_rejects_duplicate_residues():
    def residue(i, ca):
        return SimpleNamespace(residue_id=i, one_letter="A", ca=ca)

    with pytest.raises(AgentBoundaryError, match="complete requested"):
        verified_chain(SimpleNamespace(residues=[residue(1, None)]), "A", complete=True)
    with pytest.raises(AgentBoundaryError, match="duplicate"):
        verified_chain(
            SimpleNamespace(residues=[residue(1, (0, 0, 0)), residue(1, (0, 0, 0))]),
            "A",
            complete=False,
        )


def test_generated_candidate_can_fail_prediction_without_denominator_contradiction():
    values = dict(
        strategy_id="arm-a",
        planned_candidates=1,
        generated_candidates=1,
        valid_execution_products=1,
        predicted_candidates=0,
        metric_evaluable_candidates=1,
        unique_sequences=1,
        legacy_policy_pass_count=0,
        operational_failure_count=1,
        failed_prediction_attempts=1,
    )
    assert PilotArmDenominator(**values).operational_failure_count == 1
    with pytest.raises(ValidationError, match="operational failures exceed"):
        PilotArmDenominator(**{**values, "operational_failure_count": 2})
