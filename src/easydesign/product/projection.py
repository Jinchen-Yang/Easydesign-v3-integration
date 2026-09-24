"""Bounded product views derived from verified scientific contracts."""

from __future__ import annotations

from collections import Counter
from typing import Any, Literal, cast

from easydesign.agent.phase2 import Phase2Bridge
from easydesign.agent.phase3_ranking import METRIC_DIRECTIONS
from easydesign.agent.phase34_contracts import GlobalCandidatePool, PilotMeasurement
from easydesign.agent.phase34_runtime import Phase34Runtime
from easydesign.core import ArtifactRef, ManifestStateError, load_model
from easydesign.stages.s01_target_preparation.models import ResidueMapping, TargetBundle

from .artifacts import ArtifactCatalog
from .contracts import (
    ArtifactView,
    CandidateView,
    MetricView,
    Page,
    ProjectView,
    WorkbenchProjection,
)
from .domain import GATES, DomainSession, decision_view, public_value
from .preview import excerpt

PHASES = ("target", "site", "design", "pilot", "scale", "candidates", "handoff")

ROLE_ACTIVITY = {
    "target": (
        "Structure Analyst",
        "Target identity, chains and structure evidence",
        "target",
    ),
    "site": (
        "Site Strategist",
        "Mechanism-linked Site candidates and exact hotspot geometry",
        "site",
    ),
    "binder": (
        "Binder Strategist",
        "Design arms, constraints and executable YAML",
        "design",
    ),
    "judge": (
        "Evidence Judge",
        "Independent evidence and runtime-validity review",
        None,
    ),
    "pilot-diagnosis": (
        "Pilot Ranking Specialist",
        "Pilot measurements and promotion evidence",
        "pilot",
    ),
    "final-selection": (
        "Final Selection Specialist",
        "Candidate comparison and final panel evidence",
        "candidates",
    ),
}

TOOL_ACTIVITY = {
    "prepare_target": ("Target preparation", "Preparing verified target evidence."),
    "get_job_status": ("Target preparation", "Checking the authoritative target job receipt."),
    "read_target_evidence": ("Target evidence", "Reading the verified Target evidence packet."),
    "read_site_evidence": ("Site evidence", "Reading the bounded Site evidence dossier."),
    "evaluate_candidate_site": (
        "Candidate Site evaluation",
        "Validating hotspot mapping and deterministic Site constraints.",
    ),
    "read_design_evidence": ("Design evidence", "Reading the approved Site and Design evidence."),
    "evaluate_design_constraints": (
        "Design constraint validation",
        "Validating deterministic Design constraints and YAML prerequisites.",
    ),
    "read_scientific_evidence": (
        "Independent evidence review",
        "Reading the bounded evidence packet for independent review.",
    ),
    "request_scientific_decision": (
        "Scientist Gate",
        "Publishing a reviewed Gate decision for the Scientist.",
    ),
    "request_downstream_decision": (
        "Scientist Gate",
        "Publishing the next reviewed downstream Gate decision.",
    ),
    "advance_downstream": (
        "Downstream transition",
        "Advancing only the Scientist-authorized downstream state.",
    ),
}

STAGE_ACTIVITY = {
    "not-prepared": (
        "Target Intelligence",
        "Resolving target identity and structure evidence.",
    ),
    "target-running": (
        "Target preparation",
        "Reconciling the approved structure choice with the native Target run.",
    ),
    "site-not-proposed": (
        "Site Intelligence",
        "Comparing mechanism-linked Sites and exact hotspot candidates.",
    ),
    "design-not-proposed": (
        "Design Intelligence",
        "Converting the approved Site into design arms and executable YAML.",
    ),
    "judge": (
        "Independent review",
        "Checking the current proposal, evidence provenance and runtime validity.",
    ),
    "scientist-gate": (
        "Scientist Gate",
        "Preparing the current reviewed decision for explicit Scientist authority.",
    ),
    "pilot-dispatch": (
        "Pilot execution",
        "Executing only the approved Pilot authority.",
    ),
    "pilot-card": (
        "Pilot review",
        "Preparing the Pilot evidence and promotion decision.",
    ),
    "scientist-gate4": (
        "Gate 4",
        "Preparing the Pilot promotion decision for the Scientist.",
    ),
    "scale-execution": (
        "Scale campaign",
        "Projecting the authorized Scale campaign and candidate evidence.",
    ),
    "final-selection": (
        "Final selection",
        "Comparing the candidate panel and preparing the final review.",
    ),
    "scientist-gate5": (
        "Gate 5",
        "Preparing the final panel disposition for the Scientist.",
    ),
}

MILESTONE_ACTIVITY = {
    "target-assessment": (
        "target.proposal.ready",
        "Target assessment ready",
        "A structured Target interpretation is ready for independent review.",
        "target",
    ),
    "site-evidence-dossier": (
        "site.evidence.ready",
        "Site evidence ready",
        "The bounded Site evidence dossier was committed.",
        "site",
    ),
    "site-decision": (
        "site.synthesis.ready",
        "Site synthesis ready",
        "Mechanistic Site evidence was synthesized into ranked candidates.",
        "site",
    ),
    "site-proposal": (
        "site.proposal.ready",
        "Site portfolio ready",
        "The ranked Site A/B/C portfolio and hotspot geometry are ready for review.",
        "site",
    ),
    "site-approved": (
        "site.approved",
        "Site approved",
        "The Scientist-approved Site and exact hotspot residues are frozen.",
        "site",
    ),
    "design-proposal": (
        "design.proposal.ready",
        "Design specification ready",
        "Design arms, deterministic constraints and executable YAML are ready for review.",
        "design",
    ),
    "design-approved": (
        "design.approved",
        "Design approved",
        "The Scientist-approved Design specification is frozen.",
        "design",
    ),
    "phase34-pilot-dossier": (
        "pilot.review.ready",
        "Pilot evidence ready",
        "The bounded Pilot evidence dossier is ready for review.",
        "pilot",
    ),
    "phase34-pilot-promotion-card": (
        "gate.opened",
        "Gate 4 ready",
        "The Pilot promotion decision is ready for explicit Scientist authority.",
        "pilot",
    ),
    "phase34-final-review-dossier": (
        "final.review.ready",
        "Final review ready",
        "The final candidate comparison dossier is ready.",
        "candidates",
    ),
    "phase34-wet-lab-handoff-card": (
        "gate.opened",
        "Gate 5 ready",
        "The final panel disposition is ready for explicit Scientist authority.",
        "candidates",
    ),
    "phase34-wet-lab-handoff": (
        "handoff.recorded",
        "Handoff recorded",
        "The Scientist's final disposition was recorded; no order was placed.",
        "handoff",
    ),
}


def phase_for(stage: str, gate_type: str | None) -> str:
    if stage == "handoff-complete":
        return "handoff"
    if stage.startswith(("final", "scientist-gate5")):
        return "candidates"
    if stage.startswith("scale"):
        return "scale"
    if stage.startswith(("pilot", "scientist-gate4")):
        return "design" if stage == "pilot-plan-review" else "pilot"
    if gate_type in GATES:
        return GATES[gate_type][1]
    if stage.startswith(("design", "hotspot")):
        return "design"
    if stage.startswith("site"):
        return "site"
    return "target"


def population(session: DomainSession) -> tuple[list[Any], Any, dict[str, Any]]:
    b = session.bridge
    if not isinstance(b, Phase34Runtime):
        return [], None, {}
    final = b.current_final_dossier() if b.downstream_scope == "handoff" else None
    pool_event = b.project_latest("phase34-global-candidate-pool")
    authority = b.project_latest("phase34-scale-authority")
    if pool_event and authority:
        pool = b.load_contract(
            kind="phase34-global-candidate-pool", contract_type=GlobalCandidatePool
        )
        if pool.campaign.promotion_authority.model_dump(mode="json") == b.document(
            authority["ref"]
        ):
            panel = final.proposed_selection.model_dump(mode="json") if final else {}
            return list(pool.candidates), pool, panel
    dossier = b.current_pilot_dossier()
    event = b.project_latest("phase34-pilot-measurement")
    measurement = (
        dossier.measurement
        if dossier
        else (
            b.load_contract(kind="phase34-pilot-measurement", contract_type=PilotMeasurement)
            if event and b.pilot_authority()
            else None
        )
    )
    return list(measurement.candidates) if measurement else [], measurement, {}


def native_for(candidate: Any, owner: Any) -> Any:
    if isinstance(owner, GlobalCandidatePool):
        return candidate.native_evidence
    native = owner.native_evidence if owner else None
    return (
        next(
            (c for c in native.candidates if c.candidate_id == candidate.lineage.candidate_id), None
        )
        if native
        else None
    )


def candidate_view(
    session: DomainSession,
    candidate: Any,
    owner: Any,
    panel: dict[str, Any],
    catalog: ArtifactCatalog,
) -> CandidateView:
    b, line = session.bridge, candidate.lineage
    native = native_for(candidate, owner)
    values = {**native.metrics, **native.additional_metrics} if native else {}
    original_metrics = {m.metric_id.removeprefix("boltzgen-"): m for m in candidate.metrics}
    values = {**{name: m.value for name, m in original_metrics.items()}, **values}
    decisions = {d.feature: d for d in native.decisions} if native else {}
    metrics = []
    for name, value in values.items():
        if name in {"designed_chain_sequence", "target_chain_sequence"}:
            continue
        rule, observation = decisions.get(name), original_metrics.get(name)
        metrics.append(
            MetricView(
                id=name,
                label=name.replace("_", " "),
                value=value,
                unit=observation.unit if observation else None,
                direction=("lower" if rule.lower_is_better else "higher")
                if rule
                else cast(
                    Literal["lower", "higher", "context"], METRIC_DIRECTIONS.get(name, "context")
                ),
                status="missing" if value is None else "available",
                rule_result=(
                    "unknown" if rule.passed is None else "pass" if rule.passed else "fail"
                )
                if rule
                else None,
                threshold=rule.threshold if rule else None,
                profile_id=native.profile_sha256 if native else None,
                source=native.metric_sources.get(name)
                if native
                else observation.source
                if observation
                else None,
            )
        )
    if isinstance(owner, GlobalCandidatePool):
        root, _ = b.run(line.source_run_id)
        refs = line.artifact_refs
        independent = candidate.independent_prediction_status
        evaluable = candidate.validity == "valid-evaluated"
        eligible = candidate.competition_eligible
        reason = candidate.failure_reason
    else:
        execution = b.project_latest("phase34-pilot-execution")
        root, _ = b.run(execution["run_id"])
        refs = (line.original_structure, line.refolded_structure)
        independent = "not-requested" if native else "legacy-unspecified"
        evaluable = native.native_pass is not None if native else True
        eligible = native.native_pass is True if native else candidate.legacy_policy_pass
        reason = "Native evidence incomplete" if not evaluable else None
    artifacts: list[ArtifactView] = []
    seen = set()
    for ref in refs:
        if ref.file_format.lower() not in {"pdb", "cif", "mmcif"} or ref.sha256 in seen:
            continue
        seen.add(ref.sha256)
        artifacts.append(
            catalog.register(
                project=session.project,
                evidence=line.sequence_sha256,
                root=root,
                ref=ref,
                label=ref.artifact_id,
                candidate_id=line.candidate_id,
            )
        )
    role: Literal["primary", "backup"] | None = (
        "primary"
        if line.candidate_id in panel.get("primary_candidate_ids", [])
        else ("backup" if line.candidate_id in panel.get("backup_candidate_ids", []) else None)
    )
    return CandidateView(
        id=line.candidate_id,
        arm=line.strategy_id,
        backend_id=line.backend_candidate_id,
        native_status="not-available"
        if native is None
        else "incomplete"
        if native.native_pass is None
        else "pass"
        if native.native_pass
        else "fail",
        evaluable=evaluable,
        competition_eligible=eligible,
        independent_prediction=independent,
        sequence=values.get("designed_chain_sequence"),
        sequence_sha256=line.sequence_sha256,
        metrics=metrics,
        artifacts=artifacts,
        panel_role=role,
        failure_reason=reason,
        # Native evidence adapter verifies A=target / B=binder for these complexes.
        structure_roles={"A": "target", "B": "binder"} if native else {},
        lineage={
            name: getattr(line, name, None)
            for name in (
                "strategy_id",
                "batch_id",
                "source_run_id",
                "generation_task_id",
                "task_id",
            )
        },
    )


def candidate_page(
    session: DomainSession,
    catalog: ArtifactCatalog,
    offset: int,
    limit: int,
    candidate_id: str | None = None,
) -> Page:
    _, _, revision = session.current()
    candidates, owner, panel = population(session)
    # Presentation order preserves the actual selection. It does not run another ranking.
    panel_ids = [*panel.get("primary_candidate_ids", []), *panel.get("backup_candidate_ids", [])]
    if panel_ids:
        order = {identifier: index for index, identifier in enumerate(panel_ids)}
        candidates.sort(
            key=lambda c: (order.get(c.lineage.candidate_id, len(order)), c.lineage.candidate_id)
        )
    if candidate_id:
        candidates = [c for c in candidates if c.lineage.candidate_id == candidate_id]
    return Page(
        revision=revision,
        total=len(candidates),
        offset=offset,
        limit=limit,
        items=[
            candidate_view(session, c, owner, panel, catalog).model_dump(mode="json")
            for c in candidates[offset : offset + limit]
        ],
    )


def activity_rows(
    store: Any,
    thread: str,
    after: int = 0,
    limit: int = 30,
    *,
    recent: bool = False,
) -> list[dict[str, Any]]:
    rows = store.db.execute(
        "SELECT seq,kind,payload FROM events WHERE thread=? AND seq>? ORDER BY seq "
        + ("DESC" if recent else "ASC")
        + " LIMIT ?",
        (thread, after, limit),
    ).fetchall()
    import json

    items = []
    for row in reversed(rows) if recent else rows:
        payload = json.loads(row["payload"])
        kind = str(row["kind"])
        if row["kind"] == "product-activity":
            items.append({"id": row["seq"], "visible": True, **public_value(payload)})
            continue
        # Only deterministic, whitelisted summaries leave the native ledger. Raw
        # prompts, provider responses, tool results and reasoning remain private.
        text = payload.get("text", "") if kind in {"user", "assistant"} else ""
        role = str(payload.get("role") or payload.get("specialist") or "") or None
        tool = str(payload.get("name") or payload.get("tool") or "") or None
        native_status = str(payload.get("status") or "") or None
        execution_id = str(payload.get("execution_id") or "") or None
        task_id = None
        status = native_status
        title = None
        summary = None
        phase = None
        visible = False
        event_type = "runtime.record"

        if kind in {"user", "assistant"}:
            visible = True
            event_type = "scientist.message" if kind == "user" else "assistant.summary"
            title = "Scientist" if kind == "user" else "EasyDesign"
        elif kind in {"model-call", "model-response"} and role:
            title, scope, phase = ROLE_ACTIVITY.get(
                role, (role.replace("-", " ").title(), "Bounded scientific review", None)
            )
            task_id = f"specialist-{execution_id or role}"
            status = "running" if kind == "model-call" else "completed"
            event_type = "specialist.started" if kind == "model-call" else "specialist.completed"
            summary = (
                f"{title} is reviewing {scope.lower()}."
                if kind == "model-call"
                else "A structured response was received; Runtime is validating it "
                "against the scientific contract."
            )
            visible = True
        elif kind == "runtime-dispatch" and tool:
            stage = str(payload.get("stage") or "")
            title, summary = STAGE_ACTIVITY.get(
                stage,
                TOOL_ACTIVITY.get(
                    tool,
                    (tool.replace("_", " ").title(), "Executing an authorized Runtime action."),
                ),
            )
            phase = phase_for(stage, None)
            task_id = f"execution-{execution_id or payload.get('action_id') or row['seq']}"
            status = "running"
            event_type = "runtime.started"
            visible = True
        elif kind == "runtime-action-timing" and tool:
            stage = str(payload.get("stage") or "")
            title, base_summary = STAGE_ACTIVITY.get(
                stage,
                TOOL_ACTIVITY.get(
                    tool,
                    (tool.replace("_", " ").title(), "Authorized Runtime action recorded."),
                ),
            )
            phase = phase_for(stage, None)
            task_id = f"execution-{execution_id or payload.get('action_id') or row['seq']}"
            status = (
                "blocked"
                if native_status == "awaiting-human-approval"
                else "failed"
                if native_status == "failed"
                else "completed"
            )
            summary = (
                "The reviewed decision is awaiting explicit Scientist authority."
                if native_status == "awaiting-human-approval"
                else base_summary.replace("Executing", "Completed")
            )
            event_type = (
                "gate.awaiting"
                if native_status == "awaiting-human-approval"
                else "runtime.failed"
                if native_status == "failed"
                else "runtime.completed"
            )
            visible = native_status in {"awaiting-human-approval", "failed"}
        elif kind == "tool" and tool:
            title, summary = TOOL_ACTIVITY.get(
                tool,
                (tool.replace("_", " ").title(), "A bounded Runtime tool call completed."),
            )
            task_id = f"tool-{execution_id or role or 'runtime'}-{tool}"
            status = (
                "failed"
                if native_status == "failed"
                else "completed"
                if native_status in {"success", "completed", "succeeded"}
                else native_status or "completed"
            )
            event_type = "tool.failed" if status == "failed" else "tool.completed"
            visible = tool in TOOL_ACTIVITY or status == "failed"
        elif kind == "submission-preflight-passed" and role:
            title = ROLE_ACTIVITY.get(role, (role.replace("-", " ").title(), "", None))[0]
            phase = ROLE_ACTIVITY.get(role, ("", "", None))[2]
            task_id = f"contract-{execution_id or role}"
            status = "completed"
            event_type = "contract.validated"
            summary = "The structured response passed deterministic contract validation."
            visible = True
        elif kind in {"evidence-research", "evidence-selection"}:
            task_id = "research-evidence"
            status = "completed"
            title = "Evidence research"
            summary = (
                "Verified source records were retained for the current scientific question."
                if kind == "evidence-research"
                else "The bounded evidence set was bound to the current review."
            )
            event_type = (
                "research.completed" if kind == "evidence-research" else "evidence.recorded"
            )
            visible = True
        elif kind == "site-research-lifecycle":
            milestone = str(payload.get("milestone") or "")
            descriptions = {
                "initialized": "Site research initialized from the approved Target state.",
                "structured-context-acquired": "Structured Target and geometry context acquired.",
                "evidence-sufficient": "The Site evidence set is sufficient for bounded synthesis.",
                "finalization-pending": "Evidence is frozen; final Site synthesis is in progress.",
                "handoff-committed": "The Site research dossier was committed immutably.",
                "site-synthesis-ready": "Site research is ready for ranked A/B/C synthesis.",
            }
            title = "Site research"
            summary = descriptions.get(milestone, "Site research state was updated.")
            task_id = f"site-research-{execution_id or 'current'}"
            status = (
                "completed"
                if milestone in {"handoff-committed", "site-synthesis-ready"}
                else "running"
            )
            phase = "site"
            event_type = "site.research.progress"
            visible = True
        elif kind == "judge-assessment":
            verdict = str(payload.get("verdict") or "").upper()
            title = "Independent review ready"
            summary = (
                f"The Evidence Judge recorded {verdict}; explicit Scientist authority "
                "remains at the Gate."
                if verdict in {"SUPPORTED", "DISCOURAGED", "BLOCKED"}
                else "The independent evidence review was recorded for the current Gate."
            )
            task_id = f"judge-assessment-{payload.get('assessment_id') or row['seq']}"
            status = "completed"
            event_type = "judge.review.ready"
            visible = True
        elif kind in MILESTONE_ACTIVITY:
            event_type, title, summary, phase = MILESTONE_ACTIVITY[kind]
            task_id = f"milestone-{kind}-{row['seq']}"
            status = "completed"
            visible = True
        elif kind == "human-response":
            response = str(payload.get("response") or "decision").lower()
            title = "Scientist decision recorded"
            summary = {
                "approve": "The Scientist approved the selected Gate option.",
                "override": "The Scientist recorded an acknowledged override.",
                "revise": "The Scientist requested a bounded scientific revision.",
                "reject": "The Scientist rejected the current proposal; evidence was retained.",
            }.get(response, "The explicit Scientist Gate response was recorded.")
            task_id = f"gate-response-{payload.get('card') or row['seq']}"
            status = "completed"
            event_type = "gate.resolved"
            visible = True
        elif kind == "agent-terminal":
            title = "EasyDesign run"
            summary = (
                "The authorized workflow turn finished; scientific evidence and decisions "
                "are saved."
            )
            task_id = "agent-terminal"
            status = native_status or "completed"
            event_type = "agent.finished"
            visible = True
        items.append(
            {
                "id": row["seq"],
                "type": event_type,
                "visible": visible,
                "text": public_value(text),
                "role": role,
                "tool": tool,
                "status": status,
                "task_id": task_id,
                "title": title,
                "summary": summary,
                "phase": phase,
            }
        )
    return items


def activity(
    session: DomainSession, after: int = 0, limit: int = 30, *, recent: bool = False
) -> list[dict[str, Any]]:
    return activity_rows(session.bridge.store, session.bridge.thread, after, limit, recent=recent)


def activity_tasks(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for item in items:
        task_id = item.get("task_id")
        # Low-level read/format tool receipts stay in the private ledger. They are
        # useful for audit and failure diagnosis, but not as user-facing Agent tasks.
        if task_id and not (str(task_id).startswith("tool-") and item.get("visible") is False):
            latest[str(task_id)] = item
    return list(latest.values())


def context_view(
    session: DomainSession, catalog: ArtifactCatalog
) -> tuple[dict[str, Any], list[ArtifactView]]:
    b = session.bridge
    context: dict[str, Any] = {"sites": [], "arms": [], "structure": None}
    artifacts: list[ArtifactView] = []
    intent_row = b.store.db.execute(
        "SELECT payload FROM events WHERE thread=? AND kind='goal-target-intent' "
        "ORDER BY seq DESC LIMIT 1",
        (b.thread,),
    ).fetchone()
    if intent_row is not None:
        import json

        context["target_intent"] = public_value(json.loads(intent_row[0]).get("intent"))
    loaded = b.validate_project()
    source = loaded.source_path
    if source is not None:
        ref = ArtifactRef.from_file(
            run_root=b.project,
            relative_path=source.relative_to(b.project).as_posix(),
            artifact_id="input-target",
            role="user-input",
            file_format=source.suffix[1:],
        )
        raw = catalog.register(
            project=session.project,
            evidence=b.binding(),
            root=b.project,
            ref=ref,
            label="Input target",
        )
        context["structure"] = raw.model_dump(mode="json")
        artifacts.append(raw)
    else:
        context["target_source"] = public_value(loaded.config.target.source.model_dump(mode="json"))
    if not isinstance(b, Phase2Bridge) or not b.target_run_id():
        return context, artifacts
    try:
        evidence = b.read_evidence()
    except ManifestStateError:
        # Approval and native manifest publication are separate durable writes. A
        # read in that narrow interval must remain an honest partial projection,
        # not turn a healthy background transition into a product-level 500.
        context["target"] = {
            "status": "reconciling",
            "limitations": [
                "The approved Target decision is being reconciled with the native run receipt."
            ],
        }
        return context, artifacts
    context["target"] = public_value(
        {
            k: evidence.get(k)
            for k in (
                "status",
                "decision_kind",
                "hard_facts",
                "target_interpretation",
                "limitations",
                "options",
                "identity",
                "provenance",
            )
        }
    )
    if evidence["status"] != "succeeded" or evidence.get("request_identity"):
        return context, artifacts
    state = b.target_state()
    bundle = load_model(state["bundle_path"], TargetBundle)
    ref = bundle.target_pdb or bundle.target_structure
    target = catalog.register(
        project=session.project,
        evidence=state["binding"],
        root=state["root"],
        ref=ref,
        label="Prepared target",
    )
    artifacts.append(target)
    mapping = load_model(bundle.residue_mapping.verify(state["root"]), ResidueMapping)
    context["structure"] = target.model_dump(mode="json")
    context["target_id"] = bundle.target_id
    context["sequence_length"] = bundle.sequence_length
    context["chains"] = sorted({r.author_chain_id for r in mapping.entries})
    approved = b.approved_site()
    proposal = b.current_site() or (approved["proposal"] if approved else None)
    if approved:
        context["approved_site"] = {
            "selected_candidate_id": approved["proposal"].get("selected_candidate_id"),
            "selected_rank": approved["proposal"].get("selected_rank"),
            "hotspots": public_value(approved["hotspots"]),
        }
    if proposal:
        portfolio = proposal["intent"].get("portfolio") or proposal.get("ranked_portfolio", [])
        context["sites"] = [
            public_value(
                {
                    "id": item["candidate_id"],
                    "rank": item["rank"],
                    "name": item["site"]["name"],
                    "selectable": item["selectable"],
                    "design_labels": item["site"]["hotspot_label_seq_ids"],
                    "why_ranked": item["why_ranked"],
                    "risks": item["major_risks"],
                    "uncertainty": item["uncertainty"],
                    "confidence": item["confidence"],
                    "coordinates": [
                        r.model_dump(mode="json")
                        for r in mapping.entries
                        if r.label_seq_id in item["site"]["hotspot_label_seq_ids"]
                    ],
                }
            )
            for item in portfolio
        ]
        context["site_evidence_id"] = proposal["proposal_id"]
    from easydesign.agent.design import DesignBridge

    if isinstance(b, DesignBridge):
        design = b.current_design()
        approved_design = b.approved_design()
        design = design or (approved_design["proposal"] if approved_design else None)
        if design:
            context["arms"] = [
                public_value(
                    {
                        k: v
                        for k, v in arm.items()
                        if k
                        in {
                            "arm_id",
                            "name",
                            "hypothesis",
                            "rationale",
                            "role",
                            "expected_result",
                            "failure_interpretation",
                            "changed_factors",
                            "held_constant",
                        }
                    }
                )
                for arm in design["intent"]["arms"]
            ]
            artifacts.append(
                catalog.document(
                    session.project,
                    design["proposal_id"],
                    public_value(design["intent"]),
                    "Complete Design intent",
                )
            )
            context["design_approved"] = approved_design is not None
            if design.get("compiled_ref"):
                for item in b.document(design["compiled_ref"]):
                    entry = ArtifactRef.model_validate(item)
                    if entry.file_format.lower() in {"yaml", "yml"}:
                        artifacts.append(
                            catalog.register(
                                project=session.project,
                                evidence=design["proposal_id"],
                                root=b.project,
                                ref=entry,
                                label=entry.artifact_id,
                            )
                        )
    return context, artifacts


def project_view(session: DomainSession, title: str | None = None) -> ProjectView:
    action, card, _ = session.current()
    b = session.bridge
    scientific = b.scientific_state() if isinstance(b, Phase2Bridge) else {}
    gate = card.gate_type if card else scientific.get("gate_type")
    phase = phase_for(action.stage, gate)
    status = "awaiting_scientist" if card else "available" if action.tool else "incomplete"
    if action.stage in {"handoff-complete", "design-frozen", "scale-authorized"}:
        status = "complete"
    elif action.stage in {"scientist-stopped", "proposal-rejected"}:
        status = "stopped"
    elif "running" in action.stage:
        status = "running"
    elif "blocked" in action.stage:
        status = "blocked"
    elif any(word in action.stage for word in ("incomplete", "operational", "reconcile")):
        status = "incomplete"
    rows = b.store.db.execute("SELECT MAX(seq) FROM events WHERE thread=?", (b.thread,)).fetchone()
    validation = False
    if isinstance(b, Phase34Runtime):
        authority = b.project_latest("phase34-pilot-authority")
        validation = bool(
            authority and authority["contract_type"] == "ValidationExecutionAuthority"
        )
        campaign = b.project_latest("phase34-scale-campaign")
        if campaign:
            data = b.document(campaign["ref"])
            validation = validation or data["execution"]["mode"] not in {
                "production",
                "formal-pilot",
            }
            validation = (
                validation or not data["promotion_authority"]["authorizes_scientific_scale"]
            )
    return ProjectView(
        id=session.project,
        title=title or session.project,
        goal=session.goal,
        thread_id=b.thread,
        phase=phase,
        status=status,
        last_activity=rows[0] or 0,
        validation_only=validation,
    )


def workbench(
    session: DomainSession, catalog: ArtifactCatalog, title: str | None = None
) -> WorkbenchProjection:
    b = session.bridge
    action, card, revision = session.current()
    project = project_view(session, title)
    context, artifacts = context_view(session, catalog)
    candidates, owner, panel = population(session)
    counts = Counter(
        "not-available"
        if (native := native_for(c, owner)) is None
        else "incomplete"
        if native.native_pass is None
        else "pass"
        if native.native_pass
        else "fail"
        for c in candidates
    )
    context["panel"] = public_value(panel)
    if isinstance(owner, GlobalCandidatePool):
        context["campaign"] = {
            "id": owner.campaign.campaign_id,
            "planned_batches": owner.planned_batches,
            "complete_batches": len(owner.completed_batch_ids),
            "failed_batches": len(owner.failed_batch_ids),
            "resumable_batches": len(owner.resumable_batch_ids),
            "production_intent": owner.campaign.promotion_authority.model_dump(mode="json"),
            "execution": owner.campaign.execution.model_dump(mode="json"),
        }
    current_index = PHASES.index(project.phase)
    workflow: list[dict[str, Any]] = [
        {"id": "goal", "label": "Goal", "status": "complete", "gate": None}
    ] + [
        {
            "id": phase,
            "label": phase.title(),
            "status": "complete"
            if index < current_index or (index == current_index and project.status == "complete")
            else project.status
            if index == current_index
            else "locked",
            "gate": next((number for number, name in GATES.values() if name == phase), None),
        }
        for index, phase in enumerate(PHASES)
    ]
    checks = {
        "goal": [("Research goal recorded", True)],
        "target": [
            ("Interpret biological goal", True),
            (
                "Resolve target identity",
                bool(context.get("target", {}).get("hard_facts", {}).get("canonical_accession"))
                or context.get("target", {}).get("decision_kind")
                in {"structure-selection", "chain-selection"},
            ),
            (
                "Survey structure inventory",
                bool(context.get("target", {}).get("options")) or bool(context.get("target_id")),
            ),
            ("Scientist structure decision", card is not None or project.phase != "target"),
            ("Prepare Target Bundle", bool(context.get("target_id"))),
        ],
        "site": [
            ("Compare candidate sites", bool(context.get("sites"))),
            ("Review hotspot residues", bool(context.get("sites"))),
            ("Approve a binding site", bool(context.get("approved_site"))),
        ],
        "design": [
            ("Review design arms", bool(context.get("arms"))),
            ("Approve the design", bool(context.get("design_approved"))),
        ],
        "pilot": [("Review candidate evidence", bool(candidates))],
        "scale": [("Review campaign progress", bool(context.get("campaign")))],
        "candidates": [
            ("Compare the candidate panel", bool(panel)),
            ("Finalize the panel", project.phase == "handoff"),
        ],
    }
    for step in workflow:
        step["subtasks"] = [
            {"label": label, "status": "complete" if done else "waiting"}
            for label, done in checks.get(step["id"], [])
        ]
    jobs = [
        {
            "id": j.job_id,
            "phase": {
                1: "target",
                2: "site",
                3: "design",
                4: "pilot",
                5: "pilot",
                6: "scale",
                7: "candidates",
            }.get(j.step, "unknown"),
            "status": str(j.status),
            "resumable": str(j.status) in {"failed", "lost", "drained"},
            "validation_only": project.validation_only,
        }
        for j in b.controller.list(project_id=b.project_id)
    ][:40]
    events = activity(session, recent=True)
    projected_tasks = activity_tasks(activity(session, limit=200, recent=True))
    known_tasks = {task.get("task_id"): task for task in projected_tasks}
    for index, job in enumerate(jobs):
        task_id = "target-job-" + job["id"]
        native_status = job["status"]
        historical_gate_resolved = native_status == "awaiting-human-approval" and (
            (job["phase"] in PHASES and PHASES.index(job["phase"]) < current_index)
            or (job["phase"] == "target" and bool(context.get("target_id")))
            or (job["phase"] == "site" and bool(context.get("approved_site")))
            or (job["phase"] == "design" and bool(context.get("design_approved")))
        )
        projected = {
            "id": -(index + 1),
            "type": "job." + native_status,
            "task_id": task_id,
            "title": job["phase"].title() + " scientific job",
            "summary": (
                "Historical native Gate receipt; the later Scientist approval is recorded."
                if historical_gate_resolved
                else "Authoritative native execution receipt."
            ),
            "phase": job["phase"],
            "status": "completed"
            if native_status == "succeeded" or historical_gate_resolved
            else "failed"
            if native_status in {"failed", "operational-failed", "lost", "drained"}
            else "pending"
            if native_status == "queued"
            else "running",
        }
        if existing := known_tasks.get(task_id):
            existing.update(projected)
        else:
            projected_tasks.append(projected)
    from easydesign.agent.cli import public_text

    conversation = []
    for row in b.store.db.execute(
        "SELECT seq,kind,payload FROM events WHERE thread=? "
        "AND kind IN ('user','assistant') ORDER BY seq",
        (b.thread,),
    ):
        import json

        payload = json.loads(row["payload"])
        text = public_text(payload.get("text", ""))
        if text:
            conversation.append(
                {
                    "id": "native-" + str(row["seq"]),
                    "kind": "user" if row["kind"] == "user" else "summary",
                    "phase": "goal"
                    if row["kind"] == "user" and text == session.goal
                    else project.phase,
                    "text": text,
                }
            )
    role = action.arguments.get("subagent_type")
    decision = decision_view(card) if card else None
    if decision:
        assert card is not None
        detail = catalog.document(session.project, card.card_id, decision, "Complete Gate review")
        artifacts.append(detail)
        decision = {
            **decision,
            "summary": excerpt(decision["summary"]),
            "details_url": detail.url,
            "summary_is_excerpt": excerpt(decision["summary"]) != decision["summary"],
        }
    return WorkbenchProjection(
        revision=revision,
        project=project,
        workflow=workflow,
        current_action={
            "id": action.action_id,
            "stage": action.stage,
            "message": public_value(action.message),
            "resumable": action.tool is not None and card is None,
        },
        specialists=[{"role": role, "status": "pending"}] if role else [],
        scientific_context=public_value(context),
        decision=decision,
        jobs=jobs,
        artifacts=artifacts,
        recent_activity=events,
        tasks=projected_tasks,
        conversation=conversation,
        event_cursor=project.last_activity,
        candidates={
            "total": len(candidates),
            "counts": dict(counts),
            "url": f"/api/v1/projects/{session.project}/candidates",
        },
        capabilities={
            "demo_controls": False,
            "lab_order": False,
            "decide": card is not None,
            "message": True,
            "resume": action.tool is not None and card is None,
        },
    )
