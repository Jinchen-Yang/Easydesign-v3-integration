"""A derived scientific evidence boundary, using the existing project artifact store."""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import Field

from .contracts import (
    AgentBoundaryError,
    EvidenceBinding,
    EvidenceCitationMismatch,
    ResearchConclusionMismatch,
    ShortText,
    StrictDTO,
)
from .evidence_output import site_page_projection
from .evidence_research import EvidenceResearch, ResearchAssessment
from .phase2 import SITE_EVIDENCE, Phase2Bridge
from .session_store import compact, identity
from .site_contracts import SiteIntent, SiteSelection
from .site_evidence import summarize_site_facts


def explicit_site_compartment(goal: str) -> str | None:
    """Read only an explicit delivery/site constraint from the immutable user objective."""
    value = goal.casefold()
    binder = r"(?:vhh|nanobod(?:y|ies)|antibod(?:y|ies)|binder|纳米抗体|抗体|结合剂|设计)"
    extracellular = any(
        re.search(pattern, value, re.IGNORECASE)
        for pattern in (
            rf"(?:胞外|细胞外).{{0,24}}{binder}",
            rf"{binder}.{{0,24}}(?:胞外|细胞外)",
            rf"extracellular.{{0,60}}{binder}",
            rf"{binder}.{{0,60}}extracellular",
            r"required[_ -]?site[_ -]?compartment\s*[:=]\s*extracellular",
        )
    )
    intracellular = any(
        re.search(pattern, value, re.IGNORECASE)
        for pattern in (
            rf"(?:胞内|细胞内).{{0,24}}{binder}",
            rf"{binder}.{{0,24}}(?:胞内|细胞内)",
            rf"intracellular.{{0,60}}{binder}",
            rf"{binder}.{{0,60}}intracellular",
            r"required[_ -]?site[_ -]?compartment\s*[:=]\s*intracellular",
        )
    )
    if extracellular == intracellular:
        return None
    return "extracellular" if extracellular else "intracellular"


class DecisionEvidenceQuestion(ResearchAssessment):
    """A Gate-specific question and fallible assessment, not another planner or agent."""

    question: ShortText
    decision_impact: ShortText = Field(
        description="Current finding and how it changes candidate ranking, a hard constraint "
        "or major risk. State consequential unresolved limits; uncertainty is a valid result."
    )


class SiteResearchHandoff(StrictDTO):
    """Bounded decision evidence and stopping rationale; never scientific approval."""

    candidates: list[SiteSelection] = Field(
        min_length=1,
        max_length=3,
        description="Order a few mapped hypotheses by provisional preference for the user's "
        "objective and delivery constraints. Kernel names/scores do not choose the primary. "
        "An inaccessible or adverse-effect hypothesis can be an avoid/unresolved comparison.",
    )
    decision_questions: list[DecisionEvidenceQuestion] = Field(
        default_factory=list,
        max_length=6,
        description="Usually 3-6 questions derived from the biological objective, approved "
        "Target and Gate 2. Include investigated access, mechanism, candidate differences "
        "and consequential constraints; not all taxonomy topics. When Runtime issued no "
        "research query, consequential questions may remain typed with query_ids=[], status "
        "NOT_SEARCHED or UNRESOLVED, and evidence=[]; that remains structural exploration. "
        "Otherwise bind actual queries and passages.",
    )
    contradiction_search_query_ids: list[str] = Field(
        default_factory=list,
        max_length=3,
        description="Exact query_id of the targeted literature search challenging the "
        "initial ranking or testing a meaningful alternative. Record an actual search, "
        "not a named-paper acquisition. When bounded research ends before any literature "
        "search, leave this empty and retain that gap in stopping_reason and uncertainties.",
    )
    stopping_reason: ShortText = Field(
        description="Why further Standard Research is unlikely to change the Gate 2 ranking, "
        "hard constraints or main risks. State whether a contradiction/alternative search "
        "was completed or remains an explicit evidence gap. Also state "
        "whether ranking changed, remaining uncertainties and the next discriminating test. "
        "An unresolved question does not require endless searching or justify approval. "
        "Use 2-4 short sentences, at most 1500 characters; do not repeat the candidate inventory.",
    )
    research_notes: list[ShortText] = Field(default_factory=list, max_length=4)
    unresolved_questions: list[ShortText] = Field(min_length=1, max_length=6)


def candidate_membrane_facts(
    mappings: list[dict[str, Any]], analyses: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Join existing kernel geometry by exact deposited identity, never design-label arithmetic."""
    result = []
    for analysis in analyses:
        regions = analysis["residue_regions"]
        for mapping in mappings:
            for region in regions:
                source = region["residue"]
                if (
                    source["auth_asym_id"] != mapping["source_author_chain_id"]
                    or str(source["auth_seq_id"]) != mapping["source_author_residue_id"]
                    or (source.get("insertion_code") or "") != (mapping.get("insertion_code") or "")
                    or str(source["model_id"]) not in mapping["model_presence"]
                    or source["hetero_flag"] != "ATOM"
                ):
                    continue
                result.append(
                    {
                        "canonical_position": mapping["canonical_position"],
                        "source_model": str(source["model_id"]),
                        "kernel_card_id": analysis["card_id"],
                        **{
                            key: region[key]
                            for key in (
                                "region",
                                "protein_segment",
                                "axial_distance",
                                "radial_distance",
                                "pore_lining",
                            )
                        },
                    }
                )
    return result


def site_dossier(bridge: Phase2Bridge, handoff: SiteResearchHandoff) -> dict[str, Any]:
    """Rehydrate exact evidence, never summarize model/tool history or select by sentiment."""
    overview = bridge.read_site_evidence()
    binding = EvidenceBinding.model_validate({k: overview[k] for k in EvidenceBinding.model_fields})
    if SITE_EVIDENCE.get() != binding:
        raise AgentBoundaryError("Site dossier lacks its runtime-delegated Target binding")
    target, facts, facts_ref = bridge.site_facts()
    owner = bridge.store.db.execute(
        "SELECT goal FROM threads WHERE id=?", (bridge.thread,)
    ).fetchone()
    # Historical/synthetic callers may construct the scientific dossier directly without a
    # Harness thread. They receive no inferred compartment requirement. Product runs always
    # create the immutable thread goal before reaching this boundary.
    objective = str(owner["goal"]) if owner is not None else ""
    required_compartment = explicit_site_compartment(objective)
    research = EvidenceResearch(bridge).snapshot()
    cards = {c["card_id"]: c for q in research["queries"] for c in q["cards"]}
    all_passages = [c for key, c in cards.items() if key.startswith("passage-")]
    passage_ids = {c["card_id"] for c in all_passages}
    cited = {use.card_id for q in handoff.decision_questions for use in q.evidence}
    cited.update(key for candidate in handoff.candidates for key in candidate.evidence_card_ids)
    # Decision-bound official passages plus read primary publication passages.
    # Retain the latter independently of sentiment/citation selection, so an
    # unmentioned opposing experiment cannot disappear. Database pagination and
    # full acquisition records stay in the verified corpus, not this working set.
    passages = [
        c
        for c in all_passages
        if c["card_id"] in cited
        or c.get("provider", "").lower() == "uniprot"
        or (
            c.get("provider", "").replace(" ", "").lower() == "europepmc"
            and c.get("primary_eligible")
        )
    ]
    # Existing Site validation permits verified kernel cards as computational
    # evidence. They remain non-primary and cannot stand in for a publication.
    citable_ids = passage_ids | {
        c["card_id"] for c in cards.values() if c["provider"] == "EasyDesign GPCR kernel"
    }
    unknown_citations = {
        key for c in handoff.candidates for key in c.evidence_card_ids if key not in citable_ids
    }
    if unknown_citations:
        raise ResearchConclusionMismatch(
            "Research handoff evidence mismatch: "
            + compact(
                {
                    "actually_queried_topics": [
                        key
                        for key, status in research["topics"].items()
                        if status != "NOT_SEARCHED"
                    ],
                    "unknown_or_acquisition_citations": sorted(unknown_citations),
                    "citable_passage_or_kernel_card_ids": sorted(citable_ids),
                    "instruction": "Keep unsearched questions explicitly unresolved. Cite only "
                    "supplied passages or verified kernel context; kernel cards are not primary "
                    "literature. This handoff is not scientific acceptance.",
                }
            )
        )
    if research["queries"] and not handoff.decision_questions:
        raise ResearchConclusionMismatch(
            "Research needs a few decision-critical questions and a stopping reason; "
            "do not enumerate every taxonomy topic."
        )
    searches = {
        q["query_id"]: q
        for q in research["queries"]
        if q.get("query", {}).get("operation") == "literature-search"
    }
    contradiction_ids = set(handoff.contradiction_search_query_ids)
    if not searches and contradiction_ids:
        raise ResearchConclusionMismatch(
            "No literature-search query was executed, so no contradiction search ID can be "
            "claimed. Use contradiction_search_query_ids=[]; keep decision_questions bound "
            "to their actual acquisition/read query IDs and record the missing contradiction "
            "search in stopping_reason and unresolved_questions. Acquisition is not discovery."
        )
    if contradiction_ids and not contradiction_ids.issubset(searches):
        raise ResearchConclusionMismatch(
            "Every claimed contradiction/alternative search must be an actual literature-search "
            "query_id. Acquisition is not discovery. Available search IDs: "
            + compact(sorted(searches))
        )
    EvidenceResearch(bridge).validate_questions(list(handoff.decision_questions))
    memberships = [
        tuple(sorted(candidate.hotspot_label_seq_ids)) for candidate in handoff.candidates
    ]
    if len(memberships) != len(set(memberships)):
        raise ResearchConclusionMismatch(
            "Duplicate physical candidate membership; compare distinct sites"
        )
    candidates: list[dict[str, Any]] = []
    residue_facts = {}
    for candidate in handoff.candidates:
        if candidate.origin == "literature-derived" and not candidate.evidence_card_ids:
            raise ResearchConclusionMismatch("Literature-derived candidates need focused citations")
        labels = candidate.hotspot_label_seq_ids
        evaluation = bridge.evaluate_candidate(candidate_query(labels))
        observed = {
            row["residue"]["label_seq_id"] for row in facts["derived_metrics"]["sasa"]["residues"]
        }
        known_labels = [label for label in labels if label in observed]
        rows = [
            row
            for offset in range(0, len(known_labels), 12)
            for row in summarize_site_facts(facts, labels=known_labels, offset=offset)["facts"]
        ]
        for row in rows:
            residue_facts[row["mapping"]["label_seq_id"]] = row
        candidates.append(
            {
                "candidate_id": "site-"
                + identity(
                    {
                        "target_binding": target["binding"],
                        "labels": sorted(labels),
                    }
                )[:16],
                "research_hypothesis": candidate.model_dump(mode="json"),
                "deterministic_evaluation": evaluation,
            }
        )
    receptor = []
    membrane_analyses = []
    topology_by_canonical: dict[int, Any] = {}
    for card in cards.values():
        if card["provider"] != "EasyDesign GPCR kernel":
            continue
        value = json.loads(card["passage"])
        hard_facts = target["evidence"]["hard_facts"]
        analysis_refs = {
            ref["sha256"]: ref
            for ref in card["source_refs"]
            if ref["artifact_id"] == "research-receptor-analysis"
        }
        if len(analysis_refs) > 1:
            raise AgentBoundaryError("Receptor evidence binds conflicting kernel analyses")
        if analysis_refs:
            analysis = bridge.document(next(iter(analysis_refs.values())))
            if analysis["approved_design_mapping"]["target_binding"] != target["binding"]:
                raise AgentBoundaryError("Receptor geometry belongs to a different approved Target")
            membrane_analyses.append(
                {"card_id": card["card_id"], "residue_regions": analysis["residue_regions"]}
            )
        if value["identity"].get("accession") == hard_facts.get("canonical_accession") and value[
            "identity"
        ].get("receptor_chain") == hard_facts.get("selected_chain"):
            topology_by_canonical.update(
                {
                    row["gpcrdb_sequence_number"]: row
                    for row in value["topology"]["residues"]
                    if row.get("gpcrdb_sequence_number") is not None
                }
            )
        receptor.append(
            {
                "card_id": card["card_id"],
                "evidence_level": card["evidence_level"],
                "primary_eligible": card["primary_eligible"],
                **{
                    key: value[key]
                    for key in ("identity", "state", "membrane", "warnings", "avoid")
                },
                "complex_interfaces": {
                    **{key: val for key, val in value["chain_graph"].items() if key != "edges"},
                    "edges": [
                        {key: val for key, val in edge.items() if key != "contacts"}
                        for edge in value["chain_graph"]["edges"]
                    ],
                    "scope": "Exact chain/interface aggregate facts. Individual contact pairs "
                    "remain in the kernel artifact; their omission is not absence.",
                },
                "topology_qualifications": {
                    key: val
                    for key, val in value["topology"].items()
                    if key not in {"residues", "unmapped_residues"}
                },
                "scope": "State/geometry context from original kernel; candidate labels use "
                "the approved Target mapping above. Full per-residue receptor analysis "
                "remains in the original verified kernel artifact.",
            }
        )
    from .site_authority import reference_annotations, sequence_topology

    annotations = reference_annotations(bridge, research, overview["approved_target"])
    for runtime_candidate in candidates:
        mappings = [
            residue_facts[label]["mapping"]
            for label in runtime_candidate["research_hypothesis"]["hotspot_label_seq_ids"]
            if label in residue_facts
        ]
        positions = [row["canonical_position"] for row in mappings]
        runtime_candidate["location"] = {
            "canonical_positions": positions,
            "sequence_topology": sequence_topology(positions, annotations),
            "segments": list(
                dict.fromkeys(
                    topology_by_canonical.get(position, {}).get("segment", "unresolved")
                    for position in positions
                )
            ),
            "source": "Approved Target correspondence joined to the same-receptor/chain "
            "kernel topology; unknowns retained.",
            "membrane_geometry": candidate_membrane_facts(mappings, membrane_analyses),
            "geometry_scope": "Copied existing kernel region/axial/radial facts for exact source "
            "chain, author residue, insertion code and model in the approved mapping. Empty means "
            "not supplied. Topology segment annotations, signed spatial region and whole-VHH "
            "approach are different: an extracellular TM surface is possible, and point geometry "
            "does not establish framework/CDR clearance. Do not recalculate geometry from "
            "centroids.",
        }
        from .site_decision import verified_location_conflict

        conflict = verified_location_conflict(
            runtime_candidate["location"], required_compartment
        )
        runtime_candidate["runtime_eligibility"] = {
            "status": "BLOCKED" if conflict else "ELIGIBLE",
            "cause": conflict,
            "required_site_compartment": required_compartment,
            "authority": "Immutable user objective plus verified canonical topology, GPCRdb "
            "segments and/or signed kernel membrane geometry. Exposure and scientific risk do "
            "not determine eligibility.",
        }
    return {
        "kind": "site-evidence-dossier-v7",
        "reference_annotations": annotations,
        "residue_constraints": [
            {
                "residue_id": "residue-"
                + identity({"target": target["binding"], "label": label})[:16],
                "design_label": label,
                "canonical_position": row["mapping"]["canonical_position"],
                "canonical_residue": row["mapping"]["canonical_residue"],
            }
            for label, row in sorted(residue_facts.items())
        ],
        "approach_validation": {
            "status": "not-performed",
            "scientific_status": "UNRESOLVED",
            "scope": "Existing prepared-target evaluation supplies point exposure/geometry. "
            "It does not perform whole-VHH CDR/framework docking or steric clearance. "
            "These metrics support relative access concerns, not categorical impossibility "
            "or feasibility. Independent physical/experimental constraints retain their scope.",
        },
        "project_id": bridge.project_id,
        "owner_thread": bridge.thread,
        "target_binding": target["binding"],
        "evidence_binding": binding.model_dump(mode="json"),
        "facts_ref": facts_ref,
        "approved_target": overview["approved_target"],
        "runtime_status": {
            "target_gate": "resolved",
            "target_run_id": bridge.target_run_id(),
            "authority": "The runtime verified target_state before creating this dossier: "
            "Target preparation succeeded and Gate 1 has no pending request. Conditional "
            "mapping and source limitations remain scientific constraints; fallible research "
            "notes cannot reopen Gate 1 or create Site approval.",
        },
        "objective_requirements": {
            "required_site_compartment": required_compartment,
            "source": "immutable-user-objective",
            "scope": "Only an explicit extracellular/intracellular binder objective becomes a "
            "hard compartment constraint. Ambiguous wording remains unresolved.",
        },
        "scientific_context": {
            key: overview[key]
            for key in (
                "biology",
                "biology_authority",
                "membrane_geometry",
                "geometry_warnings",
                "limitations",
                "sequence_motifs",
            )
        },
        "decision_questions": [q.model_dump(mode="json") for q in handoff.decision_questions],
        "evidence_selection": {
            "read_focused_passages": len(all_passages),
            "decision_passages": len(passages),
            "literature_searches_available": len(searches),
            "contradiction_search_performed": bool(contradiction_ids),
            "contradiction_search_gap": (
                "No targeted contradiction/alternative literature search was completed; "
                "the specialist retained this as an unresolved evidence gap."
                if research["queries"] and not contradiction_ids
                else None
            ),
            "policy": "Decision-cited official evidence plus read primary publication passages, "
            "including uncited opposition. No sentiment filtering. All other exact source "
            "records remain in the durable Evidence Store.",
        },
        "candidate_comparison": candidates,
        "trusted_residue_facts": site_page_projection(
            {"facts": [residue_facts[key] for key in sorted(residue_facts)]}
        )
        if residue_facts
        else {
            "facts_table": {
                "mapping_columns": list(facts["observed_facts"]["mapping"][0]),
                "metric_columns": [
                    "raw_sasa",
                    "rsasa",
                    "model_presence_fraction",
                    "surface_eligible",
                    "declared_topology",
                ],
                "rows": [],
                "row_count": 0,
            }
        },
        "receptor_context": receptor,
        "focused_passages": [
            {
                **{
                    key: value
                    for key, value in card.items()
                    if key
                    not in {
                        "binding_context",
                        "cache_status",
                        "project_evidence_id",
                        "retrieved_at",
                        "selection_provenance",
                        "source_refs",
                    }
                },
                **(
                    {
                        "binding_context": {
                            key: value
                            for key, value in card["binding_context"].items()
                            if key not in {"acquired_binding", "current_binding"}
                        }
                    }
                    if card.get("binding_context")
                    else {}
                ),
            }
            for card in passages
        ],
        "research_outcomes": [
            {
                key: q[key]
                for key in ("query_id", "topic", "question", "query", "status", "errors")
                if key in q
            }
            for q in research["queries"]
        ],
        "source_inventory": [
            {
                key: c[key]
                for key in (
                    "card_id",
                    "provider",
                    "identifier",
                    "evidence_level",
                    "primary_eligible",
                    "does_not_support",
                )
                if key in c
            }
            for c in cards.values()
            if c.get("corpus_ref")
        ],
        "research_opinions": handoff.model_dump(
            mode="json", exclude={"candidates", "decision_questions"}
        ),
        "authority": "Runtime rehydrated original verified artifacts and deterministic facts. "
        "Decision assessments, stopping rationale and candidate preferences are unaccepted model "
        "opinions for independent review. Questions express decision scope, not a completeness "
        "checklist; unresolved evidence can suffice for a qualified next step. Decision-bound "
        "official passages and read primary publication passages are included without ranking "
        "by support; other source pages remain durable. All search/access outcomes remain. "
        "Exact passage text and scientific qualifiers are unchanged; repeated cache, selection "
        "and source-reference metadata remain in the verified durable research artifacts. "
        "Candidate hypotheses use the common trusted_residue_facts table by existing design "
        "label; table values follow mapping_columns then metric_columns, with nulls and "
        "qualifications preserved. Original-structure source identifiers and receptor canonical "
        "positions are separate namespaces from these design labels. Repeating a label does "
        "not create independent evidence. "
        "Source retrieval status is not scientific entailment. Missing evidence stays "
        "unresolved. No approval is created.",
    }


def candidate_query(labels: list[int]) -> Any:
    from .site_contracts import SiteQuery

    return SiteQuery(label_seq_ids=labels)


def persist_dossier(
    bridge: Phase2Bridge, handoff: SiteResearchHandoff, execution_id: str
) -> dict[str, Any]:
    dossier = site_dossier(bridge, handoff)
    ref = bridge.persist("site-evidence-dossier", dossier)
    bridge.store.event(
        bridge.thread,
        "site-evidence-dossier",
        {
            "execution_id": execution_id,
            "target_binding": dossier["target_binding"],
            "dossier_id": identity(dossier),
            "ref": ref,
            "chars": len(compact(dossier)),
            "passage_count": len(dossier["focused_passages"]),
        },
    )
    result = bridge.document(ref)
    assert isinstance(result, dict)
    return result


def validate_dossier_intent(bridge: Phase2Bridge, intent: SiteIntent, execution_id: str) -> None:
    event = bridge.thread_latest("site-evidence-dossier")
    if event is None or event["execution_id"] != execution_id:
        raise AgentBoundaryError("Site synthesis requires its current execution dossier")
    dossier = bridge.document(event["ref"])
    if dossier["target_binding"] != bridge.target_state()["binding"]:
        raise AgentBoundaryError("Site synthesis dossier has a stale Target binding")
    facts = dossier["trusted_residue_facts"]
    if "facts_table" in facts:
        table = facts["facts_table"]
        label_column = table["mapping_columns"].index("label_seq_id")
        available = {row[label_column] for row in table["rows"]}
    else:
        raise AgentBoundaryError("Current Site dossier requires its runtime fact table")
    selections = (
        [entry.site for entry in intent.portfolio if entry.selectable]
        if intent.portfolio is not None
        else [intent.selected_site, *intent.alternatives]
    )
    selected = {label for candidate in selections for label in candidate.hotspot_label_seq_ids}
    if not selected.issubset(available):
        raise ResearchConclusionMismatch(
            "Synthesis may use only design labels with trusted facts in its dossier: "
            + compact(sorted(available))
        )
    cited = {
        card
        for candidate in [intent.selected_site, *intent.alternatives]
        for card in candidate.evidence_card_ids
    }
    citable = {
        card["card_id"] for card in [*dossier["focused_passages"], *dossier["receptor_context"]]
    }
    if not cited.issubset(citable):
        raise EvidenceCitationMismatch(
            "Cite exact passages or kernel context supplied in this dossier"
        )
