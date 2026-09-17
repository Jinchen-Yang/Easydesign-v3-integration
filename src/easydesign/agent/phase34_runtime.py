"""Current-object authority and deterministic downstream actions in the native harness."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal, cast

from easydesign.core import canonical_model_sha256
from easydesign.orchestration.config import LoadedStructureRunConfig, PredictionBackend
from easydesign.orchestration.local_jobs import ACTIVE_JOB_STATUSES

from .contracts import AgentBoundaryError, ApplyDecision, DecisionCard, DecisionOutcome
from .control_flow import RuntimeAction, _task
from .design import DesignBridge
from .phase34_authority import (
    accept_pilot_plan,
    pilot_review_card,
    plan_for_design,
    verify_pilot_authority,
)
from .phase34_bridge import Phase34Bridge
from .phase34_contracts import (
    FinalReviewDossier,
    PilotEvidenceDossier,
    PilotMeasurement,
    ScientistPilotAuthority,
    ValidationExecutionAuthority,
)
from .phase34_execution import execute_pilot, validate_downstream_project
from .phase34_plan import BoundPilotPlan
from .phase34_read_scope import authority_read, verified_read
from .session_store import SessionStore, identity


class Phase34Runtime(Phase34Bridge):
    """An additive scope: upstream DesignBridge retains the current Phase 2 behavior."""

    def __init__(
        self,
        project: Path,
        thread: str,
        store: SessionStore,
        *,
        through: Literal["pilot", "handoff"] = "pilot",
        prediction_backend: PredictionBackend = "openfold3-af3-jax",
        pilot_allocations: dict[str, int] | None = None,
    ) -> None:
        self.downstream_scope = through
        self.prediction_backend = prediction_backend
        self.pilot_allocations = dict(pilot_allocations) if pilot_allocations is not None else None
        super().__init__(project, thread, store)
        scope: dict[str, Any] = {"through": through, "prediction_backend": prediction_backend}
        if pilot_allocations is not None:
            scope["pilot_allocations"] = pilot_allocations
        prior = self.thread_latest("phase34-scope")
        if pilot_allocations is None and prior and "pilot_allocations" in prior:
            self.pilot_allocations = dict(prior["pilot_allocations"])
            scope["pilot_allocations"] = self.pilot_allocations
        if prior and any(prior.get(k) != v for k, v in scope.items()):
            raise AgentBoundaryError("Downstream thread scope/backend is immutable")
        if prior is None:
            store.event(thread, "phase34-scope", scope)

    def validate_project(self) -> LoadedStructureRunConfig:
        return validate_downstream_project(self) or super().validate_project()

    def _design_invalidated(self, event: dict[str, Any]) -> bool:
        invalid = self.project_latest("phase34-design-invalidated")
        return bool(invalid and invalid["seq"] > event["seq"])

    @verified_read
    def current_design(self) -> dict[str, Any] | None:
        proposal = super().current_design()
        return None if proposal and self._design_invalidated(proposal) else proposal

    @verified_read
    def approved_design(self) -> dict[str, Any] | None:
        approved = self.project_latest("design-approved")
        if approved and self._design_invalidated(approved):
            return None
        return super().approved_design()

    @authority_read
    def selected_design(self) -> dict[str, Any] | None:
        current = self.current_design()
        approved = self.approved_design()
        return current or (approved["proposal"] if approved else None)

    @verified_read
    def read_design_evidence(self, query: Any = None) -> dict[str, Any]:
        packet = super().read_design_evidence(query)
        feedback = self.project_latest("phase34-design-invalidated")
        if feedback:
            card = self.store.card(feedback["thread"], feedback["card_id"])
            from .phase34_plan import PilotArmIntent
            from .phase34_science import compact_arm_intent

            raw_diagnosis = card.scientific_summary.get("diagnosis")
            if raw_diagnosis is not None and not isinstance(raw_diagnosis, dict):
                raise AgentBoundaryError("Historical Pilot diagnosis is not a structured object")
            diagnosis = dict(raw_diagnosis) if isinstance(raw_diagnosis, dict) else {}
            if "design_arms" in diagnosis:
                diagnosis["design_arms"] = [
                    compact_arm_intent(PilotArmIntent.model_validate(arm))
                    for arm in diagnosis["design_arms"]
                ]
            packet["pilot_feedback"] = {
                "source_gate4_card": card.card_id,
                "scientist_route": feedback["route"],
                "scientist_instruction": feedback["human_instruction"],
                "historical_pilot_diagnosis": diagnosis,
                "scope": "Prior Pilot evidence for revision; current Site facts "
                "remain authoritative.",
            }
            packet["evidence_id"] = identity(
                {
                    "current_design_evidence": packet["evidence_id"],
                    "pilot_feedback": packet["pilot_feedback"],
                }
            )
        return packet

    @verified_read
    def approved_site(self) -> dict[str, Any] | None:
        return super().approved_site()

    @verified_read
    def target_state(self) -> dict[str, Any]:
        return super().target_state()

    @verified_read
    def binding(self) -> dict[str, Any]:
        return super().binding()

    @verified_read
    def design_snapshot(self, proposal: dict[str, Any]) -> dict[str, Any]:
        return super().design_snapshot(proposal)

    def parent_pilot_card(self, proposal: dict[str, Any]) -> str | None:
        transition = self.project_latest("phase34-gate4-transition")
        if (
            transition
            and transition["route"] == "RUN_ANOTHER_PILOT"
            and (transition["design_proposal_id"] == proposal["proposal_id"])
        ):
            return str(transition["card_id"])
        return None

    @authority_read
    def plan(self) -> BoundPilotPlan:
        proposal = self.selected_design()
        if proposal is None:
            raise AgentBoundaryError("Pilot requires a current compiled Design")
        return plan_for_design(
            self,
            proposal,
            prediction_backend=self.prediction_backend,
            parent_gate4_card_id=self.parent_pilot_card(proposal),
            pilot_allocations=self.pilot_allocations,
        )

    @authority_read
    def pilot_authority(self) -> ScientistPilotAuthority | ValidationExecutionAuthority | None:
        event = self.project_latest("phase34-pilot-authority")
        proposal = self.selected_design()
        if event is None or proposal is None:
            return None
        kind = event["contract_type"]
        authority = cast(
            ScientistPilotAuthority | ValidationExecutionAuthority,
            self.load_contract(
                kind="phase34-pilot-authority",
                contract_type=(
                    ScientistPilotAuthority
                    if kind == "ScientistPilotAuthority"
                    else ValidationExecutionAuthority
                ),
            ),
        )
        plan = authority.pilot_plan
        if plan is None:
            raise AgentBoundaryError(
                "Product execution cannot consume an unbound fixture authority"
            )
        if plan.design_proposal_id != proposal[
            "proposal_id"
        ] or plan.parent_gate4_card_id != self.parent_pilot_card(proposal):
            return None
        if isinstance(authority, ScientistPilotAuthority):
            verify_pilot_authority(self, authority)
        else:
            current = plan_for_design(
                self,
                proposal,
                prediction_backend=plan.prediction_backend,
                mode="validation-micro",
                execution_allocations=plan.execution_allocations,
                executor=plan.executor,
            )
            if current != plan:
                raise AgentBoundaryError("Validation plan is stale")
        return authority

    @authority_read
    def current_pilot_dossier(self) -> PilotEvidenceDossier | None:
        event = self.project_latest("phase34-pilot-dossier")
        authority = self.pilot_authority()
        if event is None or authority is None:
            return None
        dossier = self.load_contract(
            kind="phase34-pilot-dossier", contract_type=PilotEvidenceDossier
        )
        if dossier.execution_authority != authority:
            return None
        measurement = self.project_latest("phase34-pilot-measurement")
        if measurement is None or measurement["contract_sha256"] != canonical_model_sha256(
            dossier.measurement
        ):
            return None
        if dossier.project_id != self.project_id:
            raise AgentBoundaryError("Pilot dossier belongs to a different project")
        if dossier.measurement.native_evidence is not None:
            from .phase3_ranking import NATIVE_RANKING_POLICY

            if (dossier.diagnosis.ranked_pilot or {}).get("policy") != NATIVE_RANKING_POLICY:
                return None
        execution = self.project_latest("phase34-pilot-execution")
        if execution is not None:
            if execution["run_id"] != dossier.pilot_run_id:
                return None
            jobs = [
                j
                for j in self.controller.list(project_id=self.project_id)
                if j.run_id == execution["run_id"]
            ]
            current_job = jobs[0].job_id if jobs else execution["job_id"]
            if (
                measurement["dependencies"].get("execution_job_id", execution["job_id"])
                != current_job
            ):
                return None
            native = dossier.measurement.native_evidence
            if native is not None and (native.source_refs or native.profiles or native.candidates):
                from .phase3_native import verify_native_measurement

                root, _ = self.run(execution["run_id"])
                verify_native_measurement(root, dossier.measurement)
        return dossier

    @authority_read
    def current_final_dossier(self) -> FinalReviewDossier | None:
        event = self.project_latest("phase34-final-review-dossier")
        if event is None:
            return None
        dossier = self.load_contract(
            kind="phase34-final-review-dossier", contract_type=FinalReviewDossier
        )
        pool = self.project_latest("phase34-global-candidate-pool")
        campaign = self.project_latest("phase34-scale-campaign")
        if pool is None or campaign is None:
            return None
        pool_data = self.document(pool["ref"])
        campaign_data = self.document(campaign["ref"])
        review_state = self.project_latest("phase34-scale-review-worker-state")
        if review_state and review_state.get("pool") == pool["contract_sha256"]:
            from .phase34_scale import scale_worker_state

            if review_state["worker_state"] != scale_worker_state(self):
                return None
        if (
            dossier.project_id != self.project_id
            or dossier.campaign_id != campaign_data["campaign_id"]
        ):
            raise AgentBoundaryError("Final review belongs to another project/campaign")
        if (
            dossier.global_pool_sha256 != pool["contract_sha256"]
            or pool_data["campaign"] != campaign_data
        ):
            return None
        pilot = self.current_pilot_dossier()
        if pilot is None or campaign_data["promotion_authority"][
            "pilot_dossier_sha256"
        ] != canonical_model_sha256(pilot):
            return None
        invalid = self.project_latest("phase34-selection-invalidated")
        from .phase4_native import verify_native_dossiers

        verify_native_dossiers(self, dossier.candidate_dossiers)
        return None if invalid and invalid["seq"] > event["seq"] else dossier

    @authority_read
    def downstream_card(self) -> DecisionCard | None:
        final = self.current_final_dossier() if self.downstream_scope == "handoff" else None
        dossier = final or self.current_pilot_dossier()
        if dossier is None:
            return None
        kind = "wet-lab-handoff" if final else "pilot-promotion"
        event = self.project_latest(f"phase34-{kind}-card")
        if event is None or event["dependencies"].get("evidence") != canonical_model_sha256(
            dossier
        ):
            return None
        return self.load_contract(kind=f"phase34-{kind}-card", contract_type=DecisionCard)

    def decision_card(self, args: ApplyDecision) -> DecisionCard:
        original = super().decision_card(args)
        return (
            pilot_review_card(self, original, self.plan())
            if original.gate_type == "design-specification"
            else original
        )

    def revision_is_current(self, outcome: DecisionOutcome) -> bool:
        card = self.store.card(self.thread, outcome.card_id)
        if card.gate_type not in {"pilot-promotion", "wet-lab-handoff"}:
            return super().revision_is_current(outcome)
        kind = (
            "phase34-gate4-transition"
            if card.gate_type == "pilot-promotion"
            else "phase34-gate5-transition"
        )
        event = self.project_latest(kind)
        if (
            not event
            or event.get("card_id") != outcome.card_id
            or event.get("outcome_sha256") != identity(outcome.model_dump(mode="json"))
        ):
            return False
        route = event["route"]
        if route == "REVISE_FINAL_SELECTION":
            return self.current_final_dossier() is None
        if route == "REVISE_DESIGN":
            return self.current_design() is None and self.approved_site() is not None
        if route == "REVISE_SITE":
            invalid = self.project_latest("site-invalidated")
            return bool(
                invalid
                and invalid.get("card_id") == card.card_id
                and invalid.get("target_binding") == self.target_state()["binding"]
                and self.approved_site() is None
            )
        return False

    def frozen_pilot_card(self) -> DecisionCard:
        approved = self.approved_design()
        if approved is None:
            raise AgentBoundaryError("No frozen Design exists for Pilot-plan review")
        original = self.store.card(approved["thread"], approved["card_id"])
        return pilot_review_card(self, original, self.plan())

    def apply_decision(self, card: DecisionCard) -> dict[str, Any]:
        if card.gate_type == "design-specification" and card.scientific_summary.get("pilot_plan"):
            response = self.store.response(self.thread, card.card_id)
            if response and response["response"] in {"approve", "override"}:
                authority = accept_pilot_plan(self, card)
                return {"status": "pilot-authorized", "authority_id": authority.authority_id}
            return super().apply_decision(card)
        if card.gate_type not in {"pilot-promotion", "wet-lab-handoff"}:
            return super().apply_decision(card)
        with self.store.writer():
            if self.store.card(self.thread, card.card_id) != card:
                raise AgentBoundaryError("Downstream card differs from its runtime copy")
            transition_kind = (
                "phase34-gate4-transition"
                if card.gate_type == "pilot-promotion"
                else "phase34-gate5-transition"
            )
            prior = next(
                (
                    e
                    for e in reversed(self.store.events(self.thread))
                    if e["kind"] == transition_kind and e["payload"]["card_id"] == card.card_id
                ),
                None,
            )
            if prior is not None:
                saved_response = self.store.response(self.thread, card.card_id)
                if (
                    saved_response is None
                    or identity(saved_response["outcome"]) != prior["payload"]["outcome_sha256"]
                ):
                    raise AgentBoundaryError("Applied downstream outcome changed")
                self._finish_transition(prior["payload"])
                self.store.delivered(self.thread, card.card_id)
                return {"status": prior["payload"]["route"], "card_id": card.card_id}
            current = self.downstream_card()
            if current != card:
                raise AgentBoundaryError(
                    "Downstream response is stale or not the current evidence/card"
                )
            event = self.project_latest(f"phase34-{card.gate_type}-card")
            assert event is not None
            response = self.store.response(event["thread"], card.card_id)
            if response is None:
                raise AgentBoundaryError("Downstream transition requires a saved Scientist outcome")
            outcome = DecisionOutcome.model_validate(response["outcome"])
            route = (
                "STOP"
                if outcome.action == "REJECT"
                else ("REVISE_SITE" if outcome.revision_gate == "site-hotspot" else "REVISE_DESIGN")
                if outcome.action == "REVISE" and card.gate_type == "pilot-promotion"
                else (
                    "REVISE_FINAL_SELECTION"
                    if outcome.action == "REVISE"
                    else self.gate4_route(card)
                    if card.gate_type == "pilot-promotion"
                    else self.gate5_route(card)
                )
            )
            proposal = self.selected_design()
            assert proposal is not None
            payload = {
                "card_id": card.card_id,
                "route": route,
                "evidence": card.evidence_id,
                "outcome_sha256": identity(response["outcome"]),
                "design_proposal_id": proposal["proposal_id"],
                "human_instruction": outcome.human_instruction,
            }
            if route == "PROMOTE_TO_SCALE":
                dossier = self.current_pilot_dossier()
                assert dossier is not None
                scale_authority = self.gate4_promotion_authority(
                    dossier=dossier,
                    card=card,
                    selected_strategy_ids=dossier.proposed_interpretation.selected_strategy_ids,
                )
                self.publish_contract(
                    kind="phase34-scale-authority",
                    contract=scale_authority,
                    dependencies={"pilot": card.evidence_id},
                )
            elif route == "APPROVE_WET_LAB_HANDOFF":
                from .phase4 import build_wet_lab_handoff

                final = self.current_final_dossier()
                assert final is not None
                authority5 = self.gate5_approval_authority(
                    final_review_dossier_sha256=card.evidence_id,
                    card=card,
                    primary_candidate_ids=final.proposed_selection.primary_candidate_ids,
                    backup_candidate_ids=final.proposed_selection.backup_candidate_ids,
                )
                handoff = build_wet_lab_handoff(
                    dossier=final, gate5_card=card, authority=authority5
                )
                self.publish_contract(
                    kind="phase34-wet-lab-handoff",
                    contract=handoff,
                    dependencies={"final": card.evidence_id, "card": card.card_id},
                )
            self.store.event(event["thread"], transition_kind, payload)
            self.failpoint("after_downstream_transition_before_invalidation")
            self._finish_transition(payload)
            self.store.delivered(event["thread"], card.card_id)
            return {"status": route, "card_id": card.card_id}

    def _finish_transition(self, payload: dict[str, Any]) -> None:
        """Complete journaled local invalidations exactly once after an interrupted response."""
        events = self.store.events(self.thread)

        def append_once(kind: str, value: dict[str, Any]) -> None:
            if not any(
                e["kind"] == kind
                and (e["payload"].get("card_id") or e["payload"].get("source_card"))
                == payload["card_id"]
                for e in events
            ):
                self.store.event(self.thread, kind, value)

        route = payload["route"]
        if route in {"REVISE_DESIGN", "REVISE_SITE"}:
            append_once("phase34-design-invalidated", payload)
        if route == "REVISE_SITE":
            append_once(
                "site-invalidated",
                {
                    "source_card": payload["card_id"],
                    "human_instruction": payload["human_instruction"],
                    "reason": "Scientist selected REVISE_SITE after Pilot diagnosis",
                    "target_binding": self.target_state()["binding"],
                },
            )
        if route == "REVISE_FINAL_SELECTION":
            append_once("phase34-selection-invalidated", payload)

    @authority_read
    def next_downstream_action(self) -> RuntimeAction | None:
        # Revisions first return through existing upstream scientific paths.
        upstream = DesignBridge.scientific_state(self)
        proposal = self.selected_design()
        if proposal is None or upstream["scientific_state"] not in {
            "design-frozen",
            "awaiting-human-approval",
        }:
            return None
        if upstream.get("gate_type") != "design-specification":
            return None
        authority = self.pilot_authority()
        if authority is None:
            approved = self.approved_design()
            if approved is None or approved["proposal_id"] != proposal["proposal_id"]:
                return None
            plan_card = self.frozen_pilot_card()
            return RuntimeAction(
                "pilot-plan-review",
                plan_card.card_id,
                "request_downstream_decision",
                {"card_id": plan_card.card_id},
            )
        bound = authority.authority_id
        transition = self.project_latest("phase34-gate4-transition")
        dossier = self.current_pilot_dossier()
        if transition and dossier and transition["evidence"] == canonical_model_sha256(dossier):
            route = transition["route"]
            if route == "STOP":
                return RuntimeAction(
                    "scientist-stopped",
                    transition["card_id"],
                    message="Scientist stopped this campaign; evidence is retained.",
                )
            if route == "PROMOTE_TO_SCALE":
                if self.downstream_scope == "pilot":
                    return RuntimeAction(
                        "scale-authorized",
                        transition["card_id"],
                        message="Gate 4 Scale intent is recorded; this thread's Pilot "
                        "scope is complete.",
                    )
                return self.next_scale_action()
        execution = self.project_latest("phase34-pilot-execution")
        if execution is None or execution["authority"] != bound:
            return RuntimeAction("pilot-dispatch", bound, "advance_downstream")
        from .phase3_import import current_native_import

        execution_complete = current_native_import(self, execution, bound)
        if not execution_complete:
            jobs = [
                j
                for j in self.controller.list(project_id=self.project_id)
                if j.run_id == execution["run_id"]
            ]
            if jobs and jobs[0].job_id != execution["job_id"]:
                return RuntimeAction("pilot-reconcile", bound, "advance_downstream")
            job = self.controller.load(execution["job_id"])
            if job.status in ACTIVE_JOB_STATUSES:
                return RuntimeAction("pilot-running", bound, "observe_downstream")
            execution_complete = job.status == "succeeded"
        measurement = self.project_latest("phase34-pilot-measurement")
        if (
            measurement is None
            or measurement["dependencies"].get("authority") != bound
            or (
                measurement["dependencies"].get("execution_job_id", execution["job_id"])
                != execution["job_id"]
            )
        ):
            return RuntimeAction(
                "pilot-measurement" if execution_complete else "pilot-operational-evidence",
                bound,
                "advance_downstream",
            )
        if dossier is None:
            return _task(
                "pilot-diagnosis",
                measurement["contract_sha256"],
                "pilot-diagnosis",
                "Interpret each approved Design arm's hypothesis "
                "against the trusted Pilot measurements; recommend one Scientist Gate 4 route.",
            )
        card = self.downstream_card()
        if card is None:
            return RuntimeAction(
                "pilot-card", canonical_model_sha256(dossier), "advance_downstream"
            )
        return RuntimeAction(
            "scientist-gate4",
            card.card_id,
            "request_downstream_decision",
            {"card_id": card.card_id},
        )

    def next_scale_action(self) -> RuntimeAction:
        final = self.current_final_dossier()
        if final:
            transition = self.project_latest("phase34-gate5-transition")
            if transition and transition["evidence"] == canonical_model_sha256(final):
                if transition["route"] in {"APPROVE_WET_LAB_HANDOFF", "STOP"}:
                    return RuntimeAction(
                        "handoff-complete"
                        if transition["route"] == "APPROVE_WET_LAB_HANDOFF"
                        else "scientist-stopped",
                        transition["card_id"],
                        message="The Scientist's final disposition is recorded; no "
                        "experiment or order was initiated.",
                    )
            card = self.downstream_card()
            if card and card.gate_type == "wet-lab-handoff":
                return RuntimeAction(
                    "scientist-gate5",
                    card.card_id,
                    "request_downstream_decision",
                    {"card_id": card.card_id},
                )
            return RuntimeAction("final-card", canonical_model_sha256(final), "advance_downstream")
        shortlist = self.project_latest("phase34-review-shortlist")
        pool = self.project_latest("phase34-global-candidate-pool")
        authority = self.project_latest("phase34-scale-authority")
        current_inputs = bool(
            shortlist
            and pool
            and authority
            and self.document(pool["ref"])["campaign"]["promotion_authority"]
            == self.document(authority["ref"])
        )
        if current_inputs:
            review_state = self.project_latest("phase34-scale-review-worker-state")
            if review_state:
                from .phase34_scale import scale_worker_state

                current_inputs = review_state["worker_state"] == scale_worker_state(self)
        if current_inputs:
            assert shortlist is not None
            return _task(
                "final-selection",
                shortlist["contract_sha256"],
                "final-selection",
                "Propose a primary and backup panel using the global "
                "shortlist, quality, diversity, hypotheses and uncertainty.",
            )
        execution = self.project_latest("phase34-scale-execution")
        manifest = self.project_latest("phase34-scale-batch-manifest")
        inconclusive = self.project_latest("phase34-scale-inconclusive")
        if (
            inconclusive
            and manifest
            and inconclusive.get("manifest") == manifest["contract_sha256"]
        ):
            from .phase34_scale import scale_worker_state

            if inconclusive["worker_state"] == scale_worker_state(self):
                return RuntimeAction(
                    inconclusive.get("status", "scale-operationally-inconclusive"),
                    manifest["contract_sha256"],
                    message=inconclusive.get(
                        "message",
                        "Scale is incomplete or has no eligible candidates; "
                        "no final handoff is authorized.",
                    ),
                )
        if (
            execution
            and manifest
            and execution.get("manifest") == manifest["contract_sha256"]
            and execution.get("job_id")
        ):
            job = self.controller.load(execution["job_id"])
            if job.status in ACTIVE_JOB_STATUSES:
                return RuntimeAction("scale-running", job.job_id, "observe_downstream")
        return RuntimeAction(
            "scale-execution",
            identity(self.project_latest("phase34-scale-authority")),
            "advance_downstream",
        )

    def get_job_status(self) -> dict[str, Any]:
        scale = self.project_latest("phase34-scale-execution")
        manifest = self.project_latest("phase34-scale-batch-manifest")
        if (
            scale
            and manifest
            and scale.get("manifest") == manifest["contract_sha256"]
            and scale.get("job_id")
        ):
            job = self.controller.load(scale["job_id"])
            return {
                "status": job.status,
                "job_id": job.job_id,
                "run_id": job.run_id,
                "phase": "scale",
            }
        authority = self.pilot_authority()
        execution = self.project_latest("phase34-pilot-execution")
        if authority and execution and execution["authority"] == authority.authority_id:
            job = self.controller.load(execution["job_id"])
            return {
                "status": job.status,
                "job_id": job.job_id,
                "run_id": job.run_id,
                "phase": "pilot",
            }
        return super().get_job_status()

    @authority_read
    def pilot_inputs(self) -> tuple[Any, Any, Any]:
        from .phase34_plan import ApprovedGate3Context, ValidatedDesignContext

        authority = self.pilot_authority()
        event = self.project_latest("phase34-pilot-measurement")
        if (
            authority is None
            or event is None
            or event["dependencies"].get("authority") != authority.authority_id
        ):
            raise AgentBoundaryError("Pilot interpretation lacks its current execution evidence")
        measurement = self.load_contract(
            kind="phase34-pilot-measurement", contract_type=PilotMeasurement
        )
        context = self.load_contract(
            kind="phase34-approved-gate3",
            contract_type=(
                ValidatedDesignContext
                if isinstance(authority, ValidationExecutionAuthority)
                else ApprovedGate3Context
            ),
        )
        if context.plan != authority.pilot_plan or context.project_id != self.project_id:
            raise AgentBoundaryError("Pilot context differs from the current authorized Design")
        native = measurement.native_evidence
        if native is not None and (native.source_refs or native.profiles or native.candidates):
            from .phase3_native import verify_native_measurement

            execution = self.project_latest("phase34-pilot-execution")
            if execution is None:
                raise AgentBoundaryError("Native measurement has no bound Pilot execution")
            root, _ = self.run(execution["run_id"])
            verify_native_measurement(root, measurement)
        return measurement, context, authority

    @authority_read
    def selection_inputs(self) -> tuple[Any, Any, Any]:
        from .phase34_contracts import FinalSelectionInput, GlobalCandidatePool, ReviewShortlist

        pool = self.load_contract(
            kind="phase34-global-candidate-pool", contract_type=GlobalCandidatePool
        )
        shortlist = self.load_contract(
            kind="phase34-review-shortlist", contract_type=ReviewShortlist
        )
        inputs = self.load_contract(
            kind="phase34-final-selection-input", contract_type=FinalSelectionInput
        )
        if (
            inputs.project_id != self.project_id
            or inputs.global_pool_sha256 != canonical_model_sha256(pool)
            or shortlist.global_pool_sha256 != canonical_model_sha256(pool)
            or (inputs.review_shortlist_sha256 != canonical_model_sha256(shortlist))
        ):
            raise AgentBoundaryError("Final selection input is stale or belongs to another project")
        ids = tuple(e.candidate_id for e in shortlist.entries)
        if ids != tuple(d.candidate.lineage.candidate_id for d in inputs.candidate_dossiers):
            raise AgentBoundaryError("Final input does not cover the current shortlist")
        from .phase4_native import verify_native_dossiers

        verify_native_dossiers(self, inputs.candidate_dossiers)
        pilot = self.current_pilot_dossier()
        authority = self.project_latest("phase34-scale-authority")
        if (
            pilot is None
            or authority is None
            or self.document(authority["ref"])
            != pool.campaign.promotion_authority.model_dump(mode="json")
            or pool.campaign.promotion_authority.pilot_dossier_sha256
            != canonical_model_sha256(pilot)
        ):
            raise AgentBoundaryError("Global pool is outside the current Pilot/Scale authority")
        review_state = self.project_latest("phase34-scale-review-worker-state")
        if review_state and review_state.get("pool") == canonical_model_sha256(pool):
            from .phase34_scale import scale_worker_state

            if review_state["worker_state"] != scale_worker_state(self):
                raise AgentBoundaryError("Scale worker changed after selection input publication")
        return pool, shortlist, inputs

    @authority_read
    def downstream_packet(self, role: str) -> dict[str, Any]:
        from .phase34_science import pilot_working_set, selection_working_set

        action = self.next_downstream_action()
        expected = {"pilot-diagnosis": "pilot-diagnosis", "final-selection": "final-selection"}
        if action is None or (role != "judge" and action.stage != expected.get(role)):
            raise AgentBoundaryError("Cognitive role is outside current downstream authority")
        if role == "pilot-diagnosis" or (
            role == "judge" and action.stage in {"pilot-review", "scientist-gate4"}
        ):
            measurement, context, _ = self.pilot_inputs()
            packet = pilot_working_set(measurement, context.plan.arms)
            execution = self.project_latest("phase34-pilot-execution")
            assert execution is not None
            packet.update(
                run_id=execution["run_id"],
                gate_type="pilot-promotion",
                evidence_refs=[*context.evidence_refs, canonical_model_sha256(measurement)],
            )
            sources = self.project_latest("phase34-pilot-measurement-sources")
            if sources and sources["authority"] == execution["authority"]:
                packet["evidence_refs"].extend(
                    f"run:{sources['run_id']}:{sources[key]['relative_path']}#{sources[key]['sha256']}"
                    for key in (
                        "candidate_index",
                        "filter_report",
                        "predictions",
                        "native_evidence",
                    )
                    if key in sources
                )
            operational = self.project_latest("phase34-pilot-operational-sources")
            if operational and operational["authority"] == execution["authority"]:
                packet["operational_source_refs"] = operational["source_refs"]
            if role == "judge":
                dossier = self.current_pilot_dossier()
                assert dossier is not None
                packet.update(
                    diagnosis=dossier.diagnosis.model_dump(mode="json", exclude={"design_arms"}),
                    proposal=dossier.proposed_interpretation.model_dump(mode="json"),
                    dossier_sha256=canonical_model_sha256(dossier),
                )
        elif role == "final-selection" or (
            role == "judge" and action.stage in {"final-review", "scientist-gate5"}
        ):
            pool, shortlist, inputs = self.selection_inputs()
            packet = selection_working_set(
                inputs.candidate_dossiers,
                primary_count=inputs.primary_count,
                backup_count=inputs.backup_count,
            )
            pilot = self.current_pilot_dossier()
            assert pilot is not None
            if pool.campaign.evidence_policy == "boltzgen-native-v1":
                approved_allocations = (
                    pool.campaign.promotion_authority.production_strategy_allocations
                )
                packet["campaign_summary"] = {
                    "execution_mode": pool.campaign.execution.mode.value,
                    "approved_allocations": approved_allocations,
                    "validation_or_execution_allocations": pool.campaign.strategy_allocations,
                    "observed": len(pool.candidates),
                    "native_pass": len(pool.global_ranking_candidate_ids),
                    "native_fail": sum(
                        c.native_evidence is not None and c.native_evidence.native_pass is False
                        for c in pool.candidates
                    ),
                    "failed_batches": pool.failed_batch_ids,
                    "resumable_batches": pool.resumable_batch_ids,
                }
                packet["arm_context"] = {
                    arm.arm_id: {
                        "strategy_ids": arm.strategy_ids,
                        "hypothesis": arm.hypothesis,
                        "changed_factors": arm.changed_factors,
                        "held_constant": arm.held_constant,
                        "scaffolds": {
                            s.get("strategy_id"): s.get("scaffold_id")
                            for s in arm.compiled_settings
                        },
                    }
                    for arm in pilot.diagnosis.design_arms
                }
            packet.update(
                run_id=pool.campaign.campaign_id,
                gate_type="wet-lab-handoff",
                evidence_refs=[
                    *pilot.evidence_refs,
                    canonical_model_sha256(pool),
                    canonical_model_sha256(shortlist),
                ],
            )
            if role == "judge":
                final = self.current_final_dossier()
                assert final is not None
                packet.update(
                    proposal=final.proposed_selection.model_dump(mode="json"),
                    dossier_sha256=canonical_model_sha256(final),
                )
        else:
            raise AgentBoundaryError("Judge is not currently delegated a downstream review")
        feedback = (
            self.project_latest("phase34-selection-invalidated")
            if role == "final-selection"
            else None
        )
        if feedback:
            packet["scientist_revision"] = feedback["human_instruction"]
            packet["scientist_revision_card_id"] = feedback["card_id"]
        binding = identity(packet)
        return {**packet, "evidence_id": binding, "request_identity": binding}

    async def advance(self) -> dict[str, Any]:
        action = self.next_downstream_action()
        if action is None or action.tool != "advance_downstream":
            raise AgentBoundaryError("No downstream execution step is currently authorized")
        if action.stage in {"pilot-dispatch", "pilot-reconcile"}:
            authority = self.pilot_authority()
            assert authority is not None
            return execute_pilot(self, authority)
        if action.stage == "pilot-operational-evidence":
            from .phase34_failures import project_generation_failure

            return project_generation_failure(self)
        if action.stage == "pilot-card":
            from .phase34_cards import pilot_card

            dossier = self.current_pilot_dossier()
            if dossier is None:
                raise AgentBoundaryError("Pilot evidence changed before Gate 4 publication")
            card = pilot_card(dossier)
            self.publish_gate_card(card=card, evidence_contract=dossier)
            return {"status": "scientist-review-ready", "card_id": card.card_id}
        if action.stage == "pilot-measurement":
            from .phase34_measurement import evaluate_pilot

            return evaluate_pilot(self)
        if action.stage == "final-card":
            from .phase34_cards import final_card

            final = self.current_final_dossier()
            if final is None:
                raise AgentBoundaryError("Final evidence changed before Gate 5 publication")
            card = final_card(final)
            self.publish_gate_card(card=card, evidence_contract=final)
            return {"status": "scientist-review-ready", "card_id": card.card_id}
        from .phase34_scale import advance_scale

        return advance_scale(self)

    def terminal_result(self, message: str) -> dict[str, Any]:
        action = self.next_downstream_action()
        if action is None:
            return super().terminal_result(message)
        return {
            "thread": self.thread,
            "status": "finished"
            if action.stage in {"handoff-complete", "scientist-stopped", "scale-authorized"}
            else "incomplete-turn",
            "scientific_state": action.stage,
            "message": action.message or message,
        }
