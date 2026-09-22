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
PREFLIGHT_FAILURE_MODE = "context-capacity-preflight"
PREFLIGHT_DIAGNOSTIC = "MODEL_CONTEXT_CAPACITY_EXCEEDED"


def evidence_binding(packet: dict[str, Any]) -> dict[str, Any]:
    return EvidenceBinding.model_validate(
        {key: packet[key] for key in EvidenceBinding.model_fields}
    ).model_dump(mode="json")


def _capacity_exceeded(usage: Any) -> bool:
    if not isinstance(usage, dict):
        return False
    chars = usage.get("input_chars_with_schemas")
    hard = usage.get("hard_limit_chars")
    tokens = usage.get("estimated_input_tokens")
    token_guard = usage.get("model_profile_token_guard")
    return (isinstance(chars, int) and isinstance(hard, int) and chars > hard) or (
        isinstance(tokens, int) and isinstance(token_guard, int) and tokens > token_guard
    )


def _assert_no_completed_or_substantive_review(
    bridge: Any, bound: dict[str, Any], events: list[dict[str, Any]]
) -> None:
    for event in events:
        if event["kind"] == "judge-assessment":
            assessment = bridge.store.assessment(bridge.thread, event["payload"]["assessment_id"])
            if evidence_binding(assessment.model_dump(mode="json")) == bound:
                raise AgentBoundaryError(
                    "An existing Judge assessment cannot be replaced by unavailability"
                )
        if (
            event["kind"] == "rejected-submission"
            and event["payload"].get("binding") == bound
            and event["payload"].get("substantive_finding")
        ):
            raise AgentBoundaryError(
                "Unresolved substantive findings cannot be hidden by unavailability"
            )


def _preflight_consumed_review_budget(
    event: dict[str, Any], execution_id: str, *, after_seq: int, before_seq: int | None = None
) -> bool:
    if event["seq"] <= after_seq or (before_seq is not None and event["seq"] >= before_seq):
        return False
    payload = event["payload"]
    return (
        event["kind"]
        in {
            "model-call",
            "model-context",
            "model-response",
            "contract-repair",
            "rejected-submission",
        }
        and payload.get("role") == "judge"
        and payload.get("execution_id") == execution_id
    )


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
    receipt: dict[str, Any] | None = next(
        (
            e
            for e in events
            if e["kind"] == "site-judge-unavailable" and e["payload"]["record_id"] == record_id
        ),
        None,
    )
    failure: dict[str, Any] | None = receipt["payload"] if receipt is not None else None
    if failure is None or failure["binding"] != bound:
        raise AgentBoundaryError("Review failure is absent, foreign or stale")
    payload = {k: v for k, v in failure.items() if k != "record_id"}
    if failure.get("source_role") != "verified-runtime" or record_id != (
        "review-unavailable-" + identity(payload)
    ):
        raise AgentBoundaryError("Review failure requires a verified runtime record")
    _assert_no_completed_or_substantive_review(bridge, bound, events)

    mode = failure.get("failure_mode")
    if mode == PREFLIGHT_FAILURE_MODE:
        evidence = [e for e in events if e["seq"] in failure.get("failure_events", [])]
        if len(evidence) != 1 or receipt is None:
            raise AgentBoundaryError("Context preflight unavailability lacks one exact event")
        event = evidence[0]
        p = event["payload"]
        if (
            event["kind"] != "site-judge-context-preflight-failed"
            or p.get("source_role") != "verified-runtime"
            or p.get("role") != "judge"
            or p.get("binding") != bound
            or p.get("execution_id") != failure["execution_id"]
            or p.get("diagnostic") != PREFLIGHT_DIAGNOSTIC
            or not _capacity_exceeded(p.get("usage"))
            or any(
                _preflight_consumed_review_budget(
                    candidate,
                    failure["execution_id"],
                    after_seq=event["seq"],
                    before_seq=receipt["seq"],
                )
                for candidate in events
            )
        ):
            raise AgentBoundaryError("Invalid context preflight unavailability evidence")
        return failure
    if mode is not None:
        raise AgentBoundaryError("Unknown review unavailability mode")

    if (
        sum(
            e["kind"] == "contract-repair"
            and e["payload"].get("execution_id") == failure["execution_id"]
            and e["payload"].get("contract") in {None, "JudgeVerdict"}
            for e in events
        )
        < 2
    ):
        raise AgentBoundaryError("Review failure requires a verified exhausted repair record")
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


def record_preflight_unavailable(bridge: Any, execution_id: str) -> dict[str, Any]:
    """Record only a verified first-call capacity failure; no repair exhaustion is needed."""
    packet = bridge.judge_evidence()  # Rebuild validates hard facts and source bindings again.
    if packet.get("gate_type") != "site-hotspot" or "fact_references" not in packet:
        raise AgentBoundaryError("Review unavailability is only enabled for dossier-backed Site")
    bound = evidence_binding(packet)
    existing = matching_failure(bridge, packet)
    if existing:
        return checked_failure(bridge, packet, existing["record_id"])
    events = bridge.store.events(bridge.thread)
    _assert_no_completed_or_substantive_review(bridge, bound, events)
    candidates = [
        event
        for event in events
        if event["kind"] == "site-judge-context-preflight-failed"
        and event["payload"].get("execution_id") == execution_id
        and event["payload"].get("binding") == bound
    ]
    if not candidates:
        raise AgentBoundaryError("Verified context preflight failure is required")
    evidence = candidates[-1]
    p = evidence["payload"]
    if (
        p.get("source_role") != "verified-runtime"
        or p.get("role") != "judge"
        or p.get("diagnostic") != PREFLIGHT_DIAGNOSTIC
        or not _capacity_exceeded(p.get("usage"))
        or any(
            _preflight_consumed_review_budget(candidate, execution_id, after_seq=evidence["seq"])
            for candidate in events
        )
    ):
        raise AgentBoundaryError("Invalid context preflight failure")
    payload: dict[str, Any] = {
        "binding": bound,
        "execution_id": execution_id,
        "failure_events": [evidence["seq"]],
        "failure_mode": PREFLIGHT_FAILURE_MODE,
        "source_role": "verified-runtime",
    }
    payload["record_id"] = "review-unavailable-" + identity(payload)
    bridge.store.event(bridge.thread, "site-judge-unavailable", payload)
    return checked_failure(bridge, packet, payload["record_id"])


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
