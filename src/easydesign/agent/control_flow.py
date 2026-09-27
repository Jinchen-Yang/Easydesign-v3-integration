"""Read-only workflow decisions derived from existing scientific authority.

No model output, conversation history, or new mutable state participates in routing.
Execution remains in the existing native graph and scientific command journal.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .contracts import DecisionOutcome, EvidenceBinding
from .design import DesignBridge
from .phase2 import Phase2Bridge
from .session_store import identity


@dataclass(frozen=True)
class RuntimeAction:
    stage: str
    binding: str
    tool: str | None = None
    arguments: dict[str, Any] = field(default_factory=dict)
    message: str = ""

    @property
    def action_id(self) -> str:
        return identity(
            {
                "stage": self.stage,
                "binding": self.binding,
                "tool": self.tool,
                "arguments": self.arguments,
            }
        )


def _task(stage: str, binding: str, specialist: str, question: str) -> RuntimeAction:
    return RuntimeAction(
        stage,
        binding,
        "task",
        {
            "subagent_type": specialist,
            "description": question,
        },
    )


def next_action(bridge: Phase2Bridge) -> RuntimeAction:
    """First unfinished authorized action within the immutable scientific scope."""
    from .phase34_runtime import Phase34Runtime

    if isinstance(bridge, Phase34Runtime):
        downstream = bridge.next_downstream_action()
        if downstream is not None:
            return downstream
    state = bridge.scientific_state()
    stage = state["scientific_state"]
    execution = bridge.store.latest_execution(bridge.thread)
    revision = (
        DecisionOutcome.model_validate(execution["revision"])
        if execution and execution.get("revision")
        else None
    )
    if isinstance(bridge, DesignBridge) and revision and revision.revision_gate == "site-hotspot":
        card = bridge.store.card(bridge.thread, revision.card_id)
        if card.gate_type == "design-specification" and not bridge.site_revision_applied(
            card.card_id
        ):
            return RuntimeAction(
                "site-revision",
                card.card_id,
                "reopen_site_decision",
                {
                    "reason": revision.human_instruction,
                },
            )
    if stage in {"running", "queued"}:
        # Existing status tool owns bounded observation. No polling by a model.
        return RuntimeAction(
            "target-running", bridge.target_run_id() or "preparing", "get_job_status"
        )
    if stage == "not-prepared":
        return _task(
            stage,
            identity(bridge.binding()),
            "target-intelligence",
            "Establish the requested Target identity and prepare the supplied structure. "
            "For a pending chain Gate, recommend an eligible option explicitly using "
            "recommended_option, respecting the scientist's stated preference.",
        )
    if stage in {"design-frozen", "hotspot-approved"} and state["next_specialist"] == "none":
        return RuntimeAction(
            stage,
            identity(state),
            message=(
                "The requested scientific scope is complete. "
                "The approved decision and its scientific limitations remain in the review record. "
                "Generation has not started."
            ),
        )
    if stage == "site-not-proposed":
        biology = bridge.biology()
        return _task(
            stage,
            identity(
                {
                    "target": bridge.target_state()["binding"],
                    "biology": biology.model_dump(mode="json") if biology else None,
                }
            ),
            "site-mechanism",
            "Research the evidence and propose the best defensible mapped Site for "
            "the original goal and current trusted revision.",
        )
    if stage == "design-not-proposed" or (
        stage == "hotspot-approved" and state["next_specialist"] == "binder-strategy"
    ):
        assert isinstance(bridge, DesignBridge)
        return _task(
            "design-not-proposed",
            bridge.read_design_evidence()["evidence_id"],
            "binder-strategy",
            "Propose the design strategy for the approved Site, "
            "original goal and current trusted revision.",
        )
    if stage != "awaiting-human-approval":
        return RuntimeAction(
            stage,
            identity(state),
            message=(
                "The scientific service has unresolved work; inspect its verified status before "
                "continuing. No new scientific work or approval was created."
            ),
        )

    # The snapshot includes current revision and exact scientific evidence. Old pending
    # cards, completed job receipts and prose cannot substitute for this binding.
    snapshot = bridge.judge_evidence()
    bound = EvidenceBinding.model_validate(
        {key: snapshot[key] for key in EvidenceBinding.model_fields}
    ).model_dump(mode="json")
    binding = identity(bound)
    gate = state["gate_type"]
    revision_event = bridge.store.revision_for(bridge.thread, snapshot["request_identity"])
    after = revision_event["seq"] if revision_event else 0
    events = bridge.store.events(bridge.thread)
    owner_seq = after
    target_owners: list[dict[str, Any]] = []
    if gate == "target-structure":
        target_owners = [
            e
            for e in events
            if e["kind"] == "target-assessment"
            and e["payload"].get("source_evidence_id") == snapshot["source_evidence_id"]
            and e["seq"] > after
        ]
        owner = target_owners[-1] if target_owners else None
        if owner is None:
            return _task(
                "target-interpretation",
                binding,
                "target-intelligence",
                "Interpret the current Target evidence and recommend the eligible "
                "chain option in recommended_option for independent review, respecting "
                "the original goal and the scientist's trusted revision.",
            )
        owner_seq = owner["seq"]
        option = owner["payload"]["interpretation"].get("recommended_option")
        if not option:
            return RuntimeAction(
                "target-choice-needed",
                binding,
                message=(
                    "Target interpretation did not propose an eligible chain option. "
                    "A scientific choice is still needed before independent review."
                ),
            )
    else:
        option = "site" if gate == "site-hotspot" else "design"
        if revision_event:
            specialist = "site-mechanism" if option == "site" else "binder-strategy"
            return _task(
                "revision-requested",
                identity({"bound": bound, "revision": after}),
                specialist,
                "Revise the current scientific proposal according to the "
                "trusted Scientist instruction, preserving valid upstream evidence.",
            )

    for event in reversed(events):
        if event["kind"] != "human-response" or event["payload"]["response"] != "reject":
            continue
        card = bridge.store.card(bridge.thread, event["payload"]["card"])
        if (
            card.request_identity == snapshot["request_identity"]
            and card.evidence_id == snapshot["evidence_id"]
        ):
            response = bridge.store.response(bridge.thread, card.card_id)
            if response and response["delivered"]:
                return RuntimeAction(
                    "proposal-rejected",
                    binding,
                    message=(
                        "The Scientist rejected this proposal. A new authorized scientific "
                        "strategy is needed; the existing evidence is preserved."
                    ),
                )
    assessment = None
    review_after = max(after, owner_seq)
    for event in reversed(events):
        if event["kind"] == "judge-assessment" and event["seq"] > review_after:
            candidate = bridge.store.assessment(bridge.thread, event["payload"]["assessment_id"])
            if (
                candidate.model_dump(mode="json", include=set(EvidenceBinding.model_fields))
                == bound
            ):
                assessment = candidate
                break
    if assessment is None and gate == "site-hotspot":
        from .site_review_policy import site_review_requirement

        review_policy = site_review_requirement(bridge, snapshot)
        if not review_policy["required"]:
            return RuntimeAction(
                "scientist-gate",
                binding,
                "request_scientific_decision",
                {"review_not_requested": True, "option_id": "site"},
            )
    if assessment is None and gate in {"site-hotspot", "design-specification"}:
        from .review_availability import checked_failure, matching_failure

        unavailable = matching_failure(bridge, snapshot)
        if unavailable:
            checked_failure(bridge, snapshot, unavailable["record_id"])
            return RuntimeAction(
                "scientist-gate",
                binding,
                "request_scientific_decision",
                {
                    "review_failure_id": unavailable["record_id"],
                    "option_id": "site" if gate == "site-hotspot" else "design",
                },
            )
    if assessment is None:
        return _task(
            "judge",
            binding,
            "evidence-judge",
            "Independently critique the current runtime-bound scientific proposal, "
            "its evidence, uncertainty and limitations for Scientist review.",
        )
    if (
        gate == "target-structure"
        and assessment.verdict == "reject"
        and assessment.recommendation is not None
        and assessment.recommendation.status == "SUPPORTED"
    ):
        recommended = assessment.recommendation.option_id
        eligible = any(
            item["option_id"] == recommended and item["eligible"]
            for item in snapshot.get("options", [])
        )
        if eligible and len(target_owners) < 3:
            findings = " ".join(assessment.reasons)
            return _task(
                "target-judge-revision",
                identity(
                    {
                        "bound": bound,
                        "assessment": assessment.assessment_id,
                        "owner_seq": owner_seq,
                    }
                ),
                "target-intelligence",
                (
                    "Re-read the current Target evidence and submit a fresh TargetInterpretation. "
                    "The independent review rejected the current interpretation and identified "
                    f"runtime-eligible option {recommended} as its supported alternative. "
                    "Resolve the review findings rather than copying its conclusion without "
                    f"evidence: {findings}"
                )[:1500],
            )
        return RuntimeAction(
            "scientific-review-blocked",
            binding,
            message=(
                "Independent review rejected the Target interpretation, but no bounded "
                "runtime-eligible owner revision remains. "
                + " ".join(assessment.reasons)
            ),
        )

    ranked_site = (
        gate == "site-hotspot"
        and snapshot.get("final_site_decision", {}).get("kind") == "RankedSiteDecision"
    )
    reviewable = (
        ranked_site
        or gate == "design-specification"
        or assessment.verdict == "ready-to-ask"
        or (
            gate == "target-structure"
            and assessment.recommendation is not None
            and assessment.recommendation.status == "DISCOURAGED"
        )
    )
    if not reviewable:
        return RuntimeAction(
            "scientific-review-blocked",
            binding,
            message=(
                "Independent review has not made this proposal ready for a Scientist Gate. "
                + " ".join(assessment.reasons)
            ),
        )
    return RuntimeAction(
        "scientist-gate",
        binding,
        "request_scientific_decision",
        {
            "assessment_id": assessment.assessment_id,
            "option_id": option,
        },
    )
