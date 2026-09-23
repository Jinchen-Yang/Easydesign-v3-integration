"""Runtime-owned advisory Judge availability across scientific Gates."""

from __future__ import annotations

from typing import Any

from .contracts import AgentBoundaryError, EvidenceBinding
from .session_store import identity

DESIGN_REVIEW_FAILURE_CODES = {
    "INVALID_REVIEW_SUBMISSION",
    "MISSING_OR_INVALID_TYPED_SUBMISSION",
    "MODEL_CONTEXT_CAPACITY_EXCEEDED",
    "OUTPUT_TRUNCATED",
    "OUTPUT_VALIDATION_EXHAUSTED",
    "PROVIDER_TIMEOUT",
    "PROVIDER_UNAVAILABLE",
    "STRUCTURED_OUTPUT_REPAIR_EXHAUSTED",
}
REVIEW_WARNING = (
    "Independent Judge review did not complete. The design remains governed by Runtime hard "
    "constraints and backend validation; review the displayed evidence and risks before approval."
)


class ReviewUnavailable(AgentBoundaryError):
    """A classified advisory-review failure, never a scientific validity result."""

    def __init__(self, code: str, detail: str):
        if code not in DESIGN_REVIEW_FAILURE_CODES:
            raise ValueError(f"Unknown review-unavailability code: {code}")
        self.code = code
        self.detail = detail[:6000]
        super().__init__(f"{code}: {self.detail}")


def evidence_binding(packet: dict[str, Any]) -> dict[str, Any]:
    return EvidenceBinding.model_validate(
        {key: packet[key] for key in EvidenceBinding.model_fields}
    ).model_dump(mode="json")


def _matching_assessment(bridge: Any, bound: dict[str, Any]) -> bool:
    for event in bridge.store.events(bridge.thread):
        if event["kind"] != "judge-assessment":
            continue
        assessment = bridge.store.assessment(bridge.thread, event["payload"]["assessment_id"])
        if evidence_binding(assessment.model_dump(mode="json")) == bound:
            return True
    return False


def _matching_design_failure(bridge: Any, packet: dict[str, Any]) -> dict[str, Any] | None:
    bound = evidence_binding(packet)
    return next(
        (
            event["payload"]
            for event in reversed(bridge.store.events(bridge.thread))
            if event["kind"] == "judge-review-unavailable"
            and event["payload"].get("gate_type") == "design-specification"
            and event["payload"].get("binding") == bound
        ),
        None,
    )


def _checked_design_failure(
    bridge: Any, packet: dict[str, Any], record_id: str
) -> dict[str, Any]:
    if packet.get("gate_type") != "design-specification":
        raise AgentBoundaryError("Design review failure belongs only to Gate 3")
    bound = evidence_binding(packet)
    failure = next(
        (
            event["payload"]
            for event in bridge.store.events(bridge.thread)
            if event["kind"] == "judge-review-unavailable"
            and event["payload"].get("record_id") == record_id
        ),
        None,
    )
    if failure is None or failure.get("binding") != bound:
        raise AgentBoundaryError("Review failure is absent, foreign or stale")
    payload = {key: value for key, value in failure.items() if key != "record_id"}
    if (
        failure.get("source_role") != "verified-runtime"
        or failure.get("gate_type") != "design-specification"
        or failure.get("failure_code") not in DESIGN_REVIEW_FAILURE_CODES
        or record_id != "review-unavailable-" + identity(payload)
    ):
        raise AgentBoundaryError("Design review failure lacks a verified Runtime receipt")
    if _matching_assessment(bridge, bound):
        raise AgentBoundaryError(
            "A completed Judge assessment cannot be replaced by unavailability"
        )
    return failure


def record_design_unavailable(
    bridge: Any,
    execution_id: str,
    *,
    failure_code: str,
    diagnostic: str,
) -> dict[str, Any]:
    """Persist one exact, classified Gate 3 review failure for the current snapshot."""

    if failure_code not in DESIGN_REVIEW_FAILURE_CODES:
        raise AgentBoundaryError("Unclassified Judge failure cannot bypass independent review")
    packet = bridge.judge_evidence()
    if packet.get("gate_type") != "design-specification":
        raise AgentBoundaryError("Only the current Gate 3 review may use this fallback")
    existing = _matching_design_failure(bridge, packet)
    if existing is not None:
        return _checked_design_failure(bridge, packet, existing["record_id"])
    bound = evidence_binding(packet)
    if _matching_assessment(bridge, bound):
        raise AgentBoundaryError("A completed Judge assessment already exists")
    payload: dict[str, Any] = {
        "binding": bound,
        "diagnostic": diagnostic[:6000],
        "execution_id": execution_id,
        "failure_code": failure_code,
        "gate_type": "design-specification",
        "source_role": "verified-runtime",
    }
    payload["record_id"] = "review-unavailable-" + identity(payload)
    bridge.store.event(bridge.thread, "judge-review-unavailable", payload)
    return _checked_design_failure(bridge, packet, payload["record_id"])


def matching_failure(bridge: Any, packet: dict[str, Any]) -> dict[str, Any] | None:
    if packet.get("gate_type") == "site-hotspot":
        from .site_review_availability import matching_failure as matching_site_failure

        return matching_site_failure(bridge, packet)
    if packet.get("gate_type") == "design-specification":
        return _matching_design_failure(bridge, packet)
    return None


def checked_failure(bridge: Any, packet: dict[str, Any], record_id: str) -> dict[str, Any]:
    if packet.get("gate_type") == "site-hotspot":
        from .site_review_availability import checked_failure as checked_site_failure

        return checked_site_failure(bridge, packet, record_id)
    if packet.get("gate_type") == "design-specification":
        return _checked_design_failure(bridge, packet, record_id)
    raise AgentBoundaryError("This Gate does not support unavailable advisory review")
