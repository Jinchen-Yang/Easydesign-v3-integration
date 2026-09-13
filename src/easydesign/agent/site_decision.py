"""A small scientific choice; exact candidate facts are hydrated by trusted runtime."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Any, Literal

from pydantic import ConfigDict, Field, model_validator

from .contracts import ResearchConclusionMismatch, StrictDTO
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
    alternative_candidate_ids: list[CandidateId] = Field(
        default_factory=list,
        max_length=2,
        description="IDs of supplied candidates used in the comparison, including rejected/avoid "
        "options. Required nonempty when more than one candidate is supplied; comparison does "
        "not recommend these alternatives. Empty only when the dossier has one candidate.",
    )
    avoid_residue_ids: list[CandidateId] = Field(
        default_factory=list,
        max_length=40,
        description="IDs from the dossier residue_constraints to exclude from the selected "
        "hotspot. Declare every proposed residue avoidance here; prose alone is not a constraint. "
        "Exclusions never subtract residues from a candidate or change its membership. "
        "Do not select a hotspot containing an excluded member. Empty means no such exclusion.",
    )
    recommendation: Literal["SUPPORTED", "DISCOURAGED"]
    why_selected: DecisionText = Field(
        description="Relative scientific preference among the supplied candidates. Avoiding one "
        "known adverse-effect epitope or constraint does not establish absence of that risk."
    )
    mechanistic_rationale: DecisionText = Field(
        description="Evidence-grounded mechanism and falsifier. A null functional response is "
        "interpretable only after target engagement and relevant assay controls are established."
    )
    approach_rationale: DecisionText = Field(
        description="Scientific access/whole-binder approach interpretation and its limits; "
        "runtime supplies the underlying geometry. Preserve mixed topology and distinguish "
        "observed residue exposure from untested whole-binder access."
    )
    alternative_comparison: DecisionText
    major_risks: list[DecisionPoint] = Field(
        default_factory=list,
        max_length=4,
        description="Address the user's forbidden effects as well as failure to achieve the "
        "goal. Avoiding a known risk factor does not establish safety or absence of that risk.",
    )
    uncertainty: list[DecisionPoint] = Field(min_length=1, max_length=4)

    @model_validator(mode="after")
    def distinct_candidates(self) -> SiteDecision:
        ids = [self.selected_candidate_id, *self.alternative_candidate_ids]
        if len(ids) != len(set(ids)):
            raise ValueError("Select each candidate at most once")
        return self


def candidate_name(candidate: dict[str, Any]) -> str:
    """Identify a runtime candidate by its existing ID and verified location, not a claim."""
    segments = candidate.get("location", {}).get("segments", [])
    location = "/".join(segments)
    return f"{candidate['candidate_id']}" + (f" ({location})" if location else "")


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
                "name": candidate_name(candidate),
                "research_declared_origin": hypothesis["origin"],
                "origin_scope": "Research classification, not proof of an experimentally "
                "established epitope. Assess the actual bound evidence below.",
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
        "approach_validation": dossier["approach_validation"],
        "reference_annotations": dossier["reference_annotations"],
        "residue_constraints": dossier["residue_constraints"],
        "decision_questions": [{"question": q["question"]} for q in dossier["decision_questions"]],
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
        "access_failures": [
            {"question": q["question"], "errors": q["errors"]}
            for q in dossier["research_outcomes"]
            if q.get("errors")
        ],
        "authority": "Runtime owns exact candidate membership, chain, canonical/design mapping "
        "and evidence bindings. Choose candidate IDs only. Candidate names, research question "
        "assessments, evidence interpretations and unresolved-question premises are fallible "
        "opinions; assess them against the current runtime facts and actual source passages. "
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
                "name": candidate_name(candidates[candidate_id]),
                "role": "primary" if primary else "backup",
                "rationale": decision.why_selected if primary else decision.alternative_comparison,
            }
        )

    constraints = {c["residue_id"]: c["design_label"] for c in dossier["residue_constraints"]}
    if not set(decision.avoid_residue_ids).issubset(constraints):
        raise ResearchConclusionMismatch("Choose only supplied residue constraint IDs")
    excluded = sorted({constraints[key] for key in decision.avoid_residue_ids})
    selected_labels = candidates[decision.selected_candidate_id]["research_hypothesis"][
        "hotspot_label_seq_ids"
    ]
    if set(excluded) & set(selected_labels):
        raise ResearchConclusionMismatch(
            "Selected hotspot conflicts with declared avoid-residue constraint: "
            + str(sorted(set(excluded) & set(selected_labels)))
            + ". Choose a compatible supplied candidate or revise the exclusion; "
            "a warning or human override cannot satisfy mutually exclusive constraints."
        )
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
        scope="mechanistic" if dossier["decision_questions"] else "structural-exploration",
        avoid_label_seq_ids=excluded,
    )
    return intent
