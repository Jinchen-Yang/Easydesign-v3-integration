"""Approved hotspot -> reviewed/frozen design, through existing scientific services."""

from __future__ import annotations

import contextvars
import json
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from easydesign.core import (
    ArtifactRef,
    ConfigurationError,
    DecisionAuthority,
    DecisionRecord,
    DecisionRequest,
    ManifestStateError,
    canonical_model_sha256,
    load_model,
    sha256_file,
)
from easydesign.orchestration.local_jobs import ACTIVE_JOB_STATUSES
from easydesign.orchestration.local_project import resolve_project_run
from easydesign.orchestration.research import (
    STRATEGY_POINTER,
    _artifact,
    _compiled_strategy_variants,
    _foundation_plan_identity,
    load_strategy,
    strategy_freeze,
    strategy_validate,
)
from easydesign.orchestration.research_approvals import approve_execution_plan
from easydesign.orchestration.research_plans import (
    StrategyFreezePlan,
    load_current_execution_plan,
    load_execution_plan,
    plan_sha256,
)
from easydesign.safe_writes import read_last_text_line
from easydesign.stages.s02_hotspot_discovery.models import HotspotsFile
from easydesign.stages.s03_boltzgen_configuration.compiler import compile_vhh_strategy_plan

from .contracts import (
    AgentBoundaryError,
    ApplyDecision,
    DecisionCard,
    DecisionOutcome,
    EvidenceBinding,
    ReconciliationRequired,
    ScientificStatus,
)
from .design_contracts import BinderIntent
from .design_evidence import design_constraints, evaluate_design, strategy_from_intent
from .native_strategy import native_input
from .phase2 import Phase2Bridge
from .session_store import SessionStore, confined, identity
from .site_contracts import SiteQuery
from .tools import scientific_environment

BINDER_EVIDENCE: contextvars.ContextVar[EvidenceBinding | None] = contextvars.ContextVar(
    "easydesign_binder_evidence",
    default=None,
)


class DesignBridge(Phase2Bridge):
    def __init__(self, project: Path, thread: str, store: SessionStore) -> None:
        super().__init__(project, thread, store, through="design")

    def read_design_evidence(self, query: SiteQuery | None = None) -> dict[str, Any]:
        site = self.approved_site()
        if site is None:
            raise AgentBoundaryError("Gate 2 must approve hotspots before Binder Strategy")
        if self.pending_site() is not None:
            raise AgentBoundaryError("This thread still has its own pending Site proposal")
        target, facts, facts_ref = self.site_facts()
        ref = ArtifactRef.model_validate(facts_ref)
        refs = [
            *target["evidence"]["evidence_refs"],
            f"site:{site['run_id']}:hotspots#sha256={site['hotspots_sha256']}",
            f"project:{ref.relative_path}#sha256={ref.sha256}",
        ]
        current = site["proposal"]
        context = self.read_site_evidence(
            query
            or SiteQuery(label_seq_ids=list(site["hotspots"]["hotspot_sets"][0]["label_seq_ids"]))
        )
        native = native_input(self)
        binding = identity(
            {"target": target["binding"], "hotspot": site["hotspots_sha256"], "facts": facts_ref}
        )
        if native:
            native_ref = native["strategy_ref"]
            refs.append(f"project:{native_ref['relative_path']}#sha256={native_ref['sha256']}")
        return {
            "gate_type": "design-specification",
            "project_id": self.project_id,
            "run_id": site["run_id"],
            "evidence_id": binding,
            "request_identity": None,
            "evidence_refs": refs,
            "approved_hotspots": site["hotspots"]["hotspot_sets"],
            "site_rationale": current["intent"],
            "site_evidence": context["facts"],
            "next_offset": context.get("next_offset"),
            "biology": context["biology"],
            "biology_authority": facts["biology_authority"],
            "upstream_decision": {
                "action": site["outcome"]["action"],
                "warnings": site["warnings"],
                "human_rationale": site["outcome"]["optional_reason"],
                "acknowledgement": site["outcome"]["explicit_acknowledgement"],
                "authority": "verified old hotspot approval; no design approval yet",
            },
            "expert_native": None
            if native is None
            else {
                "variants": native["summary"]["variants"],
                "source_bytes": (
                    "Scientist supplied; preserve unchanged. Choose strategy_source=exper"
                    "t-native and arms=[]"
                ),
                "planned_candidates": native["summary"]["planned_candidates"],
            },
            "constraints": design_constraints(),
            "limitations": facts["limitations"],
        }

    def current_design(self) -> dict[str, Any] | None:
        proposal = self.thread_latest("design-proposal")
        site = self.approved_site()
        if proposal is None or site is None:
            return None
        evidence = self.read_design_evidence()
        if proposal["input_binding"] != evidence["evidence_id"]:
            return None
        native = native_input(self)
        if proposal.get("native_input_id") != (native["input_id"] if native else None):
            return None
        self.document(proposal["spec_ref"])
        return proposal

    def _project_ref(self, path: Path, name: str) -> dict[str, Any]:
        path = confined(self.project, path)
        return ArtifactRef.from_file(
            run_root=self.project,
            relative_path=path.relative_to(self.project).as_posix(),
            artifact_id=name,
            role="scientific-evidence",
            file_format=path.suffix.lstrip("."),
        ).model_dump(mode="json")

    def register_design(
        self, intent: BinderIntent, revision: DecisionOutcome | None = None
    ) -> dict[str, Any]:
        evidence = self.read_design_evidence()
        binding = EvidenceBinding.model_validate(
            {k: evidence[k] for k in EvidenceBinding.model_fields}
        )
        if binding != BINDER_EVIDENCE.get():
            raise AgentBoundaryError(
                "Binder intent lacks its runtime-delegated approved Site snapshot"
            )
        from .target_assessment import check_fact_claims

        check_fact_claims(intent.model_dump(mode="json"), self.read_evidence())
        site = self.approved_site()
        assert site is not None
        _, facts, _ = self.site_facts()
        parent = revision.card_id if revision else None
        native = native_input(self)
        if intent.strategy_source == "expert-native" and native is None:
            raise AgentBoundaryError("No trusted expert native strategy was imported")
        if native and intent.strategy_source != "expert-native":
            raise AgentBoundaryError(
                "Preserve scientist-provided native strategy; do not substitute generated arms"
            )
        spec = {
            "owner_thread": self.thread,
            "intent": intent.model_dump(mode="json"),
            "input_binding": binding.evidence_id,
            "parent_card_id": parent,
            "source_role": "binder-strategy",
            **({"native_input_id": native["input_id"]} if native else {}),
        }
        spec_id = identity(spec)
        previous = self.current_design()
        if previous and previous["proposal_id"] == spec_id:
            return self.design_snapshot(previous)
        evaluation = evaluate_design(
            intent,
            list(site["hotspots"]["hotspot_sets"][0]["label_seq_ids"]),
            {r["label_seq_id"] for r in facts["observed_facts"]["mapping"]},
            site["warnings"],
            upstream_discouraged=site["outcome"]["action"] == "OVERRIDE",
        )
        proposal: dict[str, Any] = {
            **spec,
            "proposal_id": spec_id,
            "spec_ref": self.persist("design-spec", spec),
            "evaluation": evaluation,
            "run_id": site["run_id"],
            "request_identity": spec_id,
            "input_refs": evidence["evidence_refs"],
        }
        if evaluation["status"] != "BLOCKED":
            directory = confined(self.store.root, self.store.root / f"design-{spec_id}")
            directory.mkdir(exist_ok=True)
            strategy_path = directory / "strategy.yaml"
            try:
                strategy = (
                    load_strategy(
                        self.project,
                        ArtifactRef.model_validate(native["strategy_ref"]).verify(self.project),
                    )
                    if native
                    else strategy_from_intent(intent, site, evidence["evidence_refs"])
                )
                if native:
                    proposal["native_input"] = native
                    evaluation["planned_candidates"] = native["summary"]["planned_candidates"]
                    evaluation["planned_strategy_count"] = len(strategy.variants)
                    evaluation["arm_count"] = len({v.hypothesis_id for v in strategy.variants})
                text = yaml.safe_dump(
                    strategy.model_dump(mode="json"), allow_unicode=True, sort_keys=False
                )
                if native:
                    text = (
                        ArtifactRef.model_validate(native["strategy_ref"])
                        .verify(self.project)
                        .read_text()
                    )
                if not strategy_path.exists():
                    with strategy_path.open("x") as handle:
                        handle.write(text)
                elif strategy_path.read_text() != text:
                    raise AgentBoundaryError("Immutable design intent changed")
                load_strategy(self.project, strategy_path)
                explicit, native_variants = _compiled_strategy_variants(self.project, strategy)
                root = Path(site["foundation_root"])
                _, target_cif = _artifact(root, "target-structure")
                _, hotspots_path = _artifact(root, "hotspots")
                hotspots = HotspotsFile.model_validate(yaml.safe_load(hotspots_path.read_text()))
                compiled_root = directory / "compiled"
                receipt = directory / "compiled.json"
                if receipt.exists():
                    compiled_refs = json.loads(receipt.read_text())
                    for ref in compiled_refs:
                        ArtifactRef.model_validate(ref).verify(self.project)
                else:
                    if compiled_root.exists():
                        raise ReconciliationRequired(
                            "Interrupted compiler output requires inspection; no blind recompile"
                        )
                    _, records = compile_vhh_strategy_plan(
                        target_cif=target_cif,
                        hotspots=hotspots,
                        artifacts_root=compiled_root,
                        variants=explicit,
                        native_variants=native_variants,
                    )
                    compiled_refs = [
                        self._project_ref(
                            compiled_root / r.design_specification_path, r.strategy_id
                        )
                        for r in records
                    ]
                    # Keep all executable assets verifiable as one compilation receipt.
                    known = {ref["relative_path"] for ref in compiled_refs}
                    for index, path in enumerate(sorted(compiled_root.rglob("*"))):
                        if (
                            path.is_file()
                            and path.relative_to(self.project).as_posix() not in known
                        ):
                            compiled_refs.append(self._project_ref(path, f"compiled-asset-{index}"))
                    with receipt.open("x") as handle:
                        json.dump(compiled_refs, handle)
                with scientific_environment():
                    validated = strategy_validate(self.project, config_path=strategy_path)
                plan, plan_path = load_current_execution_plan(self.project, "strategy-freeze")
                if not isinstance(plan, StrategyFreezePlan) or plan.strategy_sha256 != sha256_file(
                    strategy_path
                ):
                    raise AgentBoundaryError(
                        "Validation did not bind the current design specification"
                    )
                evaluation["compiled_strategy_count"] = sum(
                    ref["relative_path"].endswith("/design.yaml") for ref in compiled_refs
                )
                evaluation["compiler_validation"] = "existing compiler and backend passed"
                proposal.update(
                    strategy_ref=self._project_ref(strategy_path, "design-strategy"),
                    compiled_ref=self._project_ref(receipt, "compiled-design"),
                    plan_ref=self._project_ref(plan_path, "design-freeze-plan"),
                    request_identity=plan_sha256(plan),
                    backend_validation=[e.model_dump(mode="json") for e in validated.evidence],
                )
            except (ConfigurationError, ManifestStateError, ValueError) as error:
                # A compiler/contract failure is a hard executable constraint; an unavailable
                # backend/runtime must be configured, never misrepresented as scientific evidence.
                if isinstance(error, ConfigurationError) and "runtime profile" in str(error):
                    raise AgentBoundaryError(str(error)) from error
                evaluation.update(status="BLOCKED", hard_constraints="failed")
                evaluation["blockers"].append(
                    f"Existing compiler/validator rejected the specification: {error}"
                )
        self.store.event(self.thread, "design-proposal", proposal)
        return self.design_snapshot(proposal)

    def design_snapshot(self, proposal: dict[str, Any]) -> dict[str, Any]:
        spec = self.document(proposal["spec_ref"])
        refs = list(proposal["input_refs"])
        for key in ("spec_ref", "strategy_ref", "compiled_ref", "plan_ref"):
            if key not in proposal:
                continue
            ref = ArtifactRef.model_validate(proposal[key])
            confined(self.project, ref.verify(self.project))
            refs.append(f"project:{ref.relative_path}#sha256={ref.sha256}")
        if proposal.get("native_input"):
            for entry in [
                proposal["native_input"]["strategy_ref"],
                *proposal["native_input"]["summary"]["input_refs"],
            ]:
                native_ref = ArtifactRef.model_validate(entry)
                confined(self.project, native_ref.verify(self.project))
                refs.append(f"project:{native_ref.relative_path}#sha256={native_ref.sha256}")
        if "compiled_ref" in proposal:
            for entry in self.document(proposal["compiled_ref"]):
                ref = ArtifactRef.model_validate(entry)
                confined(self.project, ref.verify(self.project))
        return {
            "target_facts": self.read_evidence()["hard_facts"],
            "gate_type": "design-specification",
            "project_id": self.project_id,
            "run_id": proposal["run_id"],
            "status": "awaiting-human-approval",
            "request_identity": proposal["request_identity"],
            "evidence_id": identity({"proposal": proposal["proposal_id"], "refs": refs}),
            "evidence_refs": refs,
            "proposal": spec["intent"],
            "native_specification": proposal.get("native_input", {}).get("summary"),
            "evaluation": proposal["evaluation"],
            "backend_validation": proposal.get("backend_validation", []),
            "upstream": self.read_design_evidence(),
            "approval_scope": (
                "Review design coherence/executability only; no future candidate "
                "success or human design approval is implied."
            ),
        }

    def judge_evidence(self) -> dict[str, Any]:
        if self.approved_site() is None or self.pending_site() is not None:
            return super().judge_evidence()
        proposal = self.current_design()
        if proposal is None:
            raise AgentBoundaryError("Delegate Binder Strategy before the Gate 3 Judge")
        return self.design_snapshot(proposal)

    def decision_card(self, args: ApplyDecision) -> DecisionCard:
        if args.option_id != "design":
            return super().decision_card(args)
        card_id = identity({"assessment": args.assessment_id, "option": "design"})
        try:
            existing = self.store.card(self.thread, card_id)
        except AgentBoundaryError:
            existing = None
        if existing and self.store.response(self.thread, existing.card_id):
            return existing
        proposal = self.current_design()
        if proposal is None:
            raise AgentBoundaryError("No current Design Specification")
        snapshot = self.design_snapshot(proposal)
        assessment = self.store.assessment(self.thread, args.assessment_id)
        if (
            assessment.evidence_id != snapshot["evidence_id"]
            or assessment.evidence_refs != tuple(snapshot["evidence_refs"])
            or assessment.request_identity != snapshot["request_identity"]
        ):
            raise AgentBoundaryError("Gate 3 Judge assessed a stale or different snapshot")
        opinion = assessment.recommendation
        if opinion and opinion.option_id != "design":
            raise AgentBoundaryError("Judge opinion belongs to a different scientific question")
        evaluation = proposal["evaluation"]
        blocked = evaluation["status"] == "BLOCKED"
        discouraged = evaluation["status"] == "DISCOURAGED" or (
            opinion and opinion.status == "DISCOURAGED"
        )
        if (
            not blocked
            and assessment.verdict != "ready-to-ask"
            and not (assessment.verdict == "reject" and discouraged)
        ):
            raise AgentBoundaryError("Judge has not supplied a reviewable Design Specification")
        status: ScientificStatus = (
            "BLOCKED" if blocked else "DISCOURAGED" if discouraged else "SUPPORTED"
        )
        warnings = list(
            dict.fromkeys([*evaluation["warnings"], *(opinion.warnings if opinion else [])])
        )
        if blocked:
            warnings = evaluation["blockers"]
        if status == "DISCOURAGED" and not warnings:
            warnings = ["The current design is scientifically discouraged; review its limitations."]
        intent = BinderIntent.model_validate(proposal["intent"])
        card = DecisionCard(
            gate_type="design-specification",
            owner_specialist="binder-strategy",
            judge_status=status,
            card_id=card_id,
            assessment_id=assessment.assessment_id,
            project_id=self.project_id,
            run_id=proposal["run_id"],
            request_identity=proposal["request_identity"],
            evidence_id=snapshot["evidence_id"],
            question="How should we design VHH binders against the approved hotspot?",
            option_id="design",
            options=[{"option_id": "design", "label": intent.objective}],
            evidence_refs=snapshot["evidence_refs"],
            limitations=list(dict.fromkeys([*intent.uncertainty, *assessment.limitations])),
            warnings=warnings,
            alternative=(opinion.alternative if opinion else None)
            or (
                (
                    "Revise crop/CDR/conditioning constraints or reduce the number of "
                    "experimental arms."
                )
                if status == "DISCOURAGED"
                else None
            ),
            parent_card_id=proposal["parent_card_id"],
            scientific_summary={
                "binder": intent.binder,
                "objective": intent.objective,
                "approach": intent.approach_rationale,
                "target_context": intent.context_rationale,
                "scaffold_cdr_constraints": intent.scaffold_cdr_rationale,
                "design_arms": (
                    proposal["native_input"]["summary"]["variants"]
                    if proposal.get("native_input")
                    else [a.model_dump(mode="json") for a in intent.arms]
                ),
                "pilot_scope": {
                    "candidates_per_arm": 280,
                    "planned_candidates": evaluation["planned_candidates"],
                    "scaffolds_per_arm": 7,
                    "generation_started": False,
                },
                "validation": "blocked"
                if blocked
                else "existing compiler and BoltzGen validation passed",
            },
            action=(
                "Approve and freeze this specification, revise, reject, or "
                "explicitly override scientific warnings. No pilot starts."
            ),
        )
        self.store.save_card(self.thread, card)
        return card

    def _frozen_match(self, proposal: dict[str, Any], actor: str) -> dict[str, Any]:
        plan_ref = ArtifactRef.model_validate(proposal["plan_ref"])
        plan = load_execution_plan(confined(self.project, plan_ref.verify(self.project)))
        if not isinstance(plan, StrategyFreezePlan):
            raise AgentBoundaryError("Expected the original strategy freeze plan")
        foundation, mapping = _foundation_plan_identity(self.project)
        if (foundation, mapping) != (plan.foundation_manifest_sha256, plan.target_mapping_sha256):
            raise AgentBoundaryError("Upstream foundation/mapping changed after design validation")
        pointer = confined(self.project, self.project / STRATEGY_POINTER)
        if not pointer.exists():
            raise ReconciliationRequired(
                "Original scientific service has not published a frozen strategy"
            )
        strategy_path = confined(self.project, self.project / read_last_text_line(pointer))
        strategy = load_strategy(self.project, strategy_path)
        intended = load_strategy(
            self.project, ArtifactRef.model_validate(proposal["strategy_ref"]).verify(self.project)
        )
        if strategy != intended:
            raise ReconciliationRequired(
                "Current scientific strategy differs from the approved design"
            )
        approval = confined(
            self.project, self.project / "approvals/strategy-freeze" / plan_sha256(plan)
        )
        request = load_model(approval / "request.json", DecisionRequest)
        record = load_model(approval / "record.json", DecisionRecord)
        if (
            record.request_sha256 != canonical_model_sha256(request)
            or record.plan_sha256 != plan_sha256(plan)
            or request.plan_sha256 != plan_sha256(plan)
            or record.authority != DecisionAuthority.HUMAN
            or record.approved_by != actor
            or record.selected_option_ids != ("approve-exact-plan",)
        ):
            raise AgentBoundaryError(
                "Old scientific approval does not match the trusted human outcome"
            )
        return {
            "strategy_ref": self._project_ref(strategy_path, "frozen-design"),
            "approval_ref": self._project_ref(approval / "record.json", "design-approval"),
        }

    def apply_decision(self, card: DecisionCard) -> dict[str, Any]:
        if card.gate_type != "design-specification":
            return super().apply_decision(card)
        with self.store.writer():
            if self.store.card(self.thread, card.card_id) != card:
                raise AgentBoundaryError("Card differs from its runtime copy")
            response = self.store.response(self.thread, card.card_id)
            if response is None:
                raise AgentBoundaryError("A model cannot manufacture human design approval")
            outcome = DecisionOutcome.model_validate(response["outcome"])
            proposal = self.current_design()
            if proposal is None or proposal["request_identity"] != card.request_identity:
                raise AgentBoundaryError("Target, hotspot or current design changed")
            if self.design_snapshot(proposal)["evidence_id"] != card.evidence_id:
                raise AgentBoundaryError("Design evidence changed before human steering")
            if outcome.action in {"REVISE", "REJECT"}:
                self.store.delivered(self.thread, card.card_id)
                self.failpoint("after_steering_delivery")
                return {
                    "status": "revision-requested"
                    if outcome.action == "REVISE"
                    else "proposal-rejected",
                    "owner_specialist": "binder-strategy",
                    "steering": response["outcome"],
                    "scientific_gate": "still-pending",
                }
            if card.judge_status == "BLOCKED" or proposal["evaluation"]["status"] == "BLOCKED":
                raise AgentBoundaryError("BLOCKED specifications cannot be frozen by override")
            if card.judge_status == "DISCOURAGED" and outcome.action != "OVERRIDE":
                raise AgentBoundaryError("Discouraged design requires explicit human override")
            command = self.store.prepare(
                self.thread,
                "design-freeze",
                {"card_id": card.card_id},
                baseline=[p.name for p in (self.project / "strategies").glob("strategy-r*.yaml")],
            )
            if command["state"] == "prepared":
                plan = load_execution_plan(
                    ArtifactRef.model_validate(proposal["plan_ref"]).verify(self.project)
                )
                current, _ = load_current_execution_plan(self.project, "strategy-freeze")
                if current != plan:
                    raise AgentBoundaryError("Current old-service freeze plan changed; revalidate")
                self.store.update(command["id"], "dispatching")
                self.failpoint("before_design_freeze")
                with scientific_environment():
                    approve_execution_plan(self.project, plan, approved_by=outcome.human_actor)
                    strategy_freeze(
                        self.project,
                        config_path=ArtifactRef.model_validate(proposal["strategy_ref"]).verify(
                            self.project
                        ),
                        confirm=True,
                        plan_sha=plan_sha256(plan),
                    )
                self.failpoint("after_design_freeze")
            matched = self._frozen_match(proposal, outcome.human_actor)
            if (
                Path(matched["strategy_ref"]["relative_path"]).name
                in command["payload"]["baseline"]
            ):
                raise ReconciliationRequired(
                    "No new scientific strategy publication for this exact response"
                )
            approved = {
                "proposal_id": proposal["proposal_id"],
                "card_id": card.card_id,
                "input_binding": proposal["input_binding"],
                "outcome": response["outcome"],
                "warnings": card.warnings,
                **matched,
            }
            previous = self.project_latest("design-approved")
            if previous is None or previous["card_id"] != card.card_id:
                self.store.event(self.thread, "design-approved", approved)
            self.store.update(command["id"], "completed")
            self.store.delivered(self.thread, card.card_id)
            return {
                "status": "design-frozen",
                "binder": "VHH",
                "warnings": card.warnings,
                "planned_candidates": proposal["evaluation"]["planned_candidates"],
                "generation_started": False,
                "next_specialist": "none",
            }

    def approved_design(self) -> dict[str, Any] | None:
        approved = self.project_latest("design-approved")
        if approved is None or self.approved_site() is None:
            return None
        proposal = self.approved_proposal("design-proposal", approved)
        if proposal["input_binding"] != self.read_design_evidence()["evidence_id"]:
            return None
        self.design_snapshot(proposal)
        matched = self._frozen_match(proposal, approved["outcome"]["human_actor"])
        if any(matched[k] != approved[k] for k in matched):
            raise AgentBoundaryError("Published design/approval identity changed")
        return {**approved, "proposal": proposal}

    def scientific_state(self) -> dict[str, Any]:
        site = super().scientific_state()
        if site["scientific_state"] != "hotspot-approved":
            return site
        approved = self.approved_design()
        local_proposal = self.current_design()
        local_pending = local_proposal and not self.proposal_was_consumed(
            local_proposal, "design-approved"
        )
        if approved and not local_pending:
            proposal = approved["proposal"]
            return {
                "frozen_design": {
                    "binder": proposal["intent"]["binder"],
                    "arms": [
                        {
                            **{
                                key: arm[key]
                                for key in (
                                    "name",
                                    "avoid_label_seq_ids",
                                    "target_crop",
                                    "cdr_overrides",
                                    "candidates_per_scaffold",
                                )
                            },
                            "binding_label_seq_ids": arm["binding_label_seq_ids"]
                            or site["site"]["hotspots"]["hotspot_sets"][0]["label_seq_ids"],
                        }
                        for arm in proposal["intent"]["arms"]
                    ],
                    "scaffolds_per_arm": 7,
                    "compiled_strategies": proposal["evaluation"]["compiled_strategy_count"],
                    "planned_candidates": proposal["evaluation"]["planned_candidates"],
                    "cdr_template_validation": proposal["evaluation"]["cdr_template_validation"],
                    "design_viewer_url": None,
                },
                "scientific_state": "design-frozen",
                "gate_type": "design-specification",
                "next_specialist": "none",
                "generation_started": False,
            }
        proposal = self.current_design()
        return {
            "scientific_state": "awaiting-human-approval" if proposal else "design-not-proposed",
            "gate_type": "design-specification",
            "next_specialist": "binder-strategy",
            "proposal": proposal["intent"] if proposal else None,
        }

    def revision_is_current(self, outcome: DecisionOutcome) -> bool:
        card = self.store.card(self.thread, outcome.card_id)
        if card.gate_type != "design-specification":
            return super().revision_is_current(outcome)
        proposal = self.current_design()
        return bool(proposal and proposal["request_identity"] == card.request_identity)

    def terminal_result(self, message: str) -> dict[str, Any]:
        if self.approved_site() is None or self.pending_site() is not None:
            return super().terminal_result(message)
        state = self.scientific_state()
        latest_run = resolve_project_run(self.project, required=False)
        pending = (
            latest_run is not None and self.run(latest_run.run_id)[1].workflow_state is not None
        )
        active = any(
            j.status in ACTIVE_JOB_STATUSES
            for j in self.controller.list(project_id=self.project_id)
        )
        if state["scientific_state"] == "design-frozen" and not pending and not active:
            return {
                "thread": self.thread,
                "status": "finished",
                "scientific_state": "design-frozen",
                "generation_started": False,
                "message": message,
            }
        proposal = self.current_design()
        rejected = False
        if proposal:
            row = self.store.db.execute(
                (
                    "SELECT id,thread FROM cards WHERE "
                    "json_extract(payload,'$.request_identity')=? ORDER BY rowid DESC "
                    "LIMIT 1"
                ),
                (proposal["request_identity"],),
            ).fetchone()
            response = self.store.response(row["thread"], row["id"]) if row else None
            rejected = bool(response and response["delivered"] and response["response"] == "reject")
        return {
            "thread": self.thread,
            "status": "proposal-rejected" if rejected else "incomplete-turn",
            "scientific_state": state["scientific_state"],
            "gate_type": "design-specification",
            "message": "The current Design Specification is not frozen; Gate 3 remains unresolved.",
        }

    def reopen_site(self, reason: str) -> dict[str, Any]:
        execution = self.store.latest_execution(self.thread)
        if not execution or not execution.get("revision"):
            raise AgentBoundaryError("Reopening a site requires a trusted human REVISE outcome")
        outcome = DecisionOutcome.model_validate(execution["revision"])
        card = self.store.card(self.thread, outcome.card_id)
        if card.gate_type != "design-specification" or outcome.action != "REVISE":
            raise AgentBoundaryError("Only a Gate 3 revision may reopen the upstream site")
        if self.approved_design() is not None:
            raise AgentBoundaryError("A completed approval is not a new upstream revision request")
        previous = self.project_latest("site-invalidated")
        if previous is None or previous["source_card"] != card.card_id:
            self.store.event(
                self.thread,
                "site-invalidated",
                {
                    "source_card": card.card_id,
                    "human_instruction": outcome.human_instruction,
                    "reason": reason,
                    "target_binding": self.target_state()["binding"],
                },
            )
        return {
            "status": "site-revision-requested",
            "owner_specialist": "site-mechanism",
            "design_status": "invalidated",
            "target_status": "preserved",
            "instruction": outcome.human_instruction,
        }
