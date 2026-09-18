"""One authoritative Site Judge view of verified artifacts, without repeating science."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from .contracts import (
    AgentBoundaryError,
    EvidenceBinding,
    JudgeStageMismatch,
    JudgeVerdict,
    ResearchConclusionMismatch,
)
from .site_authority import sequence_topology
from .site_decision import compile_site_decision, parse_site_decision


class JudgeReviewPacket(EvidenceBinding):
    """Runtime output only; the Judge never authors identities, candidates or measurements."""

    kind: Literal["site-judge-review-packet-v1"] = "site-judge-review-packet-v1"
    gate_type: Literal["site-hotspot"] = "site-hotspot"
    project_id: str
    run_id: str
    status: str
    user_objective: str
    objective_requirements: dict[str, Any] = Field(default_factory=dict)
    approved_target: dict[str, Any]
    runtime_status: dict[str, Any]
    residue_facts: dict[str, Any]
    residue_constraints: list[dict[str, Any]]
    candidate_facts: list[dict[str, Any]]
    candidate_evaluation_scope: dict[str, Any]
    reference_annotations: list[dict[str, Any]]
    receptor_context: list[dict[str, Any]]
    prepared_target_context: dict[str, Any]
    final_site_decision: dict[str, Any]
    decision_evidence: dict[str, Any]
    downstream_validation: dict[str, Any]
    authority: str = Field(
        default=(
            "Runtime owns approved identity, exact correspondence/membership, annotation and "
            "computed facts. final_site_decision is unapproved model interpretation. Original "
            "passages retain their scope and provenance, including opposition; retrieval is not "
            "entailment. Research opinions are retained only in the durable Dossier. Gate 2 "
            "requires a reasonable hotspot with correct facts, respected hard constraints and "
            "honest risks, not proof of downstream binding or function."
        )
    )


def validate_candidate_facts(
    dossier: dict[str, Any], intent: dict[str, Any], facts: dict[str, Any]
) -> None:
    """Check joins against existing mapping/annotations; never recalculate a scientific kernel."""
    table = dossier["trusted_residue_facts"]["facts_table"]
    columns = table["mapping_columns"] + table["metric_columns"]
    rows = [dict(zip(columns, values, strict=True)) for values in table["rows"]]
    by_label = {row["label_seq_id"]: row for row in rows}
    if len(by_label) != len(rows):
        raise AgentBoundaryError("HARD_FACT_CONTRADICTION: duplicate authoritative mapping rows")
    mapping = {row["label_seq_id"]: row for row in facts["observed_facts"]["mapping"]}
    for label, row in by_label.items():
        if label not in mapping or any(
            row[key] != mapping[label].get(key) for key in table["mapping_columns"]
        ):
            raise AgentBoundaryError("HARD_FACT_CONTRADICTION: canonical/design mapping mismatch")
    memberships = []
    candidate_ids = [c["candidate_id"] for c in dossier["candidate_comparison"]]
    if len(candidate_ids) != len(set(candidate_ids)):
        raise AgentBoundaryError("HARD_FACT_CONTRADICTION: duplicate candidate identity")
    from .site_decision import verified_location_conflict
    from .site_evidence import hard_site_conflict

    required_compartment = dossier.get("objective_requirements", {}).get(
        "required_site_compartment"
    )

    for candidate in dossier["candidate_comparison"]:
        labels = candidate["research_hypothesis"]["hotspot_label_seq_ids"]
        evaluation = candidate["deterministic_evaluation"]
        verified_conflict = verified_location_conflict(
            candidate.get("location", {}), required_compartment
        )
        eligibility = candidate.get("runtime_eligibility", {})
        expected_status = "BLOCKED" if verified_conflict else "ELIGIBLE"
        if eligibility and (
            eligibility.get("status") != expected_status
            or eligibility.get("cause") != verified_conflict
            or eligibility.get("required_site_compartment") != required_compartment
        ):
            raise AgentBoundaryError(
                "HARD_FACT_CONTRADICTION: candidate compartment eligibility mismatch"
            )
        conflict = hard_site_conflict(facts, labels)
        if evaluation["status"] == "BLOCKED":
            if conflict != evaluation.get("cause"):
                raise AgentBoundaryError("HARD_FACT_CONTRADICTION: unsubstantiated candidate block")
        elif conflict:
            raise AgentBoundaryError("HARD_FACT_CONTRADICTION: candidate hard error was hidden")
        known_labels = [label for label in labels if label in by_label]
        if len(labels) != len(set(labels)) or (not conflict and len(known_labels) != len(labels)):
            raise AgentBoundaryError("HARD_FACT_CONTRADICTION: candidate membership mismatch")
        memberships.append(set(labels))
        positions = [by_label[label]["canonical_position"] for label in known_labels]
        location = candidate["location"]
        if location["canonical_positions"] != positions:
            raise AgentBoundaryError(
                "HARD_FACT_CONTRADICTION: candidate canonical mapping mismatch"
            )
        if location["sequence_topology"] != sequence_topology(
            positions, dossier["reference_annotations"]
        ):
            raise AgentBoundaryError("HARD_FACT_CONTRADICTION: authoritative topology mismatch")
        evaluation = candidate["deterministic_evaluation"]
        if conflict:
            # No metrics are asserted for a hard-invalid candidate; its exact submitted labels
            # and verified exclusion cause are retained, without fabricated mapping rows.
            if evaluation.get("surface_evidence") or evaluation.get("mapped_residues"):
                raise AgentBoundaryError(
                    "HARD_FACT_CONTRADICTION: blocked candidate asserts metrics"
                )
            continue
        for collection in ("surface_evidence", "mapped_residues"):
            members = [row["label_seq_id"] for row in evaluation.get(collection, [])]
            if len(members) != len(set(members)) or set(members) != set(labels):
                raise AgentBoundaryError(
                    "HARD_FACT_CONTRADICTION: candidate evaluation scope mismatch"
                )
        for surface in evaluation.get("surface_evidence", []):
            surface_row = by_label.get(surface["label_seq_id"])
            if (
                surface_row is None
                or surface["rsasa"] != surface_row["rsasa"]
                or surface["eligible"] != surface_row["surface_eligible"]
            ):
                raise AgentBoundaryError("HARD_FACT_CONTRADICTION: competing surface measurements")
        field_mapping = {
            "label_seq_id": "label_seq_id",
            "amino_acid": "amino_acid",
            "label_asym_id": "label_chain_id",
            "auth_asym_id": "author_chain_id",
            "auth_seq_id": "author_residue_id",
            "sequence_index": "sequence_index",
            "source_auth_asym_id": "source_author_chain_id",
            "source_auth_seq_id": "source_author_residue_id",
            "insertion_code": "insertion_code",
        }
        for member in evaluation.get("mapped_residues", []):
            member_row = by_label.get(member["label_seq_id"])
            if member_row is None or any(
                member[key] != member_row[value]
                for key, value in field_mapping.items()
                if key in member
            ):
                raise AgentBoundaryError("HARD_FACT_CONTRADICTION: competing candidate mapping")
    for selection in [intent["selected_site"], *intent["alternatives"]]:
        labels = selection["hotspot_label_seq_ids"]
        if len(labels) != len(set(labels)) or set(labels) not in memberships:
            raise AgentBoundaryError(
                "HARD_FACT_CONTRADICTION: selected candidate membership mismatch"
            )
    excluded = set(intent.get("avoid_label_seq_ids", []))
    biology = facts.get("declared_biology")
    if biology:
        excluded.update(
            label
            for feature in biology["features"]
            if feature["kind"] == "exclude"
            for label in feature["label_seq_ids"]
        )
    selectable = (
        [entry["site"] for entry in intent["portfolio"] if entry["selectable"]]
        if intent.get("portfolio")
        else [intent["selected_site"]]
    )
    if any(excluded.intersection(site["hotspot_label_seq_ids"]) for site in selectable):
        raise AgentBoundaryError(
            "HARD_FACT_CONTRADICTION: selected hotspot violates avoid constraint"
        )


def validate_judge_stage(verdict: JudgeVerdict, snapshot: dict[str, Any]) -> None:
    """Validate stage meaning before persistence; never rewrite a scientific opinion."""
    pending = (
        snapshot.get("status") == "awaiting-human-approval"
        and snapshot.get("request_identity") is not None
    )
    completed_target = (
        snapshot.get("status") == "succeeded"
        and snapshot.get("request_identity") is None
        and snapshot.get("gate_type") in {None, "target-structure"}
        and bool(snapshot.get("bundle"))
    )
    if verdict.verdict == "assessed" and not completed_target:
        raise JudgeStageMismatch(
            "JUDGE_STAGE_MISMATCH: assessed is only valid for a verified completed "
            "Target-only bundle without a pending question. Current Gate: "
            + str(snapshot.get("gate_type", "target-structure"))
            + ", status: "
            + str(snapshot.get("status"))
            + ". For a pending Gate, use ready-to-ask only if scientifically reviewable; "
            "use insufficient or reject when warranted. Preserve reasons, evidence and "
            "limitations; no Scientist approval or stage completion is implied."
        )
    if verdict.verdict == "ready-to-ask" and not pending:
        raise JudgeStageMismatch(
            "JUDGE_STAGE_MISMATCH: No pending scientific question to ask. "
            "Use assessed only for a verified completed Target-only bundle; "
            "do not create or infer a Scientist Gate or approval."
        )


def validate_judge_corrections(verdict: JudgeVerdict, snapshot: dict[str, Any]) -> None:
    if not verdict.site_claim_corrections:
        return
    if snapshot.get("gate_type") != "site-hotspot":
        raise ResearchConclusionMismatch("Site claim corrections belong only to Gate 2")
    interpretation = snapshot.get("final_site_decision", {}).get(
        "interpretation", snapshot.get("proposal", {})
    )

    def texts(value: Any) -> list[str]:
        if isinstance(value, str):
            return [value]
        if isinstance(value, dict):
            return [text for child in value.values() for text in texts(child)]
        if isinstance(value, list):
            return [text for child in value for text in texts(child)]
        return []

    if any(
        not any(c.claim in text for text in texts(interpretation))
        for c in verdict.site_claim_corrections
    ):
        raise ResearchConclusionMismatch("Quote an exact current Site claim to qualify it")


def build_judge_packet(
    snapshot: dict[str, Any],
    dossier: dict[str, Any],
    facts: dict[str, Any],
    *,
    goal: str,
    decision: dict[str, Any] | None = None,
    canonical: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Project already verified artifacts. Every scoped passage/qualifier remains unchanged."""
    intent = snapshot["proposal"]
    validate_candidate_facts(dossier, intent, facts)
    if dossier["approved_target"]["hard_facts"] != snapshot["target_facts"]:
        raise AgentBoundaryError("HARD_FACT_CONTRADICTION: approved Target identity mismatch")
    if decision is not None:
        if (
            compile_site_decision(dossier, parse_site_decision(decision)).model_dump(mode="json")
            != intent
        ):
            raise AgentBoundaryError("HARD_FACT_CONTRADICTION: SiteDecision hydration mismatch")
        final = {
            "kind": "RankedSiteDecision" if intent.get("portfolio") else "SiteDecision",
            "interpretation": decision,
        }
    else:
        # Old immutable dossier-backed proposals may predate persisted SiteDecision events.
        # Preserve their actual interpretation; do not manufacture a historical model output.
        final = {"kind": "hydrated-SiteIntent", "interpretation": intent}
    candidates = []
    evaluations = [c["deterministic_evaluation"] for c in dossier["candidate_comparison"]]
    shared_limits = (
        [
            limitation
            for limitation in evaluations[0].get("limitations", [])
            if all(limitation in evaluation.get("limitations", []) for evaluation in evaluations)
        ]
        if evaluations
        else []
    )
    for candidate in dossier["candidate_comparison"]:
        evaluation = candidate["deterministic_evaluation"]
        candidates.append(
            {
                "candidate_id": candidate["candidate_id"],
                "design_labels": candidate["research_hypothesis"]["hotspot_label_seq_ids"],
                "runtime_eligibility": candidate.get(
                    "runtime_eligibility",
                    {
                        "status": "ELIGIBLE",
                        "cause": None,
                        "required_site_compartment": None,
                    },
                ),
                # Correspondence and canonical annotation are already in the single complete
                # residue table and source annotations. Keep kernel membrane geometry distinct.
                "location": {
                    k: v
                    for k, v in candidate["location"].items()
                    if k not in {"canonical_positions", "sequence_topology"}
                },
                "prepared_target_evaluation": {
                    **{
                        k: v
                        for k, v in evaluation.items()
                        if k not in {"mapped_residues", "surface_evidence", "limitations"}
                    },
                    "additional_limitations": [
                        limitation
                        for limitation in evaluation.get("limitations", [])
                        if limitation not in shared_limits
                    ],
                },
            }
        )
    packet = JudgeReviewPacket(
        **{key: snapshot[key] for key in EvidenceBinding.model_fields},
        project_id=snapshot["project_id"],
        run_id=snapshot["run_id"],
        status=snapshot["status"],
        user_objective=goal,
        objective_requirements=dossier.get("objective_requirements", {}),
        approved_target=dossier["approved_target"],
        runtime_status=dossier["runtime_status"],
        residue_facts=dossier["trusted_residue_facts"],
        candidate_facts=candidates,
        candidate_evaluation_scope={
            "shared_limitations": shared_limits,
            "scope": "These exact prepared-target limitations apply to every candidate. "
            "Candidate-specific additional_limitations remain on that candidate. Missing "
            "prepared-chain annotations do not negate independently verified receptor facts.",
        },
        # Canonical positions/residues are already in residue_facts; constraint IDs only
        # join to design labels here. No new aliases or compressed-history representation.
        residue_constraints=[
            {key: constraint[key] for key in ("residue_id", "design_label")}
            for constraint in dossier["residue_constraints"]
        ],
        reference_annotations=dossier["reference_annotations"],
        receptor_context=dossier["receptor_context"],
        prepared_target_context=dossier["scientific_context"],
        final_site_decision=final,
        decision_evidence={
            "questions": [{"question": q["question"]} for q in dossier["decision_questions"]],
            "source_passages": dossier["focused_passages"],
            "retrieval_status": (snapshot.get("research_evidence") or {}).get(
                "retrieval_status", []
            ),
            "selection_scope": dossier["evidence_selection"],
        },
        downstream_validation={
            "approach_validation": dossier["approach_validation"],
            "stage_scope": "Whole-binder orientation/clearance, actual binding mode, affinity "
            "and functional outcome require later generation, prediction or experiments. "
            "Their absence alone does not invalidate an otherwise reasonable Gate 2 hotspot. "
            "Keep current uncertainty and structural risk explicit; never infer success.",
        },
    ).model_dump(mode="json")

    from .site_fact_integrity import add_fact_references

    packet["avoid_design_labels"] = sorted(
        set(intent.get("avoid_label_seq_ids", []))
        | {
            label
            for feature in (facts.get("declared_biology") or {}).get("features", [])
            if feature["kind"] == "exclude"
            for label in feature["label_seq_ids"]
        }
    )
    return add_fact_references(packet, canonical)
