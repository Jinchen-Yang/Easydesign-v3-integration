"""Ranked Gate 2 uses Judge only for explicit or exceptional review needs."""

from __future__ import annotations

from types import SimpleNamespace

from easydesign.agent.site_review_policy import SITE_REVIEW_POLICY, site_review_requirement


class _Store:
    def __init__(self, goal: str, current_message: str | None = None) -> None:
        self.db = self
        self.goal = goal
        self.current_message = current_message

    def execute(self, _query: str, _args: object) -> _Store:
        return self

    def fetchone(self) -> dict[str, str]:
        return {"goal": self.goal}

    def latest_execution(self, _thread: str) -> dict[str, str] | None:
        return (
            {"current_user_message": self.current_message}
            if self.current_message is not None
            else None
        )


def _snapshot() -> dict[str, object]:
    return {
        "final_site_decision": {"kind": "RankedSiteDecision"},
        "approved_target": {
            "identity": {
                "ambiguities": [],
                "biological_identity_status": "resolved",
                "canonical": {"status": "resolved"},
            }
        },
        "decision_evidence": {
            "questions": [{"status": "UNRESOLVED"}, {"status": "VERIFIED"}]
        },
    }


def test_normal_ranked_site_review_is_optional() -> None:
    bridge = SimpleNamespace(thread="thread", store=_Store("Design an extracellular VHH"))
    result = site_review_requirement(bridge, _snapshot())
    assert result == {"policy_id": SITE_REVIEW_POLICY, "required": False, "reasons": []}


def test_explicit_second_opinion_or_identity_ambiguity_requires_review() -> None:
    bridge = SimpleNamespace(
        thread="thread", store=_Store("Design a VHH and obtain an independent review")
    )
    result = site_review_requirement(bridge, _snapshot())
    assert result["required"] is True
    assert "scientist-requested-independent-review" in result["reasons"]
    ambiguous = _snapshot()
    ambiguous["approved_target"]["identity"]["ambiguities"] = ["isoform unresolved"]
    bridge = SimpleNamespace(thread="thread", store=_Store("Design a VHH"))
    result = site_review_requirement(bridge, ambiguous)
    assert "target-identity-ambiguity" in result["reasons"]


def test_followup_can_explicitly_request_independent_review() -> None:
    bridge = SimpleNamespace(
        thread="thread",
        store=_Store("Design a VHH", "Please obtain a second opinion before Gate 2"),
    )
    result = site_review_requirement(bridge, _snapshot())
    assert result["required"] is True
    assert "scientist-requested-independent-review" in result["reasons"]
