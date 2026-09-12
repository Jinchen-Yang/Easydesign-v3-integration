"""Bounded source acquisition for scientific owners, on the existing HTTP/artifact stack.

This worker verifies source records, not biological entailment. It cannot approve, choose
hotspots, run compute, browse arbitrary URLs, or change canonical target identity.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse
from xml.etree import ElementTree

from pydantic import Field, model_validator

from easydesign.backends.gpcrdb import GpcrdbAdapter
from easydesign.backends.target_sources.remote import (
    RCSB_SEARCH_URL,
    RetrievedResponse,
    ScientificHttpClient,
    rcsb_entry,
    rcsb_polymer_entity,
    uniprot_accession,
    uniprot_search,
)
from easydesign.backends.target_sources.structure import inventory_structure
from easydesign.core import ArtifactRef, BackendContractError
from easydesign.core.target_identity import resolve_target_identity
from easydesign.stages.s02_hotspot_discovery.gpcr import analyze_structure, generate_candidates

from .contracts import (
    AgentBoundaryError,
    EvidenceCitationMismatch,
    ResearchConclusionMismatch,
    ShortText,
    SourceCardArgumentMismatch,
    StrictDTO,
)
from .evidence_corpus import NEEDS, EvidenceCorpus, SelectEvidence, source_key
from .session_store import compact, confined, identity

EvidenceStatus = Literal[
    "NOT_SEARCHED", "SEARCHED_NO_EVIDENCE", "CONFLICTING_EVIDENCE", "UNRESOLVED", "VERIFIED"
]
ResearchTopic = Literal[
    "identity",
    "structure-complex",
    "mutagenesis",
    "competition",
    "function",
    "epitope",
    "state",
    "ligand-partner",
    "ptm-glycan",
    "conservation",
]
TOPICS: tuple[str, ...] = (
    "identity",
    "structure-complex",
    "mutagenesis",
    "competition",
    "function",
    "epitope",
    "state",
    "ligand-partner",
    "ptm-glycan",
    "conservation",
)
HOSTS = {"www.ebi.ac.uk", "rest.uniprot.org", "search.rcsb.org", "data.rcsb.org", "gpcrdb.org"}
EUROPE_PMC = "https://www.ebi.ac.uk/europepmc/webservices/rest"


class ResearchQuery(StrictDTO):
    topic: ResearchTopic
    question: ShortText
    operation: Literal[
        "literature-search",
        "primary-record",
        "primary-fulltext",
        "uniprot-search",
        "uniprot-record",
        "structure-search",
        "structure-record",
        "gpcrdb-context",
    ]
    selection_reason: ShortText | None = Field(
        default=None,
        description="For record/fulltext acquisition: explicitly SELECT this exact source "
        "for this query topic with a scientific reason, then acquire it in the same call. "
        "Omit only if already selected for this exact topic. Not scientific approval.",
    )
    query: str = Field(
        default="",
        max_length=400,
        description="REQUIRED for any search "
        "operation: explicit database search keywords/syntax. The scientific "
        "question is separate and does not execute a search. Omit for records.",
    )
    identifier: str = Field(
        default="",
        max_length=40,
        pattern=r"^[A-Za-z0-9_.-]*$",
        description="primary-record requires PMID digits; primary-fulltext requires an "
        "actual retrieved PMCID starting PMC (never a PMID); uniprot-record an accession; "
        "structure-record a PDB code; gpcrdb-context the exact receptor entry "
        "(for example adrb2_human), plus optional pdb_id. A PDB code alone is not "
        "a receptor identifier. Search uses query instead.",
    )
    taxon_id: int | None = Field(default=None, ge=1)
    pdb_id: str | None = Field(default=None, pattern=r"^[0-9][A-Za-z0-9]{3}$")

    @model_validator(mode="before")
    @classmethod
    def explicit_structure_alias(cls, value: Any) -> Any:
        if (
            isinstance(value, dict)
            and value.get("operation") == "structure-record"
            and isinstance(value.get("pdb_id"), str)
        ):
            identifier = value.get("identifier")
            if identifier and str(identifier).upper() != value["pdb_id"].upper():
                raise ValueError("identifier and pdb_id refer to different structures")
            return {**value, "identifier": value["pdb_id"].upper()}
        return value

    @model_validator(mode="after")
    def arguments(self) -> ResearchQuery:
        if self.operation.endswith("search") and not self.query.strip():
            raise ValueError("A search requires a bounded explicit query")
        if not self.operation.endswith("search") and not self.identifier:
            raise ValueError("Retrieval requires an explicit source identifier")
        if self.operation == "uniprot-search" and self.taxon_id is None:
            raise ValueError("UniProt search must bind the requested species")
        if self.operation == "primary-record" and not self.identifier.isdigit():
            raise ValueError("Primary record identifier is a PMID")
        if self.operation == "primary-fulltext" and not re.fullmatch(r"PMC[0-9]+", self.identifier):
            raise ValueError("Full text identifier is a PMCID")
        if self.operation == "structure-record" and not re.fullmatch(
            r"[0-9][A-Za-z0-9]{3}", self.identifier
        ):
            raise ValueError("Structure identifier is a PDB code")
        return self


class EvidenceUse(StrictDTO):
    card_id: str = Field(
        min_length=1,
        max_length=80,
        description="Exact focused passage "
        "card_id returned by retrieve_evidence; never a search lead or "
        "research_evidence acquisition card. No invented IDs.",
    )
    excerpt: str = Field(
        min_length=12,
        max_length=700,
        description="Exact short verbatim "
        "substring of that retrieved passage. Do not paraphrase, quote a "
        "title/receipt, or describe unavailable text. Record access limits "
        "in limitations with evidence=[] instead.",
    )
    claim: ShortText
    relation: Literal["supports", "contradicts", "scope-limit"]
    strength: Literal["E1", "E2", "E3", "E4"]
    transfer_limit: ShortText


class ResearchConclusion(StrictDTO):
    topic: ResearchTopic
    status: EvidenceStatus
    evidence: list[EvidenceUse] = Field(default_factory=list, max_length=6)
    limitations: list[ShortText] = Field(min_length=1, max_length=4)


class ReferenceComparison(StrictDTO):
    uniprot_card_id: str = Field(
        min_length=1,
        max_length=80,
        description="Exact source card_id returned by research_evidence uniprot-record; "
        "not a UniProt accession and not a passage card_id.",
    )
    auth_chain: str = Field(min_length=1, max_length=16)


class ReceptorAnalysis(StrictDTO):
    gpcrdb_card_id: str = Field(min_length=1, max_length=80)
    auth_chain: str = Field(min_length=1, max_length=16)


class ResearchHttpClient(ScientificHttpClient):
    """Guard the existing transport; no second cache, downloader or retry engine."""

    def request(self, method: str, url: str, **kwargs: Any) -> RetrievedResponse:
        if urlparse(url).scheme != "https" or urlparse(url).hostname not in HOSTS:
            raise AgentBoundaryError("Research endpoint is outside the source allowlist")
        if method != "GET" and not (method == "POST" and url == RCSB_SEARCH_URL):
            raise AgentBoundaryError("Research permits read-only source queries only")
        if len(self.records) >= 24:
            raise AgentBoundaryError("Bounded research source-request budget exhausted")
        response = super().request(method, url, **kwargs)
        if len(response.content) > 12_000_000:
            raise BackendContractError("Source response exceeds the research document limit")
        return response


def _text(value: str) -> str:
    # Abstracts/full text may contain XML tags. This is text projection, not an HTML browser.
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", value)).strip()


def _uniprot_view(record: dict[str, Any], topic: str) -> dict[str, Any]:
    feature_types = {
        "identity": {"Signal", "Propeptide", "Chain", "Domain", "Region"},
        "ptm-glycan": {"Glycosylation", "Modified residue", "Lipidation", "Disulfide bond"},
        "mutagenesis": {"Mutagenesis", "Natural variant"},
        "state": {"Transmembrane", "Topological domain", "Binding site", "Region"},
        "epitope": {"Mutagenesis", "Binding site", "Active site", "Site"},
    }
    features = [
        f
        for f in record.get("features", [])
        if f.get("type")
        in feature_types.get(topic, {"Binding site", "Active site", "Site", "Domain"})
    ]
    comments = [
        c
        for c in record.get("comments", [])
        if c.get("commentType")
        in {
            "FUNCTION",
            "SUBUNIT",
            "COFACTOR",
            "ACTIVITY REGULATION",
            "SUBCELLULAR LOCATION",
            "PTM",
            "CATALYTIC ACTIVITY",
            "SIMILARITY",
        }
    ]
    return {
        "accession": record["primaryAccession"],
        "entry": record.get("uniProtkbId"),
        "organism": record.get("organism"),
        "protein": record.get("proteinDescription"),
        "sequence": record.get("sequence"),
        "comments": comments[:12],
        "topic_features": features[:40],
        "matching_feature_count": len(features),
        "omitted_features": max(0, len(features) - 40),
        "scope": (
            "Official annotations retain their original evidence references; "
            "relevance is not inferred."
        ),
    }


def _uniprot_sections(record: dict[str, Any]) -> list[dict[str, str]]:
    """Keep related source identity facts together before the complete field index."""
    sequence = record.get("sequence", {}).get("value")
    identity_section = {
        "accession": record["primaryAccession"],
        "organism": record.get("organism"),
        "protein": record.get("proteinDescription"),
        "source_sequence_length": len(sequence) if isinstance(sequence, str) else None,
        "processing_features": [
            f
            for f in record.get("features", [])
            if f.get("type") in {"Signal", "Propeptide", "Chain"}
        ],
        "numbering_scope": (
            "Positions are source UniProt sequence positions, not structure numbering."
        ),
    }
    return [
        {
            "location": (
                "canonical identity / accession species sequence length / "
                "precursor signal peptide mature chain boundaries"
            ),
            "text": compact(identity_section),
        }
    ] + [
        {"location": key + f"[{i}]", "text": compact(value)}
        for key, values in record.items()
        for i, value in enumerate(values if isinstance(values, list) else [values])
    ]


def _pdb_view(entry: dict[str, Any], polymers: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "pdb_id": entry.get("rcsb_id"),
        "structure": entry.get("struct"),
        "experimental_methods": entry.get("exptl"),
        "primary_citation": entry.get("rcsb_primary_citation"),
        "assembly_ids": entry.get("rcsb_entry_container_identifiers", {}).get("assembly_ids"),
        "nonpolymer_ids": entry.get("rcsb_entry_container_identifiers", {}).get(
            "non_polymer_entity_ids"
        ),
        "polymers": [
            {
                "entity_id": p.get("rcsb_id"),
                "identity": p.get("rcsb_polymer_entity_container_identifiers"),
                "description": p.get("rcsb_polymer_entity"),
                "sequence": p.get("entity_poly", {}).get("pdbx_seq_one_letter_code_can"),
                "source_organism": p.get("rcsb_entity_source_organism"),
            }
            for p in polymers
        ],
    }


def _pdb_sections(view: dict[str, Any]) -> list[dict[str, str]]:
    """Index source entities separately so a passage does not splice different chains."""
    sections = []
    for polymer in view["polymers"]:
        identifiers = polymer.get("identity") or {}
        sections.append(
            {
                "location": "structure polymer entity identity / chain inventory / "
                + str(polymer["entity_id"]),
                "text": compact(
                    {
                        "pdb_id": view["pdb_id"],
                        "entity_id": polymer["entity_id"],
                        "description": (polymer.get("description") or {}).get("pdbx_description"),
                        "auth_asym_ids": identifiers.get("auth_asym_ids"),
                        "asym_ids": identifiers.get("asym_ids"),
                        "reference_sequence_identifiers": identifiers.get(
                            "reference_sequence_identifiers"
                        ),
                        "scope": (
                            "Deposited source identifiers; "
                            "canonical mapping requires the target bundle."
                        ),
                    }
                ),
            }
        )
        for name, value in polymer.items():
            sections.append(
                {"location": f"polymer {polymer['entity_id']} / {name}", "text": compact(value)}
            )
    sections.extend(
        {"location": name, "text": compact(value)}
        for name, value in view.items()
        if name != "polymers"
    )
    return sections


class EvidenceResearch:
    """One synchronous bounded worker, shared by Target and Site typed tools."""

    def __init__(self, bridge: Any) -> None:
        self.bridge = bridge

    def snapshot(self) -> dict[str, Any]:
        binding = identity(self.bridge.binding())
        rows = self.bridge.store.db.execute(
            (
                "SELECT kind,payload FROM events WHERE thread=? AND kind IN ('evidence-res"
                "earch','evidence-view') ORDER BY seq"
            ),
            (self.bridge.thread,),
        )
        latest: dict[str, Any] = {}
        for row in rows:
            event = json.loads(row[1])
            result = self.bridge.document(event["ref"])
            corpus = EvidenceCorpus(self.bridge)
            cards = [
                corpus.source_view(card, event["target_binding"])
                for card in result["cards"]
                if event["target_binding"] == binding
                or (
                    row[0] == "evidence-research"
                    and card.get("corpus_ref")
                    and corpus.current_relation(
                        source_key(card["provider"], card["identifier"]),
                        event["target_binding"],
                        card["source_refs"],
                    )
                    == "current-canonical-reference"
                )
            ]
            if event["target_binding"] == binding or cards:
                result = {**result, "cards": cards, "target_binding": binding}
                latest[result["query_id"]] = result
        results = list(latest.values())
        return {
            "topics": {
                topic: (
                    "NOT_SEARCHED"
                    if not any(r["topic"] == topic for r in results)
                    else "SEARCHED_NO_EVIDENCE"
                    if all(
                        r["status"] == "SEARCHED_NO_EVIDENCE"
                        for r in results
                        if r["topic"] == topic
                    )
                    else "UNRESOLVED"
                )
                for topic in TOPICS
            },
            "queries": results,
            "authority": (
                "Verified source retrieval only; scientific owner and Judge assess "
                "relevance and entailment."
            ),
        }

    def acquire(self, query: ResearchQuery, *, role: str) -> dict[str, Any]:
        if role not in {"target", "site"}:
            raise AgentBoundaryError("Only Target or Site may delegate Evidence Research")
        if not query.operation.endswith("search"):
            provider = {
                "primary-record": "EuropePMC",
                "primary-fulltext": "EuropePMC",
                "uniprot-record": "UniProt",
                "structure-record": "RCSB",
                "gpcrdb-context": "GPCRdb",
            }[query.operation]
            corpus = EvidenceCorpus(self.bridge)
            if query.selection_reason is not None:
                corpus.select(
                    SelectEvidence.model_validate(
                        {
                            "provider": provider,
                            "identifier": query.identifier,
                            "need": NEEDS[query.topic],
                            "selection": "SELECTED",
                            "reason": query.selection_reason,
                        }
                    )
                )
            corpus.require_selected(provider, query.identifier, query.topic)
        bridge = self.bridge
        execution = bridge.store.latest_execution(bridge.thread)
        if execution is None:
            raise AgentBoundaryError("Research requires a persisted agent execution")
        execution_id = execution["execution_id"]
        target_binding = identity(bridge.binding())
        query_id = identity(query.model_dump(mode="json"))
        for previous in self.snapshot()["queries"]:
            if previous["query_id"] == query_id and not previous["errors"]:
                return dict(previous)  # Replay does not refetch or consume network budget.
        # A full verified source is project durable, independent of the question/topic.
        # Selection above is still required. Reuse exact source/corpus bytes, not old claims.
        if not query.operation.endswith("search"):
            candidates = [
                c
                for c in EvidenceCorpus(bridge).documents()
                if c["provider"] == provider and c["identifier"].upper() == query.identifier.upper()
            ]
            if candidates:
                reused = {
                    "query_id": query_id,
                    "topic": query.topic,
                    "question": query.question,
                    "query": query.model_dump(mode="json"),
                    "cards": [candidates[-1]],
                    "errors": [],
                    "status": "UNRESOLVED",
                    "target_binding": target_binding,
                    "source_role": "evidence-research",
                    "reused_verified_source": True,
                }
                ref = bridge.persist("evidence-research", reused)
                bridge.store.event(
                    bridge.thread,
                    "evidence-research",
                    {"target_binding": target_binding, "ref": ref},
                )
                return reused
        used = bridge.store.db.execute(
            "SELECT COUNT(*) FROM events WHERE thread=? AND kind='research-reservation' "
            "AND json_extract(payload,'$.execution_id')=?",
            (bridge.thread, execution_id),
        ).fetchone()[0]
        if used >= 12:
            raise AgentBoundaryError("This execution used its 12 bounded research queries")
        bridge.store.event(
            bridge.thread,
            "research-reservation",
            {"execution_id": execution_id, "query_id": query_id},
        )
        directory = confined(
            bridge.store.root,
            bridge.store.root / "research" / bridge.thread / f"{execution_id}-{used}",
        )
        directory.mkdir(parents=True, exist_ok=False)
        result: dict[str, Any] = {
            "query_id": query_id,
            "topic": query.topic,
            "question": query.question,
            "query": query.model_dump(mode="json"),
            "cards": [],
            "errors": [],
            "status": "UNRESOLVED",
            "source_role": "evidence-research",
            "target_binding": target_binding,
            "limits": [
                "Search results are leads. Source identity is not target/construct equivalence.",
                "Abstract evidence cannot certify quantitative residue or causal claims "
                "absent from the passage.",
            ],
        }
        with self.client(directory) as client:
            try:
                cards = self.retrieve(client, query)
                result["cards"] = [
                    EvidenceCorpus(bridge).index(self.card(client, card, i), query.topic)
                    if not query.operation.endswith("search")
                    else self.card(client, card, i)
                    for i, card in enumerate(cards)
                ]
                result["status"] = "UNRESOLVED" if cards else "SEARCHED_NO_EVIDENCE"
            except (
                BackendContractError,
                ValueError,
                KeyError,
                TypeError,
                ElementTree.ParseError,
            ) as error:
                result["errors"] = [f"{type(error).__name__}: {str(error)[:700]}"]
            result["retrieval_records"] = [r.model_dump(mode="json") for r in client.records]
        ref = bridge.persist("evidence-research", result)
        bridge.store.event(
            bridge.thread, "evidence-research", {"target_binding": target_binding, "ref": ref}
        )
        return result

    def compare_reference(self, request: ReferenceComparison) -> dict[str, Any]:
        """Read-only use of the existing four-layer identity kernel on original source bytes."""
        card = next(
            (
                c
                for q in self.snapshot()["queries"]
                for c in q["cards"]
                if c["card_id"] == request.uniprot_card_id and c["provider"] == "UniProt"
            ),
            None,
        )
        if card is None:
            if re.fullmatch(r"[A-Z][0-9][A-Z0-9]{3,7}[0-9](?:-[0-9]+)?", request.uniprot_card_id):
                raise SourceCardArgumentMismatch(
                    "uniprot_card_id requires the exact source card_id from "
                    "research_evidence(operation='uniprot-record'), not an accession. "
                    "Select/acquire the relevant reference first, then use its returned "
                    "source card_id. No comparison was performed. Reuse existing approved "
                    "mapping facts when they already answer the question."
                )
            raise AgentBoundaryError("Reference must be a retrieved UniProt source card")
        records: list[dict[str, Any]] = []
        for ref in card["source_refs"]:
            data = self.bridge.document(ref)
            records.extend(data.get("results", []) if "results" in data else [data])
        canonical = [r for r in records if r.get("primaryAccession") == card["identifier"]]
        if len(canonical) != 1:
            raise AgentBoundaryError("Canonical source record is not unique")
        loaded = self.bridge.validate_project()
        inventory = inventory_structure(loaded.source_path)
        chains = [c for c in inventory.chains if c.author_chain_id == request.auth_chain]
        if len(chains) != 1:
            raise AgentBoundaryError("Reference comparison requires one exact original auth chain")
        chain = chains[0]
        record = canonical[0]
        report = resolve_target_identity(
            target_id=self.bridge.project_id,
            canonical_sequence=record["sequence"]["value"],
            construct_sequence=chain.deposited_sequence or chain.sequence,
            source_kind="local-structure",
            accession=record["primaryAccession"],
            taxon_id=record["organism"]["taxonId"],
            auth_chain_id=chain.author_chain_id,
            label_chain_id=chain.label_chain_id,
            coordinate_present_construct_positions=chain.coordinate_label_seq_ids
            if chain.deposited_sequence
            else tuple(range(1, len(chain.sequence) + 1)),
        )
        ref = self.bridge.persist("reference-identity-comparison", report.model_dump(mode="json"))
        summary: dict[str, Any] = {
            "auth_chain": chain.author_chain_id,
            "accession": record["primaryAccession"],
            "relationship": str(report.relationship),
            "review_requirement": str(report.review_requirement),
            "mapping_status": str(report.design_scope.mapping_status),
            "canonical_length": report.canonical.sequence_length,
            "construct_length": report.construct_identity.sequence_length,
            "observed_count": len(report.observed.observed_construct_positions),
            "substitutions": len(report.alignment.substitutions) if report.alignment else None,
            "insertions": len(report.alignment.insertions) if report.alignment else None,
            "deletions": len(report.alignment.deletions) if report.alignment else None,
            "ambiguities": list(report.ambiguities),
            "limits": [
                "Read-only reference comparison; does not approve canonical identity "
                "or alter Target Bundle.",
                "Declared canonical source species does not independently prove construct species.",
                "State and physiological assembly require separate evidence.",
            ],
        }
        if chain.deposited_sequence is None:
            summary["limits"].append(
                "Full deposited construct unavailable; comparison uses observed sequence only."
            )
        card_id = "identity-" + identity({"ref": ref, "target": self.bridge.binding()})[:24]
        result = {
            "query_id": card_id,
            "topic": "identity",
            "question": "Compare original construct to retrieved canonical reference",
            "status": "UNRESOLVED",
            "errors": [],
            "target_binding": identity(self.bridge.binding()),
            "cards": [
                {
                    "card_id": card_id,
                    "provider": "EasyDesign identity kernel",
                    "identifier": record["primaryAccession"],
                    "primary_eligible": False,
                    "evidence_level": "deterministic-reference-comparison",
                    "passage": json.dumps(summary),
                    "source_verified": True,
                    "source_refs": [*card["source_refs"], ref],
                    "does_not_support": ["Approval of a canonical target or state"],
                }
            ],
        }
        result_ref = self.bridge.persist("evidence-research", result)
        self.bridge.store.event(
            self.bridge.thread,
            "evidence-research",
            {"target_binding": identity(self.bridge.binding()), "ref": result_ref},
        )
        return {**summary, "card_id": card_id}

    def analyze_receptor(self, request: ReceptorAnalysis) -> dict[str, Any]:
        card = next(
            (
                c
                for q in self.snapshot()["queries"]
                for c in q["cards"]
                if c["card_id"] == request.gpcrdb_card_id and c["provider"] == "GPCRdb"
            ),
            None,
        )
        if card is None or not card.get("context_ref"):
            raise AgentBoundaryError(
                "Receptor analysis requires a complete verified GPCRdb context card"
            )
        context = self.bridge.document(card["context_ref"])
        if context["identity"]["status"] != "resolved":
            raise AgentBoundaryError(
                "GPCR identity is not resolved; cannot select a family playbook"
            )
        path = self.bridge.validate_project().source_path
        analysis = analyze_structure(path, request.auth_chain, context["topology"])
        candidates = generate_candidates(analysis, context)
        ref = self.bridge.persist("research-receptor-analysis", candidates)
        summary = {
            "identity": candidates["identity"],
            "topology": candidates["topology"],
            "membrane": candidates["membrane"],
            "state": candidates["state"],
            "chain_graph": candidates["chain_graph"],
            "candidates": candidates["candidates"],
            "warnings": candidates["warnings"],
            "avoid": candidates["avoid"],
        }
        card_id = "receptor-" + ref["sha256"][:24]
        result = {
            "query_id": card_id,
            "topic": "structure-complex",
            "question": "Receptor geometry and context",
            "status": "UNRESOLVED",
            "errors": [],
            "target_binding": identity(self.bridge.binding()),
            "cards": [
                {
                    "card_id": card_id,
                    "provider": "EasyDesign GPCR kernel",
                    "identifier": context["identity"]["entry_name"],
                    "primary_eligible": False,
                    "evidence_level": "deterministic-structure-analysis",
                    "passage": json.dumps(summary),
                    "source_verified": True,
                    "source_refs": [*card["source_refs"], ref],
                    "does_not_support": ["Automatic site approval or binding efficacy"],
                }
            ],
        }
        result_ref = self.bridge.persist("evidence-research", result)
        self.bridge.store.event(
            self.bridge.thread,
            "evidence-research",
            {"target_binding": identity(self.bridge.binding()), "ref": result_ref},
        )
        return {**summary, "card_id": card_id, "analysis_ref": ref}

    def client(self, directory: Path) -> ScientificHttpClient:
        return ResearchHttpClient(
            evidence_dir=directory,
            cache_mode="online",
            max_attempts=1,
            connect_timeout=10,
            read_timeout=30,
        )

    def card(
        self, client: ScientificHttpClient, card: dict[str, Any], index: int
    ) -> dict[str, Any]:
        sources = []
        for record in client.records:
            if record.error_type is None:
                path = confined(self.bridge.project, client.evidence_dir / record.artifact_name)
                ref = ArtifactRef.from_file(
                    run_root=self.bridge.project,
                    relative_path=path.relative_to(self.bridge.project).as_posix(),
                    artifact_id="research-source",
                    role="scientific-evidence",
                    file_format=path.suffix.lstrip("."),
                )
                if ref.sha256 != record.response_sha256:
                    raise AgentBoundaryError("Retrieved source bytes changed before publication")
                sources.append(ref.model_dump(mode="json"))
        if card.get("context_ref"):
            sources.append(card["context_ref"])
        return {
            **card,
            "card_id": f"source-{identity({'card': card, 'sources': sources})[:20]}-{index}",
            "source_refs": sources,
            "source_verified": True,
            "retrieved_at": client.records[0].retrieved_at.isoformat() if client.records else None,
            "cache_status": list(dict.fromkeys(r.cache_status for r in client.records)),
            "does_not_support": [
                "Independent confirmation of current target identity, residue numbering, "
                "state or efficacy."
            ],
        }

    def retrieve(self, client: ScientificHttpClient, q: ResearchQuery) -> list[dict[str, Any]]:
        if q.operation in {"literature-search", "primary-record"}:
            query = (
                q.query
                if q.operation == "literature-search"
                else f"EXT_ID:{q.identifier} AND SRC:MED"
            )
            data = client.request(
                "GET",
                f"{EUROPE_PMC}/search",
                artifact_name="literature.json",
                params={"query": query, "format": "json", "resultType": "core", "pageSize": 5},
            ).json()
            if not isinstance(data.get("resultList", {}).get("result"), list):
                raise BackendContractError("Primary literature schema changed")
            cards = []
            for row in data["resultList"]["result"]:
                if q.operation == "primary-record" and (
                    row.get("id") != q.identifier or row.get("source") != "MED"
                ):
                    raise BackendContractError("Primary publication identity mismatch")
                abstract = _text(row.get("abstractText") or "")
                types = row.get("pubTypeList", {}).get("pubType", [])
                cards.append(
                    {
                        "provider": "EuropePMC",
                        "identifier": row["id"],
                        "title": row.get("title"),
                        "doi": row.get("doi"),
                        "pmcid": row.get("pmcid"),
                        "year": row.get("pubYear"),
                        "journal": row.get("journalInfo", {}).get("journal", {}).get("title"),
                        "publication_types": types,
                        "primary_eligible": q.operation == "primary-record"
                        and bool(abstract)
                        and not any(
                            excluded in str(t).lower()
                            for t in types
                            for excluded in ("review", "editorial", "comment", "meta-analysis")
                        ),
                        "evidence_level": "abstract" if abstract else "bibliographic-lead",
                        "passage": abstract if q.operation == "primary-record" else abstract[:450],
                        "truncated": q.operation == "literature-search" and len(abstract) > 450,
                    }
                )
            return cards
        if q.operation == "primary-fulltext":
            response = client.request(
                "GET", f"{EUROPE_PMC}/{q.identifier}/fullTextXML", artifact_name="primary.xml"
            )
            root = ElementTree.fromstring(response.content)
            # JATS uses both pmc (older records) and pmcid (current records). Only
            # the enclosing article's metadata binds identity; never a cited article.
            ids = {
                e.attrib.get("pub-id-type"): (e.text or "").strip()
                for e in root.findall("./front/article-meta/article-id")
            }
            pmc_ids = [ids[k].removeprefix("PMC") for k in ("pmc", "pmcid") if k in ids]
            if not pmc_ids or any(i != q.identifier.removeprefix("PMC") for i in pmc_ids):
                raise BackendContractError("Full text publication identity mismatch")
            body = root.find("body")
            if body is None:
                raise BackendContractError("Primary full text body unavailable")
            sections = []

            def visit(element: Any, location: str) -> None:
                title = element.find("title")
                if title is not None:
                    location += "/" + _text(" ".join(title.itertext()))
                for i, child in enumerate(element):
                    if child.tag in {"p", "table-wrap", "fig"}:
                        sections.append(
                            {
                                "location": f"{location}/{child.tag}[{i}]",
                                "text": _text(" ".join(child.itertext())),
                            }
                        )
                    elif child.tag == "sec":
                        visit(child, location)

            visit(body, "body")
            passage = "\n".join(s["text"] for s in sections)
            return [
                {
                    "provider": "EuropePMC",
                    "identifier": q.identifier,
                    "publication_ids": ids,
                    "primary_eligible": root.attrib.get("article-type")
                    in {"research-article", "methods-article", "data-paper", "brief-report"},
                    "publication_type": root.attrib.get("article-type", "unknown"),
                    "evidence_level": "primary-fulltext-excerpts",
                    "passage": passage,
                    "_sections": sections,
                    "truncated": False,
                }
            ]
        if q.operation in {"uniprot-search", "uniprot-record"}:
            if q.operation == "uniprot-search":
                assert q.taxon_id is not None
                records = (
                    uniprot_search(client, query=q.query, taxon_id=q.taxon_id)
                    .json()
                    .get("results", [])[:5]
                )
            else:
                records = [uniprot_accession(client, q.identifier).json()]
            return [
                {
                    "provider": "UniProt",
                    "identifier": row["primaryAccession"],
                    "primary_eligible": q.operation == "uniprot-record",
                    "evidence_level": "official-database"
                    if q.operation == "uniprot-record"
                    else "database-lead",
                    "passage": compact(_uniprot_view(row, q.topic))
                    if q.operation == "uniprot-record"
                    else compact(
                        {
                            "accession": row["primaryAccession"],
                            "organism": row.get("organism"),
                            "protein": row.get("proteinDescription"),
                        }
                    )[:450],
                    "_sections": _uniprot_sections(row) if q.operation == "uniprot-record" else [],
                    "truncated": q.operation.endswith("search"),
                }
                for row in records
            ]
        if q.operation == "structure-search":
            data = client.request(
                "POST",
                RCSB_SEARCH_URL,
                artifact_name="structure-search.json",
                json_body={
                    "query": {
                        "type": "terminal",
                        "service": "full_text",
                        "parameters": {"value": q.query},
                    },
                    "return_type": "entry",
                    "request_options": {"paginate": {"start": 0, "rows": 5}},
                },
            )
            rows = [] if not data.content.strip() else data.json().get("result_set", [])
            return [
                {
                    "provider": "RCSB",
                    "identifier": row["identifier"],
                    "primary_eligible": False,
                    "evidence_level": "structure-lead",
                    "passage": json.dumps(row),
                    "truncated": False,
                }
                for row in rows
            ]
        if q.operation == "structure-record":
            code = q.identifier.upper()
            entry = rcsb_entry(client, code).json()
            if entry.get("rcsb_id") != code:
                raise BackendContractError("PDB entry identity mismatch")
            entities = entry.get("rcsb_entry_container_identifiers", {}).get(
                "polymer_entity_ids", []
            )
            polymers = [rcsb_polymer_entity(client, code, str(i)).json() for i in entities[:8]]
            return [
                {
                    "provider": "RCSB",
                    "identifier": code,
                    "primary_eligible": True,
                    "evidence_level": "deposition-and-polymer-entities",
                    "passage": compact(_pdb_view(entry, polymers)),
                    "_sections": _pdb_sections(_pdb_view(entry, polymers)),
                    "truncated": False,
                    "limitations": [
                        "Deposited assembly and partners are not proof of physiological context."
                    ],
                }
            ]
        # Existing adapter verifies receptor identity/family; no arbitrary endpoint tool.
        context = GpcrdbAdapter(client).fetch_receptor_context(
            entry=q.identifier, pdb_code=q.pdb_id
        )
        projection = context.legacy_projection()
        return [
            {
                "provider": "GPCRdb",
                "identifier": q.identifier,
                "primary_eligible": True,
                "evidence_level": "curated-receptor-context",
                "passage": compact(projection),
                "_sections": [
                    {"location": name, "text": compact(value)} for name, value in projection.items()
                ],
                "context_ref": self.bridge.persist("research-gpcrdb-context", projection),
                "truncated": False,
                "status": context.status,
            }
        ]

    def validate_conclusions(self, conclusions: list[ResearchConclusion]) -> dict[str, Any]:
        snapshot = self.snapshot()
        queries = snapshot["queries"]
        cards = {c["card_id"]: c for r in queries for c in r["cards"]}
        used_refs = []
        if any(use.card_id not in cards for c in conclusions for use in c.evidence):
            raise AgentBoundaryError("Evidence source identifier was not retrieved in this thread")
        missing = [
            c.topic
            for c in conclusions
            if c.status == "NOT_SEARCHED" or not any(q["topic"] == c.topic for q in queries)
        ]
        if missing:
            raise ResearchConclusionMismatch(
                "Material scientific question was NOT_SEARCHED: "
                + compact(missing)
                + ". Delegate research for every material topic before resubmission. Merely "
                "renaming an unresearched question UNRESOLVED does not make it researched."
            )
        for conclusion in conclusions:
            relevant = [q for q in queries if q["topic"] == conclusion.topic]
            if conclusion.status == "SEARCHED_NO_EVIDENCE" and (
                conclusion.evidence or any(q["errors"] for q in relevant)
            ):
                raise ResearchConclusionMismatch(
                    "A source failure or cited evidence is not SEARCHED_NO_EVIDENCE"
                )
            if (
                conclusion.status in {"VERIFIED", "CONFLICTING_EVIDENCE"}
                and not conclusion.evidence
            ):
                raise ResearchConclusionMismatch(
                    "Scientific support/conflict requires source-bound passages"
                )
            if conclusion.status == "CONFLICTING_EVIDENCE" and not {
                "supports",
                "contradicts",
            }.issubset({e.relation for e in conclusion.evidence}):
                raise ResearchConclusionMismatch(
                    "Conflict requires both supporting and contradicting source passages"
                )
            if (
                conclusion.status == "CONFLICTING_EVIDENCE"
                and len(
                    {
                        (cards[e.card_id]["provider"], cards[e.card_id]["identifier"])
                        for e in conclusion.evidence
                        if e.card_id in cards
                    }
                )
                < 2
            ):
                raise ResearchConclusionMismatch(
                    "Cross-source conflict requires distinct source identities"
                )
            for use in conclusion.evidence:
                card = cards.get(use.card_id)
                if card is None:
                    raise AgentBoundaryError(
                        "Evidence source identifier was not retrieved in this thread"
                    )
                if card.get("corpus_ref") or _text(use.excerpt) not in _text(card["passage"]):
                    raise EvidenceCitationMismatch(
                        "CITATION_MISMATCH for known source " + use.card_id + ": "
                        "Use the exact focused retrieved passage card_id from retrieve_evidence "
                        "and "
                        "a verbatim substring of its passage, not a search/acquisition "
                        "receipt or paraphrase. Correct every citation in this submission. "
                        "For unread/unavailable sources, put the access limit in limitations "
                        "with evidence=[] and UNRESOLVED; do not invent quotes or support. "
                        "Read-only passage retrieval is permitted before resubmission."
                    )
                if use.strength in {"E1", "E2"} and not card["primary_eligible"]:
                    raise AgentBoundaryError(
                        "A discovery lead/review cannot become direct primary evidence"
                    )
                used_refs.extend(card["source_refs"])
        return {
            "source_snapshot": snapshot,
            "conclusions": [c.model_dump(mode="json") for c in conclusions],
            "source_refs": used_refs,
            "authority": (
                "Source binding verified; scientific conclusions remain specialist opinions "
                "for independent Judge review."
            ),
        }


def research_tool(bridge: Any, role: str) -> Any:
    from langchain_core.tools import StructuredTool

    async def acquire(**arguments: Any) -> str:
        result = EvidenceResearch(bridge).acquire(
            ResearchQuery.model_validate(arguments), role=role
        )
        # The raw source and complete index remain in existing project artifacts.
        # Return only leads or acquisition receipts, never a record/full text.
        cards = []
        for card in result["cards"]:
            view = {
                k: card[k]
                for k in (
                    "card_id",
                    "provider",
                    "identifier",
                    "title",
                    "year",
                    "doi",
                    "pmcid",
                    "evidence_level",
                    "chunk_count",
                )
                if k in card
            }
            view["source_id"] = source_key(card["provider"], card["identifier"])
            if "need" in card:
                view["original_acquisition_need"] = card["need"]
            if not arguments["operation"].endswith("search"):
                # acquire() checked explicit current selection before reusing source bytes.
                # A cached card's original need is provenance, not today's retrieval scope.
                view["retrieval_need"] = NEEDS[result["topic"]]
            if card["provider"] == "UniProt" and arguments["operation"] == "uniprot-record":
                features = EvidenceCorpus(bridge).uniprot_features(card)
                view["feature_types_available"] = sorted(
                    {f["type"] for f in features if f.get("type")}
                )
                view["focused_annotation_read"] = (
                    "For processing, active sites, topology or PTMs, retrieve_evidence with "
                    "the relevant literal feature_types above instead of paging references. "
                    "Omit the filter for narrative questions. Type presence is not entailment."
                )
            if card["provider"] == "GPCRdb" and card.get("context_ref"):
                view["available_analysis"] = (
                    "analyze_receptor_context using this card_id "
                    "and original auth_chain: obtain complete verified topology, membrane "
                    "frame, chain graph and mapped candidates before epitope interpretation."
                )
            if arguments["operation"].endswith("search"):
                view["snippet"] = card["passage"][:450]
                view["relevance"] = "Query match only; select before deeper reading"
            cards.append(view)
        return compact(
            {
                "status": result["status"],
                "topic": result["topic"],
                "need": NEEDS[result["topic"]],
                "cards": cards,
                "errors": result["errors"],
                "next": (
                    "Select relevant search leads before acquisition. For acquired cards, "
                    "retrieve_evidence uses their retrieval_need; original_acquisition_need "
                    "is historical provenance. Select explicitly before using another need."
                ),
            }
        )

    return StructuredTool.from_function(
        name="research_evidence",
        coroutine=acquire,
        args_schema=ResearchQuery,
        description=(
            "Delegate a bounded evidence question to the shared Research worker. "
            "Search literature/structures; "
            "retrieve primary PMID/PMCID, PDB complexes, UniProt or applicable GPCRdb context. "
            "For acquisition include selection_reason to explicitly select this source for "
            "the exact topic and acquire it atomically through the existing corpus. "
            "Alternatively call select_evidence first. Full records stay in the corpus; "
            "Use identifier for the source key (PMID/PMCID/accession/PDB code). "
            "Selection need must match query topic: identity=TARGET_IDENTITY, "
            "state=STRUCTURE_STATE, structure-complex=PPI_INTERFACE, "
            "function=FUNCTIONAL_MECHANISM, epitope=KNOWN_EPITOPE. "
            "use retrieve_evidence for passages and source card IDs in scientific synthesis. "
            "Failures are unresolved, never negative biology. "
            "No arbitrary URLs, shell, scientific approval or target identity mutation."
        ),
    )


def identity_comparison_tool(bridge: Any) -> Any:
    from langchain_core.tools import StructuredTool

    async def compare(uniprot_card_id: str, auth_chain: str) -> str:
        value = EvidenceResearch(bridge).compare_reference(
            ReferenceComparison(uniprot_card_id=uniprot_card_id, auth_chain=auth_chain)
        )
        return str(bridge.store.offload(bridge.thread, value))

    return StructuredTool.from_function(
        name="compare_reference_identity",
        coroutine=compare,
        args_schema=ReferenceComparison,
        description=(
            "Use the existing deterministic identity kernel to compare one original auth chain "
            "with a retrieved UniProt reference card. Reports substitutions, fusions, "
            "ambiguity and review "
            "requirements without changing or approving the canonical Target Bundle."
        ),
    )


def receptor_analysis_tool(bridge: Any) -> Any:
    from langchain_core.tools import StructuredTool

    async def analyze(gpcrdb_card_id: str, auth_chain: str) -> str:
        value = EvidenceResearch(bridge).analyze_receptor(
            ReceptorAnalysis(gpcrdb_card_id=gpcrdb_card_id, auth_chain=auth_chain)
        )
        return compact({"analysis_ref": value["analysis_ref"], "card_id": value["card_id"]})

    return StructuredTool.from_function(
        name="analyze_receptor_context",
        coroutine=analyze,
        args_schema=ReceptorAnalysis,
        description=(
            "Only for a verified GPCR: use the existing structure/topology/membrane/chain-graph "
            "and candidate kernel with a complete GPCRdb source card and original auth chain. "
            "Outputs mapped hypotheses and uncertainty, never a scientific approval."
        ),
    )
