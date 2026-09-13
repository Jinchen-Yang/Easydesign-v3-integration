"""Typed, project-bound adapters to existing science; no new scientific execution engine."""

from __future__ import annotations

import asyncio
import contextvars
import json
import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml  # type: ignore[import-untyped]

from easydesign.backends.target_sources.structure import inventory_structure
from easydesign.core import (
    ArtifactRef,
    DecisionRequest,
    ExecutionStatus,
    RunManifest,
    StageManifest,
    canonical_model_sha256,
    load_model,
    sha256_file,
)
from easydesign.core.target_identity import TargetIdentityReport
from easydesign.orchestration.application import show_run
from easydesign.orchestration.config import (
    EasyDesignRunConfig,
    LoadedStructureRunConfig,
    LocalFileSourceConfig,
    load_run_config,
)
from easydesign.orchestration.decisions import load_decision_record_context, load_pending_decision
from easydesign.orchestration.local_jobs import (
    ACTIVE_JOB_STATUSES,
    LocalStepJob,
    LocalStepJobController,
)
from easydesign.orchestration.local_project import (
    project_config_path,
    resolve_project_path,
    resolve_project_run,
)
from easydesign.orchestration.research import target_approve, target_prepare
from easydesign.orchestration.workspace import load_resolved_run_config
from easydesign.reporting.target_viewer import resolve_latest_target_viewer_report
from easydesign.stages.s01_target_preparation.models import ResidueMapping, TargetBundle
from easydesign.workspace_context import WorkspaceContext

from .contracts import (
    AgentBoundaryError,
    ApplyDecision,
    DecisionCard,
    DecisionOutcome,
    EmptyArguments,
    EvidenceAssessment,
    EvidenceBinding,
    EvidenceQuery,
    JudgeVerdict,
    ReconciliationRequired,
    TargetProvenance,
)
from .session_store import SessionStore, confined, identity

STAGE = "01-target-preparation"
LIMITATIONS = [
    "Canonical biological identity is unconfirmed; "
    "species, isoform and native construct are not established.",
    "Reference completeness is unknown. Chain selection does not confirm biological identity.",
    "Structural preparation and quality are not evidence of affinity or function.",
]
JUDGE_EVIDENCE: contextvars.ContextVar[EvidenceBinding | None] = contextvars.ContextVar(
    "judge_evidence", default=None
)


@contextmanager
def scientific_environment() -> Iterator[None]:
    """Legacy workers inherit os.environ; remove model secrets at that boundary."""
    hidden = {
        key: value
        for key, value in os.environ.items()
        if key.endswith(("API_KEY", "API_TOKEN"))
        or key in {"LANGSMITH_API_KEY", "LANGCHAIN_API_KEY"}
    }
    for key in hidden:
        os.environ.pop(key, None)
    try:
        yield
    finally:
        os.environ.update(hidden)


class TargetBridge:
    def __init__(self, project: Path, thread: str, store: SessionStore) -> None:
        self.context = WorkspaceContext.discover()
        self.project = resolve_project_path(project, must_exist=True)
        confined(self.context.projects_root, self.project)
        self.thread = thread
        self.store = store
        self.controller = LocalStepJobController(self.context)
        self.failpoint: Callable[[str], None] = lambda _name: None
        loaded = self.validate_project()
        self.project_id = loaded.config.project_id

    def validate_project(self) -> LoadedStructureRunConfig:
        path = project_config_path(self.project)
        confined(self.project, path)
        loaded = load_run_config(path, source_base_dir=self.project)
        if not isinstance(loaded, LoadedStructureRunConfig):
            raise AgentBoundaryError("Phase 1 supports explicit local PDB/mmCIF inputs only")
        config = loaded.config
        source = config.target.source
        if not isinstance(source, LocalFileSourceConfig):
            raise AgentBoundaryError("Target source must remain a local file")
        raw_source = source.path
        confined(
            self.project, raw_source if raw_source.is_absolute() else self.project / raw_source
        )
        if (
            config.workflow.stop_after_stage != 1
            or str(config.workflow.execution_mode) != "review-gated"
        ):
            raise AgentBoundaryError(
                "Existing project must already be review-gated and stop after target preparation"
            )
        if config.structure_prediction is not None or (
            source.identity.uniprot_accession is not None and not getattr(self, "is_phase2", False)
        ):
            raise AgentBoundaryError(
                "Remote identity lookup and prediction are outside this vertical slice"
            )
        confined(self.project, loaded.source_path)
        return loaded

    def binding(self) -> dict[str, Any]:
        loaded = self.validate_project()
        return {
            "project_id": loaded.config.project_id,
            "config_sha": canonical_model_sha256(loaded.config),
            "source_sha": sha256_file(loaded.source_path),
        }

    def _jobs(self) -> tuple[LocalStepJob, ...]:
        return self.controller.list(project_id=self.project_id)

    def _job_valid(self, job: LocalStepJob) -> None:
        if job.project_root != self.project or job.project_id != self.project_id or job.step != 1:
            raise AgentBoundaryError("Job does not belong to this bound target preparation")
        if job.run_root is not None:
            confined(self.context.runs_root, job.run_root)

    def _receipt(self, job: LocalStepJob) -> dict[str, Any]:
        self._job_valid(job)
        result: dict[str, Any] = {
            "status": job.status,
            "job_id": job.job_id,
            "run_id": job.run_id,
            "error": job.error,
            "phase": "prepare",
        }
        if job.status == "queued" and job.process_id is None:
            result["recovery"] = (
                "reconciliation-required: queued receipt has no confirmed process; do not resubmit"
            )
        if job.status == "succeeded" and job.run_id:
            evidence = self.read_evidence(job.run_id)
            result.update(evidence_id=evidence["evidence_id"], evidence_status=evidence["status"])
        return result

    def _attach(self, command: dict[str, Any], job: LocalStepJob) -> dict[str, Any]:
        self._job_valid(job)
        self.store.update(command["id"], "submitted", job_id=job.job_id, run_id=job.run_id)
        self.store.event(
            self.thread, "command-ref", {"command_id": command["id"], "job_id": job.job_id}
        )
        self.failpoint("after_job_binding")
        return self._receipt(job)

    def _reconcile(self, command: dict[str, Any]) -> dict[str, Any] | None:
        payload = command["payload"]
        if payload.get("job_id"):
            return self._attach(command, self.controller.load(payload["job_id"]))
        candidates = []
        for job in self._jobs():
            if job.job_id in payload["baseline"]:
                continue
            self._job_valid(job)
            if command["operation"] == "prepare":
                if job.operation != "run" or job.config_path is None:
                    continue
                confined(self.project, job.config_path)
                config = load_run_config(job.config_path, source_base_dir=self.project)
                if canonical_model_sha256(config.config) != command["binding"]["config_sha"]:
                    continue
            elif job.operation != "decision" or str(job.decision_record) != payload["record_ref"]:
                continue
            candidates.append(job)
        if len(candidates) == 1:
            return self._attach(command, candidates[0])
        if not candidates and command["operation"] == "decision":
            return (
                None  # Receipt precedes Popen: a verified record with no receipt can be submitted.
            )
        self.store.update(
            command["id"], "reconciliation-required", candidate_jobs=[j.job_id for j in candidates]
        )
        raise ReconciliationRequired(
            "Submission is uncertain; no unique matching receipt. Scientific work was not replayed."
        )

    def prepare_target(self) -> dict[str, Any]:
        with self.store.writer():
            binding = self.binding()
            command = self.store.prepare(
                self.thread, "prepare", binding, baseline=[j.job_id for j in self._jobs()]
            )
            if command["state"] != "prepared":
                if command["payload"].get("existing_run"):
                    return self.read_evidence(command["payload"]["existing_run"])
                return self._reconcile(command) or {}
            self.failpoint("prepared")
            jobs = self._jobs()
            if any(j.status in ACTIVE_JOB_STATUSES for j in jobs):
                raise AgentBoundaryError(
                    "An existing writer is active; attach using its original thread/job"
                )
            existing = resolve_project_run(self.project, required=False)
            if existing is not None:
                result = self.read_evidence(existing.run_id)
                self.store.update(command["id"], "completed", existing_run=existing.run_id)
                return result
            self.store.update(command["id"], "dispatching")
            self.failpoint("dispatching")
            with scientific_environment():
                prepared = target_prepare(self.project, detach=True)
            self.failpoint("after_dispatch")
            if prepared.job_id is None:
                raise ReconciliationRequired(
                    "Legacy prepare returned no job receipt; inspect project state"
                )
            return self._attach(command, self.controller.load(prepared.job_id))

    def get_job_status(self) -> dict[str, Any]:
        for event in reversed(self.store.events(self.thread)):
            if event["kind"] == "command-ref":
                return self._receipt(self.controller.load(event["payload"]["job_id"]))
        commands = self.store.db.execute(
            "SELECT id FROM commands WHERE thread=? ORDER BY rowid DESC", (self.thread,)
        ).fetchall()
        for row in commands:
            command = self.store.command(row[0])
            assert command is not None
            if command["payload"].get("job_id"):
                return self._receipt(self.controller.load(command["payload"]["job_id"]))
        return {"status": "no-bound-job", "phase": "prepare"}

    def run(self, run_id: str | None = None) -> tuple[Path, RunManifest]:
        summary = resolve_project_run(self.project, run_id=run_id, required=True)
        assert summary is not None
        root = confined(self.context.runs_root, summary.path)
        summary = show_run(
            self.context.runs_root, root.relative_to(self.context.runs_root).as_posix()
        )
        manifest_path = confined(root, summary.latest_manifest)
        manifest = load_model(manifest_path, RunManifest)
        if manifest.project_id != self.project_id or (
            run_id is not None and manifest.run_id != run_id
        ):
            raise AgentBoundaryError("Run identity mismatch")
        manifest.config_snapshot.verify(root)
        return root, manifest

    def terminal_result(self, message: str) -> dict[str, Any]:
        """Graph completion is not scientific completion; inspect authoritative state afresh."""
        self.validate_project()
        jobs = self._jobs()  # Original controller returns registered receipts newest first.
        for candidate in jobs:
            self._job_valid(candidate)
        summary = resolve_project_run(self.project, required=False)
        current = next(
            (j for j in jobs if summary is None or j.run_id in {None, summary.run_id}), None
        )
        job = self._receipt(current) if current else {"status": "no-bound-job", "phase": "prepare"}
        result = {"thread": self.thread, "job": job}
        if summary is None:
            if not jobs:
                # This entry point is a project-bound scientific execution session. A
                # model's prose cannot discharge that task without preparing its input.
                return {
                    **result,
                    "status": "incomplete-turn",
                    "scientific_state": "not-prepared",
                    "reason": "scientific-not-started",
                    "message": "Target preparation has not started. The supplied project input "
                    "must be prepared before this scientific task can finish.",
                }
            state = "not-prepared"
        else:
            evidence = self.read_evidence(summary.run_id)
            state = evidence["status"]
            if evidence["request_identity"] is not None:
                # Only a delivered human rejection closes the proposal, never the science gate.
                row = self.store.db.execute(
                    "SELECT id FROM cards WHERE thread=? "
                    "AND json_extract(payload, '$.request_identity')=? ORDER BY rowid DESC LIMIT 1",
                    (self.thread, evidence["request_identity"]),
                ).fetchone()
                intent = self.store.response(self.thread, row[0]) if row else None
                rejected = intent and intent["delivered"] and intent["response"] == "reject"
                return {
                    **result,
                    "status": "rejected" if rejected else "incomplete-turn",
                    "scientific_state": "awaiting-human-approval",
                    "reason": "unresolved-scientific-gate",
                    "message": (
                        "Current proposal rejected; the scientific gate remains pending."
                        if rejected
                        else "Scientific approval is still pending. "
                        "Request a reviewed proposal and a formal decision card."
                    ),
                }
            if state == "succeeded" and not any(j.status in ACTIVE_JOB_STATUSES for j in jobs):
                return {
                    **result,
                    "status": "finished",
                    "scientific_state": state,
                    "message": message,
                }
        return {
            **result,
            "status": "incomplete-turn",
            "scientific_state": state,
            "reason": "scientific-not-complete",
            "message": "Scientific preparation is not complete. Inspect the existing job; "
            "Agent completion cannot resolve scientific work.",
        }

    def revision_is_current(self, outcome: DecisionOutcome) -> bool:
        return bool(
            self.read_evidence()["request_identity"]
            == self.store.card(self.thread, outcome.card_id).request_identity
        )

    @staticmethod
    def _ref(ref: ArtifactRef) -> str:
        return f"{ref.relative_path}#sha256={ref.sha256}"

    def read_evidence(self, run_id: str | None = None) -> dict[str, Any]:
        from .contracts import TargetFacts

        self.validate_project()
        root, manifest = self.run(run_id)
        resolved, config_path = load_resolved_run_config(root)
        confined(root, config_path)
        frozen = EasyDesignRunConfig.model_validate(
            yaml.safe_load(manifest.config_snapshot.verify(root).read_text())
        )
        if canonical_model_sha256(frozen) != canonical_model_sha256(resolved.user_config):
            raise AgentBoundaryError(
                "Resolved config differs from the manifest-declared user config"
            )
        if canonical_model_sha256(frozen) != self.binding()["config_sha"]:
            raise AgentBoundaryError("Project config has drifted from the frozen scientific run")
        if (
            resolved.stop_after_stage != 1
            or resolved.project_id != self.project_id
            or resolved.run_id != manifest.run_id
        ):
            raise AgentBoundaryError("Frozen run is outside Phase 1")
        source = confined(root, resolved.input_snapshot.verify(root))
        if sha256_file(source) != sha256_file(self.validate_project().source_path):
            raise AgentBoundaryError("Project source has drifted from frozen run input")
        refs = [
            self._ref(manifest.config_snapshot),
            self._ref(resolved.input_snapshot),
            f"{config_path.relative_to(root).as_posix()}#sha256={sha256_file(config_path)}",
        ]
        result: dict[str, Any] = {
            "project_id": self.project_id,
            "run_id": manifest.run_id,
            "status": str(manifest.status),
            "limitations": LIMITATIONS,
            "request_identity": None,
            "evidence_refs": refs,
        }
        if manifest.workflow_state is not None:
            request, path = load_pending_decision(root)
            confined(root, path)
            allowed_gates = {"chain-selection"}
            if getattr(self, "is_phase2", False):
                allowed_gates |= {"target-identity-review", "scope-selection"}
            if request.stage_id != STAGE or request.gate not in allowed_gates:
                raise AgentBoundaryError(
                    "Only the existing target chain-selection gate is supported"
                )
            request_hash = canonical_model_sha256(request)
            refs.append(f"{path.relative_to(root).as_posix()}#sha256={sha256_file(path)}")
            inventory = inventory_structure(source)
            if len(inventory.chains) > 32:
                raise AgentBoundaryError(
                    "Too many chains for this slice; provide a narrower explicit input"
                )
            result.update(
                status="awaiting-human-approval",
                request_identity=request_hash,
                request_path=path.relative_to(root).as_posix(),
                question=request.message,
                options=[o.model_dump(mode="json") for o in request.options],
                chains=[
                    {
                        "auth_chain": c.author_chain_id,
                        "label_chain": c.label_chain_id,
                        "residue_count": c.residue_count,
                        "sequence_sha": identity(c.sequence),
                        "model_count": len(c.model_ids),
                        "observed_amino_acid_count": c.canonical_residue_count,
                        "construct_length": len(c.deposited_sequence)
                        if c.deposited_sequence
                        else None,
                    }
                    for c in inventory.chains
                ],
            )
            if getattr(self, "is_phase2", False):
                from .target_identity import deposited_polymer_metadata, pending_canonical

                result["deposited_entities"] = deposited_polymer_metadata(source)

                canonical, canonical_refs = pending_canonical(self, root, source, request)
                refs.extend(canonical_refs)
                result["identity_evidence"] = canonical
                result["decision_kind"] = request.gate
                if canonical:
                    result["limitations"] = canonical.get("limitations", [])
            canonical = result.get("identity_evidence", {}).get("canonical", {})
            comparisons = {
                c["auth_chain"]: c
                for c in result.get("identity_evidence", {}).get("construct_comparisons", [])
            }
            result["hard_facts"] = TargetFacts.model_validate(
                dict(
                    canonical_accession=canonical.get("accession"),
                    canonical_length=canonical.get("sequence_length"),
                    chains=[
                        {
                            "auth_chain": c["auth_chain"],
                            "label_chain": c["label_chain"],
                            "construct_length": comparisons.get(c["auth_chain"], {}).get(
                                "construct_length", c["construct_length"]
                            ),
                            "observed_length": comparisons.get(c["auth_chain"], {}).get(
                                "observed_length", c["observed_amino_acid_count"]
                            ),
                            "mapping_status": comparisons.get(c["auth_chain"], {}).get(
                                "mapping_status"
                            ),
                            "relationship": comparisons.get(c["auth_chain"], {}).get(
                                "relationship"
                            ),
                            "missing_construct_positions": comparisons.get(c["auth_chain"], {}).get(
                                "missing_construct_positions", []
                            ),
                        }
                        for c in result["chains"]
                    ],
                )
            ).model_dump(mode="json")
        elif manifest.status is ExecutionStatus.SUCCEEDED:
            stage_refs = [r for r in manifest.stage_manifest_refs if r.producer_stage == STAGE]
            if len(stage_refs) != 1 or len(manifest.stage_manifest_refs) != 1:
                raise AgentBoundaryError("Expected one completed target stage and no later stage")
            stage_ref = stage_refs[0]
            stage = load_model(confined(root, stage_ref.verify(root)), StageManifest)
            if stage.status is not ExecutionStatus.SUCCEEDED:
                raise AgentBoundaryError("Target stage has not succeeded")
            for ref in (*stage.input_artifacts, *stage.output_artifacts):
                confined(root, ref.verify(root))
            bundle_ref = stage.require_output("target-bundle")
            bundle = load_model(bundle_ref.verify(root), TargetBundle)
            declared = {r.artifact_id: r for r in stage.output_artifacts}
            for field in type(bundle).model_fields:
                ref = getattr(bundle, field)
                if isinstance(ref, ArtifactRef):
                    if declared.get(ref.artifact_id) != ref:
                        raise AgentBoundaryError(
                            "Bundle reference is not a declared stage artifact"
                        )
                    confined(root, ref.verify(root))
            mapping = load_model(bundle.residue_mapping.verify(root), ResidueMapping)
            if (
                mapping.sequence_sha256 != bundle.sequence_sha256
                or len(mapping.entries) != bundle.sequence_length
            ):
                raise AgentBoundaryError("Mapping and bundle sequence identity disagree")
            if bundle.identity_report is None:
                raise AgentBoundaryError("This slice requires a target identity report")
            report = load_model(bundle.identity_report.verify(root), TargetIdentityReport)
            provenance = json.loads(bundle.provenance.verify(root).read_text())
            provenance_values = TargetProvenance.model_validate(
                {name: provenance.get(name) for name in TargetProvenance.model_fields}
            )
            refs.extend([self._ref(stage_ref), *[self._ref(r) for r in stage.output_artifacts]])
            result.update(
                bundle={
                    "schema_version": bundle.schema_version,
                    "target_id": bundle.target_id,
                    "sequence_length": bundle.sequence_length,
                    "sequence_sha256": bundle.sequence_sha256,
                    "producer_attempt": bundle.producer_attempt,
                },
                mapping={"entries": len(mapping.entries), "sha256": bundle.residue_mapping.sha256},
                identity={
                    "biological_identity_status": str(report.biological_identity_status),
                    "auth_chain": report.construct_identity.auth_chain_id,
                    "relationship": str(report.relationship),
                    "canonical": report.canonical.model_dump(mode="json"),
                    "mapping_status": str(report.design_scope.mapping_status),
                    "ambiguities": list(report.ambiguities),
                },
                provenance={
                    "sha256": bundle.provenance.sha256,
                    **provenance_values.model_dump(mode="json"),
                },
                approval_provenance={
                    "status": "not-in-snapshot",
                    "limitation": (
                        "This snapshot does not verify DecisionRecord or human approval lineage. "
                        "The delivered selected chain is not evidence of who approved it."
                    ),
                },
            )
            result["limitations"] = [*LIMITATIONS, result["approval_provenance"]["limitation"]]
            result["hard_facts"] = TargetFacts.model_validate(
                dict(
                    canonical_accession=report.canonical.accession,
                    canonical_length=report.canonical.sequence_length,
                    selected_chain=report.construct_identity.auth_chain_id,
                    chains=[
                        {
                            "auth_chain": report.construct_identity.auth_chain_id or "unknown",
                            "label_chain": report.construct_identity.label_chain_id,
                            "construct_length": report.construct_identity.sequence_length,
                            "observed_length": len(report.observed.observed_construct_positions),
                            "missing_construct_positions": list(
                                report.observed.missing_construct_positions
                            ),
                            "mapping_status": str(report.design_scope.mapping_status),
                            "relationship": str(report.relationship),
                        }
                    ],
                )
            ).model_dump(mode="json")
            if (
                getattr(self, "is_phase2", False)
                and str(report.biological_identity_status) == "resolved"
            ):
                result["limitations"] = [
                    (
                        "Canonical reference identity is resolved; construct/state/native equ"
                        "ivalence is separate."
                    ),
                    "Structural preparation does not establish affinity or function.",
                    *list(report.ambiguities),
                    result["approval_provenance"]["limitation"],
                ]
            try:
                viewer = confined(root, resolve_latest_target_viewer_report(root))
                result["viewer"] = {"status": "verified", "path": str(viewer / "index.html")}
            except Exception as error:
                # Reporting is a separate outcome and never changes scientific success.
                result["viewer"] = {
                    "status": "reporting-failed",
                    "error_type": type(error).__name__,
                }
        result["evidence_id"] = identity(
            {"run": manifest.run_id, "refs": refs, "request": result["request_identity"]}
        )
        result.setdefault("hard_facts", TargetFacts().model_dump(mode="json"))
        result["source_evidence_id"] = result["evidence_id"]
        # Bind an owner interpretation only to the exact verified source snapshot.
        # Historical prose never becomes current facts or a new Judge approval.
        for event in reversed(self.store.events(self.thread)):
            if (
                event["kind"] == "target-assessment"
                and event["payload"].get("source_evidence_id") == result["source_evidence_id"]
            ):
                from .contracts import TargetInterpretation
                from .target_assessment import check_interpretation

                opinion = TargetInterpretation.model_validate(event["payload"]["interpretation"])
                check_interpretation(opinion, result)
                result["target_interpretation"] = opinion.model_dump(mode="json")
                result["evidence_id"] = identity(
                    {
                        "source": result["source_evidence_id"],
                        "opinion": result["target_interpretation"],
                    }
                )
                break
        return result

    def target_submission_evidence(self) -> dict[str, Any]:
        from .contracts import TargetFacts

        # Source research can legitimately finish before a scientific job exists.
        # Such a submission has no inferred sequence/mapping facts and cannot open a Gate.
        if not self._jobs():
            self.validate_project()
            return {
                "hard_facts": TargetFacts().model_dump(mode="json"),
                "source_evidence_id": identity(self.binding()),
                "evidence_refs": [],
                "options": [],
                "status": "not-prepared",
            }
        return self.read_evidence()

    def judge_evidence(self) -> dict[str, Any]:
        return self.read_evidence()

    def register_judge(self, verdict: JudgeVerdict) -> EvidenceAssessment:
        delegated = JUDGE_EVIDENCE.get()
        if delegated is None:
            raise AgentBoundaryError("Judge result lacks a runtime-delegated evidence snapshot")
        current = self.judge_evidence()
        binding = EvidenceBinding.model_validate(
            {name: current[name] for name in EvidenceBinding.model_fields}
        )
        if delegated != binding:
            raise AgentBoundaryError("Judge result is stale or outside its delegated snapshot")
        from .target_assessment import check_fact_claims

        facts = current.get(
            "hard_facts",
            current.get("target_facts", current.get("approved_target", {}).get("hard_facts")),
        )
        from .judge_packet import validate_judge_corrections, validate_judge_stage

        validate_judge_stage(verdict, current)
        validate_judge_corrections(verdict, current)
        from .site_fact_integrity import validate_fact_references

        validate_fact_references(verdict, current)
        if facts is not None and verdict.verdict in {"ready-to-ask", "assessed"}:
            check_fact_claims(verdict.model_dump(mode="json"), {"hard_facts": facts})
        assessment = EvidenceAssessment(
            **verdict.model_dump(),
            **binding.model_dump(),
            assessment_id=f"judge-{uuid4().hex}",
            source_role="evidence-judge",
        )
        self.store.save_assessment(self.thread, assessment)
        return assessment

    def decision_card(self, args: ApplyDecision) -> DecisionCard:
        assessment = self.store.assessment(self.thread, args.assessment_id)
        discouraged = (
            assessment.recommendation is not None
            and assessment.recommendation.status == "DISCOURAGED"
        )
        if assessment.verdict != "ready-to-ask" and not (
            assessment.verdict == "reject" and discouraged
        ):
            raise AgentBoundaryError(
                "Judge has not supplied a reviewable question or discouraged proposal"
            )
        card_id = identity({"assessment": args.assessment_id, "option": args.option_id})
        existing = self.store.db.execute("SELECT id FROM cards WHERE id=?", (card_id,)).fetchone()
        if existing is not None and self.store.response(self.thread, card_id):
            return self.store.card(self.thread, card_id)
        current = self.read_evidence()
        if (
            current["evidence_id"] != assessment.evidence_id
            or current["request_identity"] != assessment.request_identity
        ):
            raise AgentBoundaryError("Evidence/request changed; obtain a new Judge assessment")
        option = next((o for o in current["options"] if o["option_id"] == args.option_id), None)
        if option is None or not option["eligible"]:
            raise AgentBoundaryError(
                "BLOCKED: Option is missing or ineligible; revise the input or hard constraint."
            )
        recommendation = assessment.recommendation
        if recommendation and recommendation.option_id != args.option_id:
            raise AgentBoundaryError("Judge recommendation belongs to a different option")
        revision = self.store.revision_for(self.thread, current["request_identity"])
        if revision is not None:
            later = [e for e in self.store.events(self.thread) if e["seq"] > revision["seq"]]
            if not any(
                e["kind"] == "target-assessment"
                and e["payload"].get("revision_of_card_id") == revision["payload"]["card"]
                for e in later
            ) or not any(
                e["kind"] == "judge-assessment"
                and e["payload"]["assessment_id"] == assessment.assessment_id
                for e in later
            ):
                raise AgentBoundaryError("REVISE requires fresh owner and Judge assessments")
        card = DecisionCard(
            card_id=card_id,
            assessment_id=args.assessment_id,
            project_id=self.project_id,
            run_id=current["run_id"],
            request_identity=current["request_identity"],
            evidence_id=current["evidence_id"],
            question=current["question"],
            option_id=args.option_id,
            options=current["options"],
            evidence_refs=current["evidence_refs"],
            limitations=list(dict.fromkeys([*current["limitations"], *assessment.limitations])),
            judge_status=recommendation.status if recommendation else "SUPPORTED",
            warnings=recommendation.warnings if recommendation else [],
            alternative=recommendation.alternative if recommendation else None,
            parent_card_id=revision["payload"]["card"] if revision else None,
            scientific_summary={
                "hard_facts": current["hard_facts"],
                "interpretation": current.get("target_interpretation"),
            },
            action="Review the warning and alternative; revise, reject or explicitly override."
            if discouraged
            else "Review this chain choice; approve, revise or reject the proposal.",
        )
        self.store.save_card(self.thread, card)
        return card

    def apply_decision(self, card: DecisionCard) -> dict[str, Any]:
        with self.store.writer():
            if self.store.card(self.thread, card.card_id) != card:
                raise AgentBoundaryError("Decision card differs from its trusted runtime copy")
            intent = self.store.response(self.thread, card.card_id)
            if intent is None:
                raise AgentBoundaryError("No persisted human response; model text is not authority")
            if intent["response"] in {"reject", "revise"}:
                current = self.read_evidence(card.run_id)
                if (
                    current["evidence_id"] != card.evidence_id
                    or current["request_identity"] != card.request_identity
                ):
                    raise AgentBoundaryError("Stale steering: evidence/request changed")
                self.store.delivered(self.thread, card.card_id)
                self.failpoint("after_steering_delivery")
                return {
                    "status": "rejected"
                    if intent["response"] == "reject"
                    else "revision-requested",
                    "run_id": card.run_id,
                    "scientific_request": "still-pending",
                    "steering": intent["outcome"],
                }
            outcome = DecisionOutcome.model_validate(intent["outcome"])
            if outcome.action not in {"APPROVE", "OVERRIDE"} or card.judge_status == "BLOCKED":
                raise AgentBoundaryError("Only an admissible trusted human action can approve")
            if card.judge_status == "DISCOURAGED" and outcome.action != "OVERRIDE":
                raise AgentBoundaryError("Discouraged choices require explicit human override")
            acknowledgement = (
                "Selected by explicit human override against current "
                "Evidence Judge recommendation. "
                + "Full warnings, acknowledgement and human rationale are recorded in the "
                + f"scientist-steering outcome: {identity(intent['outcome'])}; "
                f"card: {card.card_id}."
                if outcome.action == "OVERRIDE"
                else "Approved through the local agent CLI"
            )
            current_binding = self.binding()
            root, _ = self.run(card.run_id)
            for reference in card.evidence_refs:
                relative, expected_sha = reference.rsplit("#sha256=", 1)
                if sha256_file(confined(root, root / relative)) != expected_sha:
                    raise AgentBoundaryError("Stale human response; frozen evidence changed")
            frozen, _ = load_resolved_run_config(root)
            if canonical_model_sha256(frozen.user_config) != current_binding["config_sha"]:
                raise AgentBoundaryError("Stale human response; project configuration changed")
            # The exact request path is read from the original evidence references.
            candidates = [
                r.split("#sha256=")[0] for r in card.evidence_refs if r.startswith("decisions/")
            ]
            if len(candidates) != 1:
                raise AgentBoundaryError("Card must bind exactly one scientific request")
            request_path = confined(root, root / candidates[0])
            request = load_model(request_path, DecisionRequest)
            record_path = request_path.parent / f"record.v{request.revision:04d}.json"
            command = self.store.prepare(
                self.thread,
                "decision",
                {"request": card.request_identity, "option": card.option_id, "run_id": card.run_id},
                baseline=[j.job_id for j in self._jobs()],
                record_ref=str(record_path),
                card_id=card.card_id,
            )
            if record_path.exists():
                _, record = load_decision_record_context(root, confined(root, record_path))
                if (
                    record.request_sha256 != card.request_identity
                    or record.selected_option_ids != (card.option_id,)
                    or record.approved_by != intent["user"]
                    or str(record.authority) != "human"
                    or record.acknowledgement != acknowledgement
                ):
                    raise AgentBoundaryError(
                        "Existing scientific record does not match the human response"
                    )
                attached = self._reconcile(command)
                if attached is not None:
                    self.store.delivered(self.thread, card.card_id)
                    return attached
                if any(j.status in ACTIVE_JOB_STATUSES for j in self._jobs()):
                    raise AgentBoundaryError("An existing scientific writer is active")
                self.store.update(command["id"], "dispatching")
                self.failpoint("before_decision_launch")
                with scientific_environment():
                    job = self.controller.launch(
                        operation="decision",
                        project_id=self.project_id,
                        project_root=self.project,
                        step=1,
                        decision_record=record_path,
                        run_id=card.run_id,
                        run_root=root,
                    )
            else:
                current = self.read_evidence(card.run_id)
                if (
                    current["evidence_id"] != card.evidence_id
                    or current["request_identity"] != card.request_identity
                ):
                    raise AgentBoundaryError("Stale human response; evidence/request changed")
                if command["state"] != "prepared":
                    # No record means approval did not commit; only the same intent may continue.
                    if any(j.job_id not in command["payload"]["baseline"] for j in self._jobs()):
                        raise ReconciliationRequired("Unexpected job appeared during approval")
                if any(j.status in ACTIVE_JOB_STATUSES for j in self._jobs()):
                    raise AgentBoundaryError("An existing scientific writer is active")
                self.store.update(command["id"], "dispatching")
                self.failpoint("before_record")
                payload = {
                    "schema_version": request.schema_version,
                    "decision_id": request.decision_id,
                    "request_revision": request.revision,
                    "request_sha256": card.request_identity,
                    "request_path": candidates[0],
                    "selected_option_ids": [card.option_id],
                    "approved_by": intent["user"],
                    "acknowledgement": acknowledgement,
                    "plan_type": request.plan_type,
                    "plan_sha256": request.plan_sha256,
                }
                input_path = self.store.root / f"decision-intent-{command['id']}.yaml"
                confined(self.store.root, input_path)
                if not input_path.exists():
                    with input_path.open("x", encoding="utf-8") as handle:
                        yaml.safe_dump(payload, handle, sort_keys=False)
                elif yaml.safe_load(input_path.read_text()) != payload:
                    raise AgentBoundaryError("Decision input drifted")
                with scientific_environment():
                    result = target_approve(self.project, input_path=input_path, detach=True)
                self.failpoint("after_decision_dispatch")
                if result.job_id is None:
                    raise ReconciliationRequired("Decision returned no job receipt")
                job = self.controller.load(result.job_id)
            receipt = self._attach(command, job)
            self.store.delivered(self.thread, card.card_id)
            return receipt


def build_tools(bridge: TargetBridge, role: str) -> list[Any]:
    """Each handler has a fixed role; root/run/authority never come from model args."""
    from langchain_core.tools import StructuredTool
    from langgraph.types import interrupt

    async def prepare_target_tool() -> str:
        if role != "target":
            raise AgentBoundaryError("Only Target Intelligence can prepare a target")
        return bridge.store.offload(bridge.thread, bridge.prepare_target())

    async def status_tool() -> str:
        if role not in {"target", "coordinator"}:
            raise AgentBoundaryError("Judge cannot invoke operational observation")
        # Bounded observation, never a second scheduler; cancellation only detaches.
        result = bridge.get_job_status()
        if result["status"] == "no-bound-job":
            result = {
                **result,
                "next_action": (
                    "No job exists to observe. Do not repeat get_job_status. Target Intelligence "
                    "must resolve any requested canonical reference using selected verified "
                    "sources, then call prepare_target. The Coordinator must delegate to Target."
                ),
            }
        for _ in range(40):
            if result["status"] not in ACTIVE_JOB_STATUSES:
                break
            await asyncio.sleep(0.25)
            result = bridge.get_job_status()
        return bridge.store.offload(bridge.thread, result)

    async def evidence_tool(run_id: str | None = None) -> str:
        # A model may inspect before prepare (including alongside its first skill read).
        # This is an absence of evidence, not a fabricated run or a scientific failure.
        if role in {"target", "coordinator"} and run_id is None:
            bridge.validate_project()
            if resolve_project_run(bridge.project, required=False) is None:
                return bridge.store.offload(
                    bridge.thread,
                    {
                        "status": "not-prepared",
                        "project_id": bridge.project_id,
                        "evidence_refs": [],
                        "next_action": (
                            "Target Intelligence should call prepare_target to prepare or "
                            "reattach, then get_job_status before reading scientific evidence."
                        ),
                    },
                )
        evidence = bridge.read_evidence(run_id)
        if role == "judge":
            binding = EvidenceBinding.model_validate(
                {name: evidence[name] for name in EvidenceBinding.model_fields}
            )
            if binding != JUDGE_EVIDENCE.get():
                raise AgentBoundaryError("Judge may read only its delegated evidence snapshot")
        return bridge.store.offload(bridge.thread, evidence)

    async def decision_tool(assessment_id: str, option_id: str) -> str:
        if role != "coordinator":
            raise AgentBoundaryError("Only coordinator can present a decision")
        card = bridge.decision_card(ApplyDecision(assessment_id=assessment_id, option_id=option_id))
        response = interrupt(card.model_dump(mode="json"))
        if not isinstance(response, dict) or set(response) != {"card_id", "decision"}:
            raise AgentBoundaryError("Only a bound scientist-steering response is accepted")
        intent = bridge.store.response(bridge.thread, card.card_id)
        if (
            intent is None
            or response["card_id"] != card.card_id
            or response["decision"] != intent["response"]
        ):
            raise AgentBoundaryError("Resume does not match persisted human response")
        return bridge.store.offload(bridge.thread, bridge.apply_decision(card))

    specs: list[tuple[str, Any, Any, str]] = [
        (
            "read_target_evidence",
            evidence_tool,
            EvidenceQuery,
            "Read bounded, verified target evidence for the bound project/run.",
        ),
    ]
    if role in {"target", "coordinator"}:
        specs.append(
            (
                "get_job_status",
                status_tool,
                EmptyArguments,
                "Observe an existing bound job for up to ten seconds. Requires a job receipt "
                "from prepare_target or a Gate response; no-bound-job is not a running job.",
            )
        )
    if role == "target":
        specs.append(
            (
                "prepare_target",
                prepare_target_tool,
                EmptyArguments,
                "Prepare this bound local target, or reattach its existing command. "
                "Read your Skill first. If the user requests canonical identity, "
                "acquire/read the verified source "
                "and propose_canonical_identity BEFORE preparation; preparation freezes the "
                "reference inputs. Never start it concurrently with those prerequisites.",
            )
        )
    if role == "coordinator":
        specs.append(
            (
                "apply_target_decision",
                decision_tool,
                ApplyDecision,
                "Present one eligible chain option backed by a trusted Judge assessment. "
                "Requires human approval.",
            )
        )
    return [
        StructuredTool.from_function(
            name=name, coroutine=fn, args_schema=schema, description=description
        )
        for name, fn, schema, description in specs
    ]
