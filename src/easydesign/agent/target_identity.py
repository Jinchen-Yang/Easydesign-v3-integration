"""Canonical evidence and proposals routed through the unchanged Stage 01 services."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import Field

from easydesign.backends.target_sources.structure import inventory_structure
from easydesign.core import sha256_file
from easydesign.core.target_identity import ConstructRelationship, resolve_target_identity
from easydesign.orchestration.config import EasyDesignRunConfig
from easydesign.orchestration.local_project import publish_config_revision, resolve_project_run
from easydesign.orchestration.stage01_sources import _scope, _uniprot_identity

from .contracts import AgentBoundaryError, ShortText, StrictDTO
from .evidence_research import EvidenceResearch
from .session_store import compact, confined, identity


class CanonicalProposal(StrictDTO):
    uniprot_card_id: str = Field(min_length=1, max_length=80)
    reason: ShortText


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
                "prepare_target; inspect construct differences and seek Gate 1 where required"
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
            }
        )
    return {
        "canonical": metadata,
        "scope": scope,
        "construct_comparisons": comparisons,
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
