"""Bounded source acquisition for scientific owners, on the existing HTTP/artifact stack.

This worker verifies source records, not biological entailment. It cannot approve, choose
hotspots, run compute, browse arbitrary URLs, or change canonical target identity.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse
from xml.etree import ElementTree

from Bio.PDB.MMCIF2Dict import MMCIF2Dict
from pydantic import Field, model_validator

from easydesign.backends.gpcrdb import GpcrdbAdapter
from easydesign.backends.target_sources.remote import (
    RCSB_SEARCH_URL,
    RetrievedResponse,
    ScientificHttpClient,
    rcsb_entry,
    rcsb_mmcif,
    rcsb_polymer_entity,
    uniprot_accession,
    uniprot_search,
)
from easydesign.backends.target_sources.structure import inventory_structure
from easydesign.core import ArtifactRef, BackendContractError
from easydesign.core.target_identity import resolve_target_identity
from easydesign.stages.s02_hotspot_discovery.gpcr import (
    StructureAnalysisError,
    analyze_structure,
    build_chain_graph,
    generate_candidates,
    parse_structure,
)

from .contracts import (
    AgentBoundaryError,
    EvidenceCitationMismatch,
    EvidenceRoleMismatch,
    ResearchConclusionMismatch,
    ResearchQuestionBindingMismatch,
    ResearchQuestionCitationMismatch,
    ShortText,
    SourceCardArgumentMismatch,
    StrictDTO,
)
from .evidence_corpus import NEEDS, EvidenceCorpus, RetrieveEvidence, SelectEvidence, source_key
from .evidence_policy import allowed_evidence_strengths, evidence_strength_policy
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
HOSTS = {
    "www.ebi.ac.uk",
    "rest.uniprot.org",
    "search.rcsb.org",
    "data.rcsb.org",
    "files.rcsb.org",
    "gpcrdb.org",
}
EUROPE_PMC = "https://www.ebi.ac.uk/europepmc/webservices/rest"
RESEARCH_QUERY_LIMIT = 12


class ResearchBudgetExhausted(AgentBoundaryError):
    """The durable acquisition ceiling was reached; existing evidence remains usable."""

    def __init__(self, used: int) -> None:
        self.used = used
        super().__init__(f"This execution used its {RESEARCH_QUERY_LIMIT} bounded research queries")

    def result(self, *, role: str) -> dict[str, Any]:
        return {
            "error_code": "RESEARCH_QUERY_BUDGET_COMPLETE",
            "used_queries": self.used,
            "query_limit": RESEARCH_QUERY_LIMIT,
            "required_action": (
                "submit_site_research_handoff"
                if role == "site"
                else "continue_without_new_research_queries"
            ),
            "message": (
                "The bounded acquisition budget is complete. No query ran and no absence of "
                "scientific evidence is implied. Use already acquired and focused evidence, "
                "preserve unresolved questions, and finish the current typed assessment."
            ),
        }


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
        "Omit only if already selected for this exact topic. The Site Runtime also binds "
        "gpcrdb-context to the approved canonical receptor, because this deterministic "
        "structured context is a required input rather than a literature choice. Not "
        "scientific approval.",
    )
    query: str = Field(
        default="",
        max_length=400,
        description="REQUIRED for any search "
        "operation: explicit database search keywords/syntax. The scientific "
        "question is separate and does not execute a search. Literature search uses Europe "
        "PMC: bare terms are ANDed and synonym expansion is off. Use a short target plus "
        "one decisive concept; put alternative names/effects in parenthesized OR groups. "
        "Do not AND all binder formats or every desired outcome. Irrelevant hits require "
        "one sensible reformulation, not a claim of absence. Omit for records.",
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
        "substring (12-700 characters) of that retrieved passage, with enough surrounding "
        "context for the claim; a lone short mutation symbol is not sufficient. Do not "
        "paraphrase, quote a "
        "title/receipt, or describe unavailable text. Record access limits "
        "in limitations with evidence=[] instead.",
    )
    claim: ShortText
    relation: Literal["supports", "contradicts", "scope-limit"]
    strength: Literal["E1", "E2", "E3", "E4"] = Field(
        description="Claim-specific evidence strength within the card's Runtime-owned "
        "allowed_strengths. primary_eligible is provenance only, not the complete permission. "
        "E1 requires a direct-eligible source and an exact in-scope observation; E2 covers "
        "near-direct transfer or curated identity/context. E3/E4 are context, computation, "
        "scope or uncertainty. The model may never promote a source above its allowlist."
    )
    transfer_limit: ShortText


class ResearchAssessment(StrictDTO):
    query_ids: list[str] = Field(
        max_length=6,
        description="Exact returned query_id values for the evidence questions actually "
        "investigated. Topics index sources, not mandatory separate research tasks. A "
        "relevant query may inform more than one conclusion; explain transfer in limitations. "
        "Copy the complete issued query_id, including any page suffix. A cursor's internal "
        "view ID is not a query_id; never decode a cursor to construct one. Empty is allowed "
        "only when Runtime issued no research query at all, status is NOT_SEARCHED or "
        "UNRESOLVED, and evidence is empty.",
    )
    status: EvidenceStatus = Field(
        description="VERIFIED requires at least one supporting E1/E2 passage permitted by "
        "that card's Runtime allowlist, not claims hidden in limitations or E3/E4 context. "
        "CONFLICTING_EVIDENCE requires both supporting and contradicting "
        "passages with incompatible claims in the same scope. Different source IDs alone "
        "do not prove conflict. Evidence challenging a computational hypothesis "
        "alone is not a source-vs-source conflict: preserve that evidence and use UNRESOLVED "
        "when direction or transfer remains uncertain. SEARCHED_NO_EVIDENCE requires an "
        "actual search without source failure."
    )
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


def uniprot_reference_status(record: dict[str, Any]) -> dict[str, Any]:
    """Project canonical eligibility without converting an inactive record into a successor."""
    entry_type = record.get("entryType")
    inactive = str(entry_type).strip().casefold() == "inactive"
    accession = record.get("primaryAccession")
    sequence_record = record.get("sequence")
    organism = record.get("organism")
    sequence = sequence_record.get("value") if isinstance(sequence_record, dict) else None
    taxon_id = organism.get("taxonId") if isinstance(organism, dict) else None
    eligible = (
        not inactive
        and isinstance(accession, str)
        and bool(accession.strip())
        and isinstance(sequence, str)
        and bool(sequence.strip())
        and isinstance(taxon_id, int)
        and not isinstance(taxon_id, bool)
        and taxon_id > 0
    )
    result: dict[str, Any] = {
        "entry_type": entry_type,
        "canonical_reference_eligible": eligible,
        "_resolution_complete": False,
    }
    if not inactive:
        return result
    reason = record.get("inactiveReason")
    reason_type = reason.get("inactiveReasonType") if isinstance(reason, dict) else None
    raw_replacements = reason.get("mergeDemergeTo") if isinstance(reason, dict) else None
    replacements = (
        [value for value in raw_replacements if isinstance(value, str)]
        if isinstance(raw_replacements, list)
        else []
    )
    valid_replacements = [
        value for value in replacements if re.fullmatch(r"[A-Z][0-9][A-Z0-9]{3,7}[0-9]", value)
    ]
    result["identifier_resolution"] = {
        "status": "inactive",
        "type": reason_type,
        "replacement_accessions": valid_replacements,
    }
    result["_resolution_complete"] = (
        isinstance(reason_type, str)
        and bool(reason_type.strip())
        and isinstance(raw_replacements, list)
        and bool(raw_replacements)
        and len(valid_replacements) == len(raw_replacements)
        and len(set(valid_replacements)) == len(valid_replacements)
        and accession not in valid_replacements
    )
    return result


def _uniprot_reference_projection(record: dict[str, Any]) -> dict[str, Any]:
    status = uniprot_reference_status(record)
    return {key: value for key, value in status.items() if not key.startswith("_")}


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
        **_uniprot_reference_projection(record),
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
        **_uniprot_reference_projection(record),
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


def _canonical_accession(value: Any) -> str:
    return str(value or "").strip().upper().split("-", 1)[0]


def _normalized_insertion_code(value: Any) -> str:
    normalized = str(value or "").strip()
    return "" if normalized in {".", "?"} else normalized


def _mapping_row_has_model_one(row: dict[str, Any]) -> bool:
    model_presence = {str(value) for value in row.get("model_presence") or []}
    coordinate_present = row.get("coordinate_present")
    return "1" in model_presence and coordinate_present is not False


def _verified_deposited_structure_id(path: Path) -> str | None:
    """Read a deposited PDB identity from source bytes, never from a user filename/target ID."""

    if path.suffix.casefold() not in {".cif", ".mmcif"}:
        return None
    try:
        raw: dict[str, Any] = MMCIF2Dict(str(path))  # type: ignore[no-untyped-call]
    except Exception:
        return None
    value = raw.get("_entry.id")
    values = value if isinstance(value, list) else [value]
    identifiers = {
        str(item or "").strip().upper()
        for item in values
        if re.fullmatch(r"[0-9][A-Za-z0-9]{3}", str(item or "").strip())
    }
    return next(iter(identifiers)) if len(identifiers) == 1 else None


def _polymer_accessions(polymer: dict[str, Any]) -> set[str]:
    identifiers = polymer.get("rcsb_polymer_entity_container_identifiers") or {}
    refs = identifiers.get("reference_sequence_identifiers") or []
    return {
        accession
        for row in refs
        if isinstance(row, dict)
        and (accession := _canonical_accession(row.get("database_accession")))
    }


def _polymer_canonical_positions(
    polymer: dict[str, Any], approved_accession: str
) -> dict[int, list[int]]:
    """Map deposited entity-label positions to the approved canonical sequence via SIFTS."""

    approved = _canonical_accession(approved_accession)
    positions: dict[int, set[int]] = {}
    for alignment in polymer.get("rcsb_polymer_entity_align") or []:
        if (
            str(alignment.get("reference_database_name") or "").upper() != "UNIPROT"
            or _canonical_accession(alignment.get("reference_database_accession")) != approved
        ):
            continue
        for region in alignment.get("aligned_regions") or []:
            try:
                entity_start = int(region["entity_beg_seq_id"])
                reference_start = int(region["ref_beg_seq_id"])
                length = int(region["length"])
            except (KeyError, TypeError, ValueError):
                continue
            if entity_start < 1 or reference_start < 1 or length < 1:
                continue
            for offset in range(length):
                positions.setdefault(entity_start + offset, set()).add(reference_start + offset)
    return {key: sorted(value) for key, value in positions.items()}


def _approved_design_correspondence(
    residues: list[dict[str, Any]],
    approved_mapping: list[dict[str, Any]],
    *,
    reference_is_approved_source: bool = False,
) -> list[dict[str, Any]]:
    """Join reference-complex contacts to current design labels without inferring offsets."""

    mapping_by_canonical: dict[int, list[dict[str, Any]]] = {}
    for row in approved_mapping:
        position = row.get("canonical_position")
        if isinstance(position, int):
            mapping_by_canonical.setdefault(position, []).append(row)
    result = []
    for residue in residues:
        canonical_positions = residue.get("canonical_positions") or []
        canonical_rows = [
            row
            for position in canonical_positions
            for row in mapping_by_canonical.get(position, [])
        ]
        source_rows: list[dict[str, Any]] = []
        if reference_is_approved_source:
            source_rows = [
                row
                for row in approved_mapping
                if str(row.get("source_author_chain_id") or "")
                == str(residue.get("auth_asym_id") or "")
                and str(row.get("source_author_residue_id") or "")
                == str(residue.get("auth_seq_id") or "")
                and _normalized_insertion_code(row.get("insertion_code"))
                == _normalized_insertion_code(residue.get("insertion_code"))
                and _mapping_row_has_model_one(row)
                and (
                    not row.get("source_residue_name")
                    or str(row["source_residue_name"]).upper()
                    == str(residue.get("resname") or "").upper()
                )
            ]
        rows = source_rows if reference_is_approved_source else canonical_rows
        if (
            reference_is_approved_source
            and len(
                {
                    int(row["label_seq_id"])
                    for row in source_rows
                    if isinstance(row.get("label_seq_id"), int)
                }
            )
            > 1
        ):
            raise AgentBoundaryError(
                "Approved source residue maps to conflicting current design labels"
            )
        resolved_canonical_positions = (
            sorted(
                {
                    int(position)
                    for row in source_rows
                    if isinstance((position := row.get("canonical_position")), int)
                }
            )
            or canonical_positions
        )
        result.append(
            {
                "reference_auth_asym_id": residue.get("auth_asym_id"),
                "reference_auth_seq_id": residue.get("auth_seq_id"),
                "reference_insertion_code": residue.get("insertion_code"),
                "reference_label_seq_id": residue.get("label_seq_id"),
                "resname": residue.get("resname"),
                "canonical_positions": resolved_canonical_positions,
                "current_design_label_seq_ids": sorted(
                    {
                        int(row["label_seq_id"])
                        for row in rows
                        if isinstance(row.get("label_seq_id"), int)
                        and bool(row.get("coordinate_present", row.get("model_presence")))
                    }
                ),
                "mapping_statuses": sorted(
                    {str(row["mapping_status"]) for row in rows if row.get("mapping_status")}
                ),
                "mapping_basis": (
                    "approved-source-residue-identity"
                    if source_rows
                    else "unresolved"
                    if reference_is_approved_source
                    else "canonical-position"
                    if canonical_rows
                    else "unresolved"
                ),
            }
        )
    return result


def _interface_residue_summary(
    contacts: list[dict[str, Any]],
    *,
    residue_field: str,
    resname_field: str,
) -> list[dict[str, Any]]:
    residues: dict[tuple[str, int, str, str, int | None], dict[str, Any]] = {}
    for contact in contacts:
        identity_value = contact[residue_field]
        key = (
            str(identity_value.get("auth_asym_id") or identity_value.get("chain_id") or ""),
            int(identity_value.get("auth_seq_id") or identity_value.get("seq_num")),
            str(identity_value.get("insertion_code") or ""),
            str(identity_value.get("label_chain_id") or ""),
            identity_value.get("label_seq_id"),
        )
        item = residues.setdefault(
            key,
            {
                "auth_asym_id": key[0],
                "auth_seq_id": key[1],
                "insertion_code": key[2] or None,
                "label_asym_id": key[3] or None,
                "label_seq_id": key[4],
                "resname": contact[resname_field],
                "minimum_distance_angstrom": float("inf"),
            },
        )
        item["minimum_distance_angstrom"] = min(
            item["minimum_distance_angstrom"], float(contact["minimum_distance"])
        )
    result = list(residues.values())
    for item in result:
        item["minimum_distance_angstrom"] = round(item["minimum_distance_angstrom"], 4)
    return sorted(
        result,
        key=lambda item: (
            item["auth_asym_id"],
            item["auth_seq_id"],
            item["insertion_code"] or "",
        ),
    )


def _pdb_complex_interface_view(
    structure_path: Path,
    *,
    pdb_id: str,
    polymers: list[dict[str, Any]],
    approved_accession: str,
    approved_mapping: list[dict[str, Any]] | None = None,
    approved_source_pdb_id: str | None = None,
    approved_source_auth_chain: str | None = None,
    approved_source_coordinates: bool = False,
    contact_cutoff: float = 5.0,
) -> dict[str, Any]:
    """Project source-bound target/partner contacts from one deposited coordinate model."""

    target_accession = _canonical_accession(approved_accession)
    coordinate_source = (
        "approved-target-source" if approved_source_coordinates else "retrieved-rcsb"
    )
    scope = (
        f"Heavy-atom contacts <= {contact_cutoff:.1f} Angstrom in model 1 of the deposited "
        "asymmetric unit. Geometric contact does not establish physiological assembly, "
        "binding energy, competition, or inhibitory efficacy."
    )
    chain_entities: dict[str, dict[str, Any]] = {}
    target_chains: set[str] = set()
    target_entity_ids: list[str] = []
    source_pdb_matches = bool(
        approved_source_pdb_id
        and str(approved_source_pdb_id).strip().upper() == str(pdb_id).strip().upper()
    )
    approved_source_chain = str(approved_source_auth_chain or "")
    mapped_source_chains = {
        str(row.get("source_author_chain_id") or "")
        for row in approved_mapping or []
        if row.get("source_author_chain_id") and _mapping_row_has_model_one(row)
    }
    identity_conflicts = []
    for polymer in polymers:
        identifiers = polymer.get("rcsb_polymer_entity_container_identifiers") or {}
        entity_id = str(polymer.get("rcsb_id") or "")
        description = (polymer.get("rcsb_polymer_entity") or {}).get("pdbx_description")
        accessions = sorted(_polymer_accessions(polymer))
        accession_is_target = target_accession in accessions
        entity_is_target = False
        for chain in identifiers.get("auth_asym_ids") or []:
            normalized_chain = str(chain)
            source_chain_is_target = bool(
                approved_source_coordinates
                and source_pdb_matches
                and approved_source_chain
                and normalized_chain == approved_source_chain
                and normalized_chain in mapped_source_chains
            )
            if normalized_chain in chain_entities:
                identity_conflicts.append(
                    f"auth chain {normalized_chain} belongs to multiple polymer entities"
                )
            if (
                approved_source_coordinates
                and source_pdb_matches
                and accession_is_target
                and normalized_chain != approved_source_chain
            ):
                identity_conflicts.append(
                    "approved accession and approved source chain identify different entities"
                )
            is_target = (
                source_chain_is_target
                if approved_source_coordinates and source_pdb_matches
                else accession_is_target
            )
            entity_is_target = entity_is_target or is_target
            chain_entities[normalized_chain] = {
                "entity_id": entity_id,
                "description": description,
                "reference_accessions": accessions,
                "canonical_positions_by_label": _polymer_canonical_positions(
                    polymer, approved_accession
                ),
                "is_target": is_target,
                "target_resolution": (
                    "approved-source-auth-chain"
                    if source_chain_is_target
                    else "approved-accession"
                    if accession_is_target and is_target
                    else None
                ),
            }
            if is_target:
                target_chains.add(normalized_chain)
        if entity_is_target:
            target_entity_ids.append(entity_id)
    if identity_conflicts:
        return {
            "status": "target-identity-conflict",
            "pdb_id": pdb_id,
            "approved_accession": approved_accession,
            "target_entity_ids": [],
            "target_chains": [],
            "interfaces": [],
            "coordinate_source": coordinate_source,
            "identity_conflicts": sorted(set(identity_conflicts)),
            "scope": scope,
        }
    if not target_chains:
        return {
            "status": "target-entity-unresolved",
            "pdb_id": pdb_id,
            "approved_accession": approved_accession,
            "target_entity_ids": [],
            "target_chains": [],
            "interfaces": [],
            "coordinate_source": coordinate_source,
            "scope": scope,
        }

    parsed = parse_structure(structure_path)
    present_chains = set(parsed.chain_ids(polymer_only=True))
    observed_target_chains = sorted(target_chains & present_chains)
    if not observed_target_chains:
        return {
            "status": "target-chain-unresolved",
            "pdb_id": pdb_id,
            "approved_accession": approved_accession,
            "target_entity_ids": sorted(target_entity_ids),
            "target_chains": sorted(target_chains),
            "interfaces": [],
            "coordinate_source": coordinate_source,
            "scope": scope,
        }

    graph = build_chain_graph(
        parsed,
        observed_target_chains[0],
        receptor_like_chains=tuple(observed_target_chains),
        contact_cutoff=contact_cutoff,
    )
    interfaces: list[dict[str, Any]] = []
    for edge in graph["edges"]:
        chain_a = edge["chain_a"]
        chain_b = edge["chain_b"]
        a_is_target = chain_a in target_chains
        b_is_target = chain_b in target_chains
        if a_is_target == b_is_target:
            continue
        if a_is_target:
            target_chain, partner_chain = chain_a, chain_b
            target_field, target_name = "residue_a", "resname_a"
            partner_field, partner_name = "residue_b", "resname_b"
        else:
            target_chain, partner_chain = chain_b, chain_a
            target_field, target_name = "residue_b", "resname_b"
            partner_field, partner_name = "residue_a", "resname_a"
        partner = chain_entities.get(partner_chain, {})
        target_residues = _interface_residue_summary(
            edge["contacts"],
            residue_field=target_field,
            resname_field=target_name,
        )
        canonical_by_label = chain_entities.get(target_chain, {}).get(
            "canonical_positions_by_label", {}
        )
        for residue in target_residues:
            residue["canonical_positions"] = canonical_by_label.get(residue.get("label_seq_id"), [])
        interface = {
            "target_chain": target_chain,
            "target_entity_id": chain_entities.get(target_chain, {}).get("entity_id"),
            "target_resolution": chain_entities.get(target_chain, {}).get("target_resolution"),
            "partner_chain": partner_chain,
            "partner_entity_id": partner.get("entity_id"),
            "partner_description": partner.get("description"),
            "partner_reference_accessions": partner.get("reference_accessions", []),
            "geometry_observed": edge["geometry_observed"],
            "contact_pair_count": edge["residue_pair_count"],
            "minimum_distance_angstrom": edge["minimum_distance"],
            "target_contact_residues": target_residues,
            "partner_contact_residues": _interface_residue_summary(
                edge["contacts"],
                residue_field=partner_field,
                resname_field=partner_name,
            ),
            "scope": scope,
        }
        if approved_mapping is not None:
            reference_is_approved_source = (
                chain_entities.get(target_chain, {}).get("target_resolution")
                == "approved-source-auth-chain"
            )
            correspondence = _approved_design_correspondence(
                target_residues,
                approved_mapping,
                reference_is_approved_source=reference_is_approved_source,
            )
            interface["current_design_correspondence"] = correspondence
            if reference_is_approved_source:
                for residue, projected in zip(target_residues, correspondence, strict=True):
                    residue["canonical_positions"] = projected["canonical_positions"]
                mapped_count = sum(
                    len(projected["current_design_label_seq_ids"]) == 1
                    for projected in correspondence
                )
                interface["current_design_correspondence_status"] = (
                    "complete-source-correspondence"
                    if mapped_count == len(correspondence)
                    else "partial-source-correspondence"
                )
                interface["mapped_target_contact_count"] = mapped_count
                interface["unmapped_target_contact_count"] = len(correspondence) - mapped_count
        interfaces.append(interface)
    return {
        "status": "observed" if interfaces else "no-non-target-protein-contact",
        "pdb_id": pdb_id,
        "approved_accession": approved_accession,
        "target_entity_ids": sorted(target_entity_ids),
        "target_chains": observed_target_chains,
        "coordinate_source": coordinate_source,
        "contact_cutoff_angstrom": contact_cutoff,
        "interfaces": sorted(
            interfaces,
            key=lambda item: (item["target_chain"], item["partner_chain"]),
        ),
        "scope": scope,
    }


def _pdb_interface_sections(analysis: dict[str, Any]) -> list[dict[str, str]]:
    sections = [
        {
            "location": "complex interface analysis / scope",
            "text": compact(
                {
                    key: analysis.get(key)
                    for key in (
                        "status",
                        "pdb_id",
                        "approved_accession",
                        "target_entity_ids",
                        "target_chains",
                        "contact_cutoff_angstrom",
                        "scope",
                    )
                }
            ),
        }
    ]
    for index, interface in enumerate(analysis.get("interfaces") or []):
        correspondence = interface.get("current_design_correspondence") or []
        columns = (
            "reference_auth_residue",
            "reference_label_seq_id",
            "resname",
            "canonical_positions",
            "current_design_label_seq_ids",
            "mapping_statuses",
            "mapping_basis",
        )
        sections.append(
            {
                "location": (
                    "complex interface analysis / target contact mapping / "
                    f"{index} / {interface['target_chain']}:{interface['partner_chain']}"
                ),
                "text": compact(
                    {
                        "pdb_id": analysis.get("pdb_id"),
                        "approved_accession": analysis.get("approved_accession"),
                        "coordinate_source": analysis.get("coordinate_source"),
                        "target_resolution": interface.get("target_resolution"),
                        "partner_chain": interface["partner_chain"],
                        "partner_description": interface.get("partner_description"),
                        "partner_reference_accessions": interface.get(
                            "partner_reference_accessions", []
                        ),
                        "contact_pair_count": interface.get("contact_pair_count"),
                        "correspondence_status": interface.get(
                            "current_design_correspondence_status"
                        ),
                        "mapped_target_contact_count": interface.get("mapped_target_contact_count"),
                        "unmapped_target_contact_count": interface.get(
                            "unmapped_target_contact_count"
                        ),
                        "columns": list(columns),
                        "rows": [
                            [
                                (
                                    f"{row.get('reference_auth_asym_id')}:"
                                    f"{row.get('reference_auth_seq_id')}"
                                    f"{row.get('reference_insertion_code') or ''}"
                                ),
                                row.get("reference_label_seq_id"),
                                row.get("resname"),
                                row.get("canonical_positions"),
                                row.get("current_design_label_seq_ids"),
                                row.get("mapping_statuses"),
                                row.get("mapping_basis"),
                            ]
                            for row in correspondence
                        ],
                        "scope": interface.get("scope"),
                    }
                ),
            }
        )
        sections.append(
            {
                "location": (
                    "complex interface analysis / target-partner interface / "
                    f"{index} / {interface['target_chain']}:{interface['partner_chain']}"
                ),
                "text": compact(interface),
            }
        )
    return sections


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
        if name not in {"polymers", "complex_interface_analysis"}
    )
    if isinstance(view.get("complex_interface_analysis"), dict):
        sections.extend(_pdb_interface_sections(view["complex_interface_analysis"]))
    return sections


class EvidenceResearch:
    """One synchronous bounded worker, shared by Target and Site typed tools."""

    def __init__(self, bridge: Any) -> None:
        self.bridge = bridge

    def snapshot(self, *, execution_id: str | None = None) -> dict[str, Any]:
        """Return current-binding evidence, optionally scoped to one execution.

        The unscoped view preserves the historical project-wide evidence behavior used by
        Target identity and source reuse. Site lifecycle/accounting passes an execution ID so
        Gate 1 reads cannot masquerade as Gate 2 research progress.
        """
        binding = identity(self.bridge.binding())
        query = (
            "SELECT kind,payload FROM events WHERE thread=? "
            "AND kind IN ('evidence-research','evidence-view')"
        )
        arguments: list[Any] = [self.bridge.thread]
        if execution_id is not None:
            query += " AND json_extract(payload,'$.execution_id')=?"
            arguments.append(execution_id)
        rows = self.bridge.store.db.execute(query + " ORDER BY seq", arguments)
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
            selection_reason = query.selection_reason
            if role == "site" and query.operation == "gpcrdb-context":
                # The approved Target and the adapter's accession check make this one
                # acquisition deterministic. Requiring the research model to separately
                # SELECT the same mandatory receptor context caused repeated
                # SOURCE_NOT_SELECTED turns before the already-defined kernel could run.
                # Other records/full text still require an explicit scientific selection.
                try:
                    target, _, _ = self.bridge.site_facts()
                    approved_accession = target["evidence"]["hard_facts"].get("canonical_accession")
                except (AttributeError, AgentBoundaryError, KeyError, TypeError):
                    approved_accession = None
                if isinstance(approved_accession, str) and approved_accession:
                    selection_reason = selection_reason or (
                        "Runtime-required deterministic GPCR context for the approved "
                        f"canonical receptor {approved_accession}; identity is independently "
                        "verified by the GPCRdb adapter."
                    )
            if selection_reason is not None:
                corpus.select(
                    SelectEvidence.model_validate(
                        {
                            "provider": provider,
                            "identifier": query.identifier,
                            "need": NEEDS[query.topic],
                            "selection": "SELECTED",
                            "reason": selection_reason,
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
                # Replay does not refetch or consume network budget, but it is an explicit
                # current-execution evidence use so lifecycle state remains restart-safe.
                replayed = dict(previous)
                ref = bridge.persist("evidence-research", replayed)
                bridge.store.event(
                    bridge.thread,
                    "evidence-research",
                    {
                        "target_binding": target_binding,
                        "ref": ref,
                        "execution_id": execution_id,
                        "role": role,
                        "replayed_verified_result": True,
                    },
                )
                return replayed
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
                    {
                        "target_binding": target_binding,
                        "ref": ref,
                        "execution_id": execution_id,
                        "role": role,
                    },
                )
                return reused
        used = bridge.store.db.execute(
            "SELECT COUNT(*) FROM events WHERE thread=? AND kind='research-reservation' "
            "AND json_extract(payload,'$.execution_id')=?",
            (bridge.thread, execution_id),
        ).fetchone()[0]
        if used >= RESEARCH_QUERY_LIMIT:
            raise ResearchBudgetExhausted(used)
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
            bridge.thread,
            "evidence-research",
            {
                "target_binding": target_binding,
                "ref": ref,
                "execution_id": execution_id,
                "role": role,
            },
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
        protein_chain_ids = frozenset(inventory.protein_chain_ids)
        chains = [
            chain
            for chain in inventory.chains
            if chain.author_chain_id == request.auth_chain
            and chain.author_chain_id in protein_chain_ids
            and bool(chain.deposited_sequence or chain.sequence)
        ]
        if len(chains) != 1:
            raise AgentBoundaryError(
                "Reference comparison requires one exact original protein auth chain"
            )
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
        execution = self.bridge.store.latest_execution(self.bridge.thread)
        self.bridge.store.event(
            self.bridge.thread,
            "evidence-research",
            {
                "target_binding": identity(self.bridge.binding()),
                "ref": result_ref,
                "execution_id": execution["execution_id"] if execution else None,
                "role": "target",
            },
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
        target, facts, facts_ref = self.bridge.site_facts()

        def summary(value: dict[str, Any]) -> dict[str, Any]:
            return {
                "identity": value["identity"],
                "topology": value["topology"],
                "membrane": value["membrane"],
                "state": value["state"],
                "chain_graph": value["chain_graph"],
                "candidates": value["candidates"],
                "warnings": value["warnings"],
                "avoid": value["avoid"],
                "approved_design_mapping": value["approved_design_mapping"],
            }

        # GPCRdb acquisition atomically creates this deterministic kernel. A later
        # analyze_receptor_context call is the model-facing read of that artifact,
        # not permission to recompute it. Reuse only the current Target binding and
        # requested original auth chain.
        for evidence_query in self.snapshot()["queries"]:
            for existing in evidence_query["cards"]:
                if existing.get("provider") != "EasyDesign GPCR kernel":
                    continue
                analysis_ref = next(
                    (
                        ref
                        for ref in reversed(existing.get("source_refs", []))
                        if ref.get("artifact_id") == "research-receptor-analysis"
                    ),
                    None,
                )
                if analysis_ref is None or card["context_ref"] not in existing.get(
                    "source_refs", []
                ):
                    continue
                candidates = self.bridge.document(analysis_ref)
                if (
                    candidates.get("identity", {}).get("receptor_chain") != request.auth_chain
                    or candidates.get("approved_design_mapping", {}).get("target_binding")
                    != target["binding"]
                ):
                    continue
                return {
                    **summary(candidates),
                    "card_id": existing["card_id"],
                    "analysis_ref": analysis_ref,
                    "reused": True,
                }

        path = self.bridge.validate_project().source_path
        analysis = analyze_structure(path, request.auth_chain, context["topology"])
        candidates = generate_candidates(analysis, context)
        from .site_evidence import receptor_candidate_mapping

        hard_facts = target["evidence"]["hard_facts"]
        candidates = {
            **candidates,
            "approved_design_mapping": {
                **receptor_candidate_mapping(
                    facts,
                    candidates,
                    approved_accession=hard_facts["canonical_accession"],
                    approved_auth_chain=hard_facts["selected_chain"],
                ),
                "target_binding": target["binding"],
                "source_refs": [facts_ref],
            },
        }
        ref = self.bridge.persist("research-receptor-analysis", candidates)
        summary_value = summary(candidates)
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
                    "passage": json.dumps(summary_value),
                    "source_verified": True,
                    "source_refs": [*card["source_refs"], facts_ref, ref],
                    "does_not_support": ["Automatic site approval or binding efficacy"],
                }
            ],
        }
        result_ref = self.bridge.persist("evidence-research", result)
        execution = self.bridge.store.latest_execution(self.bridge.thread)
        self.bridge.store.event(
            self.bridge.thread,
            "evidence-research",
            {
                "target_binding": identity(self.bridge.binding()),
                "ref": result_ref,
                "execution_id": execution["execution_id"] if execution else None,
                "role": "site",
            },
        )
        return {
            **summary_value,
            "card_id": card_id,
            "analysis_ref": ref,
            "reused": False,
        }

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
                    **(
                        _uniprot_reference_projection(row)
                        if q.operation == "uniprot-record"
                        else {}
                    ),
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
            view = _pdb_view(entry, polymers)
            limitations = [
                "Deposited assembly and partners are not proof of physiological context."
            ]
            approved_accession = None
            approved_mapping: list[dict[str, Any]] | None = None
            approved_source_pdb_id = None
            approved_source_auth_chain = None
            approved_target_ref = None
            approved_source_path: Path | None = None
            try:
                target, target_facts, approved_target_ref = self.bridge.site_facts()
                hard_facts = target["evidence"]["hard_facts"]
                value = hard_facts.get("canonical_accession")
                if isinstance(value, str) and value:
                    approved_accession = value
                approved_source_path = self.bridge.validate_project().source_path
                approved_source_pdb_id = _verified_deposited_structure_id(approved_source_path)
                selected_chain = hard_facts.get("selected_chain")
                if isinstance(selected_chain, str) and selected_chain:
                    approved_source_auth_chain = selected_chain
                rows = target_facts.get("observed_facts", {}).get("mapping")
                if isinstance(rows, list):
                    approved_mapping = [row for row in rows if isinstance(row, dict)]
            except (AttributeError, AgentBoundaryError, KeyError, TypeError):
                pass
            if q.topic == "structure-complex" and approved_accession:
                try:
                    coordinates = rcsb_mmcif(client, code)
                    analysis_path = coordinates.artifact_path
                    use_approved_source_coordinates = bool(
                        approved_source_pdb_id
                        and code == str(approved_source_pdb_id).strip().upper()
                        and approved_source_auth_chain
                        and approved_source_path is not None
                    )
                    if use_approved_source_coordinates:
                        assert approved_source_path is not None
                        analysis_path = approved_source_path
                    view["complex_interface_analysis"] = _pdb_complex_interface_view(
                        analysis_path,
                        pdb_id=code,
                        polymers=polymers,
                        approved_accession=approved_accession,
                        approved_mapping=approved_mapping,
                        approved_source_pdb_id=approved_source_pdb_id,
                        approved_source_auth_chain=approved_source_auth_chain,
                        approved_source_coordinates=use_approved_source_coordinates,
                    )
                    limitations.append(
                        "Interface residues are coordinate-derived heavy-atom contacts, not "
                        "independent functional or competition evidence."
                    )
                except (BackendContractError, FileNotFoundError, StructureAnalysisError) as error:
                    view["complex_interface_analysis"] = {
                        "status": "analysis-unavailable",
                        "pdb_id": code,
                        "approved_accession": approved_accession,
                        "interfaces": [],
                        "scope": "Coordinate-derived interface analysis was unavailable.",
                        "error_type": type(error).__name__,
                    }
                    limitations.append(
                        "Coordinate-derived interface analysis was unavailable; no interface "
                        "absence may be inferred."
                    )
            return [
                {
                    "provider": "RCSB",
                    "identifier": code,
                    "primary_eligible": True,
                    "evidence_level": (
                        "deposition-polymer-entities-and-coordinate-contacts"
                        if view.get("complex_interface_analysis", {}).get("status") == "observed"
                        else "deposition-and-polymer-entities"
                    ),
                    "passage": compact(view),
                    **(
                        {"context_ref": approved_target_ref}
                        if approved_target_ref is not None
                        and view.get("complex_interface_analysis", {}).get("coordinate_source")
                        == "approved-target-source"
                        else {}
                    ),
                    "_sections": _pdb_sections(view),
                    "truncated": False,
                    "limitations": limitations,
                }
            ]
        # Existing adapter verifies receptor identity/family; no arbitrary endpoint tool.
        # GPCRdb entry names are database-specific (for example NK2R_HUMAN rather than
        # the HGNC mnemonic TACR2_HUMAN). When an Agent-supplied entry is absent, use
        # the already approved canonical accession as a deterministic identity lookup.
        # The adapter independently verifies that the resolved record has that accession.
        approved_accession = None
        try:
            target, _, _ = self.bridge.site_facts()
            value = target["evidence"]["hard_facts"].get("canonical_accession")
            if isinstance(value, str) and value:
                approved_accession = value
        except (AttributeError, AgentBoundaryError, KeyError, TypeError):
            pass
        adapter = GpcrdbAdapter(client)
        resolution = {
            "requested_identifier": q.identifier,
            "method": "entry",
            "approved_accession_fallback": None,
        }
        if approved_accession and q.identifier.upper() == approved_accession.upper():
            context = adapter.fetch_receptor_context(
                accession=approved_accession, pdb_code=q.pdb_id
            )
            resolution["method"] = "approved-accession"
        else:
            try:
                context = adapter.fetch_receptor_context(entry=q.identifier, pdb_code=q.pdb_id)
            except BackendContractError as error:
                if approved_accession is None or "status=404" not in str(error):
                    raise
                context = adapter.fetch_receptor_context(
                    accession=approved_accession, pdb_code=q.pdb_id
                )
                resolution.update(
                    method="approved-accession-after-entry-404",
                    approved_accession_fallback=approved_accession,
                )
        projection = {
            **context.legacy_projection(),
            "identifier_resolution": resolution,
        }
        return [
            {
                "provider": "GPCRdb",
                "identifier": q.identifier,
                "resolved_identifier": projection["identity"]["entry_name"],
                "identifier_resolution": resolution,
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

    def validate_questions(self, conclusions: Sequence[ResearchAssessment]) -> dict[str, Any]:
        snapshot = self.snapshot()
        queries = snapshot["queries"]
        cards = {c["card_id"]: c for r in queries for c in r["cards"]}
        used_refs = []
        if any(use.card_id not in cards for c in conclusions for use in c.evidence):
            raise AgentBoundaryError("Evidence source identifier was not retrieved in this thread")
        query_by_id = {q["query_id"]: q for q in queries}
        unknown = {key for c in conclusions for key in c.query_ids if key not in query_by_id}
        errors = []
        question_binding_errors = []
        question_binding_indices = []
        citation_errors = []
        citation_findings = []
        citation_repair_keys = []
        citation_copy_blocks: dict[str, dict[str, Any]] = {}
        has_unkeyed_citation_error = False
        role_errors = []
        if unknown:
            errors.append(
                "Unknown evidence query IDs: "
                + compact(sorted(unknown))
                + ". Copy complete issued query_id values, including page suffixes; "
                "do not derive them from cursors."
            )
        for index, conclusion in enumerate(conclusions):
            scope = f"question[{index}]: "
            relevant = [query_by_id[key] for key in conclusion.query_ids if key in query_by_id]
            bounded_without_queries = (
                not query_by_id
                and not conclusion.query_ids
                and conclusion.status in {"NOT_SEARCHED", "UNRESOLVED"}
                and not conclusion.evidence
            )
            if not bounded_without_queries and (
                conclusion.status == "NOT_SEARCHED" or not relevant
            ):
                question_binding_indices.append(index)
                question_binding_errors.append(
                    scope
                    + "Decision question has status NOT_SEARCHED or no relevant issued query. "
                    "Bind only actual relevant Runtime-issued query_ids and use an honest searched "
                    "status. If no issued query is relevant, remove this item from "
                    "decision_questions and preserve the material gap in stopping_reason and "
                    "unresolved_questions. Do not invent an ID, relabel an unperformed inquiry, "
                    "or issue new research during finalization."
                )
            if conclusion.status == "SEARCHED_NO_EVIDENCE" and (
                conclusion.evidence
                or any(q["errors"] for q in relevant)
                or not any(
                    q.get("query", {}).get("operation", "").endswith("search") for q in relevant
                )
            ):
                errors.append(
                    scope + "A source failure, cited evidence or acquisition without a search "
                    "is not SEARCHED_NO_EVIDENCE"
                )
            if (
                conclusion.status in {"VERIFIED", "CONFLICTING_EVIDENCE"}
                and not conclusion.evidence
            ):
                errors.append(scope + "Scientific support/conflict requires source-bound passages")
            if conclusion.status == "CONFLICTING_EVIDENCE" and not {
                "supports",
                "contradicts",
            }.issubset({e.relation for e in conclusion.evidence}):
                errors.append(
                    scope + "Conflict requires both supporting and contradicting source passages"
                )
            verified_support = False
            for use in conclusion.evidence:
                card = cards.get(use.card_id)
                if card is None:
                    raise AgentBoundaryError(
                        "Evidence source identifier was not retrieved in this thread"
                    )
                if card.get("corpus_ref") or _text(use.excerpt) not in _text(card["passage"]):
                    is_receipt = bool(card.get("corpus_ref"))
                    citation_findings.append((index, use.card_id, is_receipt))
                    citation_errors.append(
                        scope + "CITATION_MISMATCH for known source " + use.card_id + ": "
                        "Use a verbatim substring of the exact focused retrieved passage, "
                        "including its spacing, not a paraphrase or acquisition receipt. "
                        "For unread/unavailable sources retain the access limit and UNRESOLVED; "
                        "do not invent support."
                        + (
                            " This is an acquisition receipt, not a focused passage."
                            if card.get("corpus_ref")
                            else " The exact already-read passage remains in Runtime-owned "
                            "evidence data."
                        )
                    )
                    if card.get("corpus_ref"):
                        has_unkeyed_citation_error = True
                    else:
                        citation_repair_keys.append("known-source:" + use.card_id)
                        passage = _text(card["passage"])
                        block = citation_copy_blocks.setdefault(
                            use.card_id,
                            {
                                "card_id": use.card_id,
                                "passage": passage,
                                "passage_sha256": hashlib.sha256(
                                    passage.encode("utf-8")
                                ).hexdigest(),
                                "passage_chars": len(passage),
                                "locations": [],
                            },
                        )
                        location = {"kind": "decision-question", "question_index": index}
                        if location not in block["locations"]:
                            block["locations"].append(location)
                policy = evidence_strength_policy(card)
                if use.strength not in allowed_evidence_strengths(card):
                    role_errors.append(
                        scope
                        + f"EVIDENCE_ROLE_MISMATCH: {use.card_id} has "
                        + f"source_use_class={policy['source_use_class']} and "
                        + f"allowed_strengths={policy['allowed_strengths']} but was assigned "
                        + f"strength={use.strength}. Use an allowed strength without changing "
                        + "source identity. If no supporting E1/E2 passage is allowed, keep "
                        + "the claim unresolved."
                    )
                elif use.relation == "supports" and use.strength in {"E1", "E2"}:
                    verified_support = True
                used_refs.extend(card["source_refs"])
            if conclusion.status == "VERIFIED" and not verified_support:
                errors.append(
                    scope
                    + "VERIFIED requires at least one supporting passage assigned E1/E2 "
                    + "within that card's Runtime-owned allowed_strengths; contradicting, "
                    + "scope-limit or E3/E4 context does not satisfy this floor"
                )
        if role_errors:
            eligible = sorted(
                card_id
                for card_id, card in cards.items()
                if set(allowed_evidence_strengths(card)) & {"E1", "E2"}
                and card_id.startswith("passage-")
            )
            raise EvidenceRoleMismatch(
                "\n".join(role_errors)
                + ("\n" + "\n".join(errors) if errors else "")
                + "\nRuntime-owned E1/E2-eligible focused passage card_ids: "
                + compact(eligible)
                + ". Do not change source identity or invent support."
            )
        if errors or question_binding_errors or citation_errors:
            # Validate the whole opinion in one pass. Serial first-error feedback spent
            # the unchanged two corrections on independent mistakes in the same DTO.
            # Integrity/source-identity failures above remain fatal; nothing is accepted,
            # normalized, inferred or rewritten on the model's behalf.
            diagnostic = "\n".join(errors + question_binding_errors + citation_errors)
            if unknown:
                diagnostic += "\nAvailable complete query_ids: " + compact(sorted(query_by_id))
            if question_binding_errors and citation_errors and not errors:
                raise ResearchQuestionCitationMismatch(
                    diagnostic,
                    question_indices=question_binding_indices,
                    citation_findings=citation_findings,
                    citation_repair_keys=(sorted(set(citation_repair_keys))),
                    citation_unkeyed=has_unkeyed_citation_error,
                    citation_copy_blocks=[
                        citation_copy_blocks[key] for key in sorted(citation_copy_blocks)
                    ],
                )
            if question_binding_errors and not errors and not citation_errors:
                raise ResearchQuestionBindingMismatch(diagnostic)
            if errors or question_binding_errors:
                raise ResearchConclusionMismatch(diagnostic)
            repair_keys = sorted(set(citation_repair_keys))
            raise EvidenceCitationMismatch(
                diagnostic,
                repair_keys=repair_keys,
                citation_findings=citation_findings,
                citation_unkeyed=has_unkeyed_citation_error,
                citation_copy_blocks=[
                    citation_copy_blocks[key] for key in sorted(citation_copy_blocks)
                ],
            )
        return {
            "source_snapshot": snapshot,
            "source_refs": used_refs,
            "authority": (
                "Source binding verified; scientific conclusions remain specialist opinions "
                "for independent Judge review."
            ),
        }


def research_tool(bridge: Any, role: str) -> Any:
    from langchain_core.tools import StructuredTool

    async def acquire(**arguments: Any) -> str:
        query = ResearchQuery.model_validate(arguments)
        worker = EvidenceResearch(bridge)
        result = worker.acquire(query, role=role)
        receptor_analysis = None
        automatic_interface_read = None
        if (
            role == "site"
            and query.operation == "structure-record"
            and query.topic == "structure-complex"
            and not result["errors"]
        ):
            interface_cards = [
                card
                for card in result["cards"]
                if card.get("provider") == "RCSB"
                and card.get("evidence_level")
                == "deposition-polymer-entities-and-coordinate-contacts"
            ]
            if len(interface_cards) == 1:
                source = interface_cards[0]
                automatic_interface_read = EvidenceCorpus(bridge).retrieve(
                    RetrieveEvidence(
                        need="PPI_INTERFACE",
                        question=(
                            "target contact mapping canonical positions current design labels "
                            "partner identity coordinate interface"
                        ),
                        source_id=source_key(source["provider"], source["identifier"]),
                        page_size=1,
                    )
                )
        if role == "site" and query.operation == "gpcrdb-context" and not result["errors"]:
            context_cards = [
                card
                for card in result["cards"]
                if card["provider"] == "GPCRdb" and card.get("context_ref")
            ]
            if len(context_cards) != 1:
                raise AgentBoundaryError(
                    "A verified GPCRdb acquisition must resolve one receptor context card"
                )
            target, _, _ = bridge.site_facts()
            auth_chain = target["evidence"]["hard_facts"].get("selected_chain")
            if not isinstance(auth_chain, str) or not auth_chain:
                raise AgentBoundaryError(
                    "Automatic receptor analysis requires the approved original auth chain"
                )
            source = context_cards[0]
            source_refs = source.get("source_refs", [])
            existing = next(
                (
                    card
                    for evidence_query in worker.snapshot()["queries"]
                    for card in evidence_query["cards"]
                    if card["provider"] == "EasyDesign GPCR kernel"
                    and all(ref in card.get("source_refs", []) for ref in source_refs)
                ),
                None,
            )
            if existing is None:
                analysis = worker.analyze_receptor(
                    ReceptorAnalysis(gpcrdb_card_id=source["card_id"], auth_chain=auth_chain)
                )
                receptor_analysis = {
                    "card_id": analysis["card_id"],
                    "analysis_ref": analysis["analysis_ref"],
                    "auth_chain": auth_chain,
                    "reused": False,
                }
            else:
                receptor_analysis = {
                    "card_id": existing["card_id"],
                    "analysis_ref": existing["source_refs"][-1],
                    "auth_chain": auth_chain,
                    "reused": True,
                }
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
                    "resolved_identifier",
                    "identifier_resolution",
                    "title",
                    "year",
                    "doi",
                    "pmcid",
                    "evidence_level",
                    "chunk_count",
                    "entry_type",
                    "canonical_reference_eligible",
                    "identifier_resolution",
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
                    "Runtime has computed the deterministic receptor kernel for this card and "
                    "will project its verified topology, membrane frame, chain graph and mapped "
                    "candidates automatically on the next Site research decision call."
                )
            if arguments["operation"].endswith("search"):
                view["snippet"] = card["passage"][:450]
                view["relevance"] = "Query match only; select before deeper reading"
            cards.append(view)
        return compact(
            {
                "query_id": result["query_id"],
                "status": result["status"],
                "topic": result["topic"],
                "need": NEEDS[result["topic"]],
                "cards": cards,
                "errors": result["errors"],
                **(
                    {
                        "automatic_interface_read": {
                            **automatic_interface_read,
                            "authority": (
                                "Runtime-derived source-bound coordinate contacts and exact "
                                "mapping correspondence only; Site still owns scientific "
                                "ranking and the Scientist still owns approval."
                            ),
                        }
                    }
                    if automatic_interface_read is not None
                    else {}
                ),
                **(
                    {
                        "automatic_receptor_analysis": {
                            **receptor_analysis,
                            "authority": (
                                "Deterministic topology, membrane-frame, chain-graph and "
                                "candidate derivation only; Site still owns ranking and the "
                                "Scientist still owns approval."
                            ),
                        }
                    }
                    if receptor_analysis is not None
                    else {}
                ),
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
            "the exact topic and acquire it atomically through the existing corpus. The one "
            "exception is Site gpcrdb-context for the approved canonical receptor: Runtime "
            "binds that mandatory deterministic context and the adapter verifies identity. "
            "Alternatively call select_evidence first. Full records stay in the corpus; "
            "Use identifier for the source key (PMID/PMCID/accession/PDB code). "
            "Selection need must match query topic: identity=TARGET_IDENTITY, "
            "state=STRUCTURE_STATE, structure-complex=PPI_INTERFACE, "
            "function=FUNCTIONAL_MECHANISM, epitope=KNOWN_EPITOPE. "
            "For a selected Site structure-complex with observed target-partner contacts, "
            "the same call returns an automatic focused interface passage and records it for "
            "scientific synthesis; do not rediscover or manually remap those Runtime facts. "
            "Otherwise use retrieve_evidence for passages and source card IDs. "
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
