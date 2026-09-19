"""Deterministic policy for optional independent review at ranked Site Gate 2."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypedDict

if TYPE_CHECKING:
    from .phase2 import Phase2Bridge

SITE_REVIEW_POLICY = "ranked-site-review-v1"
_EXPLICIT_REVIEW_PHRASES = (
    "independent review",
    "second opinion",
    "evidence judge",
    "judge review",
    "独立审查",
    "独立复核",
    "第二意见",
    "judge",
)
_CONFLICTING = {"CONFLICTING", "CONFLICTING_EVIDENCE", "CONTRADICTED"}


class SiteReviewRequirement(TypedDict):
    policy_id: str
    required: bool
    reasons: list[str]


def site_review_requirement(
    bridge: Phase2Bridge, snapshot: dict[str, Any]
) -> SiteReviewRequirement:
    """Require Judge only for an explicit request or a material exceptional state."""
    reasons: list[str] = []
    decision = snapshot.get("final_site_decision", {})
    if decision.get("kind") != "RankedSiteDecision":
        reasons.append("legacy-or-unranked-site-proposal")
    approved = snapshot.get("approved_target", {})
    identity = approved.get("identity", {})
    canonical = identity.get("canonical", {})
    if identity.get("ambiguities"):
        reasons.append("target-identity-ambiguity")
    if (
        identity.get("biological_identity_status") != "resolved"
        or canonical.get("status") != "resolved"
    ):
        reasons.append("canonical-target-identity-unresolved")
    questions = snapshot.get("decision_evidence", {}).get("questions", [])
    if any(str(question.get("status", "")).upper() in _CONFLICTING for question in questions):
        reasons.append("material-conflicting-evidence")
    row = bridge.store.db.execute(
        "SELECT goal FROM threads WHERE id=?", (bridge.thread,)
    ).fetchone()
    request_text = str(row["goal"] if row is not None else "")
    execution = bridge.store.latest_execution(bridge.thread)
    if execution is not None:
        request_text += " " + str(execution.get("current_user_message", ""))
    if any(phrase in request_text.casefold() for phrase in _EXPLICIT_REVIEW_PHRASES):
        reasons.append("scientist-requested-independent-review")
    return {
        "policy_id": SITE_REVIEW_POLICY,
        "required": bool(reasons),
        "reasons": reasons,
    }
