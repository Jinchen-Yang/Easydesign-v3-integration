"""A small scientific choice; exact candidate facts are hydrated by trusted runtime."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Any, Literal

from pydantic import ConfigDict, Field, model_validator

from .contracts import ResearchConclusionMismatch, StrictDTO
from .site_contracts import SiteIntent, SitePortfolioEntry, SiteSelection

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


class RankedCandidate(StrictDTO):
    candidate_id: CandidateId
    tied_with_previous: bool = Field(
        default=False,
        description="Only when the evidence cannot "
        "distinguish this candidate from the preceding hard-valid candidate. Shared uncertainty "
        "alone is not a tie. Supply the specific missing discriminator in tie_reason.",
    )
    tie_reason: DecisionPoint | None = None
    why_ranked: DecisionText
    mechanistic_rationale: DecisionText
    approach_rationale: DecisionText
    supporting_evidence: list[DecisionPoint] = Field(min_length=1, max_length=3)
    major_risks: list[DecisionPoint] = Field(default_factory=list, max_length=4)
    uncertainty: list[DecisionPoint] = Field(min_length=1, max_length=4)
    confidence: Literal["low", "medium", "high"]

    @model_validator(mode="after")
    def justified_tie(self) -> RankedCandidate:
        if self.tied_with_previous != bool(self.tie_reason):
            raise ValueError("A tie requires its specific missing discriminator")
        return self


class RankedSiteDecision(StrictDTO):
    """SiteDecision is the sole ranking authority; Runtime supplies exact facts."""

    candidates: list[RankedCandidate] = Field(
        min_length=1,
        max_length=3,
        description="Every supplied candidate exactly once, best first. Rank all hard-valid "
        "candidates relatively, even if all are weak. Include hard-invalid candidates last for "
        "explanation; Runtime displays them separately without a rank. Unknown accessibility, "
        "weak evidence and scientific risks lower rank/confidence, never eligibility.",
    )
    avoid_residue_ids: list[CandidateId] = Field(
        default_factory=list,
        max_length=40,
        description="Only explicit residue exclusions from supplied constraint IDs. Do not turn "
        "scientific uncertainty, cysteine membership or poor exposure into hard exclusions.",
    )

    @model_validator(mode="after")
    def distinct(self) -> RankedSiteDecision:
        ids = [candidate.candidate_id for candidate in self.candidates]
        if self.candidates[0].tied_with_previous:
            raise ValueError("The first candidate has no preceding candidate to tie with")
        if len(ids) != len(set(ids)):
            raise ValueError("Each supplied candidate must occur exactly once")
        return self


def parse_site_decision(value: dict[str, Any]) -> SiteDecision | RankedSiteDecision:
    # Historical persisted decisions retain their original contract.
    return (RankedSiteDecision if "candidates" in value else SiteDecision).model_validate(value)


def candidate_name(candidate: dict[str, Any]) -> str:
    """Identify a runtime candidate by its existing ID and verified location, not a claim."""
    segments = candidate.get("location", {}).get("segments", [])
    location = "/".join(segments)
    return f"{candidate['candidate_id']}" + (f" ({location})" if location else "")


def verified_location_conflict(
    location: dict[str, Any], required_compartment: str | None
) -> str | None:
    """Return a hard conflict only when independent verified sidedness agrees.

    TM membership, point burial, low exposure and an uncertain whole-binder approach remain
    ranking penalties. A block requires an explicit user compartment plus decisive topology or
    concordant canonical annotation and signed membrane geometry.
    """
    if required_compartment not in {"extracellular", "intracellular"}:
        return None
    segments = {str(value) for value in location.get("segments", [])}
    annotations = {
        str(annotation.get("description", "")).casefold()
        for row in location.get("sequence_topology", [])
        for annotation in row.get("annotations", [])
        if annotation.get("type") == "Topological domain"
    }
    has_extra = bool(annotations & {"extracellular", "outside"})
    has_cyto = bool(annotations & {"cytoplasmic", "intracellular", "cytosolic"})
    geometry = location.get("membrane_geometry", [])
    regions = {str(row.get("region", "")) for row in geometry}
    axial = [row.get("axial_distance") for row in geometry]
    signed = bool(axial) and all(isinstance(value, (int, float)) for value in axial)

    if required_compartment == "extracellular":
        declared_conflict = bool(segments) and segments <= {"ICL1", "ICL2", "ICL3", "C-term"}
        geometric_conflict = bool(geometry) and (
            regions <= {"intracellular", "intracellular_tm_surface"}
            or (
                regions <= {"inner_pore"}
                and signed
                and all(value < 0 for value in axial)
                and has_cyto
                and not has_extra
            )
        )
        if declared_conflict or geometric_conflict:
            return "verified-compartment-conflict"
    else:
        declared_conflict = bool(segments) and segments <= {
            "N-term",
            "ECD",
            "ECL1",
            "ECL2",
            "ECL3",
        }
        geometric_conflict = bool(geometry) and (
            regions <= {"extracellular", "extracellular_tm_surface", "outer_vestibule"}
            and signed
            and all(value > 0 for value in axial)
            and has_extra
            and not has_cyto
        )
        if declared_conflict or geometric_conflict:
            return "verified-compartment-conflict"
    return None


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
                    if label in rows
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
        "and evidence bindings. Choose candidate IDs only. Decision questions define inquiry "
        "scope, not scientific conclusions. Assess candidate hypotheses against the supplied "
        "runtime facts, scoped source evidence and access failures. "
        "A source passage supports only its actual claim and scope. No approval is implied.",
    }


def hydrate_site_decision(
    bridge: Phase2Bridge, decision: SiteDecision | RankedSiteDecision, execution_id: str | None
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


def compile_site_decision(
    dossier: dict[str, Any], decision: SiteDecision | RankedSiteDecision
) -> SiteIntent:
    """Pure trusted hydration after the caller verifies the dossier's binding/artifacts.

    This is not a model tool. Production enters through hydrate_site_decision;
    read-only validation replays can use an independently verified saved dossier.
    """
    if isinstance(decision, RankedSiteDecision):
        return compile_ranked_decision(dossier, decision)
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


def compile_ranked_decision(dossier: dict[str, Any], decision: RankedSiteDecision) -> SiteIntent:
    candidates = {c["candidate_id"]: c for c in dossier["candidate_comparison"]}
    if {c.candidate_id for c in decision.candidates} != set(candidates):
        raise ResearchConclusionMismatch(
            "Rank every supplied candidate exactly once: " + ", ".join(candidates)
        )
    constraints = {c["residue_id"]: c["design_label"] for c in dossier["residue_constraints"]}
    if not set(decision.avoid_residue_ids).issubset(constraints):
        raise ResearchConclusionMismatch("Choose only supplied residue constraint IDs")
    excluded = sorted({constraints[key] for key in decision.avoid_residue_ids})
    entries: list[SitePortfolioEntry] = []
    ranked_count = 0
    preference_group = 0
    for interpretation in decision.candidates:
        candidate = candidates[interpretation.candidate_id]
        evaluation = candidate["deterministic_evaluation"]
        original = candidate["research_hypothesis"]
        block = evaluation.get("cause") if evaluation["status"] == "BLOCKED" else None
        eligibility = candidate.get("runtime_eligibility", {})
        if eligibility.get("status") == "BLOCKED":
            block = eligibility.get("cause") or "verified-compartment-conflict"
        if set(original["hotspot_label_seq_ids"]) & set(excluded):
            block = "explicit-avoid-residue-constraint"
        rank = None if block else "ABC"[ranked_count]
        tied_id = None
        if interpretation.tied_with_previous:
            if block or not entries or not entries[-1].selectable:
                raise ResearchConclusionMismatch(
                    "A tie must connect adjacent hard-valid candidates"
                )
            tied_id = entries[-1].candidate_id
        if rank:
            ranked_count += 1
            if not tied_id:
                preference_group += 1
        site = SiteSelection.model_validate(
            {
                **original,
                "name": candidate_name(candidate),
                "role": "primary" if rank == "A" else "backup",
                "rationale": interpretation.why_ranked,
            }
        )
        entries.append(
            SitePortfolioEntry.model_validate(
                {
                    **interpretation.model_dump(mode="json", exclude={"tied_with_previous"}),
                    "tied_with_candidate_id": tied_id,
                    "preference_group": preference_group if rank else None,
                    "site": site,
                    "rank": rank,
                    "selectable": block is None,
                    "hard_block": block,
                }
            )
        )
    entries.sort(key=lambda entry: entry.rank or "Z")
    primary = entries[0]
    return SiteIntent(
        portfolio=entries,
        selected_site=primary.site,
        alternatives=[entry.site for entry in entries[1:]],
        positive_evidence=primary.supporting_evidence,
        mechanistic_rationale=primary.mechanistic_rationale,
        accessibility_rationale=primary.approach_rationale,
        binder_approach=primary.approach_rationale,
        risks=primary.major_risks,
        uncertainty=primary.uncertainty,
        recommendation="SUPPORTED",
        scope="mechanistic" if dossier["decision_questions"] else "structural-exploration",
        avoid_label_seq_ids=excluded,
    )
