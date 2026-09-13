"""Runtime-owned absence of a Site review, separate from scientific recommendations."""

from __future__ import annotations

from typing import Any

from .contracts import AgentBoundaryError, EvidenceBinding
from .session_store import identity

TECHNICAL_FAILURES = {
    "OUTPUT_TRUNCATED",
    "MISSING_OR_INVALID_TYPED_SUBMISSION",
    "PROVIDER_TIMEOUT",
    "PROVIDER_UNAVAILABLE",
}
REVIEW_WARNING = (
    "Independent Judge review did not complete. The displayed Site interpretation has not "
    "received an independent model review. Review the evidence and retained risks yourself; "
    "continuation requires explicit acknowledgement and a human rationale."
)


def evidence_binding(packet: dict[str, Any]) -> dict[str, Any]:
    return EvidenceBinding.model_validate(
        {key: packet[key] for key in EvidenceBinding.model_fields}
    ).model_dump(mode="json")


def matching_failure(bridge: Any, packet: dict[str, Any]) -> dict[str, Any] | None:
    bound = evidence_binding(packet)
    return next(
        (
            e["payload"]
            for e in reversed(bridge.store.events(bridge.thread))
            if e["kind"] == "site-judge-unavailable" and e["payload"]["binding"] == bound
        ),
        None,
    )


def checked_failure(bridge: Any, packet: dict[str, Any], record_id: str) -> dict[str, Any]:
    if packet.get("gate_type") != "site-hotspot" or "fact_references" not in packet:
        raise AgentBoundaryError("Only a current dossier-backed Site supports manual review")
    bound = evidence_binding(packet)
    events = bridge.store.events(bridge.thread)
    failure: dict[str, Any] | None = next(
        (
            e["payload"]
            for e in events
            if e["kind"] == "site-judge-unavailable" and e["payload"]["record_id"] == record_id
        ),
        None,
    )
    if failure is None or failure["binding"] != bound:
        raise AgentBoundaryError("Review failure is absent, foreign or stale")
    payload = {k: v for k, v in failure.items() if k != "record_id"}
    if (
        failure.get("source_role") != "verified-runtime"
        or record_id != "review-unavailable-" + identity(payload)
        or sum(
            e["kind"] == "contract-repair"
            and e["payload"].get("execution_id") == failure["execution_id"]
            and e["payload"].get("contract") in {None, "JudgeVerdict"}
            for e in events
        )
        < 2
    ):
        raise AgentBoundaryError("Review failure requires a verified exhausted repair record")
    for e in events:
        if e["kind"] == "judge-assessment":
            assessment = bridge.store.assessment(bridge.thread, e["payload"]["assessment_id"])
            if evidence_binding(assessment.model_dump(mode="json")) == bound:
                raise AgentBoundaryError(
                    "An existing Judge assessment cannot be replaced by unavailability"
                )
        if (
            e["kind"] == "rejected-submission"
            and e["payload"].get("binding") == bound
            and e["payload"].get("substantive_finding")
        ):
            raise AgentBoundaryError(
                "Unresolved substantive findings cannot be hidden by unavailability"
            )
    receipts = {e["seq"]: e for e in events if e["kind"] == "rejected-submission"}
    if not failure["failure_events"]:
        raise AgentBoundaryError("Review unavailability lacks technical failure evidence")
    for seq in failure["failure_events"]:
        event = receipts.get(seq)
        if event is None:
            raise AgentBoundaryError("Missing review failure evidence")
        p = event["payload"]
        if (
            p.get("role") != "judge"
            or p.get("binding") != bound
            or p.get("execution_id") != failure["execution_id"]
            or p.get("diagnostic") not in TECHNICAL_FAILURES
            or p.get("substantive_finding")
        ):
            raise AgentBoundaryError("Invalid review unavailability evidence")
    return failure


def record_unavailable(bridge: Any, execution_id: str) -> dict[str, Any]:
    packet = bridge.judge_evidence()  # Existing runtime rebuilding verifies all source bindings.
    if packet.get("gate_type") != "site-hotspot" or "fact_references" not in packet:
        raise AgentBoundaryError("Review unavailability is only enabled for dossier-backed Site")
    bound = evidence_binding(packet)
    existing = matching_failure(bridge, packet)
    if existing:
        return checked_failure(bridge, packet, existing["record_id"])
    events = bridge.store.events(bridge.thread)
    failures = [
        e
        for e in events
        if e["kind"] == "rejected-submission"
        and e["payload"].get("execution_id") == execution_id
        and e["payload"].get("binding") == bound
    ]
    repairs = [
        e
        for e in events
        if e["kind"] == "contract-repair"
        and e["payload"].get("execution_id") == execution_id
        and e["payload"].get("contract") in {None, "JudgeVerdict"}
    ]
    if (
        not failures
        or len(repairs) < 2
        or any(
            e["payload"]["diagnostic"] not in TECHNICAL_FAILURES
            or e["payload"].get("substantive_finding")
            for e in failures
        )
    ):
        raise AgentBoundaryError("Classified technical failure and exhausted repairs are required")
    # Check completed reviews before recording absence, including a prior negative opinion.
    for event in events:
        if event["kind"] == "judge-assessment":
            assessment = bridge.store.assessment(bridge.thread, event["payload"]["assessment_id"])
            if evidence_binding(assessment.model_dump(mode="json")) == bound:
                raise AgentBoundaryError("A completed Judge opinion already exists")
    payload: dict[str, Any] = {
        "binding": bound,
        "execution_id": execution_id,
        "failure_events": [e["seq"] for e in failures],
        "source_role": "verified-runtime",
    }
    payload["record_id"] = "review-unavailable-" + identity(payload)
    bridge.store.event(bridge.thread, "site-judge-unavailable", payload)
    return checked_failure(bridge, packet, payload["record_id"])
