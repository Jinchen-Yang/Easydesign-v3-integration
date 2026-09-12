"""A small scientific choice; exact candidate facts are hydrated by trusted runtime."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Any, Literal

from pydantic import ConfigDict, Field, model_validator

from .contracts import ResearchConclusionMismatch, StrictDTO
from .evidence_research import ResearchConclusion
from .site_contracts import SiteIntent, SiteSelection

if TYPE_CHECKING:
    from .phase2 import Phase2Bridge

DecisionText = Annotated[str, Field(min_length=1, max_length=1000)]
DecisionPoint = Annotated[str, Field(min_length=1, max_length=600)]
CandidateId = Annotated[str, Field(min_length=1, max_length=64)]


class SiteDecision(StrictDTO):
    """Choose supplied candidates and explain the science; never emit residue identities."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    selected_candidate_id: CandidateId
    alternative_candidate_ids: list[CandidateId] = Field(default_factory=list, max_length=2)
    recommendation: Literal["SUPPORTED", "DISCOURAGED"]
    why_selected: DecisionText
    mechanistic_rationale: DecisionText
    approach_rationale: DecisionText = Field(
        description="Scientific access/whole-binder approach interpretation and its limits; "
        "runtime supplies the underlying geometry."
    )
    alternative_comparison: DecisionText
    major_risks: list[DecisionPoint] = Field(default_factory=list, max_length=4)
    uncertainty: list[DecisionPoint] = Field(min_length=1, max_length=4)

    @model_validator(mode="after")
    def distinct_candidates(self) -> SiteDecision:
        ids = [self.selected_candidate_id, *self.alternative_candidate_ids]
        if len(ids) != len(set(ids)):
            raise ValueError("Select each candidate at most once")
        return self


def decision_working_set(dossier: dict[str, Any]) -> dict[str, Any]:
    """Scientific projection of a verified dossier, not a message/history compressor.

    The immutable dossier retains exact membership/evaluations for hydration. The
    inference receives only the chosen candidate facts and consequential evidence;
    no binding hashes, query receipts, duplicate mapping namespaces or taxonomy forms
    need to be regenerated in its answer.
    """
    table = dossier["trusted_residue_facts"]["facts_table"]
    columns = table["mapping_columns"] + table["metric_columns"]
    rows = {
        r["label_seq_id"]: r
        for values in table["rows"]
        for r in [dict(zip(columns, values, strict=True))]
    }
    candidates = []
    for candidate in dossier["candidate_comparison"]:
        hypothesis = candidate["research_hypothesis"]
        evaluation = candidate["deterministic_evaluation"]
        candidates.append(
            {
                "candidate_id": candidate["candidate_id"],
                "name": hypothesis["name"],
                "research_preference": hypothesis["role"],
                "research_rationale": hypothesis["rationale"],
                "origin": hypothesis["origin"],
                "location": candidate.get("location", {"topology": "unresolved"}),
                "residue_facts": [
                    {
                        key: rows[label][key]
                        for key in (
                            "canonical_position",
                            "canonical_residue",
                            "amino_acid",
                            "mapping_status",
                            "model_presence",
                            "rsasa",
                            "surface_eligible",
                        )
                    }
                    for label in hypothesis["hotspot_label_seq_ids"]
                ],
                "geometry_scope": "Prepared-target calculation with its explicit BiologyContext. "
                "Its missing-annotation limitations do not negate independently retrieved "
                "receptor topology/state or literature supplied elsewhere in this dossier.",
                "geometry_and_constraints": {
                    key: value
                    for key, value in evaluation.items()
                    if key not in {"mapped_residues", "surface_evidence", "centroid_angstrom"}
                },
            }
        )
    return {
        "kind": "site-decision-working-set-v1",
        "approved_target": dossier["approved_target"],
        "runtime_status": dossier["runtime_status"],
        "scientific_context": dossier["scientific_context"],
        "candidates": candidates,
        "receptor_context": dossier["receptor_context"],
        "decision_questions": [
            {
                "question": q["question"],
                "status": q["status"],
                "decision_impact": q["decision_impact"],
                "limitations": q["limitations"],
                "evidence_interpretations": [
                    {
                        key: use[key]
                        for key in ("claim", "relation", "strength", "transfer_limit", "excerpt")
                    }
                    for use in q["evidence"]
                ],
            }
            for q in dossier["decision_questions"]
        ],
        "evidence": [
            {
                key: value
                for key, value in card.items()
                if key
                in {
                    "provider",
                    "identifier",
                    "source_id",
                    "title",
                    "passage",
                    "location",
                    "section",
                    "evidence_level",
                    "primary_eligible",
                    "partial",
                    "limitations",
                    "does_not_support",
                    "binding_context",
                }
            }
            for card in dossier["focused_passages"]
        ],
        "research_stopping_assessment": dossier["research_opinions"],
        "access_failures": [
            {"question": q["question"], "errors": q["errors"]}
            for q in dossier["research_outcomes"]
            if q.get("errors")
        ],
        "authority": "Runtime owns exact candidate membership, chain, canonical/design mapping "
        "and evidence bindings. Choose candidate IDs only. Research preferences, evidence "
        "interpretations and stopping claims are fallible opinions; assess independently. "
        "A source passage supports only its actual claim and scope. No approval is implied.",
    }


def hydrate_site_decision(
    bridge: Phase2Bridge, decision: SiteDecision, execution_id: str | None
) -> SiteIntent:
    """Resolve IDs in the exact runtime dossier, without alignment or model fact copying."""
    from .site_dossier import validate_dossier_intent

    event = bridge.thread_latest("site-evidence-dossier")
    if execution_id is None or event is None or event["execution_id"] != execution_id:
        raise ResearchConclusionMismatch("SiteDecision requires the current execution dossier")
    dossier = bridge.document(event["ref"])
    if (
        dossier["target_binding"] != bridge.target_state()["binding"]
        or dossier["owner_thread"] != bridge.thread
    ):
        raise ResearchConclusionMismatch(
            "SiteDecision dossier has stale Target or foreign ownership"
        )
    intent = compile_site_decision(dossier, decision)
    validate_dossier_intent(bridge, intent, execution_id)
    return intent


def compile_site_decision(dossier: dict[str, Any], decision: SiteDecision) -> SiteIntent:
    """Pure trusted hydration after the caller verifies the dossier's binding/artifacts.

    This is not a model tool. Production enters through hydrate_site_decision;
    read-only validation replays can use an independently verified saved dossier.
    """
    candidates = {c["candidate_id"]: c for c in dossier["candidate_comparison"]}
    selected_ids = [decision.selected_candidate_id, *decision.alternative_candidate_ids]
    if not set(selected_ids).issubset(candidates):
        raise ResearchConclusionMismatch(
            "Choose only supplied candidate IDs: " + ", ".join(candidates)
        )
    if len(candidates) > 1 and not decision.alternative_candidate_ids:
        raise ResearchConclusionMismatch("Compare at least one supplied alternative candidate")

    def selection(candidate_id: str, primary: bool) -> SiteSelection:
        original = candidates[candidate_id]["research_hypothesis"]
        return SiteSelection.model_validate(
            {
                **original,
                "role": "primary"
                if primary
                else original["role"]
                if original["role"] in {"avoid", "unresolved"}
                else "backup",
                "rationale": decision.why_selected if primary else decision.alternative_comparison,
            }
        )

    conclusions = [
        ResearchConclusion.model_validate(
            {key: value for key, value in q.items() if key in ResearchConclusion.model_fields}
        )
        for q in dossier["decision_questions"]
    ]
    intent = SiteIntent(
        selected_site=selection(decision.selected_candidate_id, True),
        positive_evidence=[decision.why_selected],
        mechanistic_rationale=decision.mechanistic_rationale,
        accessibility_rationale=decision.approach_rationale,
        binder_approach=decision.approach_rationale,
        risks=decision.major_risks,
        uncertainty=decision.uncertainty,
        alternatives=[
            selection(candidate_id, False) for candidate_id in decision.alternative_candidate_ids
        ],
        recommendation=decision.recommendation,
        scope="mechanistic" if conclusions else "structural-exploration",
        material_questions=[conclusion.topic for conclusion in conclusions],
        research_conclusions=conclusions,
    )
    return intent
