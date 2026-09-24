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
        "weak evidence and scientific risks normally lower rank/confidence, never eligibility. "
        "For an extracellular deep-orthosteric GPCR candidate, untested whole-binder access "
        "cannot demote it from A.",
    )
    avoid_residue_ids: list[CandidateId] = Field(
        default_factory=list,
        max_length=40,
        description="Advisory downstream not-binding residues from supplied residue IDs. Do not "
        "turn scientific uncertainty, activation risk, cysteine membership or poor exposure "
        "into candidate ineligibility. Runtime removes every exclusion that overlaps a "
        "hard-valid candidate, so this field cannot block or rerank the supplied portfolio.",
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
        geometric_conflict = (
            bool(geometry)
            and regions
            <= {"inner_pore", "intracellular", "intracellular_tm_surface"}
            and signed
            and all(value < 0 for value in axial)
            and has_cyto
            and not has_extra
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
        geometric_conflict = (
            bool(geometry)
            and regions
            <= {
                "outer_pore",
                "extracellular",
                "extracellular_tm_surface",
                "outer_vestibule",
            }
            and signed
            and all(value > 0 for value in axial)
            and has_extra
            and not has_cyto
        )
        if declared_conflict or geometric_conflict:
            return "verified-compartment-conflict"
    return None


def _compact_target(target: dict[str, Any]) -> dict[str, Any]:
    identity_facts = target.get("identity", {})
    hard = target.get("hard_facts", {})
    return {
        "target_id": target.get("bundle", {}).get("target_id"),
        "canonical_accession": hard.get("canonical_accession"),
        "canonical_length": hard.get("canonical_length"),
        "selected_chain": hard.get("selected_chain"),
        "identity": {
            key: identity_facts.get(key)
            for key in (
                "auth_chain",
                "biological_identity_status",
                "mapping_status",
                "relationship",
                "canonical",
                "ambiguities",
            )
        },
        "limitations": target.get("limitations", []),
    }


def _compact_location(location: dict[str, Any]) -> dict[str, Any]:
    membrane_rows: list[dict[str, Any]] = []
    seen_membrane: set[tuple[Any, ...]] = set()
    keys = (
        "canonical_position",
        "region",
        "protein_segment",
        "axial_distance",
        "radial_distance",
        "pore_lining",
    )
    for row in location.get("membrane_geometry", []):
        signature = tuple(row.get(key) for key in keys)
        if signature in seen_membrane:
            continue
        seen_membrane.add(signature)
        membrane_rows.append({key: row.get(key) for key in keys})
    topology = []
    for row in location.get("sequence_topology", []):
        topology.append(
            {
                "canonical_position": row.get("canonical_position"),
                "annotations": [
                    {
                        "type": item.get("type"),
                        "description": item.get("description"),
                    }
                    for item in row.get("annotations", [])
                ],
            }
        )
    return {
        "canonical_positions": location.get("canonical_positions", []),
        "segments": location.get("segments", []),
        "membrane_geometry": membrane_rows,
        "sequence_topology": topology,
    }


def _compact_receptor_context(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep decision-bearing receptor facts once; full kernel cards stay in the dossier."""
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for card in cards:
        identity_facts = card.get("identity", {})
        membrane = card.get("membrane", {})
        context_key = repr(
            (
                identity_facts.get("accession"),
                identity_facts.get("receptor_chain"),
                identity_facts.get("entry_name"),
                membrane.get("status"),
                membrane.get("extracellular_boundary"),
                membrane.get("intracellular_boundary"),
                card.get("state", {}).get("assignment"),
            )
        )
        if context_key in seen:
            continue
        seen.add(context_key)
        receptor_chain = identity_facts.get("receptor_chain")
        interfaces = card.get("complex_interfaces", {})
        receptor_edges = [
            {
                key: edge.get(key)
                for key in (
                    "chain_a",
                    "chain_b",
                    "interface_type",
                    "geometry_observed",
                    "minimum_distance",
                    "residue_count_a",
                    "residue_count_b",
                    "residue_pair_count",
                )
            }
            for edge in interfaces.get("edges", [])
            if receptor_chain in {edge.get("chain_a"), edge.get("chain_b")}
        ]
        self_occlusion = interfaces.get("self_occlusion", {})
        result.append(
            {
                "identity": {
                    key: identity_facts.get(key)
                    for key in (
                        "status",
                        "accession",
                        "entry_name",
                        "family",
                        "family_slug",
                        "receptor_class",
                        "species",
                        "receptor_chain",
                    )
                },
                "membrane": {
                    key: membrane.get(key)
                    for key in (
                        "status",
                        "reliable",
                        "topology_reliable",
                        "confidence",
                        "direction_source",
                        "extracellular_boundary",
                        "intracellular_boundary",
                        "helix_count",
                        "helix_direction_consistency",
                        "reasons",
                    )
                },
                "state": card.get("state", {}),
                "topology_qualifications": card.get("topology_qualifications", {}),
                "receptor_interfaces": receptor_edges,
                "self_occlusion": {
                    key: self_occlusion.get(key)
                    for key in (
                        "observed",
                        "reason",
                        "ecd_residue_count",
                        "ecd_total_residue_count",
                        "mouth_residue_count",
                        "residue_pair_count",
                    )
                },
                "warnings": card.get("warnings", []),
                "avoid": card.get("avoid", []),
            }
        )
    return result


def decision_working_set(dossier: dict[str, Any]) -> dict[str, Any]:
    """Compact decision view; the immutable dossier remains the exact audit authority."""
    table = dossier["trusted_residue_facts"]["facts_table"]
    columns = table["mapping_columns"] + table["metric_columns"]
    rows = {
        r["label_seq_id"]: r
        for values in table["rows"]
        for r in [dict(zip(columns, values, strict=True))]
    }
    candidates = []
    candidate_positions: set[int] = set()
    for candidate in dossier["candidate_comparison"]:
        hypothesis = candidate["research_hypothesis"]
        evaluation = candidate["deterministic_evaluation"]
        location = _compact_location(candidate.get("location", {}))
        candidate_positions.update(location["canonical_positions"])
        candidates.append(
            {
                "candidate_id": candidate["candidate_id"],
                "name": candidate_name(candidate),
                "research_hypothesis": {
                    key: hypothesis.get(key)
                    for key in (
                        "origin",
                        "role",
                        "evidence_card_ids",
                    )
                },
                "location": {
                    "canonical_positions": location["canonical_positions"],
                    "segments": location["segments"],
                },
                "residue_fact_columns": [
                    "label_seq_id",
                    "canonical_position",
                    "canonical_residue",
                    "amino_acid",
                    "mapping_status",
                    "model_presence",
                    "rsasa",
                    "surface_eligible",
                    "membrane_region",
                    "protein_segment",
                    "axial_distance",
                    "radial_distance",
                    "pore_lining",
                    "topology_annotations",
                ],
                "residue_facts": [
                    [
                        rows[label].get("label_seq_id"),
                        rows[label].get("canonical_position"),
                        rows[label].get("canonical_residue"),
                        rows[label].get("amino_acid"),
                        rows[label].get("mapping_status"),
                        rows[label].get("model_presence"),
                        rows[label].get("rsasa"),
                        rows[label].get("surface_eligible"),
                        next(
                            (
                                item.get("region")
                                for item in location["membrane_geometry"]
                                if item.get("canonical_position")
                                == rows[label].get("canonical_position")
                            ),
                            None,
                        ),
                        next(
                            (
                                item.get("protein_segment")
                                for item in location["membrane_geometry"]
                                if item.get("canonical_position")
                                == rows[label].get("canonical_position")
                            ),
                            None,
                        ),
                        next(
                            (
                                item.get("axial_distance")
                                for item in location["membrane_geometry"]
                                if item.get("canonical_position")
                                == rows[label].get("canonical_position")
                            ),
                            None,
                        ),
                        next(
                            (
                                item.get("radial_distance")
                                for item in location["membrane_geometry"]
                                if item.get("canonical_position")
                                == rows[label].get("canonical_position")
                            ),
                            None,
                        ),
                        next(
                            (
                                item.get("pore_lining")
                                for item in location["membrane_geometry"]
                                if item.get("canonical_position")
                                == rows[label].get("canonical_position")
                            ),
                            None,
                        ),
                        [
                            f"{item.get('type')}: {item.get('description')}"
                            for topology in location["sequence_topology"]
                            if topology.get("canonical_position")
                            == rows[label].get("canonical_position")
                            for item in topology.get("annotations", [])
                        ],
                    ]
                    for label in hypothesis["hotspot_label_seq_ids"]
                    if label in rows
                ],
                "evaluation": {
                    key: evaluation.get(key)
                    for key in (
                        "status",
                        "hard_constraints",
                        "warnings",
                        "motif_warnings",
                        "overlapping_features",
                        "radius_gyration_angstrom",
                        "spatial_components",
                    )
                },
                "runtime_eligibility": candidate.get("runtime_eligibility", {}),
            }
        )
    reference_annotations = []
    for annotation in dossier["reference_annotations"]:
        reference_annotations.append(
            {
                "accession": annotation.get("accession"),
                "numbering": annotation.get("numbering"),
                "disulfide_assignments": annotation.get("disulfide_assignments", {}),
                "features": [
                    feature
                    for feature in annotation.get("features", [])
                    if any(
                        feature.get("location", {}).get("start", {}).get("value", position)
                        <= position
                        <= feature.get("location", {}).get("end", {}).get("value", position)
                        for position in candidate_positions
                    )
                ],
            }
        )
    return {
        "kind": "site-decision-working-set-v2",
        "approved_target": _compact_target(dossier["approved_target"]),
        "runtime_status": dossier["runtime_status"],
        "scientific_context": {
            "biology": dossier["scientific_context"].get("biology"),
            "geometry_warnings": dossier["scientific_context"].get("geometry_warnings", []),
        },
        "candidates": candidates,
        "receptor_context": _compact_receptor_context(dossier["receptor_context"]),
        "approach_validation": dossier["approach_validation"],
        "reference_annotations": reference_annotations,
        "residue_constraint_columns": [
            "residue_id",
            "design_label",
            "canonical_position",
            "canonical_residue",
        ],
        "residue_constraints": [
            [
                item.get("residue_id"),
                item.get("design_label"),
                item.get("canonical_position"),
                item.get("canonical_residue"),
            ]
            for item in dossier["residue_constraints"]
        ],
        "research_findings": [
            {
                key: question.get(key)
                for key in (
                    "question",
                    "status",
                    "decision_impact",
                    "limitations",
                    "query_ids",
                )
            }
            | {
                "evidence": [
                    {
                        key: use.get(key)
                        for key in ("card_id", "claim", "relation", "strength", "transfer_limit")
                    }
                    for use in question.get("evidence", [])
                ]
            }
            for question in dossier["decision_questions"]
        ],
        "evidence": [
            {
                key: value
                for key, value in card.items()
                if key
                in {
                    "card_id",
                    "provider",
                    "identifier",
                    "source_id",
                    "title",
                    "passage",
                    "location",
                    "section",
                    "evidence_level",
                    "primary_eligible",
                    "source_use_class",
                    "allowed_strengths",
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
        "and evidence bindings. The full immutable dossier remains available for audit. Rank every "
        "supplied hard-valid candidate by ID; scientific risk lowers rank or confidence, while "
        "only Runtime hard-invalid status removes selectability.",
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
        scope=(
            "mechanistic"
            if any(question.get("query_ids") for question in dossier["decision_questions"])
            else "structural-exploration"
        ),
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
    proposed_exclusions = {constraints[key] for key in decision.avoid_residue_ids}

    def runtime_block(candidate: dict[str, Any]) -> str | None:
        evaluation = candidate["deterministic_evaluation"]
        block = evaluation.get("cause") if evaluation["status"] == "BLOCKED" else None
        eligibility = candidate.get("runtime_eligibility", {})
        if eligibility.get("status") == "BLOCKED":
            block = eligibility.get("cause") or "verified-compartment-conflict"
        return block

    def mandatory_gpcr_a(candidate: dict[str, Any]) -> bool:
        """Recognize a narrow model/runtime-consistency invariant, not a new epitope claim.

        Research must itself identify the candidate as orthosteric. Runtime independently
        supplies the extracellular outer-pore geometry. This prevents an unperformed whole-VHH
        clearance guess from reversing the explicit GPCR ranking policy.
        """
        if runtime_block(candidate) is not None:
            return False
        hypothesis = candidate.get("research_hypothesis", {})
        interpretation = " ".join(
            str(hypothesis.get(key, "")) for key in ("name", "rationale")
        ).casefold()
        if "orthosteric" not in interpretation and "正构" not in interpretation:
            return False
        geometry = candidate.get("location", {}).get("membrane_geometry", [])
        outer_pore = [
            row
            for row in geometry
            if row.get("region") == "outer_pore"
            and row.get("pore_lining") is True
            and isinstance(row.get("axial_distance"), (int, float))
            and not isinstance(row.get("axial_distance"), bool)
            and row["axial_distance"] > 0
        ]
        return bool(outer_pore) and len(outer_pore) == len(geometry)

    receptor_verified = any(
        context.get("identity", {}).get("status") == "resolved"
        and context.get("membrane", {}).get("reliable") is True
        for context in dossier.get("receptor_context", [])
    )
    policy_applies = (
        dossier.get("objective_requirements", {}).get("required_site_compartment")
        == "extracellular"
        and receptor_verified
        and dossier.get("approach_validation", {}).get("status") == "not-performed"
    )
    mandatory_ids = {
        candidate_id
        for candidate_id, candidate in candidates.items()
        if policy_applies and mandatory_gpcr_a(candidate)
    }
    first_selectable = next(
        (
            interpretation.candidate_id
            for interpretation in decision.candidates
            if runtime_block(candidates[interpretation.candidate_id]) is None
        ),
        None,
    )
    if mandatory_ids and first_selectable not in mandatory_ids:
        raise ResearchConclusionMismatch(
            "GPCR_ORTHOSTERIC_A_REQUIRED: rank one supplied extracellular deep-orthosteric "
            "outer-pore candidate first: "
            + ", ".join(sorted(mandatory_ids))
            + ". approach_validation is not-performed, so speculative whole-VHH framework/CDR "
            "access cannot demote it below a peripheral or shallow ECL candidate."
        )

    # Ranked Site synthesis owns relative preference, not hard eligibility. In particular, a
    # model-authored not-binding suggestion for the default candidate must not silently remove a
    # different hard-valid candidate from A/B/C. Preserve suggestions only where they cannot
    # conflict with any selectable portfolio member (for example, a verified intracellular
    # transducer-facing candidate that Runtime already blocked).
    selectable_labels = {
        label
        for candidate in candidates.values()
        if runtime_block(candidate) is None
        for label in candidate["research_hypothesis"]["hotspot_label_seq_ids"]
    }
    excluded = sorted(proposed_exclusions - selectable_labels)
    entries: list[SitePortfolioEntry] = []
    ranked_count = 0
    preference_group = 0
    for interpretation in decision.candidates:
        candidate = candidates[interpretation.candidate_id]
        original = candidate["research_hypothesis"]
        block = runtime_block(candidate)
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
        scope=(
            "mechanistic"
            if any(question.get("query_ids") for question in dossier["decision_questions"])
            else "structural-exploration"
        ),
        avoid_label_seq_ids=excluded,
    )
