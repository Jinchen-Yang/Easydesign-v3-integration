"""Target -> Site -> Design adapters; scientific jobs and approvals stay in existing services."""

from __future__ import annotations

import contextvars
import json
from dataclasses import replace
from pathlib import Path
from typing import Any, Literal

import yaml  # type: ignore[import-untyped]

from easydesign.core import (
    ArtifactRef,
    StageManifest,
    canonical_model_sha256,
    load_model,
)
from easydesign.orchestration.config import LoadedStructureRunConfig, load_run_config
from easydesign.orchestration.hotspots import export_hotspot_review
from easydesign.orchestration.local_jobs import ACTIVE_JOB_STATUSES, LocalStepJob
from easydesign.orchestration.local_project import project_config_path, resolve_project_run
from easydesign.orchestration.research import (
    _artifact,
    _latest_foundation,
    _runs,
    site_approve,
    site_propose,
)
from easydesign.orchestration.workspace import load_resolved_run_config
from easydesign.stages.s01_target_preparation.models import TargetBundle
from easydesign.stages.s02_hotspot_discovery.models import HotspotReviewRequest, HotspotsFile

from .contracts import (
    AgentBoundaryError,
    ApplyDecision,
    DecisionCard,
    DecisionOutcome,
    EvidenceBinding,
    EvidenceCitationMismatch,
    ReconciliationRequired,
)
from .evidence_research import EvidenceResearch
from .session_store import SessionStore, compact, confined, identity
from .site_contracts import (
    BiologyContext,
    CanonicalMappingQuery,
    FocusedSiteQuery,
    SiteIntent,
    SiteQuery,
)
from .site_evidence import (
    analyze_site_facts,
    canonical_mapping_rows,
    evaluate_site,
    summarize_site_facts,
)
from .tools import STAGE, TargetBridge, scientific_environment

SITE_EVIDENCE: contextvars.ContextVar[EvidenceBinding | None] = contextvars.ContextVar(
    "site_evidence", default=None
)


class Phase2Bridge(TargetBridge):
    is_phase2 = True

    def __init__(
        self,
        project: Path,
        thread: str,
        store: SessionStore,
        *,
        through: Literal["site", "design"] = "site",
    ) -> None:
        super().__init__(project, thread, store)
        self.through = through
        prior = next((e for e in store.events(thread) if e["kind"] == "scientific-scope"), None)
        if prior and prior["payload"]["through"] != through:
            raise AgentBoundaryError(
                "Thread scientific scope is immutable; create a new thread to extend it"
            )
        if prior is None:
            store.event(thread, "scientific-scope", {"through": through})

    def validate_project(self) -> LoadedStructureRunConfig:
        # Original site_propose advances CONFIG_CURRENT to a stop-after-site revision.
        # Keep Target evidence bound to the original preparation config, while verifying
        # that the only permitted downstream changes are site config and stop boundary.
        path = confined(self.project, project_config_path(self.project))
        loaded = load_run_config(path, source_base_dir=self.project)
        if not isinstance(loaded, LoadedStructureRunConfig):
            raise AgentBoundaryError("Phase 2 requires the approved local structure source")
        if loaded.config.workflow.stop_after_stage == 1:
            return super().validate_project()
        if loaded.config.workflow.stop_after_stage != 2:
            raise AgentBoundaryError("Scientific execution is outside the Phase 2 boundary")
        targets = []
        for run in _runs(self.project):
            resolved, _ = load_resolved_run_config(run.path)
            if resolved.stop_after_stage == 1:
                targets.append(resolved.user_config)
        if not targets:
            raise AgentBoundaryError("No verified target preparation config precedes this site")
        target = targets[-1]
        comparable = loaded.config.model_copy(
            update={
                "workflow": loaded.config.workflow.model_copy(update={"stop_after_stage": 1}),
                "stage02": target.stage02,
            }
        )
        if canonical_model_sha256(comparable) != canonical_model_sha256(target):
            raise AgentBoundaryError("Upstream target/project configuration changed")
        confined(self.project, loaded.source_path)
        return replace(loaded, config=target)

    def project_latest(self, kind: str) -> dict[str, Any] | None:
        """Project evidence/authority only; pending conversation uses thread_latest."""
        row = self.store.db.execute(
            "SELECT seq,thread,payload FROM events WHERE kind=? ORDER BY seq DESC LIMIT 1", (kind,)
        ).fetchone()
        return (
            None
            if row is None
            else {"seq": row["seq"], "thread": row["thread"], **json.loads(row["payload"])}
        )

    def thread_latest(self, kind: str) -> dict[str, Any] | None:
        row = self.store.db.execute(
            "SELECT seq,thread,payload FROM events WHERE kind=? AND thread=? "
            "ORDER BY seq DESC LIMIT 1",
            (kind, self.thread),
        ).fetchone()
        return (
            None
            if row is None
            else {"seq": row["seq"], "thread": row["thread"], **json.loads(row["payload"])}
        )

    def approved_proposal(self, kind: str, approval: dict[str, Any]) -> dict[str, Any]:
        """Resolve the exact historical proposal; never substitute a later conversation."""
        row = self.store.db.execute(
            "SELECT seq,thread,payload FROM events WHERE kind=? AND thread=? AND seq<? "
            "AND json_extract(payload,'$.proposal_id')=? ORDER BY seq DESC LIMIT 1",
            (kind, approval["thread"], approval["seq"], approval["proposal_id"]),
        ).fetchone()
        if row is None:
            raise AgentBoundaryError("Approved scientific state has no bound owner proposal")
        return {"seq": row["seq"], "thread": row["thread"], **json.loads(row["payload"])}

    def proposal_was_consumed(self, proposal: dict[str, Any], approval_kind: str) -> bool:
        # Historical consumption is conversational state, not current scientific authority.
        return (
            self.store.db.execute(
                "SELECT 1 FROM events WHERE kind=? AND thread=? "
                "AND json_extract(payload,'$.proposal_id')=? LIMIT 1",
                (approval_kind, proposal["thread"], proposal["proposal_id"]),
            ).fetchone()
            is not None
        )

    def pending_site(self) -> dict[str, Any] | None:
        proposal = self.current_site()
        if proposal and not self.proposal_was_consumed(proposal, "site-approved"):
            return proposal
        return None

    def _jobs(self) -> tuple[LocalStepJob, ...]:
        # Target replay remains strictly attached to original target jobs.
        return tuple(j for j in super()._jobs() if j.step == 1)

    def target_run_id(self) -> str | None:
        candidates = []
        for run in _runs(self.project):
            resolved, _ = load_resolved_run_config(run.path)
            if resolved.stop_after_stage == 1:
                candidates.append(run)
        return candidates[-1].run_id if candidates else None

    def run(self, run_id: str | None = None) -> Any:
        return super().run(run_id or self.target_run_id())

    def read_evidence(self, run_id: str | None = None) -> dict[str, Any]:
        return super().read_evidence(run_id or self.target_run_id())

    def prepare_target(self) -> dict[str, Any]:
        current = self.target_run_id()
        if current:
            if any(j.status in ACTIVE_JOB_STATUSES for j in self._jobs()):
                return self.get_job_status()
            return self.read_evidence(current)
        return super().prepare_target()

    def target_state(self) -> dict[str, Any]:
        evidence = self.read_evidence()
        if evidence["status"] != "succeeded" or evidence["request_identity"] is not None:
            raise AgentBoundaryError("Gate 1 must resolve before Site Intelligence")
        root, manifest = self.run()
        ref = next(r for r in manifest.stage_manifest_refs if r.producer_stage == STAGE)
        stage = load_model(ref.verify(root), StageManifest)
        bundle_ref = stage.require_output("target-bundle")
        bundle = load_model(bundle_ref.verify(root), TargetBundle)
        binding = {
            "target_structure": bundle.target_structure.sha256,
            "mapping": bundle.residue_mapping.sha256,
            "target_bundle": bundle_ref.sha256,
            "project": self.binding(),
        }
        return {
            "binding": identity(binding),
            "root": root,
            "bundle_path": bundle_ref.verify(root),
            "evidence": evidence,
        }

    def persist(self, kind: str, payload: Any) -> dict[str, Any]:
        """One immutable project evidence object, using the existing ArtifactRef validator."""
        encoded = compact(payload)
        directory = confined(self.project, self.store.root / "agent-evidence")
        directory.mkdir(exist_ok=True)
        path = confined(directory, directory / f"{kind}-{identity(payload)}.json")
        if path.exists():
            if path.read_text() != encoded:
                raise AgentBoundaryError("Immutable scientific evidence changed")
        else:
            with path.open("x") as handle:
                handle.write(encoded)
        return ArtifactRef.from_file(
            run_root=self.project,
            relative_path=path.relative_to(self.project).as_posix(),
            artifact_id=kind,
            role="scientific-evidence",
            file_format="json",
        ).model_dump(mode="json")

    def document(self, ref: dict[str, Any]) -> Any:
        artifact = ArtifactRef.model_validate(ref)
        path = confined(self.project, artifact.verify(self.project))
        return json.loads(path.read_text())

    def import_biology(self, path: Path) -> None:
        biology = BiologyContext.model_validate(yaml.safe_load(path.read_text()))
        value = self.persist("biology-context", biology.model_dump(mode="json"))
        current = self.project_latest("biology-context")
        if current is None or current["ref"] != value:
            self.store.event(self.thread, "biology-context", {"ref": value})

    def biology(self) -> BiologyContext | None:
        event = self.project_latest("biology-context")
        return None if event is None else BiologyContext.model_validate(self.document(event["ref"]))

    def site_facts(self) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        target = self.target_state()
        biology = self.biology()
        binding = identity(
            {
                "target": target["binding"],
                "biology": biology.model_dump(mode="json") if biology else None,
            }
        )
        previous = self.project_latest("site-facts")
        if previous and previous["binding"] == binding:
            ref = previous["ref"]
            facts = self.document(ref)
        else:
            facts = analyze_site_facts(target["root"], target["bundle_path"], biology)
            ref = self.persist("site-facts", facts)
            self.store.event(
                self.thread,
                "site-facts",
                {"binding": binding, "target_binding": target["binding"], "ref": ref},
            )
        return target, facts, ref

    def read_site_evidence(
        self, query: SiteQuery | FocusedSiteQuery | None = None
    ) -> dict[str, Any]:
        query = query or SiteQuery()
        target, facts, ref = self.site_facts()
        activity = EvidenceResearch(self).snapshot()
        research_status = (
            {
                "queried_topics": {
                    k: v for k, v in activity["topics"].items() if v != "NOT_SEARCHED"
                },
                "authority": activity["authority"] + " Topic labels are not a research checklist.",
            }
            if isinstance(query, FocusedSiteQuery)
            else {k: v for k, v in activity.items() if k != "queries"}
        )
        result = {
            "project_id": self.project_id,
            "run_id": target["evidence"]["run_id"],
            "evidence_id": ref["sha256"],
            "request_identity": None,
            "evidence_refs": [f"project:{ref['relative_path']}#sha256={ref['sha256']}"],
            "approved_target": {
                k: target["evidence"][k]
                for k in ("identity", "bundle", "provenance", "limitations", "hard_facts")
            },
            **summarize_site_facts(
                facts,
                labels=query.label_seq_ids,
                offset=query.offset if isinstance(query, SiteQuery) else 0,
                limit=max(12, len(query.label_seq_ids))
                if isinstance(query, FocusedSiteQuery)
                else 12,
            ),
            "query_scope": "focused-residues" if query.label_seq_ids else "overview",
            "requested_labels": query.label_seq_ids,
            "research": research_status,
        }
        if isinstance(query, FocusedSiteQuery) and not query.label_seq_ids:
            # An overview is not the first page of a whole-target residue table.
            # Exact residue rows are a separate, explicitly requested scientific read.
            for key in ("facts", "offset", "page_total", "next_offset"):
                result.pop(key)
            result["declared_scope_complete"] = True
            result["scope_limits"] = (
                "Complete prepared-target candidate overview, not complete biological evidence. "
                "No residue rows were requested. Use read_site_evidence with exact candidate "
                "design labels for mapping/exposure, or read_canonical_mapping for literature "
                "positions. Missing declared biology does not negate independently retrieved "
                "receptor context. For a verified GPCR obtain its context and kernel analysis "
                "before interpreting scan patches; do not page this overview for topology."
            )
        return result

    def read_canonical_mapping(self, query: CanonicalMappingQuery) -> dict[str, Any]:
        target, facts, ref = self.site_facts()
        return {
            "target_binding": target["binding"],
            "source_refs": [ref],
            "query_scope": "approved-canonical-correspondence",
            **canonical_mapping_rows(facts, query),
        }

    def evaluate_candidate(self, query: SiteQuery) -> dict[str, Any]:
        target, facts, _ = self.site_facts()
        return evaluate_site(target["root"], target["bundle_path"], facts, query.label_seq_ids)

    def current_site(self) -> dict[str, Any] | None:
        proposal = self.thread_latest("site-proposal")
        transferred = self.thread_latest("site-proposal-transferred")
        if proposal and transferred and transferred["proposal_id"] == proposal["proposal_id"]:
            return None
        return proposal if proposal and self.site_proposal_is_current(proposal) else None

    def transfer_unreviewed_site(
        self, source_thread: str, *, expected_proposal_id: str
    ) -> dict[str, Any]:
        """Explicit trusted recovery of a completed Site job into a fresh review thread.

        Not a model tool. The caller must stop the source Agent first. No source
        checkpoint/fingerprint/budget is changed and no scientific job is relaunched.
        Reviewed or scientist-responded proposals require ordinary steering instead.
        """
        if source_thread == self.thread:
            raise AgentBoundaryError("Site transfer requires a distinct fresh thread")
        if not self.store.db.execute(
            "SELECT 1 FROM threads WHERE id=?", (source_thread,)
        ).fetchone():
            raise AgentBoundaryError("Source thread is not in this project")
        prior = self.thread_latest("site-proposal-received")
        if prior:
            current = self.current_site()
            if (
                prior["source_thread"] != source_thread
                or prior["proposal_id"] != expected_proposal_id
                or current is None
                or current["proposal_id"] != expected_proposal_id
            ):
                raise AgentBoundaryError("Conflicting Site transfer")
            return self.site_snapshot(current)
        if self.thread_latest("site-proposal") or self.store.latest_execution(self.thread):
            raise AgentBoundaryError("Site transfer destination must be a fresh thread")
        source = Phase2Bridge(self.project, source_thread, self.store)
        with self.store.writer():
            if any(
                j.status in ACTIVE_JOB_STATUSES
                for j in self.controller.list(project_id=self.project_id)
            ):
                raise AgentBoundaryError("An existing scientific writer is active")
            proposal = source.pending_site()
            if proposal is None or proposal["proposal_id"] != expected_proposal_id:
                raise AgentBoundaryError("Source Site proposal is missing, changed or consumed")
            snapshot = source.site_snapshot(proposal)
            if proposal["evaluation"]["status"] == "BLOCKED" or not proposal.get("job_id"):
                raise AgentBoundaryError("Only a completed executable Site proposal can transfer")
            job = self.controller.load(proposal["job_id"])
            if (
                job.project_root != self.project
                or job.step != 2
                or job.run_id != proposal["run_id"]
                or job.status != "awaiting-human-approval"
            ):
                raise AgentBoundaryError("Original Site job is not pending review")
            if (
                self.store.db.execute(
                    "SELECT 1 FROM assessments WHERE thread=? "
                    "AND json_extract(payload,'$.evidence_id')=? LIMIT 1",
                    (source_thread, snapshot["evidence_id"]),
                ).fetchone()
                or self.store.db.execute(
                    "SELECT 1 FROM cards WHERE thread=? "
                    "AND json_extract(payload,'$.request_identity')=? LIMIT 1",
                    (source_thread, proposal["request_identity"]),
                ).fetchone()
            ):
                raise AgentBoundaryError("Reviewed Site proposals require ordinary steering")
            payload = {k: v for k, v in proposal.items() if k not in {"seq", "thread"}}
            provenance = {
                "source_thread": source_thread,
                "destination_thread": self.thread,
                "proposal_id": expected_proposal_id,
                "source_proposal_seq": proposal["seq"],
                "snapshot_sha256": identity(snapshot),
                "job_id": proposal["job_id"],
                "authority": "Unreviewed proposal continuity only; no Judge or Gate approval",
            }
            with self.store.db:
                self.store.db.executemany(
                    "INSERT INTO events(thread,kind,payload) VALUES(?,?,?)",
                    [
                        (source_thread, "site-proposal-transferred", compact(provenance)),
                        (self.thread, "site-proposal", compact(payload)),
                        (self.thread, "site-proposal-received", compact(provenance)),
                    ],
                )
        current = self.current_site()
        assert current is not None
        return self.site_snapshot(current)

    def site_proposal_is_current(self, proposal: dict[str, Any]) -> bool:
        invalidation = self.project_latest("site-invalidated")
        if proposal is None or (invalidation and invalidation["seq"] >= proposal["seq"]):
            return False
        target = self.target_state()
        facts = self.project_latest("site-facts")
        biology = self.biology()
        binding = identity(
            {
                "target": target["binding"],
                "biology": biology.model_dump(mode="json") if biology else None,
            }
        )
        if (
            proposal["target_binding"] != target["binding"]
            or not facts
            or facts["binding"] != binding
            or proposal["facts_ref"] != facts["ref"]
        ):
            return False
        self.document(proposal["facts_ref"])
        return True

    def validate_site_research(self, intent: SiteIntent) -> dict[str, Any]:
        """Read-only citation preflight; no scientific proposal is registered here."""
        from .site_dossier import DecisionEvidenceQuestion

        event = self.thread_latest("site-evidence-dossier")
        execution = self.store.latest_execution(self.thread)
        questions = []
        if event and execution and event["execution_id"] == execution["execution_id"]:
            dossier = self.document(event["ref"])
            if dossier["target_binding"] != self.target_state()["binding"]:
                raise AgentBoundaryError("Site dossier has a stale Target binding")
            questions = [
                DecisionEvidenceQuestion.model_validate(q) for q in dossier["decision_questions"]
            ]
        elif intent.scope == "mechanistic":
            raise AgentBoundaryError("Mechanistic Site requires its current execution dossier")
        research = EvidenceResearch(self).validate_questions(questions)
        cards = {
            c["card_id"]: c for q in research["source_snapshot"]["queries"] for c in q["cards"]
        }
        for site_candidate in [intent.selected_site, *intent.alternatives]:
            if (
                site_candidate.origin == "literature-derived"
                and not site_candidate.evidence_card_ids
            ):
                raise AgentBoundaryError("Literature-derived sites require retrieved source cards")
            if not set(site_candidate.evidence_card_ids).issubset(cards):
                raise AgentBoundaryError("Site source identifier was not retrieved in this thread")
            for card_id in site_candidate.evidence_card_ids:
                if cards[card_id].get("corpus_ref"):
                    raise EvidenceCitationMismatch(
                        "Cite a focused passage, not a full source acquisition receipt"
                    )
                research["source_refs"].extend(cards[card_id]["source_refs"])
        return research

    def register_site(self, intent: SiteIntent, revision: DecisionOutcome | None) -> dict[str, Any]:
        snapshot = self.read_site_evidence()
        if SITE_EVIDENCE.get() != EvidenceBinding.model_validate(
            {k: snapshot[k] for k in EvidenceBinding.model_fields}
        ):
            raise AgentBoundaryError("Site proposal lacks its runtime-delegated target snapshot")
        target, facts, facts_ref = self.site_facts()
        from .target_assessment import check_fact_claims

        check_fact_claims(intent.model_dump(mode="json"), target["evidence"])
        research = self.validate_site_research(intent)
        if intent.portfolio is not None:
            from .site_decision import hydrate_site_decision, parse_site_decision

            decision_event = self.thread_latest("site-decision")
            if decision_event is None:
                raise AgentBoundaryError("Ranked Site requires its bound SiteDecision")
            bound_intent = hydrate_site_decision(
                self,
                parse_site_decision(decision_event["decision"]),
                decision_event["execution_id"],
            )
            if bound_intent != intent:
                raise AgentBoundaryError("Ranked Site differs from its bound SiteDecision")
        dossier_event = self.thread_latest("site-evidence-dossier")
        execution = self.store.latest_execution(self.thread)
        dossier_eligibility: dict[str, dict[str, Any]] = {}
        if (
            dossier_event
            and execution
            and dossier_event["execution_id"] == execution["execution_id"]
            and dossier_event["target_binding"] == target["binding"]
        ):
            dossier = self.document(dossier_event["ref"])
            dossier_eligibility = {
                candidate["candidate_id"]: candidate.get("runtime_eligibility", {})
                for candidate in dossier.get("candidate_comparison", [])
            }
            # Keep decision-critical opposing evidence visible to Judge even if the
            # final SiteIntent does not cite it. Existing refs verify all originals.
            cards = {
                c["card_id"]: c for q in research["source_snapshot"]["queries"] for c in q["cards"]
            }
            research["source_refs"].append(dossier_event["ref"])
            research["source_refs"].extend(
                a["source_ref"] for a in dossier["reference_annotations"]
            )
            for card in dossier["focused_passages"]:
                research["source_refs"].extend(cards[card["card_id"]]["source_refs"])
            for question in dossier["decision_questions"]:
                for use in question["evidence"]:
                    research["source_refs"].extend(cards[use["card_id"]]["source_refs"])
        evaluation = evaluate_site(
            target["root"], target["bundle_path"], facts, intent.selected_site.hotspot_label_seq_ids
        )
        alternatives = [
            evaluate_site(target["root"], target["bundle_path"], facts, a.hotspot_label_seq_ids)
            for a in intent.alternatives
        ]
        if intent.portfolio is None and any(a["status"] == "BLOCKED" for a in alternatives):
            raise AgentBoundaryError(
                "An alternative site contains a hard mapping/constraint violation"
            )
        portfolio_evaluations = {}
        if intent.portfolio is not None:
            for entry, checked in zip(intent.portfolio, [evaluation, *alternatives], strict=True):
                conflict = checked.get("cause") if checked["status"] == "BLOCKED" else None
                runtime_eligibility = dossier_eligibility.get(entry.candidate_id, {})
                if runtime_eligibility.get("status") == "BLOCKED":
                    conflict = (
                        runtime_eligibility.get("cause") or "verified-compartment-conflict"
                    )
                if set(entry.site.hotspot_label_seq_ids) & set(intent.avoid_label_seq_ids):
                    conflict = "explicit-avoid-residue-constraint"
                if entry.hard_block != conflict or entry.selectable != (conflict is None):
                    raise AgentBoundaryError(
                        "Portfolio eligibility contradicts Runtime hard checks"
                    )
                portfolio_evaluations[entry.candidate_id] = (
                    {
                        "status": "BLOCKED",
                        "cause": conflict,
                        "remedy": "Revise the explicit constraint or candidate.",
                    }
                    if conflict
                    else checked
                )
            evaluation = portfolio_evaluations[intent.portfolio[0].candidate_id]
        parent = None
        if revision:
            previous_card = self.store.card(self.thread, revision.card_id)
            if previous_card.gate_type in {"site-hotspot", "design-specification"}:
                parent = previous_card.card_id
        payload = {
            "owner_thread": self.thread,
            "target_binding": target["binding"],
            "facts_ref": facts_ref,
            "intent": intent.model_dump(mode="json"),
            "evaluation": evaluation,
            "alternative_evaluations": alternatives,
            "parent_card_id": parent,
            "source_role": "site-mechanism",
            "research_ref": self.persist("site-research-snapshot", research),
        }
        if intent.portfolio is not None:
            payload["portfolio_evaluations"] = portfolio_evaluations
        proposal_id = identity(payload)
        old = self.current_site()
        if old and old["proposal_id"] == proposal_id:
            return self.site_snapshot(old)
        payload["proposal_id"] = proposal_id
        if evaluation["status"] != "BLOCKED":
            fragment: dict[str, Any] = {
                "mode": "user-provided",
                "methods": [],
                "automatic": None,
                "annotations": {"uniprot": "off"},
                "user_regions": {
                    "source": {
                        "type": "residue-list",
                        "numbering": "label",
                        "regions": (
                            [
                                {
                                    "id": entry.rank,
                                    "residues": [
                                        str(n) for n in sorted(entry.site.hotspot_label_seq_ids)
                                    ],
                                }
                                for entry in intent.portfolio
                                if entry.selectable
                            ]
                            if intent.portfolio is not None
                            else [
                                {
                                    "id": "A",
                                    "residues": [
                                        str(n)
                                        for n in sorted(intent.selected_site.hotspot_label_seq_ids)
                                    ],
                                }
                            ]
                        ),
                    }
                },
            }
            input_path = confined(
                self.store.root, self.store.root / f"site-intent-{proposal_id}.yaml"
            )
            if not input_path.exists():
                with input_path.open("x") as handle:
                    yaml.safe_dump(fragment, handle, sort_keys=False)
            elif yaml.safe_load(input_path.read_text()) != fragment:
                raise AgentBoundaryError("Site intent changed")
            with self.store.writer():
                command = self.store.prepare(
                    self.thread,
                    "site-propose",
                    {"proposal_id": proposal_id},
                    baseline=[j.job_id for j in self.controller.list(project_id=self.project_id)],
                )
                job = None
                if command["payload"].get("job_id"):
                    job = self.controller.load(command["payload"]["job_id"])
                elif command["state"] != "prepared":
                    matches = []
                    for candidate in self.controller.list(project_id=self.project_id):
                        if (
                            candidate.job_id in command["payload"]["baseline"]
                            or candidate.step != 2
                            or candidate.config_path is None
                        ):
                            continue
                        config = load_run_config(
                            confined(self.project, candidate.config_path),
                            source_base_dir=self.project,
                        ).config
                        if (
                            config.stage02
                            and config.stage02.model_dump(mode="json", exclude_none=True)[
                                "user_regions"
                            ]["source"]["regions"]
                            == fragment["user_regions"]["source"]["regions"]
                        ):
                            matches.append(candidate)
                    if len(matches) != 1:
                        raise ReconciliationRequired(
                            "Site submission has no unique original job; do not replay"
                        )
                    job = matches[0]
                if job is None:
                    if any(
                        j.status in ACTIVE_JOB_STATUSES
                        for j in self.controller.list(project_id=self.project_id)
                    ):
                        raise AgentBoundaryError("An existing scientific writer is active")
                    self.store.update(command["id"], "dispatching")
                    with scientific_environment():
                        result = site_propose(
                            self.project, input_path=input_path, from_pse_colors=False, detach=False
                        )
                    self.failpoint("after_site_dispatch")
                    if not result.job_id:
                        raise ReconciliationRequired("Site proposal returned no original job")
                    job = self.controller.load(result.job_id)
                if job.project_root != self.project or job.step != 2:
                    raise AgentBoundaryError("Site job ownership mismatch")
                self.store.update(command["id"], "submitted", job_id=job.job_id, run_id=job.run_id)
                if job.status in ACTIVE_JOB_STATUSES:
                    raise AgentBoundaryError(
                        "Site work is still running; resume its existing Agent execution"
                    )
                if job.status != "awaiting-human-approval" or not job.run_id or not job.run_root:
                    raise AgentBoundaryError(f"Site computation did not reach review: {job.status}")
                root = confined(self.context.runs_root, job.run_root)
                review = confined(
                    self.project,
                    self.project / f"site-proposal.agent-{proposal_id}.{job.run_id}.yaml",
                )
                if not review.exists():
                    export_hotspot_review(root, output=review)
                request = HotspotReviewRequest.model_validate(yaml.safe_load(review.read_text()))
                payload.update(
                    run_id=job.run_id,
                    run_root=str(root),
                    job_id=job.job_id,
                    review_ref=ArtifactRef.from_file(
                        run_root=self.project,
                        relative_path=review.relative_to(self.project).as_posix(),
                        artifact_id="site-review",
                        role="scientific-proposal",
                        file_format="yaml",
                    ).model_dump(mode="json"),
                    request_identity=canonical_model_sha256(request),
                )
                self.store.update(command["id"], "completed")
        else:
            payload.update(run_id=target["evidence"]["run_id"], request_identity=proposal_id)
        self.store.event(self.thread, "site-proposal", payload)
        return self.site_snapshot(payload)

    def site_snapshot(self, proposal: dict[str, Any], *, for_judge: bool = False) -> dict[str, Any]:
        from .site_decision import candidate_name

        facts = self.document(proposal["facts_ref"])
        ref = proposal["facts_ref"]
        refs = [f"project:{ref['relative_path']}#sha256={ref['sha256']}"]
        research = None
        dossier = None
        dossier_context = None
        if proposal.get("research_ref"):
            research_ref = proposal["research_ref"]
            research = self.document(research_ref)
            for source in research["source_refs"]:
                confined(self.project, ArtifactRef.model_validate(source).verify(self.project))
            refs.append(f"project:{research_ref['relative_path']}#sha256={research_ref['sha256']}")
            dossier_refs = {
                source["sha256"]: source
                for source in research["source_refs"]
                if source["artifact_id"] == "site-evidence-dossier"
            }
            if len(dossier_refs) > 1:
                raise AgentBoundaryError("Site proposal binds conflicting evidence dossiers")
            if dossier_refs:
                dossier = self.document(next(iter(dossier_refs.values())))
                if (
                    dossier["target_binding"] != proposal["target_binding"]
                    or dossier["owner_thread"] != proposal["owner_thread"]
                ):
                    raise AgentBoundaryError("Site dossier differs from proposal Target or owner")
                dossier_context = {
                    "runtime_status": dossier["runtime_status"],
                    "reference_annotations": dossier.get("reference_annotations", []),
                    "residue_constraints": dossier.get("residue_constraints", []),
                    "approach_validation": dossier.get(
                        "approach_validation", {"status": "not-supplied"}
                    ),
                    "trusted_residue_facts": dossier["trusted_residue_facts"],
                    "receptor_context": dossier["receptor_context"],
                    "candidates": [
                        {
                            "candidate_id": candidate["candidate_id"],
                            "name": candidate_name(candidate),
                            "design_labels": candidate["research_hypothesis"][
                                "hotspot_label_seq_ids"
                            ],
                            "location": candidate["location"],
                        }
                        for candidate in dossier["candidate_comparison"]
                    ],
                    "authority": "Exact approved mapping, current Gate status and existing kernel "
                    "topology/state. Candidate names and research classifications are fallible "
                    "hypotheses; a kernel-generated candidate is not a database-endorsed epitope. "
                    "Sequence overlap, surface exposure and full-binder access are distinct.",
                }
        if proposal.get("review_ref"):
            review = ArtifactRef.model_validate(proposal["review_ref"])
            review.verify(self.project)
            refs.append(f"project:{review.relative_path}#sha256={review.sha256}")
            root, manifest = super().run(proposal["run_id"])
            stage_ref = next(
                r
                for r in manifest.stage_manifest_refs
                if r.producer_stage == "02-hotspot-discovery"
            )
            stage = load_model(stage_ref.verify(root), StageManifest)
            for artifact in stage.output_artifacts:
                confined(root, artifact.verify(root))
            # Site approval changes this manifest; pending and approved snapshots cannot mix.
            refs.append(
                f"run:{proposal['run_id']}:{stage_ref.relative_path}#sha256={stage_ref.sha256}"
            )
        # Historical immutable proposals remain readable without revalidating obsolete DTOs.
        from .site_contracts import SiteSelection

        selection = SiteSelection.model_validate(proposal["intent"]["selected_site"])
        cited_cards = {
            card_id
            for candidate in [
                proposal["intent"]["selected_site"],
                *proposal["intent"]["alternatives"],
            ]
            for card_id in candidate.get("evidence_card_ids", [])
        }
        snapshot = {
            "target_facts": self.read_evidence()["hard_facts"],
            **({"site_dossier_facts": dossier_context} if dossier_context is not None else {}),
            "gate_type": "site-hotspot",
            "project_id": self.project_id,
            "run_id": proposal["run_id"],
            "status": "awaiting-human-approval",
            "request_identity": proposal["request_identity"],
            "evidence_id": identity({"proposal": proposal["proposal_id"], "refs": refs}),
            "evidence_refs": refs,
            "proposal": proposal["intent"],
            "research_evidence": None
            if research is None
            else {
                "authority": research["authority"],
                "decision_questions": [
                    {"question": q["question"]} for q in dossier["decision_questions"]
                ]
                if dossier
                else [],
                "retrieval_status": [
                    {key: q[key] for key in ("topic", "question", "status", "errors")}
                    for q in research["source_snapshot"]["queries"]
                ],
                "source_cards": [
                    {key: value for key, value in c.items() if key != "source_refs"}
                    for c in (
                        dossier["focused_passages"]
                        if dossier
                        else [
                            c
                            for q in research["source_snapshot"]["queries"]
                            for c in q["cards"]
                            if c["card_id"] in cited_cards
                        ]
                    )
                ],
            },
            "evaluation": proposal["evaluation"],
            "alternative_evaluations": proposal["alternative_evaluations"],
            "scientific_context": summarize_site_facts(
                facts,
                labels=[]
                if proposal["evaluation"]["status"] == "BLOCKED"
                else selection.hotspot_label_seq_ids,
            ),
            "approval_scope": (
                "Review this proposed site only; not human authority or future binder success."
            ),
        }
        if for_judge and dossier is not None:
            from .judge_packet import build_judge_packet
            from .site_fact_integrity import canonical_reference

            decision = None
            for event in self.store.events(proposal["owner_thread"]):
                if event["kind"] != "site-decision":
                    continue
                value = event["payload"]
                if value["hydrated_intent_sha256"] == identity(proposal["intent"]):
                    if value["dossier_ref"]["sha256"] not in dossier_refs:
                        raise AgentBoundaryError("SiteDecision binds a different evidence dossier")
                    decision = value["decision"]
            owner = self.store.db.execute(
                "SELECT goal FROM threads WHERE id=?", (proposal["owner_thread"],)
            ).fetchone()
            if owner is None:
                raise AgentBoundaryError("Site proposal has no bound user objective")
            return build_judge_packet(
                snapshot,
                dossier,
                facts,
                goal=owner["goal"],
                decision=decision,
                canonical=canonical_reference(self, dossier),
            )
        return snapshot

    def judge_evidence(self) -> dict[str, Any]:
        target = self.read_evidence()
        if target["request_identity"] is not None:
            return target
        proposal = self.current_site()
        if proposal is None:
            raise AgentBoundaryError(
                "Delegate Site & Mechanism before asking for a Site Judge opinion"
            )
        return self.site_snapshot(proposal, for_judge=True)

    def approved_site(self) -> dict[str, Any] | None:
        approved = self.project_latest("site-approved")
        if approved is None:
            return None
        proposal = self.approved_proposal("site-proposal", approved)
        from .site_portfolio import selected_proposal

        proposal = selected_proposal(proposal, approved["outcome"].get("selected_option_id"))
        if not self.site_proposal_is_current(proposal):
            return None
        foundation = _latest_foundation(self.project)
        if foundation is None or foundation.run_id != proposal["run_id"]:
            return None
        ref, path = _artifact(foundation.path, "hotspots")
        if ref.sha256 != approved["hotspots_sha256"]:
            raise AgentBoundaryError("Approved hotspots changed")
        hotspots = HotspotsFile.model_validate(yaml.safe_load(path.read_text()))
        if list(hotspots.hotspot_sets[0].label_seq_ids) != sorted(
            proposal["intent"]["selected_site"]["hotspot_label_seq_ids"]
        ):
            raise AgentBoundaryError("Approved hotspot numbering differs from its proposal")
        return {
            **approved,
            "proposal": proposal,
            "hotspots": hotspots.model_dump(mode="json"),
            "foundation_root": str(foundation.path),
        }

    def scientific_state(self) -> dict[str, Any]:
        if any(j.status in ACTIVE_JOB_STATUSES for j in self._jobs()):
            return {
                "scientific_state": "running",
                "gate_type": "target-structure",
                "next_specialist": "target-intelligence",
            }
        if self.target_run_id() is None:
            return {"scientific_state": "not-prepared", "next_specialist": "target-intelligence"}
        target = self.read_evidence()
        if target["status"] != "succeeded":
            return {
                "scientific_state": target["status"],
                "gate_type": "target-structure",
                "next_specialist": "target-intelligence",
            }
        proposal = self.current_site()
        approved = self.approved_site()
        if approved and self.pending_site() is None:
            return {
                "scientific_state": "hotspot-approved",
                "gate_type": "site-hotspot",
                "next_specialist": "none" if self.through == "site" else "binder-strategy",
                "site": approved,
            }
        revision = (
            self.store.revision_for(self.thread, proposal["request_identity"]) if proposal else None
        )
        return {
            "scientific_state": "awaiting-human-approval" if proposal else "site-not-proposed",
            "gate_type": "site-hotspot",
            "next_specialist": "site-mechanism" if not proposal or revision else "evidence-judge",
            "proposal": proposal["intent"] if proposal else None,
        }

    def terminal_result(self, message: str) -> dict[str, Any]:
        jobs = self.controller.list(project_id=self.project_id)
        active = any(j.status in ACTIVE_JOB_STATUSES for j in jobs)
        latest_run = resolve_project_run(self.project, required=False)
        pending = False
        if latest_run is not None:
            _, manifest = super().run(latest_run.run_id)
            pending = manifest.workflow_state is not None
        state = self.scientific_state()
        if active or (pending and state["scientific_state"] == "hotspot-approved"):
            return {
                "thread": self.thread,
                "status": "incomplete-turn",
                "scientific_state": "awaiting-human-approval" if pending else "running",
                "reason": "authoritative-scientific-work-pending",
                "message": (
                    "The scientific service has unresolved work or approval; a prior "
                    "approved site cannot complete it."
                ),
            }
        if state["scientific_state"] == "hotspot-approved" and self.through == "site":
            return {
                "thread": self.thread,
                "status": "finished",
                "scientific_state": "hotspot-approved",
                "message": message,
            }
        if (
            state["scientific_state"] in {"not-prepared", "queued", "running"}
            or state.get("gate_type") == "target-structure"
        ):
            return super().terminal_result(message)
        proposal = self.current_site()
        rejected = False
        if proposal:
            row = self.store.db.execute(
                (
                    "SELECT id,thread FROM cards WHERE json_extract(payload, "
                    "'$.evidence_id')=? ORDER BY rowid DESC LIMIT 1"
                ),
                (self.site_snapshot(proposal)["evidence_id"],),
            ).fetchone()
            response = self.store.response(row["thread"], row["id"]) if row else None
            rejected = bool(response and response["delivered"] and response["response"] == "reject")
        return {
            "thread": self.thread,
            "status": "proposal-rejected" if rejected else "incomplete-turn",
            "scientific_state": state["scientific_state"],
            "gate_type": state.get("gate_type"),
            "message": "Current proposal was rejected; a new local scientific strategy is needed."
            if rejected
            else (
                "The requested scientific scope is not complete. A reviewed "
                "Site/Hotspot decision is still required."
            ),
        }

    def revision_is_current(self, outcome: DecisionOutcome) -> bool:
        card = self.store.card(self.thread, outcome.card_id)
        if card.gate_type == "target-structure":
            return super().revision_is_current(outcome)
        current = self.current_site()
        return bool(current and current["request_identity"] == card.request_identity)

    def decision_card(self, args: ApplyDecision) -> DecisionCard:
        existing_id = (
            identity({"assessment": args.assessment_id, "option": args.option_id})
            if args.assessment_id
            else identity({"review_failure": args.review_failure_id, "option": args.option_id})
        )
        if self.store.response(self.thread, existing_id) is not None:
            return self.store.card(self.thread, existing_id)
        if self.read_evidence()["request_identity"] is not None:
            return super().decision_card(args)
        proposal = self.current_site()
        if proposal is None:
            raise AgentBoundaryError("No current trusted Site proposal")
        snapshot = self.site_snapshot(proposal)
        assessment = (
            self.store.assessment(self.thread, args.assessment_id) if args.assessment_id else None
        )
        if args.option_id != "site" or (
            assessment is not None
            and (
                assessment.evidence_id != snapshot["evidence_id"]
                or assessment.request_identity != snapshot["request_identity"]
            )
        ):
            raise AgentBoundaryError(
                "Site Judge assessment is stale or belongs to a different question"
            )
        from .site_fact_integrity import fact_paths, render_fact, render_judge

        judge_packet = self.site_snapshot(proposal, for_judge=True)
        failure = None
        if assessment is None:
            from .site_review_availability import checked_failure

            assert args.review_failure_id is not None
            failure = checked_failure(self, judge_packet, args.review_failure_id)
        rendered = (
            render_judge(assessment, judge_packet)
            if assessment is not None
            else {
                "reasons": [],
                "limitations": [],
                "recommendation": None,
                "site_claim_corrections": [],
            }
        )
        evaluation = proposal["evaluation"]
        opinion = assessment.recommendation if assessment is not None else None
        if opinion and opinion.option_id != "site":
            raise AgentBoundaryError(
                "Judge recommendation belongs to a different scientific option"
            )
        blocked = evaluation["status"] == "BLOCKED"
        discouraged = (
            evaluation["status"] == "DISCOURAGED"
            or proposal["intent"]["recommendation"] == "DISCOURAGED"
            or (opinion and opinion.status == "DISCOURAGED")
            or bool(assessment and assessment.site_claim_corrections)
        )
        portfolio = proposal["intent"].get("portfolio")
        if (
            assessment is not None
            and not blocked
            and not portfolio
            and assessment.verdict != "ready-to-ask"
        ):
            raise AgentBoundaryError("Judge has not supplied a reviewable Site question")
        status: Literal["SUPPORTED", "DISCOURAGED", "BLOCKED"] = (
            "BLOCKED" if blocked else "DISCOURAGED" if discouraged else "SUPPORTED"
        )
        if failure and blocked and not portfolio:
            raise AgentBoundaryError("BLOCKED Site cannot use review unavailability to proceed")
        warnings = list(
            dict.fromkeys(
                [
                    *evaluation.get("warnings", []),
                    *proposal["intent"]["risks"],
                    *((rendered["recommendation"] or {}).get("warnings", [])),
                    *(
                        f"Judge qualification of unaccepted Site claim ‘{c['claim']}’: "
                        f"{c['qualification']}"
                        for c in rendered["site_claim_corrections"]
                    ),
                ]
            )
        )
        if blocked:
            warnings = [evaluation["cause"], evaluation["remedy"]]
        alternative = (rendered["recommendation"] or {}).get("alternative")
        if not alternative and proposal["intent"]["alternatives"]:
            alternative = (
                proposal["intent"]["alternatives"][0]["name"]
                + ": "
                + proposal["intent"]["alternatives"][0]["rationale"]
            )
        if status == "DISCOURAGED" and not alternative:
            alternative = (
                "Reassess a more accessible mapped region or supply the missing "
                "biological/topology evidence before selecting it."
            )
        if status == "DISCOURAGED" and not warnings:
            warnings = [
                (
                    "The scientific specialist discourages this exploratory site; review "
                    "its stated uncertainty."
                )
            ]
        if failure:
            from .site_review_availability import REVIEW_WARNING

            warnings.insert(0, REVIEW_WARNING)
        selected = proposal["intent"]["selected_site"]
        card = DecisionCard(
            gate_type="site-hotspot",
            owner_specialist="site-mechanism",
            judge_status=None if failure else status,
            card_id=existing_id,
            assessment_id=assessment.assessment_id if assessment else None,
            project_id=self.project_id,
            run_id=snapshot["run_id"],
            request_identity=snapshot["request_identity"],
            evidence_id=snapshot["evidence_id"],
            question="Which site and hotspot residues should the binder target?",
            option_id="site",
            options=[
                {
                    "option_id": "site",
                    "label": selected["name"],
                    "description": selected["rationale"],
                    "eligible": not blocked,
                }
            ],
            evidence_refs=snapshot["evidence_refs"],
            limitations=list(
                dict.fromkeys([*rendered["limitations"], *proposal["intent"]["uncertainty"]])
            ),
            warnings=warnings,
            alternative=alternative,
            parent_card_id=proposal["parent_card_id"],
            scientific_summary={
                "hotspots": evaluation.get("mapped_residues", selected["hotspot_label_seq_ids"]),
                "evidence": proposal["intent"]["positive_evidence"],
                "mechanism": proposal["intent"]["mechanistic_rationale"],
                "accessibility": proposal["intent"]["accessibility_rationale"],
                "approach": proposal["intent"]["binder_approach"],
                "interpretation_scope": "Unapproved specialist hypotheses; independent Judge "
                "qualifications below apply to their interpretation, not to runtime hard facts.",
                "independent_review": {
                    **(
                        {
                            "availability": "unavailable",
                            "failure_record_id": failure["record_id"],
                            "source_role": "verified-runtime",
                            "warning": warnings[0],
                        }
                        if failure
                        else {}
                    ),
                    "reasons": rendered["reasons"],
                    "limitations": rendered["limitations"],
                    "claim_corrections": rendered["site_claim_corrections"],
                    "cited_fact_ids": list(
                        dict.fromkeys(
                            [
                                *rendered.get("fact_refs", []),
                                *(c["fact_ref"] for c in rendered.get("fact_claims", [])),
                            ]
                        )
                    ),
                    **(
                        {
                            "runtime_facts": {
                                key: {"rendered": render_fact(judge_packet, key), **ref}
                                for key, ref in fact_paths(judge_packet).items()
                            },
                            "fact_binding": judge_packet["evidence_id"],
                            "sequence_mapping_scope": judge_packet["peptide_reference"],
                            "fact_scope": "Runtime-rendered facts; source passages, scopes, exact "
                            "tables and raw Judge opinion remain in the bound evidence audit. "
                            "Judge prose is scientific interpretation, not a verified fact source. "
                            "Precise ranges, mappings and topology above come from Runtime; "
                            "only structured fact assertions are checked for exact consistency.",
                        }
                        if "fact_references" in judge_packet
                        else {}
                    ),
                },
            },
            action=(
                "Independent review did not complete. Review the original Site evidence, revise, "
                "reject, or acknowledge the missing review and provide a rationale to continue."
                if failure
                else (
                    "Review this proposed region and structural-only limitations. Approve "
                    "its explicit residue choices, revise, reject, or acknowledge warnings "
                    "and override if discouraged."
                )
            ),
        )
        if portfolio:
            from .site_portfolio import PORTFOLIO_POLICY, portfolio_options

            options = portfolio_options(proposal, self.document(proposal["facts_ref"]))
            available = [option for option in options if option["eligible"]]
            review_summary = card.scientific_summary["independent_review"]
            assert isinstance(review_summary, dict)
            independent = dict(review_summary)
            warnings = list(
                dict.fromkeys(
                    [
                        *((rendered["recommendation"] or {}).get("warnings", [])),
                        *(
                            f"Judge qualification of unaccepted Site claim ‘{c['claim']}’: "
                            f"{c['qualification']}"
                            for c in rendered["site_claim_corrections"]
                        ),
                    ]
                )
            )
            if failure:
                independent["warning"] = (
                    "Independent review unavailable; ranking retained. "
                    "Scientist chooses with lower review confidence."
                )
                warnings = [str(independent["warning"]), *warnings]
            independent.update(
                {
                    "ranking_authority": "SiteDecision; Judge cannot reorder candidates",
                    "verdict": assessment.verdict if assessment else None,
                    "recommendation": rendered["recommendation"],
                }
            )
            card = DecisionCard.model_validate(
                {
                    **card.model_dump(mode="json"),
                    "option_id": available[0]["option_id"] if available else "site",
                    "options": options,
                    "warnings": warnings,
                    "limitations": rendered["limitations"],
                    "scientific_summary": {
                        "selection_policy": PORTFOLIO_POLICY,
                        "ranking_authority": "SiteDecision",
                        "independent_review": independent,
                        "default_candidate_id": available[0]["option_id"] if available else None,
                        "default_is_approval": False,
                        "interpretation_scope": "Relative scientific recommendations; "
                        "exact residue facts "
                        "are Runtime-owned. Judge qualifications apply to interpretation.",
                    },
                    "action": (
                        "Approve the displayed default A or choose any selectable candidate "
                        "by its ID; revise/reject remain available. Scientific risks and "
                        "unavailable review do not require an override."
                        if available
                        else "All supplied candidates have hard conflicts. Revise the candidate "
                        "set or explicit constraints, or reject this proposal."
                    ),
                }
            )
        self.store.save_card(self.thread, card)
        return card

    def _approved_hotspots_match(
        self, proposal: dict[str, Any], request: HotspotReviewRequest
    ) -> dict[str, Any]:
        foundation = _latest_foundation(self.project)
        if foundation is None or foundation.run_id != proposal["run_id"]:
            raise ReconciliationRequired(
                "Site approval is not fully published by the original scientific service"
            )
        normalized_ref, normalized_path = _artifact(foundation.path, "approval-request")
        observed = HotspotReviewRequest.model_validate(yaml.safe_load(normalized_path.read_text()))
        hotspots_ref, hotspots_path = _artifact(foundation.path, "hotspots")
        hotspots = HotspotsFile.model_validate(yaml.safe_load(hotspots_path.read_text()))
        if (
            observed != request
            or hotspots.approval_request_sha256 != normalized_ref.sha256
            or hotspots.approved_by != request.approved_by
            or hotspots.approval_authority != "human"
        ):
            raise AgentBoundaryError(
                "Scientific site approval does not match the exact trusted human outcome"
            )
        if len(hotspots.hotspot_sets) != 1 or list(
            hotspots.hotspot_sets[0].label_seq_ids
        ) != sorted(proposal["intent"]["selected_site"]["hotspot_label_seq_ids"]):
            raise AgentBoundaryError("Scientific hotspot approval changed the selected residues")
        return {"hotspots_sha256": hotspots_ref.sha256, "run_id": foundation.run_id}

    def apply_decision(self, card: DecisionCard) -> dict[str, Any]:
        if card.gate_type == "target-structure":
            return super().apply_decision(card)
        if card.gate_type != "site-hotspot":
            raise AgentBoundaryError("Unsupported scientific gate")
        with self.store.writer():
            if self.store.card(self.thread, card.card_id) != card:
                raise AgentBoundaryError("Card differs from its trusted runtime copy")
            response = self.store.response(self.thread, card.card_id)
            if response is None:
                raise AgentBoundaryError("No trusted human response; model text is not authority")
            outcome = DecisionOutcome.model_validate(response["outcome"])
            proposal = self.current_site()
            if proposal is None or proposal["request_identity"] != card.request_identity:
                raise AgentBoundaryError(
                    "Upstream target, context or current Site proposal changed"
                )
            if outcome.action in {"REVISE", "REJECT"}:
                if (
                    not response["delivered"]
                    and self.site_snapshot(proposal)["evidence_id"] != card.evidence_id
                ):
                    raise AgentBoundaryError("Site evidence changed before steering")
                self.store.delivered(self.thread, card.card_id)
                self.failpoint("after_steering_delivery")
                return {
                    "status": "revision-requested"
                    if outcome.action == "REVISE"
                    else "proposal-rejected",
                    "owner_specialist": "site-mechanism",
                    "steering": response["outcome"],
                    "scientific_gate": "still-pending",
                }
            if card.assessment_id is None:
                from .site_review_availability import checked_failure

                review = card.scientific_summary["independent_review"]
                assert isinstance(review, dict)
                checked_failure(
                    self, self.site_snapshot(proposal, for_judge=True), review["failure_record_id"]
                )
            if card.judge_status == "BLOCKED" or proposal["evaluation"]["status"] == "BLOCKED":
                raise AgentBoundaryError(
                    "BLOCKED: change the input or hard constraint; override cannot execute it"
                )
            from .site_portfolio import is_portfolio_card, selected_proposal

            ranked = is_portfolio_card(card)
            if ranked != bool(proposal["intent"].get("portfolio")):
                raise AgentBoundaryError("Site selection policy changed since the displayed card")
            chosen = selected_proposal(proposal, outcome.selected_option_id)
            if (
                card.judge_status in {"DISCOURAGED", None}
                and outcome.action != "OVERRIDE"
                and not ranked
            ):
                raise AgentBoundaryError(
                    "Discouraged or unreviewed site requires explicit human acknowledgement"
                )
            review_ref = ArtifactRef.model_validate(proposal["review_ref"])
            template = HotspotReviewRequest.model_validate(
                yaml.safe_load(review_ref.verify(self.project).read_text())
            )
            rationale = chosen["intent"]["mechanistic_rationale"]
            if outcome.action == "OVERRIDE":
                rationale += (
                    " Selected by explicit human decision with Judge review unavailable. "
                    if card.assessment_id is None
                    else " Selected by explicit human override against Judge recommendation. "
                ) + f"Human outcome: {identity(response['outcome'])}."
            selections = [
                s.model_copy(
                    update={
                        "biological_rationale": rationale,
                        "structural_rationale": chosen["intent"]["accessibility_rationale"],
                    }
                )
                for s in template.selections
                if not ranked or s.id == chosen["selected_rank"]
            ]
            request = HotspotReviewRequest.model_validate(
                {
                    **template.model_dump(),
                    "selections": selections,
                    "approved_by": outcome.human_actor,
                    "acknowledge_user_provided_regions": True,
                    "acknowledge_evidence_limitations": True,
                }
            )
            command = self.store.prepare(
                self.thread,
                "site-approve",
                {"card_id": card.card_id, "request": card.request_identity},
                outcome=response["outcome"],
            )
            if command["state"] == "prepared":
                if self.site_snapshot(proposal)["evidence_id"] != card.evidence_id:
                    raise AgentBoundaryError("Site snapshot changed before approval")
                path = confined(
                    self.project,
                    self.project / f"site-human.{proposal['run_id']}.{card.card_id}.yaml",
                )
                encoded = yaml.safe_dump(
                    request.model_dump(mode="json"), allow_unicode=True, sort_keys=False
                )
                if not path.exists():
                    with path.open("x") as handle:
                        handle.write(encoded)
                elif path.read_text() != encoded:
                    raise AgentBoundaryError("Human site intent changed")
                self.store.update(command["id"], "dispatching", request_path=str(path))
                self.failpoint("before_site_approval")
                with scientific_environment():
                    site_approve(self.project, input_path=path, confirm=True)
                self.failpoint("after_site_approval")
            matched = self._approved_hotspots_match(chosen, request)
            approved = {
                "proposal_id": proposal["proposal_id"],
                "target_binding": proposal["target_binding"],
                "card_id": card.card_id,
                "outcome": response["outcome"],
                "warnings": outcome.recorded_warnings,
                "judge_status": card.judge_status,
                "limitations": list(
                    dict.fromkeys(
                        [
                            *card.limitations,
                            *chosen["intent"]["uncertainty"],
                        ]
                    )
                )
                if ranked
                else card.limitations,
                "judge_review": card.scientific_summary.get("independent_review", {}),
                **matched,
            }
            previous = self.project_latest("site-approved")
            if previous is None or previous["card_id"] != card.card_id:
                self.store.event(self.thread, "site-approved", approved)
            self.store.update(command["id"], "completed")
            self.store.delivered(self.thread, card.card_id)
            return {
                "status": "hotspot-approved",
                "site": chosen["intent"]["selected_site"],
                "warnings": outcome.recorded_warnings,
                "next_specialist": "none" if self.through == "site" else "binder-strategy",
            }
