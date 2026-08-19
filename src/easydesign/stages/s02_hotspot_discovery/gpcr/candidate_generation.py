"""Family-aware, non-fused GPCR hotspot hypothesis generation."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, cast

CANDIDATE_SCHEMA = "gpcr-hotspot-candidates-v1"
MAX_HOTSPOT_RESIDUES = 8
EVIDENCE_ORDER = {"T1": 0, "T2": 1, "T3": 2, "T4": 3, "UNRESOLVED": 4}
PUBLICATION_EVIDENCE_ORDER = {
    "same_receptor_experiment": 0,
    "gpcrdb_curated": 1,
    "same_receptor_model": 2,
    "mapped_homolog": 3,
    "family_prior": 4,
    "unresolved": 5,
}
DISPOSITION_ORDER = {"primary": 0, "backup": 1, "avoid": 2, "unresolved": 3}
MODE_ORDER = {"inhibit": 0, "activate": 1}

MECHANISM_ORDER = {
    "outer-vestibule-blockade": 10,
    "transmembrane-pore-blockade": 20,
    "peptide-footprint-blockade": 30,
    "self-occlusion-stabilization": 40,
    "dimer-interface-blockade": 50,
    "core-pore-activation": 110,
    "peptide-agonist-mimicry": 120,
    "ecd-agonist-site": 130,
    "self-occlusion-release": 140,
    "dimer-allosteric-stabilization": 150,
    "intracellular-effector-face": 900,
    "gprotein-is-not-dimer": 910,
    "axis-free-pore-guess": 920,
}


@dataclass(frozen=True)
class Evidence:
    tier: str
    evidence_type: str
    source: str
    detail: str
    direct: bool = False
    identifiers: Mapping[str, Any] = field(default_factory=dict)

    @property
    def evidence_id(self) -> str:
        payload = json.dumps(
            {
                "tier": self.tier,
                "type": self.evidence_type,
                "source": self.source,
                "detail": self.detail,
                "direct": self.direct,
                "identifiers": dict(self.identifiers),
            },
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return "evidence-" + hashlib.sha256(payload).hexdigest()[:16]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.evidence_id,
            "tier": self.tier,
            "type": self.evidence_type,
            "source": self.source,
            "claim": self.detail,
            "detail": self.detail,
            "direct": self.direct,
            "identifiers": dict(self.identifiers),
        }


@dataclass
class CandidateHypothesis:
    candidate_id: str
    mode: str
    disposition: str
    mechanism: str
    label: str
    residues: list[dict[str, Any]]
    evidence: list[Evidence]
    rationale: list[str]
    limitations: list[str]
    family_applicability: list[str]
    membrane_reliable: bool
    mapping_reliable: bool

    @property
    def internal_evidence_tier(self) -> str:
        if not self.evidence:
            return "UNRESOLVED"
        return min(
            (item.tier for item in self.evidence),
            key=lambda tier: EVIDENCE_ORDER.get(tier, 99),
        )

    @property
    def evidence_tier(self) -> str:
        best = self.internal_evidence_tier
        if best == "T1":
            return (
                "same_receptor_experiment"
                if any(
                    item.identifiers.get("pdb_code") or item.identifiers.get("experimental") is True
                    for item in self.evidence
                )
                else "gpcrdb_curated"
            )
        if best == "T2":
            return "same_receptor_annotation"
        if best == "T3":
            return "gpcrdb_curated"
        if best == "T4":
            return "family_prior"
        return "unresolved"

    @property
    def confidence(self) -> str:
        if self.disposition == "unresolved" or not self.residues:
            return "unresolved"
        if self.internal_evidence_tier == "T1" and self.disposition == "primary":
            return "high"
        if self.internal_evidence_tier in {"T1", "T2", "T3"}:
            return "medium"
        return "low"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.candidate_id,
            "mode": self.mode,
            "classification": self.disposition,
            "role": self.mechanism,
            "hypothesis": self.rationale[0] if self.rationale else self.label,
            "functional_site": self.label,
            "evidence_tier": self.evidence_tier,
            "evidence": [
                item.to_dict()
                for item in sorted(
                    self.evidence,
                    key=lambda value: (
                        EVIDENCE_ORDER.get(value.tier, 99),
                        value.evidence_type,
                        value.source,
                        value.detail,
                    ),
                )
            ],
            "residues": _deduplicate_residues(self.residues),
            "target_state": "inactive" if self.mode == "inhibit" else "active",
            "counterstate": "active" if self.mode == "inhibit" else "inactive",
            "approach_direction": (
                "intracellular"
                if self.mechanism in {"intracellular-effector-face", "gprotein-is-not-dimer"}
                else "extracellular"
            ),
            "approach_checks": {
                "status": "unresolved",
                "required": [
                    "CDR access",
                    "framework-membrane collision",
                    "ECD/glycan collision",
                    "partner/protomer collision",
                ],
            },
            "evidence_ids": sorted(item.evidence_id for item in self.evidence),
            "hard_gates": [
                {
                    "name": "exact_residue_mapping",
                    "status": "pass" if self.mapping_reliable and self.residues else "unresolved",
                },
                {
                    "name": "signed_membrane_orientation",
                    "status": "pass" if self.membrane_reliable else "unresolved",
                },
            ],
            "risks": sorted(set(self.limitations)),
            "limitations": sorted(set(self.limitations)),
            "confidence": self.confidence,
            "falsifier": (
                "Reject if state-matched functional assays show no mechanism-consistent effect "
                "at verified occupancy."
            ),
            "assays": (
                ["concentration-response inhibition assay", "orthogonal binding/competition assay"]
                if self.mode == "inhibit"
                else [
                    "concentration-response activation assay",
                    "basal-activity/counterstate control",
                ]
            ),
            "family_applicability": sorted(set(self.family_applicability)),
        }


def _identity_dict(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    nested = value.get("residue") or value.get("identity")
    source = nested if isinstance(nested, Mapping) else value
    chain = source.get("auth_asym_id", source.get("chain_id"))
    seq_num = source.get(
        "auth_seq_id",
        source.get(
            "author_residue_number", source.get("sequence_number", source.get("residue_number"))
        ),
    )
    try:
        seq_num = int(seq_num)
    except (TypeError, ValueError):
        return None
    insertion = str(source.get("insertion_code", source.get("icode", "")) or "").strip()
    model_id = str(source.get("model_id", "1") or "1")
    chain_id = str(chain or "")
    hetero = str(source.get("hetero_flag", "ATOM") or "ATOM")
    key = source.get("key") or f"{model_id}|{chain_id}|{hetero}|{seq_num}{insertion}"
    return {
        "key": str(key),
        "model_id": model_id,
        "chain_id": chain_id,
        "auth_asym_id": chain_id,
        "auth_seq_id": seq_num,
        "insertion_code": insertion,
        "hetero_flag": hetero,
        "label_chain_id": source.get("label_chain_id", source.get("label_asym_id")),
        "label_asym_id": source.get("label_asym_id", source.get("label_chain_id")),
        "label_seq_id": source.get("label_seq_id"),
    }


def _residue_sort(value: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        str(value.get("model_id", "")),
        str(value.get("chain_id", "")),
        int(value.get("auth_seq_id", -(10**12))),
        str(value.get("insertion_code", "")),
        str(value.get("hetero_flag", "")),
    )


def _deduplicate_residues(values: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    unique: dict[str, dict[str, Any]] = {}
    for value in values:
        identity = _identity_dict(value)
        if identity is not None:
            record = dict(value)
            record.pop("residue", None)
            record.pop("identity", None)
            record.update(identity)
            previous = unique.get(identity["key"], {})
            unique[identity["key"]] = {
                **previous,
                **{key: item for key, item in record.items() if item is not None},
            }
    return sorted(unique.values(), key=_residue_sort)


def _candidate_sort(value: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        DISPOSITION_ORDER.get(str(value.get("classification")), 99),
        PUBLICATION_EVIDENCE_ORDER.get(str(value.get("evidence_tier")), 99),
        MECHANISM_ORDER.get(str(value.get("role")), 500),
        str(value.get("id", "")),
    )


def _as_mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _family_class(context: Mapping[str, Any]) -> tuple[str, str]:
    family = _as_mapping(context.get("family"))
    structures = _as_mapping(context.get("structures"))
    selected = _as_mapping(structures.get("selected"))
    raw = str(
        family.get("class") or selected.get("class") or context.get("receptor_class") or "Unknown"
    )
    lowered = raw.lower()
    if "class b2" in lowered or "adhesion" in lowered:
        code = "B2"
    elif "class b1" in lowered or "secretin" in lowered:
        code = "B1"
    elif "class c" in lowered or "glutamate" in lowered:
        code = "C"
    elif "class f" in lowered or "frizzled" in lowered:
        code = "F"
    elif "class a" in lowered or "rhodopsin" in lowered:
        code = "A"
    else:
        code = "OTHER"
    return code, raw


def _regions_by_name(analysis: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    output: dict[str, list[dict[str, Any]]] = {}
    values = analysis.get("residue_regions")
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        return output
    for value in values:
        if not isinstance(value, Mapping):
            continue
        identity = _identity_dict(value.get("residue"))
        region = str(value.get("region") or "")
        if identity and region:
            record = dict(value)
            record.pop("residue", None)
            record.update(identity)
            output.setdefault(region, []).append(record)
    for region in output:
        output[region] = _deduplicate_residues(output[region])
    return output


def _compact_residues(
    values: Sequence[Mapping[str, Any]],
    *,
    priority_keys: set[str] | None = None,
    normalized_axial_target: float | None = None,
    limit: int = MAX_HOTSPOT_RESIDUES,
) -> list[dict[str, Any]]:
    priority = priority_keys or set()

    def numeric(value: Any, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def sort_key(value: Mapping[str, Any]) -> tuple[Any, ...]:
        identity = _identity_dict(value) or {}
        normalized = numeric(value.get("normalized_axial"), float("inf"))
        axial_distance = (
            abs(normalized - normalized_axial_target)
            if normalized_axial_target is not None and normalized != float("inf")
            else 0.0
        )
        return (
            0 if identity.get("key") in priority else 1,
            numeric(value.get("radial_distance"), float("inf")),
            axial_distance,
            _residue_sort(identity),
        )

    return _deduplicate_residues(sorted(values, key=sort_key)[: max(0, limit)])


def _region_record_indexes(
    analysis: Mapping[str, Any],
) -> tuple[
    dict[tuple[str, int, str], dict[str, Any]],
    dict[int, list[dict[str, Any]]],
    dict[int, dict[str, Any]],
]:
    exact: dict[tuple[str, int, str], dict[str, Any]] = {}
    by_number: dict[int, list[dict[str, Any]]] = {}
    by_sequence: dict[int, dict[str, Any]] = {}
    values = analysis.get("residue_regions")
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        return exact, by_number, by_sequence
    for value in values:
        if not isinstance(value, Mapping):
            continue
        identity = _identity_dict(value.get("residue"))
        if identity is None:
            continue
        key = (
            identity["chain_id"],
            identity["auth_seq_id"],
            identity["insertion_code"],
        )
        item = dict(value)
        item["residue"] = identity
        exact[key] = item
        by_number.setdefault(identity["auth_seq_id"], []).append(item)

    topology = analysis.get("topology")
    topology_values = topology.get("residues") if isinstance(topology, Mapping) else None
    if isinstance(topology_values, Sequence) and not isinstance(topology_values, (str, bytes)):
        region_by_key = {
            item["residue"]["key"]: item
            for item in exact.values()
            if isinstance(item.get("residue"), Mapping)
        }
        for assignment in topology_values:
            if not isinstance(assignment, Mapping):
                continue
            try:
                sequence_number = int(cast(Any, assignment.get("sequence_number")))
            except (TypeError, ValueError):
                continue
            identity = _identity_dict(assignment.get("residue"))
            if identity and identity["key"] in region_by_key:
                by_sequence[sequence_number] = region_by_key[identity["key"]]
    return exact, by_number, by_sequence


def _residue_metadata(analysis: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Build the dual-numbering residue surface required by the review contract."""

    metadata: dict[str, dict[str, Any]] = {}
    topology = analysis.get("topology")
    topology_values = topology.get("residues") if isinstance(topology, Mapping) else None
    if isinstance(topology_values, Sequence) and not isinstance(topology_values, (str, bytes)):
        for assignment in topology_values:
            if not isinstance(assignment, Mapping):
                continue
            identity = _identity_dict(assignment.get("residue", assignment))
            if identity is None:
                continue
            metadata[identity["key"]] = {
                **identity,
                "amino_acid": assignment.get("amino_acid"),
                "observed_amino_acid": assignment.get("observed_amino_acid"),
                "sequence_index": assignment.get("sequence_index"),
                "gpcrdb_sequence_number": assignment.get(
                    "gpcrdb_sequence_number", assignment.get("sequence_number")
                ),
                "generic_number": assignment.get(
                    "generic_number", assignment.get("display_generic_number")
                ),
                "alternative_generic_numbers": assignment.get("alternative_generic_numbers", []),
                "segment": assignment.get("segment", assignment.get("protein_segment")),
                "observed": assignment.get("observed", True),
                "mapping_status": assignment.get("mapping_status", "exact"),
                "mapping_note": assignment.get("mapping_note"),
            }

    regions = analysis.get("residue_regions")
    if isinstance(regions, Sequence) and not isinstance(regions, (str, bytes)):
        for region in regions:
            if not isinstance(region, Mapping):
                continue
            identity = _identity_dict(region.get("residue"))
            if identity is None:
                continue
            record = metadata.setdefault(identity["key"], identity)
            record.update(
                {
                    "amino_acid": record.get("amino_acid") or region.get("amino_acid"),
                    "generic_number": record.get("generic_number") or region.get("generic_number"),
                    "segment": record.get("segment") or region.get("protein_segment"),
                    "membrane_facing": region.get("region"),
                    "functional_role": region.get("region"),
                }
            )
    return metadata


def _selected_structure(context: Mapping[str, Any]) -> Mapping[str, Any]:
    structures = context.get("structures")
    if isinstance(structures, Mapping) and isinstance(structures.get("selected"), Mapping):
        return cast(Mapping[str, Any], structures["selected"])
    return {}


def _ligand_function_map(context: Mapping[str, Any]) -> dict[str, str]:
    output: dict[str, str] = {}
    selected = _selected_structure(context)
    ligands = selected.get("ligands") if isinstance(selected, Mapping) else None
    if isinstance(ligands, Sequence) and not isinstance(ligands, (str, bytes)):
        for ligand in ligands:
            if not isinstance(ligand, Mapping):
                continue
            name = str(ligand.get("name") or "").strip().lower()
            if name:
                output[name] = str(ligand.get("function") or "").strip()
    return output


def _function_mode(value: str) -> str | None:
    lowered = value.lower()
    if any(
        token in lowered
        for token in (
            "inverse agonist",
            "antagonist",
            "inhibitor",
            "blocker",
            "negative allosteric",
        )
    ):
        return "inhibit"
    if any(token in lowered for token in ("agonist", "activator", "positive allosteric")):
        return "activate"
    return None


def _interaction_residues(
    analysis: Mapping[str, Any],
    context: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    exact, by_number, by_sequence = _region_record_indexes(analysis)
    receptor_chain = str((analysis.get("identity") or {}).get("receptor_chain") or "")
    function_by_ligand = _ligand_function_map(context)
    interactions = _as_mapping(context.get("interactions"))
    output: dict[str, dict[str, Any]] = {
        "inhibit": {"residues": [], "records": []},
        "activate": {"residues": [], "records": []},
        "peptide": {"residues": [], "records": []},
        "gprotein": {"residues": [], "records": []},
        "unknown": {"residues": [], "records": []},
    }

    def resolve(record: Mapping[str, Any]) -> dict[str, Any] | None:
        number = record.get(
            "sequence_number",
            record.get("receptor_residue_number", record.get("residue_number")),
        )
        try:
            number_int = int(number)
        except (TypeError, ValueError):
            return None
        sequence_match = by_sequence.get(number_int)
        if sequence_match:
            return cast(dict[str, Any], sequence_match["residue"])
        chain = str(record.get("receptor_chain") or receptor_chain)
        insertion = str(record.get("insertion_code") or "")
        region = exact.get((chain, number_int, insertion))
        if region:
            return cast(dict[str, Any], region["residue"])
        matches = by_number.get(number_int, [])
        return cast(dict[str, Any], matches[0]["residue"]) if len(matches) == 1 else None

    ligand_values = interactions.get("ligand")
    if isinstance(ligand_values, Sequence) and not isinstance(ligand_values, (str, bytes)):
        for record in ligand_values:
            if not isinstance(record, Mapping):
                continue
            residue = resolve(record)
            ligand_name = str(record.get("ligand_name") or record.get("ligand") or "").lower()
            function = str(record.get("function") or function_by_ligand.get(ligand_name, ""))
            category_name = _function_mode(function) or "unknown"
            output[category_name]["records"].append(dict(record))
            if residue:
                output[category_name]["residues"].append(residue)

    peptide_values = interactions.get("peptide")
    if isinstance(peptide_values, Sequence) and not isinstance(peptide_values, (str, bytes)):
        selected_modes = {
            mode
            for mode in (_function_mode(value) for value in function_by_ligand.values())
            if mode
        }
        peptide_mode = next(iter(selected_modes)) if len(selected_modes) == 1 else None
        for record in peptide_values:
            if not isinstance(record, Mapping):
                continue
            residue = resolve(record)
            output["peptide"]["records"].append(dict(record))
            if residue:
                output["peptide"]["residues"].append(residue)
                if peptide_mode:
                    output[peptide_mode]["residues"].append(residue)

    gprotein_values = interactions.get("gprotein")
    if isinstance(gprotein_values, Sequence) and not isinstance(gprotein_values, (str, bytes)):
        for record in gprotein_values:
            if not isinstance(record, Mapping):
                continue
            residue = resolve(record)
            output["gprotein"]["records"].append(dict(record))
            if residue:
                output["gprotein"]["residues"].append(residue)

    for bucket in output.values():
        bucket["residues"] = _deduplicate_residues(bucket["residues"])
    return output


def _mutation_records_by_residue(
    analysis: Mapping[str, Any], context: Mapping[str, Any]
) -> dict[str, list[dict[str, Any]]]:
    _, by_number, by_sequence = _region_record_indexes(analysis)
    values = context.get("mutations")
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        return {}
    output: dict[str, list[dict[str, Any]]] = {}
    for record in values:
        if not isinstance(record, Mapping):
            continue
        try:
            position = int(cast(Any, record.get("mutation_pos")))
        except (TypeError, ValueError):
            continue
        region = by_sequence.get(position)
        if region is None:
            matches = by_number.get(position, [])
            region = matches[0] if len(matches) == 1 else None
        if not region or not isinstance(region.get("residue"), Mapping):
            continue
        identity = _identity_dict(region["residue"])
        if identity is None:
            continue
        output.setdefault(identity["key"], []).append(dict(record))
    return output


def _attach_mutation_evidence(
    collector: _Collector, mutation_records: Mapping[str, Sequence[Mapping[str, Any]]]
) -> None:
    for candidate in collector.items:
        keys = {
            identity["key"]
            for identity in (_identity_dict(value) for value in candidate.residues)
            if identity is not None
        }
        records = [record for key in sorted(keys) for record in mutation_records.get(key, [])]
        if not records:
            continue
        references = sorted(
            {str(record.get("reference")) for record in records if record.get("reference")}
        )
        candidate.evidence.append(
            _evidence(
                "T2",
                "same_receptor_mutation_experiment",
                "GPCRdb mutation annotation",
                (
                    f"{len(records)} mutation experiment record(s) overlap this compact "
                    "candidate; effect direction remains assay-specific"
                ),
                direct=False,
                identifiers={
                    "experimental": True,
                    "assay_matched": False,
                    "record_count": len(records),
                    "references": references[:10],
                },
            )
        )


def _edge_receptor_residues(edge: Mapping[str, Any], receptor_chain: str) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    contacts = edge.get("contacts")
    if not isinstance(contacts, Sequence) or isinstance(contacts, (str, bytes)):
        return values
    for contact in contacts:
        if not isinstance(contact, Mapping):
            continue
        for label in ("residue_a", "residue_b"):
            residue = _identity_dict(contact.get(label))
            if residue and residue["chain_id"] == receptor_chain:
                values.append(residue)
    return _deduplicate_residues(values)


def _self_occlusion_residues(
    analysis: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    graph = _as_mapping(analysis.get("chain_graph"))
    interface = _as_mapping(graph.get("self_occlusion"))
    ecd: list[dict[str, Any]] = []
    mouth: list[dict[str, Any]] = []
    contacts = interface.get("contacts")
    if isinstance(contacts, Sequence) and not isinstance(contacts, (str, bytes)):
        for contact in contacts:
            if not isinstance(contact, Mapping):
                continue
            residue_a = _identity_dict(contact.get("residue_a"))
            residue_b = _identity_dict(contact.get("residue_b"))
            if residue_a:
                ecd.append(residue_a)
            if residue_b:
                mouth.append(residue_b)
    return _deduplicate_residues(ecd), _deduplicate_residues(mouth)


def _selection_keys(selection: Any, label: str) -> set[str]:
    if not isinstance(selection, Mapping):
        return set()
    values = selection.get(label, selection.get(f"{label}_residues", []))
    if isinstance(values, Mapping):
        values = [values]
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        return set()
    keys: set[str] = set()
    for value in values:
        if isinstance(value, str):
            keys.add(value)
        else:
            identity = _identity_dict(value)
            if identity:
                keys.add(identity["key"])
    return keys


def _apply_selection(
    residues: Sequence[Mapping[str, Any]],
    selection: Any,
) -> tuple[list[dict[str, Any]], list[str]]:
    included = _selection_keys(selection, "include")
    excluded = _selection_keys(selection, "exclude")
    values = _deduplicate_residues(residues)
    limitations: list[str] = []
    if included:
        values = [value for value in values if value["key"] in included]
        limitations.append("residues were restricted by explicit include selection")
    if excluded:
        before = len(values)
        values = [value for value in values if value["key"] not in excluded]
        if len(values) != before:
            limitations.append("explicitly excluded residues were removed")
    return values, limitations


def _evidence(
    tier: str,
    evidence_type: str,
    source: str,
    detail: str,
    *,
    direct: bool = False,
    identifiers: Mapping[str, Any] | None = None,
) -> Evidence:
    return Evidence(tier, evidence_type, source, detail, direct, identifiers or {})


class _Collector:
    def __init__(
        self,
        selection: Any,
        residue_metadata: Mapping[str, Mapping[str, Any]],
        *,
        membrane_reliable: bool,
        mapping_reliable: bool,
    ) -> None:
        self.selection = selection
        self.residue_metadata = residue_metadata
        self.membrane_reliable = membrane_reliable
        self.mapping_reliable = mapping_reliable
        self.items: list[CandidateHypothesis] = []

    def add(
        self,
        *,
        candidate_id: str,
        mode: str,
        disposition: str,
        mechanism: str,
        label: str,
        residues: Sequence[Mapping[str, Any]] = (),
        evidence: Sequence[Evidence] = (),
        rationale: Sequence[str] = (),
        limitations: Sequence[str] = (),
        family_applicability: Sequence[str] = (),
    ) -> None:
        if disposition in {"avoid", "unresolved"}:
            filtered = _deduplicate_residues(residues)
            selection_limitations: list[str] = []
        else:
            filtered, selection_limitations = _apply_selection(residues, self.selection)
        final_disposition = disposition
        final_limitations = list(limitations) + selection_limitations
        if disposition in {"primary", "backup"} and not filtered:
            final_disposition = "unresolved"
            final_limitations.append("no exact structure residues support this hypothesis")
        if disposition == "primary" and not self.membrane_reliable:
            final_disposition = "unresolved"
            final_limitations.append("primary publication requires reliable membrane orientation")
        if disposition == "primary" and not self.mapping_reliable:
            final_disposition = "unresolved"
            final_limitations.append("primary publication requires reliable residue mapping")
        enriched = [dict(self.residue_metadata.get(value["key"], value)) for value in filtered]
        if disposition in {"primary", "backup"}:
            mismatch_count = sum(
                value.get("mapping_status") == "sequence_mismatch" for value in enriched
            )
            if mismatch_count:
                enriched = [
                    value
                    for value in enriched
                    if value.get("mapping_status") != "sequence_mismatch"
                ]
                final_limitations.append(
                    f"removed {mismatch_count} GPCRdb/structure sequence mismatch residue(s)"
                )
            if not enriched:
                final_disposition = "unresolved"
                final_limitations.append(
                    "no sequence-consistent structure residues remain after "
                    "construct-risk filtering"
                )
        self.items.append(
            CandidateHypothesis(
                candidate_id=candidate_id,
                mode=mode,
                disposition=final_disposition,
                mechanism=mechanism,
                label=label,
                residues=enriched,
                evidence=list(evidence),
                rationale=list(rationale),
                limitations=final_limitations,
                family_applicability=list(family_applicability),
                membrane_reliable=self.membrane_reliable,
                mapping_reliable=self.mapping_reliable,
            )
        )

    def arrays(self, requested_modes: set[str]) -> dict[str, list[dict[str, Any]]]:
        output: dict[str, list[dict[str, Any]]] = {"inhibit": [], "activate": []}
        for item in self.items:
            if item.mode not in requested_modes:
                continue
            output[item.mode].append(item.to_dict())
        for mode in output:
            output[mode].sort(key=_candidate_sort)
        return output

    def evidence_records(self, requested_modes: set[str]) -> list[dict[str, Any]]:
        records: dict[str, dict[str, Any]] = {}
        for item in self.items:
            if item.mode not in requested_modes:
                continue
            for evidence in item.evidence:
                records[evidence.evidence_id] = evidence.to_dict()
        return [records[key] for key in sorted(records)]


def _has_direct_mode_interactions(interactions: Mapping[str, Any], mode: str) -> bool:
    value = interactions.get(mode)
    return bool(isinstance(value, Mapping) and value.get("records"))


def generate_candidates(
    structure_analysis: Mapping[str, Any],
    receptor_context: Mapping[str, Any] | None,
    mode: str = "both",
    selection: Any = None,
) -> dict[str, Any]:
    """Return the analysis root with deterministic, separate hotspot hypotheses.

    The function never produces a composite score or a single winning site. Direct
    ligand contacts, structure-derived geometry, annotations, and family heuristics
    remain distinct evidence tiers.
    """

    mode = str(mode).lower()
    if mode not in {"both", "inhibit", "activate"}:
        raise ValueError("mode must be 'both', 'inhibit', or 'activate'")
    requested_modes = {"inhibit", "activate"} if mode == "both" else {mode}
    context: Mapping[str, Any] = receptor_context or {}
    root = deepcopy(dict(structure_analysis))
    family_code, family_name = _family_class(context)
    regions = _regions_by_name(root)
    interactions = _interaction_residues(root, context)
    membrane = _as_mapping(root.get("membrane"))
    frame_reliable = bool(membrane.get("reliable") or membrane.get("status") == "resolved")
    topology = _as_mapping(root.get("topology"))
    context_warnings = context.get("warnings")
    blocking_codes = (
        {
            str(item.get("code"))
            for item in context_warnings
            if isinstance(item, Mapping) and item.get("code")
        }
        if isinstance(context_warnings, Sequence) and not isinstance(context_warnings, (str, bytes))
        else set()
    )
    mapping_reliable = bool(
        topology.get("mapping_reliable") or topology.get("mapping_status") == "resolved"
    ) and not blocking_codes.intersection(
        {"identifier_conflict", "mapping_conflict", "schema_change"}
    )
    receptor_chain = str(_as_mapping(root.get("identity")).get("receptor_chain") or "")
    residue_metadata = _residue_metadata(root)
    collector = _Collector(
        selection,
        residue_metadata,
        membrane_reliable=frame_reliable,
        mapping_reliable=mapping_reliable,
    )
    sequence_mismatches = [
        dict(value)
        for value in residue_metadata.values()
        if value.get("mapping_status") == "sequence_mismatch"
    ]
    if sequence_mismatches:
        for candidate_mode in ("inhibit", "activate"):
            collector.add(
                candidate_id=f"{candidate_mode}.avoid-sequence-mismatch",
                mode=candidate_mode,
                disposition="avoid",
                mechanism="construct-or-identity-mismatch",
                label="Avoid unresolved construct or sequence-mismatch residues",
                residues=sequence_mismatches,
                evidence=[
                    _evidence(
                        "T2",
                        "gpcrdb_structure_sequence_mismatch",
                        "local structure-to-GPCRdb mapping",
                        "observed structure residues differ from the mapped canonical sequence",
                        direct=True,
                    )
                ],
                rationale=[
                    "A sequence mismatch can represent an engineered mutation, isoform, "
                    "variant, or incorrect identity and must not anchor an automatic hotspot."
                ],
                limitations=["resolve construct provenance before manual inclusion"],
                family_applicability=["A", "B1", "B2", "C", "F", "D", "O", "T", "Other"],
            )

    selected_structure = _selected_structure(context)
    pdb_code = selected_structure.get("pdb_code") if selected_structure else None
    structure_identifiers = {"pdb_code": pdb_code} if pdb_code else {}

    direct_inhibit_keys = {item["key"] for item in interactions["inhibit"]["residues"]}
    direct_activate_keys = {item["key"] for item in interactions["activate"]["residues"]}
    outer_vestibule = _compact_residues(
        regions.get("outer_vestibule", []),
        priority_keys=direct_inhibit_keys,
        normalized_axial_target=1.0,
    )
    outer_pore = _compact_residues(
        regions.get("outer_pore", []),
        priority_keys=direct_inhibit_keys,
        normalized_axial_target=0.6,
    )
    core_pore = _compact_residues(
        regions.get("core_pore", []),
        priority_keys=direct_activate_keys,
        normalized_axial_target=0.0,
    )
    outer_pore_keys = {item["key"] for item in outer_pore}
    core_pore_keys = {item["key"] for item in core_pore}
    direct_inhibit = any(
        item["key"] in outer_pore_keys for item in interactions["inhibit"]["residues"]
    )
    direct_activate = any(
        item["key"] in core_pore_keys for item in interactions["activate"]["residues"]
    )
    intracellular = _compact_residues(
        regions.get("intracellular", [])
        + regions.get("intracellular_tm_surface", [])
        + regions.get("inner_pore", [])
    )

    collector.add(
        candidate_id="inhibit.outer-vestibule",
        mode="inhibit",
        disposition="primary",
        mechanism="outer-vestibule-blockade",
        label="Block the extracellular vestibule",
        residues=outer_vestibule,
        evidence=[
            _evidence(
                "T2",
                "signed_membrane_geometry",
                "local structure analysis",
                "extracellular-loop residues lie at the signed 7TM mouth",
                direct=True,
            )
        ]
        if outer_vestibule
        else [],
        rationale=[
            "An extracellular binder can sterically restrict ligand entry and extracellular gating."
        ],
        limitations=[] if frame_reliable else ["signed membrane geometry is unavailable"],
        family_applicability=["A", "B1", "B2", "C", "F"],
    )

    pore_evidence = []
    if outer_pore:
        pore_evidence.append(
            _evidence(
                "T2",
                "pore_geometry",
                "local structure analysis",
                "side-chain geometry is compatible with the extracellular half of the 7TM pore",
                direct=True,
            )
        )
    if direct_inhibit:
        pore_evidence.append(
            _evidence(
                "T1",
                "inhibitory_ligand_contacts",
                "GPCRdb structure interaction annotation",
                "the selected structure contains antagonist/inverse-agonist receptor contacts",
                direct=True,
                identifiers=structure_identifiers,
            )
        )
    collector.add(
        candidate_id="inhibit.transmembrane-pore",
        mode="inhibit",
        disposition="primary" if direct_inhibit else "backup",
        mechanism="transmembrane-pore-blockade",
        label="Block the extracellular half of the 7TM pore",
        residues=outer_pore,
        evidence=pore_evidence,
        rationale=[
            "Occluding the upper pore can prevent productive occupancy or conformational closure."
        ],
        limitations=[]
        if frame_reliable
        else ["pore position cannot be assigned without a signed TM frame"],
        family_applicability=["A", "B1", "B2", "C", "F"],
    )

    core_evidence = []
    if core_pore:
        core_evidence.append(
            _evidence(
                "T2",
                "core_pore_geometry",
                "local structure analysis",
                "pore-facing residues occupy the signed center of the TM bundle",
                direct=True,
            )
        )
    if direct_activate:
        core_evidence.append(
            _evidence(
                "T1",
                "agonist_contacts",
                "GPCRdb structure interaction annotation",
                "the selected structure contains agonist receptor contacts",
                direct=True,
                identifiers=structure_identifiers,
            )
        )
    collector.add(
        candidate_id="activate.core-pore",
        mode="activate",
        disposition="primary",
        mechanism="core-pore-activation",
        label="Engage the central 7TM activation pocket",
        residues=core_pore,
        evidence=core_evidence,
        rationale=[
            "The central pore is the primary activation hypothesis requested for "
            "transmembrane signaling."
        ],
        limitations=[]
        if frame_reliable
        else ["core position cannot be assigned without a signed TM frame"],
        family_applicability=["A", "B1", "B2", "C", "F"],
    )

    peptide_residues = _compact_residues(interactions["peptide"]["residues"])
    peptide_function_modes = {
        _function_mode(value) for value in _ligand_function_map(context).values()
    } - {None}
    if peptide_residues:
        peptide_tier = "T1" if pdb_code else "T2"
        peptide_common_evidence = [
            _evidence(
                peptide_tier,
                "peptide_contact_footprint",
                "GPCRdb peptide interaction annotation",
                "receptor residues directly contact a peptide ligand in the selected "
                "structure/model",
                direct=True,
                identifiers=structure_identifiers,
            )
        ]
        if "inhibit" in peptide_function_modes or not peptide_function_modes:
            collector.add(
                candidate_id="inhibit.peptide-footprint",
                mode="inhibit",
                disposition="primary" if "inhibit" in peptide_function_modes else "backup",
                mechanism="peptide-footprint-blockade",
                label="Block the observed peptide-binding footprint",
                residues=peptide_residues,
                evidence=peptide_common_evidence,
                rationale=["An extracellular binder can occlude the actual peptide footprint."],
                family_applicability=["B1", "B2", "C", "F"],
            )
        if "activate" in peptide_function_modes or not peptide_function_modes:
            collector.add(
                candidate_id="activate.peptide-footprint",
                mode="activate",
                disposition="backup",
                mechanism="peptide-agonist-mimicry",
                label="Mimic or stabilize the observed peptide agonist footprint",
                residues=peptide_residues,
                evidence=peptide_common_evidence,
                rationale=[
                    "A binder may reproduce or stabilize extracellular peptide-driven "
                    "activation geometry."
                ],
                limitations=[
                    "binding alone does not prove agonism; functional validation is required"
                ],
                family_applicability=["B1", "B2", "C", "F"],
            )

    graph = _as_mapping(root.get("chain_graph"))
    raw_edges = graph.get("edges")
    edges = raw_edges if isinstance(raw_edges, Sequence) else []
    dimer_edges = [
        edge
        for edge in edges
        if isinstance(edge, Mapping)
        and edge.get("interface_type") == "gpcr_dimer"
        and edge.get("geometry_observed") is True
    ]
    dimer_residues = _compact_residues(
        [
            residue
            for edge in dimer_edges
            for residue in _edge_receptor_residues(edge, receptor_chain)
        ]
    )
    if dimer_residues:
        dimer_evidence = [
            _evidence(
                "T2",
                "receptor_receptor_contacts",
                "local structure analysis",
                "explicit receptor-like chains form a heavy-atom contact interface",
                direct=True,
            )
        ]
        collector.add(
            candidate_id="inhibit.dimer-interface",
            mode="inhibit",
            disposition="backup",
            mechanism="dimer-interface-blockade",
            label="Disrupt the observed receptor-receptor interface",
            residues=dimer_residues,
            evidence=dimer_evidence,
            rationale=[
                "A geometry-supported receptor interface can be tested as a separate "
                "inhibitory mechanism."
            ],
            limitations=["an observed interface does not establish physiological oligomerization"],
            family_applicability=[family_code],
        )
        collector.add(
            candidate_id="activate.dimer-interface",
            mode="activate",
            disposition="backup",
            mechanism="dimer-allosteric-stabilization",
            label="Stabilize the observed receptor-receptor interface",
            residues=dimer_residues,
            evidence=dimer_evidence,
            rationale=[
                "Interface stabilization is an independent allosteric activation hypothesis."
            ],
            limitations=["an observed interface does not establish a productive signaling dimer"],
            family_applicability=[family_code],
        )

    self_interface = _as_mapping(graph.get("self_occlusion"))
    ecd_contact_residues, mouth_contact_residues = _self_occlusion_residues(root)
    if self_interface.get("observed") is True and ecd_contact_residues and mouth_contact_residues:
        self_evidence = [
            _evidence(
                "T2",
                "ecd_7tm_contacts",
                "local structure analysis",
                "the receptor ECD forms a coordinate-derived contact interface with its 7TM mouth",
                direct=True,
            )
        ]
        combined = _compact_residues(ecd_contact_residues + mouth_contact_residues)
        collector.add(
            candidate_id="inhibit.self-occlusion",
            mode="inhibit",
            disposition="backup",
            mechanism="self-occlusion-stabilization",
            label="Stabilize the observed autoinhibitory ECD-to-7TM interface",
            residues=combined,
            evidence=self_evidence,
            rationale=[
                "Stabilizing an existing occluded geometry may preserve an inactive receptor state."
            ],
            limitations=[
                "contact geometry alone does not prove that the interface is autoinhibitory"
            ],
            family_applicability=[family_code],
        )
        collector.add(
            candidate_id="activate.self-occlusion-release",
            mode="activate",
            disposition="backup",
            mechanism="self-occlusion-release",
            label="Disrupt the observed ECD-to-7TM occluding interface",
            residues=combined,
            evidence=self_evidence,
            rationale=[
                "Releasing an observed occluding ECD interface is an independent "
                "activation hypothesis."
            ],
            limitations=[
                "the direction of functional effect requires experiment or state-paired structures"
            ],
            family_applicability=[family_code],
        )

    # Family annotations create hypotheses, never geometry claims.
    family_evidence = _evidence(
        "T4",
        "family_mechanism_prior",
        "GPCRdb receptor family annotation",
        f"family class {family_name} changes which mechanisms should be inspected "
        "but does not prove a site",
    )
    if family_code == "B2" and not self_interface.get("observed"):
        for candidate_mode, mechanism, label in (
            (
                "inhibit",
                "self-occlusion-stabilization",
                "Test ECD/GAIN/tethered-agonist autoinhibition",
            ),
            (
                "activate",
                "self-occlusion-release",
                "Test release of ECD/GAIN/tethered-agonist autoinhibition",
            ),
        ):
            collector.add(
                candidate_id=f"{candidate_mode}.unresolved-self-occlusion",
                mode=candidate_mode,
                disposition="unresolved",
                mechanism=mechanism,
                label=label,
                evidence=[family_evidence],
                rationale=[
                    "Adhesion GPCR biology makes this mechanism plausible enough to inspect."
                ],
                limitations=[
                    "no actual ECD-to-7TM contact geometry was observed in the supplied structure"
                ],
                family_applicability=["B2"],
            )
    if family_code == "C" and not dimer_residues:
        for candidate_mode, mechanism, label in (
            ("inhibit", "dimer-interface-blockade", "Test a Class C receptor-receptor interface"),
            ("activate", "dimer-allosteric-stabilization", "Test Class C dimer allostery"),
        ):
            collector.add(
                candidate_id=f"{candidate_mode}.unresolved-dimer",
                mode=candidate_mode,
                disposition="unresolved",
                mechanism=mechanism,
                label=label,
                evidence=[family_evidence],
                rationale=["Class C receptors often require receptor-receptor context."],
                limitations=[
                    "no explicit receptor-like partner with qualifying contact geometry "
                    "was supplied"
                ],
                family_applicability=["C"],
            )

    ecd_interaction_residues: list[dict[str, Any]] = []
    ecd_region_keys = {
        residue["key"]
        for region in ("extracellular_domain", "extracellular_loop", "outer_vestibule")
        for residue in regions.get(region, [])
    }
    for category in ("activate", "inhibit", "peptide"):
        ecd_interaction_residues.extend(
            residue
            for residue in interactions[category]["residues"]
            if residue["key"] in ecd_region_keys
        )
    ecd_interaction_residues = _compact_residues(ecd_interaction_residues)
    if family_code in {"B1", "C", "F"}:
        if ecd_interaction_residues:
            collector.add(
                candidate_id="activate.ecd-agonist-site",
                mode="activate",
                disposition="backup",
                mechanism="ecd-agonist-site",
                label="Engage the observed extracellular agonist-binding domain",
                residues=ecd_interaction_residues,
                evidence=[
                    _evidence(
                        "T1" if pdb_code else "T2",
                        "ecd_ligand_contacts",
                        "GPCRdb interaction annotation",
                        "ligand-contacting residues map to the receptor extracellular domain",
                        direct=True,
                        identifiers=structure_identifiers,
                    )
                ],
                rationale=[
                    "Large ECD/VFT/CRD receptors can transmit activation from an "
                    "extracellular ligand site."
                ],
                limitations=[
                    "functional direction follows ligand annotation and still requires validation"
                ],
                family_applicability=[family_code],
            )
        else:
            collector.add(
                candidate_id="activate.unresolved-ecd-site",
                mode="activate",
                disposition="unresolved",
                mechanism="ecd-agonist-site",
                label="Resolve the extracellular agonist-binding domain",
                evidence=[family_evidence],
                rationale=[
                    "This family can signal through a large extracellular ligand-binding domain."
                ],
                limitations=["no actual ligand-contact geometry mapped to the ECD"],
                family_applicability=[family_code],
            )

    allow_intracellular = bool(
        isinstance(selection, Mapping) and selection.get("allow_intracellular", False)
    )
    if intracellular and not allow_intracellular:
        for candidate_mode in ("inhibit", "activate"):
            collector.add(
                candidate_id=f"{candidate_mode}.avoid-intracellular-face",
                mode=candidate_mode,
                disposition="avoid",
                mechanism="intracellular-effector-face",
                label="Avoid intracellular-only residues for an extracellular binder",
                residues=intracellular,
                evidence=[
                    _evidence(
                        "T2",
                        "signed_membrane_geometry",
                        "local structure analysis",
                        "residues lie on the intracellular side of a reliable signed "
                        "membrane frame",
                        direct=True,
                    )
                ],
                rationale=["The default selection context assumes extracellular binder access."],
                limitations=[
                    "override with selection.allow_intracellular only for an intracellular modality"
                ],
                family_applicability=["A", "B1", "B2", "C", "F"],
            )

    gprotein_residues = list(interactions["gprotein"]["residues"])
    for edge in edges:
        if isinstance(edge, Mapping) and edge.get("interface_type") == "gprotein":
            gprotein_residues.extend(_edge_receptor_residues(edge, receptor_chain))
    gprotein_residues = _compact_residues(gprotein_residues)
    if gprotein_residues:
        for candidate_mode in ("inhibit", "activate"):
            collector.add(
                candidate_id=f"{candidate_mode}.avoid-gprotein-as-dimer",
                mode=candidate_mode,
                disposition="avoid",
                mechanism="gprotein-is-not-dimer",
                label="Do not interpret the G-protein interface as a receptor dimer",
                residues=gprotein_residues,
                evidence=[
                    _evidence(
                        "T1",
                        "gprotein_interface",
                        "GPCRdb complex interaction annotation",
                        "these receptor residues contact a signaling G protein, not another GPCR",
                        direct=True,
                        identifiers=structure_identifiers,
                    )
                ],
                rationale=[
                    "Effector contacts and receptor-receptor interfaces are different mechanisms."
                ],
                family_applicability=["A", "B1", "B2", "C", "F"],
            )

    if not frame_reliable:
        for candidate_mode in ("inhibit", "activate"):
            collector.add(
                candidate_id=f"{candidate_mode}.avoid-axis-free-pore-guess",
                mode=candidate_mode,
                disposition="avoid",
                mechanism="axis-free-pore-guess",
                label="Avoid guessing pore depth without topology and signed orientation",
                evidence=[
                    _evidence(
                        "UNRESOLVED",
                        "missing_membrane_frame",
                        "local structure analysis",
                        "topology plus extracellular/intracellular direction did not "
                        "meet reliability gates",
                    )
                ],
                rationale=[
                    "Outer, core, and inner pore labels are undefined without a reliable "
                    "signed frame."
                ],
                family_applicability=["A", "B1", "B2", "C", "F"],
            )

    _attach_mutation_evidence(collector, _mutation_records_by_residue(root, context))
    candidate_arrays = collector.arrays(requested_modes)
    root["schema_version"] = "1.0"
    root["mode"] = mode
    root["candidate_schema_version"] = CANDIDATE_SCHEMA
    root["candidates"] = candidate_arrays

    structure = dict(_as_mapping(root.get("structure")))
    structure["receptor_chain"] = receptor_chain
    root["structure"] = structure

    identity = dict(_as_mapping(root.get("identity")))
    context_identity = context.get("identity")
    if isinstance(context_identity, Mapping):
        for key in ("entry_name", "accession", "pdb_code", "preferred_chain"):
            if context_identity.get(key) is not None:
                identity[key] = context_identity[key]
    receptor = context.get("receptor")
    if isinstance(receptor, Mapping):
        identity.update(
            {
                "entry_name": receptor.get("entry_name", identity.get("entry_name")),
                "accession": receptor.get("accession", identity.get("accession")),
                "species": receptor.get("species"),
                "family_slug": receptor.get("family"),
            }
        )
        identity["status"] = "resolved"
    family_context = context.get("family")
    if isinstance(family_context, Mapping):
        identity["family_slug"] = family_context.get("slug", identity.get("family_slug"))
        identity["receptor_class"] = family_context.get("class") or family_name
        family_record = family_context.get("record")
        if isinstance(family_record, Mapping):
            identity["family"] = family_record.get("name")
    root["identity"] = identity

    state = dict(_as_mapping(root.get("state")))
    context_state = context.get("state")
    if isinstance(context_state, Mapping) and context_state.get("selected") is not None:
        state.update(
            {
                "assignment": str(context_state["selected"]).lower(),
                "source": context_state.get("source"),
                "confidence": "high",
            }
        )
    if mode == "inhibit":
        state.update({"target": "inactive", "counterstate": "active"})
    elif mode == "activate":
        state.update({"target": "active", "counterstate": "inactive"})
    else:
        state.update({"target": None, "counterstate": None})
    state.setdefault("evidence_ids", [])
    root["state"] = state
    root.setdefault("avoid", [])
    root["avoid"] = sorted(
        list(root["avoid"]),
        key=lambda item: str(item.get("id", "")) if isinstance(item, Mapping) else str(item),
    )
    existing_evidence = root.get("evidence")
    if not isinstance(existing_evidence, Sequence) or isinstance(existing_evidence, (str, bytes)):
        existing_evidence = []
    family_evidence_record = {
        "id": "evidence-family-context-"
        + hashlib.sha256(family_name.encode("utf-8")).hexdigest()[:12],
        "tier": "T3",
        "type": "family_context",
        "claim": f"candidate rules evaluated for {family_name}",
        "detail": f"candidate rules evaluated for {family_name}",
        "source": "GPCRdb receptor context",
    }
    evidence_by_id: dict[str, dict[str, Any]] = {}
    for item in (
        list(existing_evidence)
        + collector.evidence_records(requested_modes)
        + [family_evidence_record]
    ):
        if not isinstance(item, Mapping):
            continue
        record = dict(item)
        evidence_id = str(record.get("id") or "")
        if not evidence_id:
            evidence_id = (
                "evidence-"
                + hashlib.sha256(
                    json.dumps(record, sort_keys=True, default=str).encode("utf-8")
                ).hexdigest()[:16]
            )
            record["id"] = evidence_id
        evidence_by_id[evidence_id] = record
    root["evidence"] = [evidence_by_id[key] for key in sorted(evidence_by_id)]

    existing_warnings = root.get("warnings")
    warnings: list[Any] = (
        list(existing_warnings)
        if isinstance(existing_warnings, Sequence)
        and not isinstance(existing_warnings, (str, bytes))
        else []
    )
    if isinstance(context_warnings, Sequence) and not isinstance(context_warnings, (str, bytes)):
        warnings.extend(deepcopy(list(context_warnings)))
    warning_by_json = {
        json.dumps(item, ensure_ascii=True, sort_keys=True, default=str): item for item in warnings
    }
    root["warnings"] = [warning_by_json[key] for key in sorted(warning_by_json)]

    provenance = root.get("provenance")
    if isinstance(provenance, Mapping):
        provenance = dict(provenance)
    else:
        provenance = {"legacy": deepcopy(provenance)} if provenance else {}
    context_provenance = context.get("provenance")
    if isinstance(context_provenance, Sequence) and not isinstance(
        context_provenance, (str, bytes)
    ):
        provenance["gpcrdb"] = deepcopy(list(context_provenance))
    provenance["candidate_engine"] = {
        "requested_mode": mode,
        "family_code": family_code,
        "family_name": family_name,
        "ordering": "classification, evidence tier, fixed mechanism order, candidate id",
        "no_fused_winner": True,
    }
    root["provenance"] = provenance
    return root


select_hotspots = generate_candidates
build_hypotheses = generate_candidates


__all__ = [
    "CANDIDATE_SCHEMA",
    "CandidateHypothesis",
    "Evidence",
    "MAX_HOTSPOT_RESIDUES",
    "build_hypotheses",
    "generate_candidates",
    "select_hotspots",
]
