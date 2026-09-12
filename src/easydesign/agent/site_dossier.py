"""A derived scientific evidence boundary, using the existing project artifact store."""

from __future__ import annotations

import json
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
from .evidence_research import EvidenceResearch, ResearchConclusion
from .phase2 import SITE_EVIDENCE, Phase2Bridge
from .session_store import compact, identity
from .site_contracts import SiteIntent, SiteSelection
from .site_evidence import summarize_site_facts


class DecisionEvidenceQuestion(ResearchConclusion):
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
        "and consequential constraints; not all taxonomy topics. Empty only for purely "
        "structural exploration with no external research. Bind actual queries and passages.",
    )
    contradiction_search_query_ids: list[str] = Field(
        default_factory=list,
        max_length=3,
        description="Exact query_id of the targeted literature search challenging the "
        "initial ranking or testing a meaningful alternative. Record an actual search, "
        "not a named-paper acquisition. Required when decision_questions are present.",
    )
    stopping_reason: ShortText = Field(
        description="Why further Standard Research is unlikely to change the Gate 2 ranking, "
        "hard constraints or main risks after the contradiction/alternative check. State "
        "whether ranking changed, remaining uncertainties and the next discriminating test. "
        "An unresolved question does not require endless searching or justify approval. "
        "Use 2-4 short sentences, at most 1500 characters; do not repeat the candidate inventory.",
    )
    research_notes: list[ShortText] = Field(default_factory=list, max_length=4)
    unresolved_questions: list[ShortText] = Field(min_length=1, max_length=6)


def site_dossier(bridge: Phase2Bridge, handoff: SiteResearchHandoff) -> dict[str, Any]:
    """Rehydrate exact evidence, never summarize model/tool history or select by sentiment."""
    overview = bridge.read_site_evidence()
    binding = EvidenceBinding.model_validate({k: overview[k] for k in EvidenceBinding.model_fields})
    if SITE_EVIDENCE.get() != binding:
        raise AgentBoundaryError("Site dossier lacks its runtime-delegated Target binding")
    target, facts, facts_ref = bridge.site_facts()
    research = EvidenceResearch(bridge).snapshot()
    cards = {c["card_id"]: c for q in research["queries"] for c in q["cards"]}
    # Include ALL focused passages, including counterevidence, irrespective of the
    # researcher's candidate choices. Acquisition bodies remain in the corpus.
    passages = [c for key, c in cards.items() if key.startswith("passage-")]
    passage_ids = {c["card_id"] for c in passages}
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
    if (handoff.decision_questions and not handoff.contradiction_search_query_ids) or not set(
        handoff.contradiction_search_query_ids
    ).issubset(searches):
        raise ResearchConclusionMismatch(
            "Bind an actual targeted contradiction/alternative literature search query_id. "
            "Acquisition is not discovery. Available search IDs: " + compact(sorted(searches))
        )
    EvidenceResearch(bridge).validate_conclusions(list(handoff.decision_questions))
    candidates = []
    residue_facts = {}
    for candidate in handoff.candidates:
        if candidate.origin == "literature-derived" and not candidate.evidence_card_ids:
            raise ResearchConclusionMismatch("Literature-derived candidates need focused citations")
        labels = candidate.hotspot_label_seq_ids
        evaluation = bridge.evaluate_candidate(candidate_query(labels))
        if evaluation["status"] == "BLOCKED":
            observed = {
                row["residue"]["label_seq_id"]
                for row in facts["derived_metrics"]["sasa"]["residues"]
            }
            raise ResearchConclusionMismatch(
                "Research candidate is hard-invalid: "
                + compact(
                    {
                        "candidate": candidate.name,
                        "submitted_design_labels": labels,
                        "unobserved_or_unmapped_labels": sorted(set(labels) - observed),
                        "evaluation": evaluation,
                        "instruction": "Correct this candidate using the approved mapping. "
                        "Do not shift other candidates or infer a global numbering offset. "
                        "Kernel canonical/source positions are not design labels.",
                    }
                )
            )
        rows = [
            row
            for offset in range(0, len(labels), 12)
            for row in summarize_site_facts(facts, labels=labels, offset=offset)["facts"]
        ]
        for row in rows:
            residue_facts[row["mapping"]["label_seq_id"]] = row
        candidates.append(
            {
                "research_hypothesis": candidate.model_dump(mode="json"),
                "deterministic_evaluation": evaluation,
            }
        )
    receptor = []
    for card in cards.values():
        if card["provider"] != "EasyDesign GPCR kernel":
            continue
        value = json.loads(card["passage"])
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
    return {
        "kind": "site-evidence-dossier-v4",
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
        "candidate_comparison": candidates,
        "trusted_residue_facts": site_page_projection(
            {"facts": [residue_facts[key] for key in sorted(residue_facts)]}
        ),
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
        "checklist; unresolved evidence can suffice for a qualified next step. All focused "
        "passages and all search/access outcomes are included without ranking by support. "
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
    critical_topics = {q["topic"] for q in dossier["decision_questions"]}
    if not critical_topics.issubset(intent.material_questions):
        raise ResearchConclusionMismatch(
            "SiteIntent must address the dossier's decision-critical questions (including "
            "unresolved/contradictory findings), without adding unrelated taxonomy tasks: "
            + compact(sorted(critical_topics))
        )
    facts = dossier["trusted_residue_facts"]
    if "facts_table" in facts:
        table = facts["facts_table"]
        label_column = table["mapping_columns"].index("label_seq_id")
        available = {row[label_column] for row in table["rows"]}
    else:
        available = {row["mapping"]["label_seq_id"] for row in facts["facts"]}
    selected = {
        label
        for candidate in [intent.selected_site, *intent.alternatives]
        for label in candidate.hotspot_label_seq_ids
    }
    if not selected.issubset(available):
        raise ResearchConclusionMismatch(
            "Synthesis may use only design labels with trusted facts in its dossier: "
            + compact(sorted(available))
        )
    cited = {
        use.card_id for conclusion in intent.research_conclusions for use in conclusion.evidence
    }
    cited.update(
        card
        for candidate in [intent.selected_site, *intent.alternatives]
        for card in candidate.evidence_card_ids
    )
    citable = {
        card["card_id"] for card in [*dossier["focused_passages"], *dossier["receptor_context"]]
    }
    if not cited.issubset(citable):
        raise EvidenceCitationMismatch(
            "Cite exact passages or kernel context supplied in this dossier"
        )
