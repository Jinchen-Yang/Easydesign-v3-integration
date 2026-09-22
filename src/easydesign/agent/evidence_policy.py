"""Runtime-owned source ceilings for scientific evidence use.

The policy is deliberately conservative: source provenance determines only the
strongest claim class a passage may be assigned.  It does not decide whether a
passage entails a particular biological claim; that remains specialist and Judge
work.
"""

from __future__ import annotations

from typing import Any, Literal

from .contracts import AgentBoundaryError

EvidenceStrength = Literal["E1", "E2", "E3", "E4"]

_ORDER: tuple[EvidenceStrength, ...] = ("E1", "E2", "E3", "E4")
_CURATED_LEVELS = {"official-database", "curated-receptor-context"}
_CURATED_PROVIDERS = {"UniProt", "GPCRdb"}
_DIRECT_LEVELS = {
    "abstract",
    "primary-abstract",
    "primary-fulltext-excerpts",
    "deposition-and-polymer-entities",
    "deposition-polymer-entities-and-coordinate-contacts",
}
_DIRECT_PROVIDERS = {"EuropePMC", "RCSB"}


def evidence_strength_policy(card: dict[str, Any]) -> dict[str, Any]:
    """Return the deterministic source class and allowed claim strengths.

    Old cards are hydrated from immutable provider metadata.  A persisted explicit
    allowlist may narrow the derived policy, but may never widen it.
    """

    source_status = str(card.get("source_status", ""))
    provider = str(card.get("provider", ""))
    level = str(card.get("evidence_level", ""))
    relation = str(card.get("binding_context", {}).get("relation", ""))

    if source_status == "DISCOVERY_LEAD" or level in {
        "bibliographic-lead",
        "database-lead",
        "structure-lead",
    }:
        source_use_class = "discovery-lead"
        derived: tuple[EvidenceStrength, ...] = ()
    elif card.get("primary_eligible") is not True:
        source_use_class = "context-only"
        derived = ("E3", "E4")
    elif provider in _CURATED_PROVIDERS and level in _CURATED_LEVELS:
        source_use_class = "curated-context"
        derived = ("E2", "E3", "E4")
    elif provider in _DIRECT_PROVIDERS and level in _DIRECT_LEVELS:
        source_use_class = "direct-eligible"
        derived = _ORDER
    else:
        # Unknown or incomplete provenance must not inherit E1/E2 merely because a
        # legacy card happened to carry primary_eligible=true.
        source_use_class = "unknown-context"
        derived = ("E3", "E4")

    if relation == "historical-target" and "E1" in derived:
        source_use_class = "historical-near-direct"
        derived = tuple(value for value in derived if value != "E1")

    explicit = card.get("allowed_strengths")
    if explicit is not None:
        if not isinstance(explicit, (list, tuple)) or any(
            value not in _ORDER for value in explicit
        ):
            raise AgentBoundaryError("Evidence card allowed_strengths is malformed")
        explicit_set = set(explicit)
        if not explicit_set.issubset(set(derived)):
            raise AgentBoundaryError(
                "Evidence card allowed_strengths widens its Runtime-derived source ceiling"
            )
        derived = tuple(value for value in _ORDER if value in explicit_set)

    return {
        "source_use_class": source_use_class,
        "allowed_strengths": list(derived),
    }


def allowed_evidence_strengths(card: dict[str, Any]) -> tuple[EvidenceStrength, ...]:
    return tuple(evidence_strength_policy(card)["allowed_strengths"])
