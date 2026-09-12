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
from .evidence_research import TOPICS, EvidenceResearch, ResearchTopic
from .phase2 import SITE_EVIDENCE, Phase2Bridge
from .session_store import compact, identity
from .site_contracts import SiteIntent, SiteSelection
from .site_evidence import summarize_site_facts


class SiteResearchHandoff(StrictDTO):
    """Candidate questions and notes are research opinions, never hard facts or approval."""

    candidates: list[SiteSelection] = Field(min_length=1, max_length=3)
    material_questions: list[ResearchTopic] = Field(
        default_factory=list,
        max_length=len(TOPICS),
        description="Material topics actually queried in this research stage, using the exact "
        "topic names from research_evidence. Put still-unsearched questions in "
        "unresolved_questions; never relabel them as researched.",
    )
    research_notes: list[ShortText] = Field(default_factory=list, max_length=6)
    unresolved_questions: list[ShortText] = Field(min_length=1, max_length=6)


def site_dossier(bridge: Phase2Bridge, handoff: SiteResearchHandoff) -> dict[str, Any]:
    """Rehydrate exact evidence, never summarize model/tool history or select by sentiment."""
    overview = bridge.read_site_evidence()
    binding = EvidenceBinding.model_validate({k: overview[k] for k in EvidenceBinding.model_fields})
    if SITE_EVIDENCE.get() != binding:
        raise AgentBoundaryError("Site dossier lacks its runtime-delegated Target binding")
    target, facts, facts_ref = bridge.site_facts()
    research = EvidenceResearch(bridge).snapshot()
    missing = [
        topic for topic in handoff.material_questions if research["topics"][topic] == "NOT_SEARCHED"
    ]
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
    if missing or unknown_citations:
        raise ResearchConclusionMismatch(
            "Research handoff evidence mismatch: "
            + compact(
                {
                    "unsearched_material_topics": missing,
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
    candidates = []
    residue_facts = {}
    for candidate in handoff.candidates:
        if candidate.origin == "literature-derived" and not candidate.evidence_card_ids:
            raise ResearchConclusionMismatch("Literature-derived candidates need focused citations")
        labels = candidate.hotspot_label_seq_ids
        evaluation = bridge.evaluate_candidate(candidate_query(labels))
        if evaluation["status"] == "BLOCKED":
            raise ResearchConclusionMismatch(
                "Research candidate is hard-invalid: " + compact(evaluation)
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
                "source_refs": card["source_refs"],
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
                "remains in source_refs.",
            }
        )
    return {
        "kind": "site-evidence-dossier-v2",
        "project_id": bridge.project_id,
        "owner_thread": bridge.thread,
        "target_binding": target["binding"],
        "evidence_binding": binding.model_dump(mode="json"),
        "facts_ref": facts_ref,
        "approved_target": overview["approved_target"],
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
        "candidate_comparison": candidates,
        "trusted_residue_facts": [residue_facts[key] for key in sorted(residue_facts)],
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
                    "source_refs",
                )
                if key in c
            }
            for c in cards.values()
            if c.get("corpus_ref")
        ],
        "research_opinions": handoff.model_dump(mode="json", exclude={"candidates"}),
        "authority": "Runtime rehydrated original verified artifacts and deterministic facts. "
        "Research notes and candidate preferences are unaccepted model opinions. All focused "
        "passages and all search/access outcomes are included without ranking by support. "
        "Exact passage text and scientific qualifiers are unchanged; repeated cache, selection "
        "and source-reference metadata remain in the verified durable research artifacts. "
        "Candidate hypotheses use the common trusted_residue_facts table by existing design "
        "label; repeating a label does not create independent evidence. "
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
    available = {row["mapping"]["label_seq_id"] for row in dossier["trusted_residue_facts"]}
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
