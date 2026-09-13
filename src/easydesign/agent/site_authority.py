"""Source-bound annotation projections; no new geometry or scientific kernel."""

from __future__ import annotations

from hashlib import sha256
from typing import Any

from .contracts import AgentBoundaryError


def reference_annotations(
    bridge: Any, research: dict[str, Any], approved_target: dict[str, Any]
) -> list[dict[str, Any]]:
    """Copy official features from the exact approved canonical sequence, not model quotes."""
    canonical = approved_target.get("identity", {}).get("canonical", {})
    accession = canonical.get("accession")
    if not accession:
        return []
    records = {}
    for query in research["queries"]:
        for card in query["cards"]:
            if card.get("provider", "").lower() != "uniprot":
                continue
            for ref in card.get("source_refs", []):
                if ref["sha256"] in records or ref.get("file_format") != "json":
                    continue
                record = bridge.document(ref)
                if not isinstance(record, dict) or record.get("primaryAccession") != accession:
                    continue
                sequence = record.get("sequence", {}).get("value", "")
                if sha256(sequence.encode()).hexdigest() != canonical.get("sequence_sha256"):
                    raise AgentBoundaryError(
                        "Canonical annotation source differs from approved sequence"
                    )
                features = [
                    feature
                    for feature in record.get("features", [])
                    if feature["type"]
                    in {
                        "Disulfide bond",
                        "Topological domain",
                        "Transmembrane",
                        "Glycosylation",
                        "Modified residue",
                    }
                ]
                records[ref["sha256"]] = {
                    "accession": accession,
                    "source_ref": ref,
                    "numbering": "canonical",
                    "features": features,
                    "disulfide_assignments": disulfide_assignments(features),
                    "authority": "Exact official annotations for the approved canonical sequence. "
                    "Annotation and experimental provenance retained; no construct-specific "
                    "occupancy, whole-binder clearance or functional effect is computed here.",
                }
    return list(records.values())


def disulfide_assignments(features: list[dict[str, Any]]) -> dict[str, Any]:
    """Distinct pairs coexist; only a shared endpoint with different partners is ambiguous."""
    pairs = set()
    for feature in features:
        if feature["type"] != "Disulfide bond":
            continue
        start, end = feature["location"]["start"], feature["location"]["end"]
        if start.get("modifier") == end.get("modifier") == "EXACT":
            pairs.add(tuple(sorted((start["value"], end["value"]))))
    partners: dict[int, set[int]] = {}
    for a, b in pairs:
        partners.setdefault(a, set()).add(b)
        partners.setdefault(b, set()).add(a)
    return {
        "pairs": [list(pair) for pair in sorted(pairs)],
        "multiple_partner_annotations": {
            str(position): sorted(values)
            for position, values in sorted(partners.items())
            if len(values) > 1
        },
        "scope": "Annotation consistency only. Disjoint endpoint pairs are compatible, "
        "not mutually exclusive alternatives. Retain source qualifications for multiple partners.",
    }


def sequence_topology(
    positions: list[int | None], annotations: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Join exact canonical ranges; do not relabel domains from candidate names or geometry."""
    result = []
    for position in positions:
        matches = []
        for record in annotations:
            for feature in record["features"]:
                if feature["type"] not in {"Topological domain", "Transmembrane"}:
                    continue
                start, end = feature["location"]["start"], feature["location"]["end"]
                if (
                    position is not None
                    and start.get("modifier") == end.get("modifier") == "EXACT"
                    and start["value"] <= position <= end["value"]
                ):
                    matches.append(
                        {
                            "type": feature["type"],
                            "description": feature.get("description", ""),
                            "source_sha256": record["source_ref"]["sha256"],
                        }
                    )
        result.append({"canonical_position": position, "annotations": matches})
    return result
