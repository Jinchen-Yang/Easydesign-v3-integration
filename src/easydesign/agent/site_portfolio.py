"""Versioned Gate 2 selection policy and runtime projections of the chosen candidate."""

from __future__ import annotations

from typing import Any

from .contracts import AgentBoundaryError, DecisionCard

PORTFOLIO_POLICY = "ranked-site-portfolio-v1"


def is_portfolio_card(card: DecisionCard) -> bool:
    return (
        card.gate_type == "site-hotspot"
        and card.scientific_summary.get("selection_policy") == PORTFOLIO_POLICY
    )


def selected_proposal(proposal: dict[str, Any], candidate_id: str | None) -> dict[str, Any]:
    """Project the approved choice; never mutate or relabel the original ranked portfolio."""
    portfolio = proposal["intent"].get("portfolio")
    if portfolio is None:
        if candidate_id is not None:
            raise AgentBoundaryError("Legacy Site approval does not accept a candidate choice")
        return proposal
    entry = next((entry for entry in portfolio if entry["candidate_id"] == candidate_id), None)
    if entry is None or not entry["selectable"]:
        raise AgentBoundaryError("Choose one selectable candidate from the bound portfolio")
    intent = {
        **proposal["intent"],
        "selected_site": {**entry["site"], "role": "primary"},
        "alternatives": [
            {**other["site"], "role": "backup"}
            for other in portfolio
            if other["candidate_id"] != candidate_id
        ],
        "positive_evidence": entry["supporting_evidence"],
        "mechanistic_rationale": entry["mechanistic_rationale"],
        "accessibility_rationale": entry["approach_rationale"],
        "binder_approach": entry["approach_rationale"],
        "risks": entry["major_risks"],
        "uncertainty": entry["uncertainty"],
    }
    # The chosen SiteIntent remains independently valid; the immutable original ranking
    # is preserved alongside it rather than claiming its former default is still selected.
    intent.pop("portfolio")
    return {
        **proposal,
        "ranked_portfolio": portfolio,
        "intent": intent,
        "selected_candidate_id": candidate_id,
        "selected_rank": entry["rank"],
        "evaluation": proposal["portfolio_evaluations"][candidate_id],
    }


def portfolio_options(proposal: dict[str, Any], facts: dict[str, Any]) -> list[dict[str, object]]:
    mapping = {row["label_seq_id"]: row for row in facts["observed_facts"]["mapping"]}
    options: list[dict[str, object]] = []
    for entry in proposal["intent"]["portfolio"]:
        evaluation = proposal["portfolio_evaluations"][entry["candidate_id"]]
        labels = entry["site"]["hotspot_label_seq_ids"]
        options.append(
            {
                "option_id": entry["candidate_id"],
                "rank": entry["rank"],
                "label": entry["site"]["name"],
                "description": entry["why_ranked"],
                "priority": {1: "Preferred", 2: "Alternative", 3: "Exploratory"}.get(
                    entry.get("preference_group"), "Blocked"
                ),
                "preference_group": entry.get("preference_group"),
                "tied_with_candidate_id": entry.get("tied_with_candidate_id"),
                "tie_reason": entry.get("tie_reason"),
                "eligible": entry["selectable"],
                "hard_block": entry["hard_block"],
                "design_labels": labels,
                "runtime_residue_facts": [mapping[label] for label in labels if label in mapping],
                "mechanism": entry["mechanistic_rationale"],
                "approach": entry["approach_rationale"],
                "supporting_evidence": entry["supporting_evidence"],
                "evidence_card_ids": entry["site"]["evidence_card_ids"],
                "major_risks": list(
                    dict.fromkeys([*entry["major_risks"], *evaluation.get("warnings", [])])
                ),
                "uncertainty": entry["uncertainty"],
                "confidence": entry["confidence"],
            }
        )
    return options
