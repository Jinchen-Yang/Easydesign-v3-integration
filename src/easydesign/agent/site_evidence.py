"""Thin scientific adapters: use the existing structure, SASA, mapping and GPCR kernel."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from easydesign.core import load_model
from easydesign.stages.s01_target_preparation.models import ResidueMapping, TargetBundle
from easydesign.stages.s02_hotspot_discovery.annotations import sequence_motif_warnings
from easydesign.stages.s02_hotspot_discovery.automatic import run_sasa_surface_diversity
from easydesign.stages.s02_hotspot_discovery.geometry import (
    StructureContext,
    load_structure_context,
    radius_gyration,
)
from easydesign.stages.s02_hotspot_discovery.gpcr.structure_context import analyze_structure
from easydesign.stages.s02_hotspot_discovery.user_regions import normalize_manual_regions

from .contracts import AgentBoundaryError, SiteResidueQueryMismatch
from .session_store import compact, identity
from .site_contracts import BiologyContext, CanonicalMappingQuery


def structure_inputs(
    root: Path, bundle_path: Path
) -> tuple[TargetBundle, StructureContext, ResidueMapping]:
    bundle, geometry = load_structure_context(run_root=root, target_bundle_path=bundle_path)
    mapping = load_model(bundle.residue_mapping.verify(root), ResidueMapping)
    return bundle, geometry, mapping


def analyze_site_facts(
    root: Path, bundle_path: Path, biology: BiologyContext | None
) -> dict[str, Any]:
    bundle, geometry, mapping = structure_inputs(root, bundle_path)
    mapped = {e.label_seq_id: e for e in mapping.entries}
    chains = {e.source_author_chain_id or e.author_chain_id for e in mapping.entries}
    if biology is not None:
        if chains != {biology.target_auth_chain}:
            raise AgentBoundaryError(
                "BLOCKED: biology context chain conflicts with approved target"
            )
        context_labels = {r.label_seq_id for r in biology.topology}
        context_labels.update(n for f in biology.features for n in f.label_seq_ids)
        if not context_labels.issubset(mapped):
            raise AgentBoundaryError("BLOCKED: biology context contains unmapped target residues")
    # Same implementation, parameters, normalization and ensemble semantics as Stage 02.
    residues, pool, recommended = run_sasa_surface_diversity(context=geometry)
    topology = []
    if biology is not None:
        for row in biology.topology:
            entry = mapped[row.label_seq_id]
            topology.append(
                {
                    "auth_asym_id": entry.author_chain_id,
                    "auth_seq_id": entry.author_residue_id,
                    "insertion_code": entry.insertion_code or "",
                    "label_seq_id": entry.label_seq_id,
                    "amino_acid": entry.amino_acid,
                    "protein_segment": row.segment,
                }
            )
    chain = mapping.entries[0].author_chain_id
    gpcr = (
        analyze_structure(bundle.target_structure.verify(root), chain, topology)
        if biology is not None and biology.target_kind == "gpcr"
        else None
    )
    sequence = "".join(e.amino_acid for e in mapping.entries)
    motifs = [m.model_dump(mode="json") for m in sequence_motif_warnings(sequence)]
    limitations = [
        (
            "SASA describes solvent exposure of the prepared target, not binder "
            "affinity or functional relevance."
        ),
        "Region scores are existing uncalibrated geometric heuristics, not epitope probabilities.",
        (
            "No full binder docking, clash simulation, secondary-structure "
            "assignment or dynamics was performed."
        ),
        "Glycosylation motifs are sequence warnings, not observed glycan occupancy.",
        (
            "Prepared-chain exposure excludes unresolved loops, absent glycans and "
            "omitted interaction partners."
        ),
    ]
    if biology is None:
        limitations.append(
            "No biological topology, structural state, mechanism or conservation evidence supplied."
        )
    else:
        limitations.extend(biology.limitations)
        if biology.target_kind in {"membrane", "gpcr"}:
            limitations.append(
                "Membrane access must be interpreted against topology and signed "
                "geometry; SASA alone is insufficient."
            )
        if gpcr is None or not gpcr["membrane"].get("reliable"):
            limitations.append(
                "A reliable signed membrane frame is unavailable; extracellular "
                "approach is not verified."
            )
    return {
        "schema_version": "site-facts-1",
        "target_structure_sha256": bundle.target_structure.sha256,
        "mapping_sha256": bundle.residue_mapping.sha256,
        "observed_facts": {
            "mapping": [e.model_dump(mode="json") for e in mapping.entries],
            "coordinate_model_ids": list(geometry.model_ids),
        },
        "derived_metrics": {
            "sasa": residues.model_dump(mode="json"),
            "candidate_pool": pool.model_dump(mode="json"),
            "geometric_recommendations": recommended.model_dump(mode="json"),
            "sequence_motifs": motifs,
            "gpcr_geometry": gpcr,
        },
        "declared_biology": biology.model_dump(mode="json") if biology else None,
        "biology_authority": (
            "user-supplied context; coordinate mapping is validated, biological "
            "assertions are not independently certified"
        ),
        "limitations": limitations,
    }


def canonical_mapping_rows(
    analysis: dict[str, Any], query: CanonicalMappingQuery
) -> dict[str, Any]:
    """Exact lookup in the approved mapping, including unobserved/nonunique rows."""
    rows = analysis["observed_facts"]["mapping"]
    observed = {
        r["residue"]["label_seq_id"] for r in analysis["derived_metrics"]["sasa"]["residues"]
    }
    matches = []
    for position in query.canonical_positions:
        matched = [r for r in rows if r.get("canonical_position") == position]
        matches.append(
            {
                "canonical_position": position,
                "mapping_rows": matched,
                "observed_design_labels": [
                    r["label_seq_id"] for r in matched if r["label_seq_id"] in observed
                ],
                "status": "mapped" if matched else "no-approved-correspondence",
            }
        )
    return {
        "matches": matches,
        "limitations": [
            "Lookup of the already approved mapping only; no alignment, offset inference "
            "or biological interpretation was performed.",
            "Preserve every mapping_status/edit_type qualification and model_presence. "
            "A conditional or ambiguous row is not proof of a unique native correspondence.",
            "Empty mapping_rows means no correspondence in this approved design scope, "
            "not absence from the canonical protein. Empty observed_design_labels means "
            "none of its matched rows has a supplied coordinate-derived SASA row.",
            "Observed correspondence alone does not establish topology, accessibility, "
            "a valid hotspot or approval. Evaluate the returned design labels separately.",
        ],
    }


def receptor_candidate_mapping(
    facts: dict[str, Any],
    receptor: dict[str, Any],
    *,
    approved_accession: str | None,
    approved_auth_chain: str | None,
) -> dict[str, Any]:
    """Join candidate canonical positions to existing Target rows, without alignment."""
    source = receptor["identity"]
    if (
        not approved_accession
        or source.get("accession") != approved_accession
        or not approved_auth_chain
        or source.get("receptor_chain") != approved_auth_chain
    ):
        raise AgentBoundaryError(
            "GPCR candidate reference/chain differs from the approved Target; "
            "canonical correspondences cannot be transferred between targets."
        )
    positions = sorted(
        {
            row["gpcrdb_sequence_number"]
            for candidates in receptor["candidates"].values()
            for candidate in candidates
            for row in candidate["residues"]
            if row.get("gpcrdb_sequence_number") is not None
        }
    )
    matches = [
        match
        for start in range(0, len(positions), 6)
        for match in canonical_mapping_rows(
            facts, CanonicalMappingQuery(canonical_positions=positions[start : start + 6])
        )["matches"]
    ]
    return {
        "canonical_accession": approved_accession,
        "source_auth_chain": approved_auth_chain,
        "requested_canonical_positions": positions,
        "unmapped_canonical_positions": [
            match["canonical_position"] for match in matches if not match["mapping_rows"]
        ],
        "facts": [
            {
                "mapping": row,
                "coordinate_observed": row["label_seq_id"] in match["observed_design_labels"],
            }
            for match in matches
            for row in match["mapping_rows"]
        ],
        "limitations": [
            "Exact lookup in the approved Target mapping, not a new alignment or offset. "
            "Each label_seq_id is an approved design label; source receptor labels are separate.",
            "All matching rows, nulls, edit_type, mapping_status and model_presence are retained. "
            "Conditional/nonunique correspondence remains conditional; unobserved rows "
            "are not valid coordinate-backed hotspots.",
            "Candidate inventory and mutation-record counts do not establish the only possible "
            "epitope, whole-VHH access, functional efficacy or a preferred ranking.",
        ],
    }


def summarize_site_facts(
    analysis: dict[str, Any], *, labels: list[int], offset: int = 0, limit: int = 12
) -> dict[str, Any]:
    metrics = analysis["derived_metrics"]
    rows = metrics["sasa"]["residues"]
    available = {r["residue"]["label_seq_id"] for r in rows}
    if not set(labels).issubset(available):
        ranges: list[list[int]] = []
        for label in sorted(available):
            if ranges and label == ranges[-1][1] + 1:
                ranges[-1][1] = label
            else:
                ranges.append([label, label])
        raise SiteResidueQueryMismatch(
            "BLOCKED read-only query: unmapped or unobserved design labels "
            + compact(sorted(set(labels) - available))
            + ". Canonical, source-author, source-label and normalized design numbering "
            "are not interchangeable. Do not invent an offset. Observed design-label "
            "inclusive ranges (at most first40 ranges shown): "
            + compact(ranges[:40])
            + ". For canonical positions use read_canonical_mapping first; otherwise use exact "
            "approved mapping/candidate labels for a focused question. "
            "No rows were returned and no hotspot/proposal/approval was changed."
        )
    selected = [r for r in rows if not labels or r["residue"]["label_seq_id"] in labels]
    page = selected[offset : offset + limit]
    mappings = {r["label_seq_id"]: r for r in analysis["observed_facts"]["mapping"]}
    biology = analysis["declared_biology"]
    topology = {r["label_seq_id"]: r["segment"] for r in biology["topology"]} if biology else {}
    gpcr = metrics["gpcr_geometry"]
    return {
        "facts": [
            {
                "mapping": mappings[r["residue"]["label_seq_id"]],
                "raw_sasa": r["raw_sasa"],
                "rsasa": r["rsasa"],
                "model_presence_fraction": r["model_presence_fraction"],
                "surface_eligible": r["eligible"],
                "declared_topology": topology.get(r["residue"]["label_seq_id"]),
            }
            for r in page
        ],
        "offset": offset,
        "page_total": len(selected),
        "next_offset": offset + len(page) if offset + len(page) < len(selected) else None,
        "mapped_residue_count": len(rows),
        "candidate_patches": [
            {
                "name": r["region_id"],
                "label_seq_ids": [m["label_seq_id"] for m in r["members"]],
                "metrics": r["metrics"],
            }
            for r in metrics["geometric_recommendations"]["regions"]
        ],
        "candidate_status": metrics["geometric_recommendations"]["status"],
        "sequence_motifs": metrics["sequence_motifs"],
        "biology": {
            **biology,
            "topology": "See declared_topology in the paginated residue rows",
            "topology_residue_count": len(biology["topology"]),
        }
        if biology
        else None,
        "biology_authority": analysis["biology_authority"],
        "membrane_geometry": gpcr["membrane"] if gpcr else {"status": "not-available"},
        "geometry_warnings": gpcr["warnings"] if gpcr else [],
        "limitations": analysis["limitations"],
    }


def evaluate_site(
    root: Path, bundle_path: Path, analysis: dict[str, Any], labels: list[int]
) -> dict[str, Any]:
    bundle, geometry, mapping = structure_inputs(root, bundle_path)
    known = {e.label_seq_id for e in mapping.entries}
    if not labels or len(labels) != len(set(labels)) or not set(labels).issubset(known):
        return {
            "status": "BLOCKED",
            "cause": "invalid-approved-mapping",
            "remedy": "Select existing unique labels from the approved target mapping.",
        }
    if not set(labels).issubset(geometry.models[geometry.representative_model_id].residues):
        return {
            "status": "BLOCKED",
            "cause": "missing-required-coordinates",
            "remedy": "Revise the selected region or supply a reviewed structure containing it.",
        }
    biology = analysis["declared_biology"]
    excluded = (
        {n for f in biology["features"] if f["kind"] == "exclude" for n in f["label_seq_ids"]}
        if biology
        else set()
    )
    if set(labels) & excluded:
        return {
            "status": "BLOCKED",
            "cause": "explicit-excluded-region",
            "remedy": "Change the hotspot or explicitly revise the upstream exclusion constraint.",
        }
    regions, _, validation = normalize_manual_regions(
        bundle=bundle,
        context=geometry,
        mapping=mapping,
        numbering="label",
        chain=None,
        configured_regions=[("A", tuple(str(n) for n in sorted(labels)))],
        input_config_sha256=identity({"label_seq_ids": sorted(labels)}),
    )
    metrics = analysis["derived_metrics"]
    selected = [r for r in metrics["sasa"]["residues"] if r["residue"]["label_seq_id"] in labels]
    warnings = list(validation.warnings)
    if any(not r["eligible"] for r in selected):
        warnings.append(
            "One or more hotspot residues fail the existing surface-exposure "
            "criterion; binding approach may be poor."
        )
    overlapping = [m for m in metrics["sequence_motifs"] if set(m["label_seq_ids"]) & set(labels)]
    if overlapping:
        warnings.append(
            "Potential glycosylation motif overlaps this region; occupancy and "
            "shielding are unverified."
        )
    features = (
        [f for f in biology["features"] if set(f["label_seq_ids"]) & set(labels)] if biology else []
    )
    if any(f["kind"] in {"glycan", "ptm"} for f in features):
        warnings.append(
            "Supplied glycan/PTM evidence overlaps this region; steric shielding requires review."
        )
    segments = (
        {r["segment"] for r in biology["topology"] if r["label_seq_id"] in labels}
        if biology
        else set()
    )
    if any(s.startswith(("TM", "ICL")) or s == "C-term" for s in segments):
        warnings.append(
            "The supplied topology places part of the site in a "
            "transmembrane/intracellular region; extracellular binder access is "
            "discouraged, not a mapping prohibition."
        )
    gpcr = metrics["gpcr_geometry"]
    if (
        biology
        and biology["target_kind"] in {"membrane", "gpcr"}
        and (not gpcr or not gpcr["membrane"].get("reliable"))
    ):
        warnings.append(
            "Signed membrane approach is unresolved; the proposal remains an "
            "exploratory hypothesis."
        )
    return {
        "status": "DISCOURAGED" if warnings else "SUPPORTED",
        "hard_constraints": "passed",
        "mapped_residues": [m.model_dump(mode="json") for m in regions.regions[0].members],
        "spatial_components": validation.spatial_component_counts["A"],
        "radius_gyration_angstrom": radius_gyration(geometry, tuple(sorted(labels))),
        "centroid_angstrom": regions.regions[0].centroid_angstrom,
        "surface_evidence": [
            {
                "label_seq_id": r["residue"]["label_seq_id"],
                "rsasa": r["rsasa"],
                "eligible": r["eligible"],
            }
            for r in selected
        ],
        "declared_segments": sorted(segments),
        "overlapping_features": features,
        "motif_warnings": overlapping,
        "warnings": warnings,
        "limitations": analysis["limitations"],
    }
