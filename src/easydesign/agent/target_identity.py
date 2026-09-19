"""Canonical evidence and proposals routed through the unchanged Stage 01 services."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from pydantic import Field

from easydesign.backends.target_sources.structure import inventory_structure
from easydesign.core import sha256_file
from easydesign.core.target_identity import (
    ConstructRelationship,
    TargetIdentityReport,
    resolve_target_identity,
)
from easydesign.orchestration.config import EasyDesignRunConfig
from easydesign.orchestration.local_project import publish_config_revision, resolve_project_run
from easydesign.orchestration.stage01_sources import _scope, _uniprot_identity

from .contracts import AgentBoundaryError, ShortText, StrictDTO
from .evidence_research import EvidenceResearch
from .session_store import compact, confined, identity


class CanonicalProposal(StrictDTO):
    uniprot_card_id: str = Field(min_length=1, max_length=80)
    reason: ShortText


def explicit_canonical_identity_request(text: str) -> bool:
    """Recognize an explicit request to resolve the target against a canonical source."""
    value = text.casefold()
    return any(
        re.search(pattern, value, re.IGNORECASE)
        for pattern in (
            r"(?:resolve|verify|confirm|establish).{0,32}(?:target|biological|canonical).{0,16}identity",
            r"canonical.{0,16}(?:identity|reference|sequence)",
            r"(?:target|biological).{0,16}identity.{0,16}(?:resolution|verification)",
            r"(?:解析|确认|核实|验证).{0,16}(?:目标|靶标|生物学|规范).{0,8}(?:身份|序列)",
            r"(?:目标|靶标).{0,8}(?:身份|规范序列).{0,16}(?:解析|确认|核实|验证)",
        )
    )


def deposited_uniprot_leads(metadata: dict[str, Any]) -> list[str]:
    """Return distinct depositor-supplied UniProt accessions without treating them as proof."""
    leads: list[str] = []
    for entity in metadata.get("entities", []):
        for reference in entity.get("deposited_database_references", []):
            database = str(reference.get("database_name", "")).casefold()
            accession = reference.get("accession")
            if database in {"unp", "uniprot", "uniprotkb"} and isinstance(accession, str):
                value = accession.strip()
                if value and value not in leads:
                    leads.append(value)
    return leads


def constant_canonical_offset(report: TargetIdentityReport) -> int | None:
    """Display an offset only when every existing kernel mapping row proves it."""
    rows = report.design_scope.residues
    if report.ambiguities or not rows or any(r.canonical_position is None for r in rows):
        return None
    if [r.construct_position for r in rows] != list(
        range(1, report.construct_identity.sequence_length + 1)
    ):
        return None
    offsets = {
        r.canonical_position - r.construct_position
        for r in rows
        if r.canonical_position is not None
    }
    return offsets.pop() if len(offsets) == 1 else None


def deposited_polymer_metadata(source: Path) -> dict[str, Any]:
    """Project depositor annotations from the caller's verified frozen input; no alignment."""
    rows: list[dict[str, Any]] = []
    if source.suffix.lower() in {".cif", ".mmcif"}:
        import gemmi

        block = gemmi.cif.read_file(str(source)).sole_block()
        entities = block.get_mmcif_category("_entity.")
        polymers = block.get_mmcif_category("_entity_poly.")
        asym = block.get_mmcif_category("_struct_asym.")
        descriptions = dict(
            zip(entities.get("id", []), entities.get("pdbx_description", []), strict=False)
        )
        labels = list(zip(asym.get("id", []), asym.get("entity_id", []), strict=False))
        source_annotations = block.get_mmcif_category("_entity_src_gen.")
        segments: dict[str, list[dict[str, Any]]] = {}
        for i, entity in enumerate(source_annotations.get("entity_id", [])):
            annotation = {}
            for key in (
                "pdbx_beg_seq_num",
                "pdbx_end_seq_num",
                "pdbx_gene_src_scientific_name",
                "pdbx_gene_src_ncbi_taxonomy_id",
            ):
                values = source_annotations.get(key, [])
                annotation[key] = values[i] if i < len(values) else None
            segments.setdefault(entity, []).append(annotation)
        deposited_references = block.get_mmcif_category("_struct_ref.")
        references: dict[str, list[dict[str, Any]]] = {}
        for i, entity in enumerate(deposited_references.get("entity_id", [])):
            reference = {}
            for source_key, output_key in (
                ("db_name", "database_name"),
                ("db_code", "database_code"),
                ("pdbx_db_accession", "accession"),
                ("pdbx_db_isoform", "isoform"),
            ):
                values = deposited_references.get(source_key, [])
                value = values[i] if i < len(values) else None
                reference[output_key] = None if value in {None, "?", "."} else value
            references.setdefault(entity, []).append(reference)
        types = polymers.get("type", [])
        all_strands = polymers.get("pdbx_strand_id", [])
        for i, entity in enumerate(polymers.get("entity_id", [])):
            strands = all_strands[i] if i < len(all_strands) else None
            rows.append(
                {
                    "entity_id": entity,
                    "deposited_description": descriptions.get(entity),
                    "deposited_source_segments": segments.get(entity, []),
                    "deposited_database_references": references.get(entity, []),
                    "polymer_type": types[i] if i < len(types) else None,
                    "source_label_chain_ids": [
                        label for label, parent in labels if parent == entity
                    ],
                    "source_auth_chain_ids": [x.strip() for x in strands.split(",")]
                    if isinstance(strands, str) and strands not in {"?", "."}
                    else [],
                }
            )
    return {
        "status": "reported" if rows else "not-reported-in-input",
        "authority": "Depositor annotations in the checksum-verified frozen input. "
        "Descriptions are source annotations, not identities inferred from alignment "
        "and not proof of biological state, processing or function.",
        "entities": rows,
    }


def has_current_identity_view(bridge: Any, source_id: str, *, after_seq: int = 0) -> bool:
    """Require actual focused passages for this source and current project binding."""
    binding = identity(bridge.binding())
    for event in reversed(bridge.store.events(bridge.thread)):
        if event["seq"] <= after_seq:
            break
        if event["kind"] == "evidence-view":
            view = bridge.document(event["payload"]["ref"])
            if view.get("need") == "TARGET_IDENTITY" and any(
                c.get("source_id") == source_id
                and c.get("binding_context", {}).get("current_binding") == binding
                for c in view.get("cards", [])
            ):
                return True
    return False


def pending_canonical_source_read(bridge: Any) -> str | None:
    """A canonical config revision requires its selected source in the new evidence view."""
    revisions = [
        e for e in bridge.store.events(bridge.thread) if e["kind"] == "canonical-reference-proposal"
    ]
    if not revisions:
        return None
    revision = revisions[-1]
    source_id = "UniProt:" + revision["payload"]["accession"]
    return (
        None
        if has_current_identity_view(bridge, source_id, after_seq=revision["seq"])
        else source_id
    )


def propose_canonical(bridge: Any, request: CanonicalProposal) -> dict[str, Any]:
    """Configure a verified reference before preparation; this is not an approval."""
    with bridge.store.writer():
        loaded = bridge.validate_project()
        cards = [
            c
            for q in EvidenceResearch(bridge).snapshot()["queries"]
            for c in q["cards"]
            if c["card_id"] == request.uniprot_card_id
            and c["provider"] == "UniProt"
            and c["evidence_level"] == "official-database"
        ]
        # Publishing the reference changes the config binding. A replay can still
        # verify the exact prior source and confirm the already configured value.
        # An old-binding source is never allowed to change a different reference.
        replay = not cards
        if replay and loaded.config.target.source.identity.uniprot_accession:
            cards = [
                card
                for event in bridge.store.events(bridge.thread)
                if event["kind"] == "evidence-research"
                for card in bridge.document(event["payload"]["ref"])["cards"]
                if card["card_id"] == request.uniprot_card_id
                and card["provider"] == "UniProt"
                and card["evidence_level"] == "official-database"
            ]
        if not cards:
            raise AgentBoundaryError(
                "Canonical proposal requires an acquired official UniProt card"
            )
        card = cards[0]
        records = [bridge.document(ref) for ref in card["source_refs"]]
        records = [r for r in records if r.get("primaryAccession") == card["identifier"]]
        if len(records) != 1:
            raise AgentBoundaryError("Canonical source record is not unique")
        accession, _, source_identity = _uniprot_identity(records[0])
        current = loaded.config.target.source.identity
        if current.taxon_id and current.taxon_id != source_identity["taxonomy_id"]:
            raise AgentBoundaryError(
                "Canonical source conflicts with the scientist-configured species"
            )
        if (
            current.uniprot_accession == accession
            and current.taxon_id == source_identity["taxonomy_id"]
        ):
            return {
                "status": "canonical-reference-configured",
                "accession": accession,
                "next": "prepare_target; existing deterministic mapping and Gate 1 apply",
            }
        if replay:
            raise AgentBoundaryError("Stale canonical evidence cannot change the current reference")
        if resolve_project_run(bridge.project, required=False) is not None or bridge._jobs():
            raise AgentBoundaryError(
                "Existing Target science cannot be retargeted by a model. Configure t"
                "he reference before preparation."
            )
        if current.uniprot_accession and current.uniprot_accession != accession:
            raise AgentBoundaryError(
                "Model cannot replace the scientist-configured canonical identity"
            )
        if not has_current_identity_view(bridge, "UniProt:" + accession):
            return {
                "status": "REQUIRES_ACTION",
                "reason": "Acquisition is a receipt, not a focused reading of the source.",
                "source_id": "UniProt:" + accession,
                "next": "Use retrieve_evidence with need=TARGET_IDENTITY, this source_id "
                "and a focused canonical/construct identity question, then repeat this "
                "proposal. No configuration was changed; no download is needed.",
            }
        payload = loaded.config.model_dump(mode="json")
        payload["stage01"]["target"]["source"]["identity"].update(
            uniprot_accession=accession, taxon_id=source_identity["taxonomy_id"]
        )
        configured = EasyDesignRunConfig.model_validate(payload)
        prior_binding = identity(bridge.binding())
        path = publish_config_revision(bridge.project, configured)
        bridge.store.event(
            bridge.thread,
            "canonical-reference-proposal",
            {
                "prior_binding": prior_binding,
                "target_binding": identity(bridge.binding()),
                "source_refs": card["source_refs"],
                "reason": request.reason,
                "config_path": str(path.relative_to(bridge.project)),
                "accession": accession,
                "authority": "Proposal only; old mapping and decision service own approval",
            },
        )
        return {
            "status": "canonical-reference-configured",
            "accession": accession,
            "taxon_id": source_identity["taxonomy_id"],
            "next": (
                "Prior evidence cursors are invalid. Read needed TARGET_IDENTITY passages "
                "with cursor omitted in the new view, reusing the verified UniProt source. "
                "Then prepare_target, inspect construct differences and seek Gate 1 where required."
            ),
        }


def pending_canonical(
    bridge: Any, root: Path, source: Path, request: Any
) -> tuple[dict[str, Any], list[str]]:
    config = bridge.validate_project().config
    declared = config.target.source.identity
    accession = declared.uniprot_accession
    if accession is None:
        return {}, []
    paths = sorted(
        root.glob(
            f"stages/01-target-preparation/attempts/*/work/retrieval/uniprot-{accession}.json"
        )
    )
    # RunWorkspace is the source of the layout; old public runs may use attempts below stages.
    if not paths:
        paths = sorted(root.glob(f"**/work/retrieval/uniprot-{accession}.json"))
    if not paths:
        raise AgentBoundaryError("Pending canonical decision has no frozen UniProt retrieval")
    records = [(confined(root, p), json.loads(confined(root, p).read_text())) for p in paths]
    if len({sha256_file(p) for p, _ in records}) != 1:
        raise AgentBoundaryError(
            "Canonical source changed between pending attempts; reconcile before approval"
        )
    path, record = records[-1]
    observed_accession, canonical, metadata = _uniprot_identity(record)
    metadata = {**metadata, "sequence_length": len(canonical)}
    if observed_accession != accession or (
        declared.taxon_id and metadata["taxonomy_id"] != declared.taxon_id
    ):
        raise AgentBoundaryError("Canonical accession/species does not match the configured target")
    refs = [f"{path.relative_to(root).as_posix()}#sha256={sha256_file(path)}"]
    if request.gate == "scope-selection":
        return {
            "canonical": metadata,
            "scope": "human selection required; no mapping selected",
        }, refs
    _, start, end, scope = _scope(
        config, reference_sequence=canonical, features=record.get("features")
    )
    comparisons = []
    for chain in inventory_structure(source).chains:
        report = resolve_target_identity(
            target_id=config.target.target_id,
            canonical_sequence=canonical,
            construct_sequence=chain.deposited_sequence or chain.sequence,
            source_identity_status="resolved",
            source_kind="local-structure",
            accession=accession,
            isoform=declared.isoform,
            taxon_id=metadata["taxonomy_id"],
            auth_chain_id=chain.author_chain_id,
            label_chain_id=chain.label_chain_id,
            coordinate_present_construct_positions=chain.coordinate_label_seq_ids,
            declared_relationship=ConstructRelationship(declared.relationship)
            if declared.relationship
            else None,
            canonical_scope_start=start,
            canonical_scope_end=end,
        )
        comparisons.append(
            {
                "auth_chain": chain.author_chain_id,
                "relationship": str(report.relationship),
                "review_requirement": str(report.review_requirement),
                "mapping_status": str(report.design_scope.mapping_status),
                "canonical_length": report.canonical.sequence_length,
                "construct_length": report.construct_identity.sequence_length,
                "label_chain": chain.label_chain_id,
                "observed_length": len(report.observed.observed_construct_positions),
                "missing_construct_positions": list(report.observed.missing_construct_positions),
                "design_length": len(report.design_scope.sequence),
                "ambiguities": list(report.ambiguities),
                "substitutions": len(report.alignment.substitutions) if report.alignment else None,
                "insertions": len(report.alignment.insertions) if report.alignment else None,
                "deletions": len(report.alignment.deletions) if report.alignment else None,
                "constant_canonical_offset": constant_canonical_offset(report),
                "design_scope_row_count": len(report.design_scope.residues),
                "design_scope_mapped_rows": sum(
                    row.canonical_position is not None for row in report.design_scope.residues
                ),
                "design_scope_unmapped_rows": sum(
                    row.canonical_position is None for row in report.design_scope.residues
                ),
            }
        )
    return {
        "canonical": metadata,
        "scope": scope,
        "construct_comparisons": comparisons,
        "difference_semantics": (
            "deletions are canonical-to-construct alignment gaps. missing_construct_positions "
            "are construct residues lacking coordinates, not alignment gaps. A non-null "
            "constant_canonical_offset proves canonical_position=construct_position+offset "
            "for every construct row; human review does not erase this known correspondence. "
            "A null constant offset does not mean no mapping exists: inspect the mapped and "
            "unmapped design-scope row counts. These are the old engine's chosen alignment "
            "rows; ambiguity means uniqueness is unproven, not that all rows are absent. "
            "Approval cannot make an ambiguous mapping unique or fill unmapped insertions."
        ),
        "authority": (
            "Unchanged deterministic identity engine; pending human decision, not approval"
        ),
        "limitations": [
            ("Canonical identity does not establish native state, assembly, function or binding.")
        ],
    }, refs


def canonical_tool(bridge: Any) -> Any:
    from langchain_core.tools import StructuredTool

    async def propose(**arguments: Any) -> str:
        return compact(propose_canonical(bridge, CanonicalProposal.model_validate(arguments)))

    return StructuredTool.from_function(
        name="propose_canonical_identity",
        coroutine=propose,
        args_schema=CanonicalProposal,
        description=(
            "Before target preparation, bind an acquired UniProt source card as a"
            " proposed canonical reference. Runtime copies accession/species; old"
            " Stage 01 computes mapping and presents Gate 1 for consequential amb"
            "iguity. Cannot change an existing Target or replace the scientist's "
            "configured reference."
        ),
    )
