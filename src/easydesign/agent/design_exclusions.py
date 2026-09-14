"""Project verified GPCR intracellular evidence into executable design exclusions."""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Any

import gemmi

from .contracts import AgentBoundaryError
from .site_authority import reference_annotations

POLICY = "extracellular-gpcr-not-binding-v1"
INTRACELLULAR_SEGMENTS = {"ICL1", "ICL2", "ICL3", "C-term"}


def deposited_transducers(path: Path) -> dict[str, dict[str, str]]:
    """Read explicit mmCIF entity names, never infer partner roles from chain letters."""
    if path.suffix.lower() not in {".cif", ".mmcif"}:
        return {}
    block = gemmi.cif.read_file(str(path)).sole_block()
    entities = block.get_mmcif_category("_entity.")
    names = dict(zip(entities.get("id", []), entities.get("pdbx_description", []), strict=True))
    polymers = block.get_mmcif_category("_entity_poly.")
    result = {}
    for entity, chains in zip(
        polymers.get("entity_id", []), polymers.get("pdbx_strand_id", []), strict=True
    ):
        description = names.get(entity, "")
        normalized = description.casefold()
        role = None
        if normalized.startswith("guanine nucleotide-binding protein g(") and re.search(
            r"\bsubunit (alpha|beta|gamma)\b", normalized
        ):
            role = "gprotein"
        elif re.fullmatch(r"(?:beta-)?arrestin(?:[- ]?[1-4])?", normalized):
            role = "arrestin"
        if role:
            for chain in chains.split(","):
                result[chain.strip()] = {"role": role, "entity_description": description}
    return result


def gpcr_design_exclusions(
    bridge: Any, target: dict[str, Any], facts: dict[str, Any], site: dict[str, Any]
) -> dict[str, Any] | None:
    """Reuse the approved Site's source snapshot; no network, model or new geometry."""
    biology = facts.get("declared_biology") or {}
    if not (
        biology.get("target_kind") == "gpcr"
        and biology.get("required_site_compartment") == "extracellular"
    ):
        return None
    mapping = facts["observed_facts"]["mapping"]
    observed = {row["label_seq_id"]: row for row in mapping if row.get("coordinate_present", True)}
    canonical: dict[int, list[int]] = defaultdict(list)
    for row in mapping:
        if row.get("canonical_position") is not None:
            canonical[row["canonical_position"]].append(row["label_seq_id"])
    groups: list[dict[str, Any]] = []
    refs: dict[str, dict[str, Any]] = {}
    omitted = set()

    def add(reason: str, labels: list[int], **provenance: Any) -> None:
        missing = sorted(set(labels) - observed.keys())
        omitted.update(missing)
        groups.append(
            {
                "reason": reason,
                "label_seq_ids": sorted(set(labels) & observed.keys()),
                "unobserved_label_seq_ids": missing,
                **provenance,
            }
        )

    def source_labels(source: dict[str, Any]) -> list[int]:
        matches = [
            label
            for label, row in observed.items()
            if row.get("source_author_chain_id") == source["auth_asym_id"]
            and row.get("source_author_residue_id") == str(source["auth_seq_id"])
            and (row.get("insertion_code") or "") == (source.get("insertion_code") or "")
            and str(source["model_id"]) in row["model_presence"]
            and source["hetero_flag"] == "ATOM"
        ]
        if len(matches) > 1:
            raise AgentBoundaryError("GPCR interface has ambiguous source mapping")
        return matches

    add(
        "declared intracellular topology",
        [
            r["label_seq_id"]
            for r in biology.get("topology", [])
            if r["segment"] in INTRACELLULAR_SEGMENTS
        ],
        source=biology.get("topology_source"),
    )
    for feature in biology.get("features", []):
        if feature["kind"] == "exclude":
            add("declared exclusion", feature["label_seq_ids"], feature=feature)

    research_ref = site["proposal"].get("research_ref")
    research = bridge.document(research_ref)["source_snapshot"] if research_ref else {"queries": []}
    if research_ref:
        refs[research_ref["sha256"]] = research_ref
    for record in reference_annotations(bridge, research, target["evidence"]):
        refs[record["source_ref"]["sha256"]] = record["source_ref"]
        for feature in record["features"]:
            if feature["type"] != "Topological domain" or feature.get(
                "description", ""
            ).casefold() not in {"cytoplasmic", "intracellular"}:
                continue
            start, end = feature["location"]["start"], feature["location"]["end"]
            if start.get("modifier") != "EXACT" or end.get("modifier") != "EXACT":
                continue
            positions = range(start["value"], end["value"] + 1)
            if any(len(canonical[n]) > 1 for n in positions):
                raise AgentBoundaryError("GPCR exclusion has ambiguous canonical mapping")
            add(
                "canonical intracellular annotation",
                [label for n in positions for label in canonical[n]],
                source_sha256=record["source_ref"]["sha256"],
                feature=feature,
                unmapped_canonical_positions=[n for n in positions if not canonical[n]],
            )

    transducers = None
    for query in research["queries"]:
        for card in query["cards"]:
            if card.get("provider") != "EasyDesign GPCR kernel":
                continue
            for ref in card["source_refs"]:
                if ref["artifact_id"] != "research-receptor-analysis" or ref["sha256"] in refs:
                    continue
                analysis = bridge.document(ref)
                hard = target["evidence"]["hard_facts"]
                if (
                    analysis["approved_design_mapping"]["target_binding"] != target["binding"]
                    or analysis["identity"]["accession"] != hard["canonical_accession"]
                    or analysis["identity"]["receptor_chain"] != hard["selected_chain"]
                    or analysis["structure"]["sha256"] != bridge.binding()["source_sha"]
                ):
                    raise AgentBoundaryError("GPCR exclusion analysis has a stale Target binding")
                refs[ref["sha256"]] = ref
                if analysis.get("membrane", {}).get("reliable") is True:
                    add(
                        "signed intracellular geometry",
                        [
                            label
                            for region in analysis["residue_regions"]
                            if region["region"] in {"intracellular", "intracellular_tm_surface"}
                            for label in source_labels(region["residue"])
                        ],
                        source_sha256=ref["sha256"],
                    )
                if transducers is None:
                    transducers = deposited_transducers(bridge.validate_project().source_path)
                for edge in analysis["chain_graph"]["edges"]:
                    receptor = hard["selected_chain"]
                    if receptor not in (edge["chain_a"], edge["chain_b"]):
                        continue
                    side = "a" if edge["chain_a"] == receptor else "b"
                    partner = edge["chain_b" if side == "a" else "chain_a"]
                    declared = transducers.get(partner, {})
                    role = declared.get("role", edge["interface_type"])
                    if role not in {"gprotein", "arrestin"} or not edge["geometry_observed"]:
                        continue
                    labels = []
                    for contact in edge["contacts"]:
                        labels.extend(source_labels(contact["residue_" + side]))
                    add(
                        role + "-facing receptor contacts",
                        labels,
                        partner_auth_chain=partner,
                        partner_identity=declared,
                        source_sha256=ref["sha256"],
                        contact_cutoff_angstrom=analysis["chain_graph"]["contact_cutoff"],
                    )
    labels = sorted({n for group in groups for n in group["label_seq_ids"]})
    return {
        "policy": POLICY,
        "label_seq_ids": labels,
        "sources": [g for g in groups if g["label_seq_ids"] or g["unobserved_label_seq_ids"]],
        "source_refs": list(refs.values()),
        "unobserved_label_seq_ids": sorted(omitted),
        "status": "applied" if labels else "no-verified-residues",
        "limitations": [
            "Only mapped, coordinate-present receptor residues enter not_binding. "
            "Absent coordinates and unannotated partners are not invented. "
            "Annotation provenance is retained; it is not independent experimental certification.",
            "not_binding constrains contacts; it is not a membrane or accessibility simulation.",
            *(
                []
                if labels
                else [
                    "Intracellular exclusion evidence is unavailable; "
                    "an empty default is not evidence that no intracellular region exists."
                ]
            ),
        ],
    }
