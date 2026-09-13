"""Bound fact references for Site Judge text, using the existing verified snapshot.

This is an output grammar, not a free-text truth/entailment parser. Numeric and
location literals belong in fact references; unrestricted interpretation still
requires independent scientific review. Original submissions stay in the audit.
"""

from __future__ import annotations

import re
from hashlib import sha256
from typing import Any, cast

from .contracts import AgentBoundaryError, JudgeVerdict, ResearchConclusionMismatch
from .session_store import identity

_TOKEN = re.compile(r"\[fact:([a-f0-9]{16}:[a-z]+:[0-9]+)\]")
# Deliberately a lexical output rule, not guessed numerical claim extraction.
_LITERAL = re.compile(
    r"\d|\b(?:extracellular|intracellular|cytoplasmic|transmembrane|"
    r"outer_pore|core_pore|inner_pore|ECL|ICL|TM|chain\s+[A-Za-z])\b|"
    r"细胞外|细胞内|胞外|胞内|跨膜|残基|编号",
    re.IGNORECASE,
)
_PEPTIDE = re.compile(r"(?<![A-Za-z])[ACDEFGHIKLMNPQRSTVWY]{6,}(?![A-Za-z])")


def canonical_reference(bridge: Any, dossier: dict[str, Any]) -> dict[str, Any] | None:
    """Read the already bound official record; never retrieve or realign anything."""
    expected = dossier["approved_target"].get("identity", {}).get("canonical", {})
    for annotation in dossier["reference_annotations"]:
        ref = annotation["source_ref"]
        record = bridge.document(ref)  # existing confined, content-hash checked read
        sequence = record.get("sequence", {}).get("value", "")
        if record.get("primaryAccession") != expected.get("accession") or sha256(
            sequence.encode()
        ).hexdigest() != expected.get("sequence_sha256"):
            raise AgentBoundaryError("HARD_FACT_CONTRADICTION: peptide reference mismatch")
        return {"sequence": sequence, "source_ref": ref, **expected}
    return None


def peptide_occurrences(sequence: str, peptide: str) -> list[list[int]]:
    """All exact, overlapping, one-based occurrences. Never choose the first or align variants."""
    if not peptide or not re.fullmatch(r"[ACDEFGHIKLMNPQRSTVWY]+", peptide):
        raise ValueError("Expected a literal amino-acid sequence")
    return [
        [i + 1, i + len(peptide)]
        for i in range(len(sequence) - len(peptide) + 1)
        if sequence.startswith(peptide, i)
    ]


def _rows(packet: dict[str, Any]) -> list[dict[str, Any]]:
    table = packet["residue_facts"]["facts_table"]
    return [
        dict(zip(table["mapping_columns"] + table["metric_columns"], row, strict=True))
        for row in table["rows"]
    ]


def add_fact_references(packet: dict[str, Any], canonical: dict[str, Any] | None) -> dict[str, Any]:
    """References point into the packet, avoiding another registry or competing fact table."""
    if canonical is not None:
        digest = sha256(canonical["sequence"].encode()).hexdigest()
        approved = packet["approved_target"].get("identity", {}).get("canonical", {})
        if digest != canonical["sequence_sha256"] or (
            approved.get("sequence_sha256") and digest != approved["sequence_sha256"]
        ):
            raise AgentBoundaryError("HARD_FACT_CONTRADICTION: canonical sequence binding")
    peptides: dict[str, dict[str, Any]] = {}
    passages = expand_source_passages(packet)
    for index, passage in enumerate(passages):
        if not passage.get("source_verified"):
            continue
        for sequence in _PEPTIDE.findall(passage["passage"]):
            if sequence not in peptides:
                occurrences = (
                    peptide_occurrences(canonical["sequence"], sequence) if canonical else []
                )
                peptides[sequence] = {
                    "sequence": sequence,
                    "canonical_occurrences": occurrences,
                    "status": (
                        "reference-unavailable"
                        if canonical is None
                        else "unique-exact-match"
                        if len(occurrences) == 1
                        else "multiple-exact-matches"
                        if occurrences
                        else "no-exact-match"
                    ),
                    "passage_indices": [],
                }
            peptides[sequence]["passage_indices"].append(index)
    packet["peptide_reference"] = {
        "source_ref": canonical["source_ref"] if canonical else None,
        "sequence_sha256": canonical["sequence_sha256"] if canonical else None,
        "scope": "Literal sequence candidates from verified source passages (uppercase words "
        "can also be candidates). Only exact canonical occurrences are established. No epitope, "
        "assay, construct equivalence or efficacy is inferred. Absent/repeated matches stay "
        "unresolved; variants are never aligned or guessed. Overlap is sequence correspondence "
        "only, with substitutions/unmapped members retained; no spatial inference.",
    }
    packet["peptide_facts"] = list(peptides.values())
    rows = {r["label_seq_id"]: r for r in _rows(packet)}
    overlaps = []
    for peptide_index, peptide in enumerate(packet["peptide_facts"]):
        for candidate in packet["candidate_facts"]:
            overlaps.append(
                {
                    "peptide_index": peptide_index,
                    "candidate_id": candidate["candidate_id"],
                    "occurrences": [
                        {
                            "canonical_range": interval,
                            "members": [
                                {
                                    "canonical_position": rows[label]["canonical_position"],
                                    "design_label": label,
                                    "canonical_residue": rows[label]["canonical_residue"],
                                    "design_residue": rows[label]["amino_acid"],
                                }
                                for label in candidate["design_labels"]
                                if rows[label]["canonical_position"] is not None
                                and interval[0] <= rows[label]["canonical_position"] <= interval[1]
                            ],
                        }
                        for interval in peptide["canonical_occurrences"]
                    ],
                    "unmapped_design_labels": [
                        label
                        for label in candidate["design_labels"]
                        if rows[label]["canonical_position"] is None
                    ],
                }
            )
    packet["peptide_overlaps"] = overlaps
    # Known common source metadata is stored once; exact passage strings and every
    # differing qualifier remain in their original records. Expansion is lossless.
    common_keys = {
        "binding_context",
        "does_not_support",
        "evidence_level",
        "identifier",
        "need",
        "partial",
        "primary_eligible",
        "provider",
        "source_id",
        "source_status",
        "source_verified",
        "truncated",
    }
    groups: list[dict[str, Any]] = []
    compact_passages = []
    for passage in passages:
        common = {k: v for k, v in passage.items() if k in common_keys}
        if common not in groups:
            groups.append(common)
        compact_passages.append(
            {
                "source_group": groups.index(common),
                **{k: v for k, v in passage.items() if k not in common_keys},
            }
        )
    packet["decision_evidence"]["source_metadata"] = groups
    packet["decision_evidence"]["source_passages"] = compact_passages
    references: dict[str, Any] = {}

    def collection(kind: str, path: list[str], count: int, *, single: bool = False) -> None:
        references[kind] = {"path": path, "count": count, "single": single}

    collection("target", ["approved_target", "identity"], 1, single=True)
    collection("mapping", ["residue_facts", "facts_table", "rows"], len(_rows(packet)))
    collection("candidate", ["candidate_facts"], len(packet["candidate_facts"]))
    # Topology references address the candidate's location; canonical annotations are
    # joined at rendering from the same exact mapping and official source feature table.
    collection("topology", ["candidate_facts"], len(packet["candidate_facts"]))
    collection("exclusions", ["avoid_design_labels"], 1, single=True)
    annotations = [
        ["reference_annotations", i, "features", j]
        for i, annotation in enumerate(packet["reference_annotations"])
        for j in range(len(annotation["features"]))
    ]
    references["annotation"] = {"paths": annotations, "count": len(annotations)}
    collection(
        "motif",
        ["prepared_target_context", "sequence_motifs"],
        len(packet["prepared_target_context"].get("sequence_motifs", [])),
    )
    collection("peptide", ["peptide_facts"], len(packet["peptide_facts"]))
    collection("overlap", ["peptide_overlaps"], len(overlaps))
    collection("source", ["decision_evidence", "source_passages"], len(passages))
    packet["fact_references"] = references
    packet["fact_revision"] = fact_revision(packet)
    packet["fact_reference_contract"] = (
        "In ALL Judge reasons, limitations, warnings, alternatives and correction qualifications, "
        "use [fact:REVISION:kind:index] with fact_revision and a zero-based index in "
        "fact_references. Runtime expands the addressed fact. "
        "Do not type any digits, peptide sequences, residue/chain IDs, source IDs or topology "
        "classifications outside tokens, even correct ones. Write scientific interpretation, "
        "evidence strength, risk and uncertainty in words. Exact correction.claim quotations "
        "alone are exempt and shown as quoted unaccepted Site claims. References cannot assert "
        "new ranges or memberships. The runtime table remains authoritative; a reference does "
        "not verify scientific entailment. All references are bound to this evidence revision."
    )
    return packet


def expand_source_passages(packet: dict[str, Any]) -> list[dict[str, Any]]:
    evidence = packet["decision_evidence"]
    return [
        {
            **evidence["source_metadata"][p["source_group"]],
            **{k: v for k, v in p.items() if k != "source_group"},
        }
        if "source_group" in p
        else dict(p)
        for p in evidence["source_passages"]
    ]


def fact_revision(packet: dict[str, Any]) -> str:
    return identity(
        {k: v for k, v in packet.items() if k not in {"fact_revision", "fact_reference_contract"}}
    )[:16]


def fact_paths(packet: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result = {}
    for kind, collection in packet["fact_references"].items():
        for index in range(collection["count"]):
            if "paths" in collection:
                path = collection["paths"][index]
            else:
                path = [*collection["path"], *([] if collection["single"] else [index])]
                if kind == "topology":
                    path.append("location")
            key = f"{packet['fact_revision']}:{kind}:{index}"
            result[key] = {"kind": kind, "path": path}
    return result


def _opinion_texts(verdict: JudgeVerdict) -> list[str]:
    texts = [*verdict.reasons, *verdict.limitations]
    if verdict.recommendation:
        texts += verdict.recommendation.warnings
        if verdict.recommendation.alternative:
            texts.append(verdict.recommendation.alternative)
    texts += [c.qualification for c in verdict.site_claim_corrections]
    return texts


def validate_fact_references(verdict: JudgeVerdict, packet: dict[str, Any]) -> None:
    """Same check before persistence and before card rendering, including legacy assessments."""
    if "fact_references" not in packet:
        return  # Target/Design and pre-dossier Site contracts retain their existing semantics.
    if packet["fact_revision"] != fact_revision(packet):
        raise ResearchConclusionMismatch("JUDGE_FACT_REFERENCE: changed referenced fact")
    references = fact_paths(packet)
    for text in _opinion_texts(verdict):
        tokens = _TOKEN.findall(text)
        if any(key not in references for key in tokens):
            raise ResearchConclusionMismatch("JUDGE_FACT_REFERENCE: unknown or stale fact ID")
        prose = _TOKEN.sub(" verified fact ", text)
        if (
            "[fact:" in prose
            or _LITERAL.search(prose)
            or any(p["sequence"] in prose for p in packet["peptide_facts"])
        ):
            raise ResearchConclusionMismatch(
                "JUDGE_FACT_REFERENCE: use supplied [fact:REVISION:kind:index] tokens "
                "for all numeric, "
                "peptide, chain, source and topology facts; runtime renders the exact values. "
                "Keep scientific reasoning and uncertainty in words, with no factual literals. "
                "Do not change scientific verdict just to satisfy this output grammar. "
                + f"Unbound opinion text requiring correction: {text[:350]!r}"
            )
        expanded = _TOKEN.sub(lambda m: render_fact(packet, m[1]), text)
        limit = 800 if text in [c.qualification for c in verdict.site_claim_corrections] else 1500
        if len(expanded) > limit:
            raise ResearchConclusionMismatch(
                "JUDGE_FACT_REFERENCE: rendered text exceeds the existing field limit; "
                "use fewer references per field and concise interpretation."
            )


def render_fact(packet: dict[str, Any], key: str) -> str:
    ref = fact_paths(packet)[key]
    value: Any = packet
    for part in ref["path"]:
        value = value[part]
    kind = ref["kind"]
    if kind == "peptide":
        ranges = ", ".join(f"{a}–{b}" for a, b in value["canonical_occurrences"])
        return (
            f"Source sequence token {value['sequence']} "
            f"(canonical {ranges or 'unresolved'}; {value['status']})"
        )
    if kind == "mapping":
        row = _rows(packet)[ref["path"][-1]]
        return (
            f"canonical {row['canonical_residue']}{row['canonical_position']} → design "
            f"{row['amino_acid']}{row['label_seq_id']}; chain {row['label_chain_id']}; "
            f"source author {row['source_author_chain_id']}:{row['source_author_residue_id']}; "
            f"construct {row['construct_position']}; mapping {row['mapping_status']}"
        )
    if kind == "candidate":
        rows = {r["label_seq_id"]: r for r in _rows(packet)}
        pairs = ", ".join(
            f"{rows[label]['canonical_position']}→{label}" for label in value["design_labels"]
        )
        return f"{value['candidate_id']} (canonical→design: {pairs})"
    if kind == "topology":
        from .site_authority import sequence_topology

        candidate = packet["candidate_facts"][ref["path"][1]]
        rows = {r["label_seq_id"]: r for r in _rows(packet)}
        topology = value.get(
            "sequence_topology",
            sequence_topology(
                [rows[label]["canonical_position"] for label in candidate["design_labels"]],
                packet["reference_annotations"],
            ),
        )
        annotations = "; ".join(
            f"{row['canonical_position']}: "
            + ", ".join(a["description"] or a["type"] for a in row["annotations"])
            for row in topology
        )
        regions = sorted({p["region"] for p in value.get("membrane_geometry", [])})
        return (
            f"Canonical annotations [{annotations}]; GPCRdb segments {value['segments']}; "
            f"kernel point regions {regions or 'unavailable'}. Distinct scopes; "
            "no whole-binder clearance established."
        )
    if kind == "overlap":
        peptide = packet["peptide_facts"][value["peptide_index"]]
        intervals = "; ".join(
            f"canonical {o['canonical_range']}: "
            + ", ".join(
                f"{m['canonical_position']}→{m['design_label']} "
                f"({m['canonical_residue']}→{m['design_residue']})"
                for m in o["members"]
            )
            for o in value["occurrences"]
        )
        return (
            f"{value['candidate_id']} / {peptide['sequence']} overlap "
            f"(canonical→design): {intervals or 'unresolved'}; "
            f"unmapped labels {value['unmapped_design_labels']}. Sequence relation only."
        )
    if kind == "source":
        value = expand_source_passages(packet)[ref["path"][-1]]
        return (
            f"{value.get('provider', 'source')}:{value.get('identifier', value.get('card_id'))} "
            f"[{value.get('card_id')}; {value.get('evidence_level', 'scope in source passage')}]"
        )
    # Structured JSON preserves nulls, scopes and per-occurrence ambiguity, especially topology.
    import json

    return f"{kind}: " + json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def render_judge(verdict: JudgeVerdict, packet: dict[str, Any]) -> dict[str, Any]:
    validate_fact_references(verdict, packet)
    result = verdict.model_dump(mode="json")
    if "fact_references" not in packet:
        return result

    def render(value: Any) -> Any:
        if isinstance(value, str):
            return _TOKEN.sub(lambda m: render_fact(packet, m[1]), value)
        if isinstance(value, list):
            return [render(v) for v in value]
        if isinstance(value, dict):
            return {k: v if k == "claim" else render(v) for k, v in value.items()}
        return value

    return cast(dict[str, Any], render(result))
