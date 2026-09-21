"""Durable Site Research lifecycle and bounded Runtime-built model packets."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Literal

from langchain_core.messages import AIMessage, HumanMessage
from pydantic import Field

from .contracts import AgentBoundaryError, StrictDTO
from .evidence_output import receptor_research_projection, scientific_projection
from .session_store import compact
from .site_contracts import FocusedSiteQuery

if TYPE_CHECKING:
    from .phase2 import Phase2Bridge


SiteResearchMilestone = Literal[
    "initialized",
    "structured-context-acquired",
    "receptor-kernel-ready",
    "receptor-kernel-projected",
    "focused-research",
    "decision-relevant-reading",
    "evidence-sufficient",
    "budget-exhausted-with-open-uncertainty",
    "finalization-pending",
    "handoff-committed",
    "site-synthesis-ready",
]

MILESTONE_ORDER: tuple[SiteResearchMilestone, ...] = (
    "initialized",
    "structured-context-acquired",
    "receptor-kernel-ready",
    "receptor-kernel-projected",
    "focused-research",
    "decision-relevant-reading",
    "evidence-sufficient",
    "budget-exhausted-with-open-uncertainty",
    "finalization-pending",
    "handoff-committed",
    "site-synthesis-ready",
)


class SiteResearchExecutionState(StrictDTO):
    """One event-sourced execution record; no transcript inference is authoritative."""

    execution_id: str
    milestones: list[SiteResearchMilestone] = Field(default_factory=list)
    current_phase: SiteResearchMilestone
    kernel_card_id: str | None = None
    kernel_ref: dict[str, Any] | None = None
    research_query_count: int = 0
    literature_discovery_count: int = 0
    focused_passage_count: int = 0
    scientific_model_calls: int = 0
    auxiliary_model_calls: int = 0
    total_provider_calls: int = 0
    finalization_reason: str | None = None
    handoff_ref: dict[str, Any] | None = None


def _current_execution(bridge: Phase2Bridge, execution_id: str) -> None:
    execution = bridge.store.latest_execution(bridge.thread)
    if execution is None or execution["execution_id"] != execution_id:
        raise AgentBoundaryError("Site Research state is not bound to the current execution")


def mark_site_research_milestone(
    bridge: Phase2Bridge,
    execution_id: str,
    milestone: SiteResearchMilestone,
    *,
    reason: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Append an idempotent durable milestone for one execution."""
    _current_execution(bridge, execution_id)
    payload = {
        "role": "site",
        "execution_id": execution_id,
        "milestone": milestone,
        "reason": reason,
        "details": details or {},
    }
    with bridge.store.db:
        exists = bridge.store.db.execute(
            "SELECT 1 FROM events WHERE thread=? AND kind='site-research-lifecycle' "
            "AND json_extract(payload,'$.execution_id')=? "
            "AND json_extract(payload,'$.milestone')=? LIMIT 1",
            (bridge.thread, execution_id, milestone),
        ).fetchone()
        if exists is None:
            bridge.store.db.execute(
                "INSERT INTO events(thread,kind,payload) VALUES(?, 'site-research-lifecycle', ?)",
                (bridge.thread, compact(payload)),
            )


def _kernel_record(
    bridge: Phase2Bridge, execution_id: str
) -> dict[str, Any] | None:
    """Resolve the current Target-bound deterministic kernel from durable artifacts."""
    from .evidence_research import EvidenceResearch

    research = EvidenceResearch(bridge).snapshot(execution_id=execution_id)
    possible: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for query in reversed(research["queries"]):
        for card in reversed(query["cards"]):
            if card.get("provider") != "EasyDesign GPCR kernel":
                continue
            ref = next(
                (
                    item
                    for item in reversed(card.get("source_refs", []))
                    if item.get("artifact_id") == "research-receptor-analysis"
                ),
                None,
            )
            if ref is None:
                continue
            possible.append((card, ref))
    if not possible:
        return None
    target_binding = bridge.target_state()["binding"]
    for card, ref in possible:
        value = bridge.document(ref)
        if value.get("approved_design_mapping", {}).get("target_binding") != target_binding:
            continue
        return {"card_id": card["card_id"], "ref": ref, "value": value}
    return None


def refresh_site_research_activity(
    bridge: Phase2Bridge, execution_id: str
) -> SiteResearchExecutionState:
    """Reconcile durable artifacts/events into explicit monotonic milestones."""
    from .evidence_research import EvidenceResearch

    mark_site_research_milestone(bridge, execution_id, "initialized")
    mark_site_research_milestone(bridge, execution_id, "structured-context-acquired")
    research = EvidenceResearch(bridge).snapshot(execution_id=execution_id)
    kernel = _kernel_record(bridge, execution_id)
    if kernel is not None:
        mark_site_research_milestone(
            bridge,
            execution_id,
            "receptor-kernel-ready",
            details={"card_id": kernel["card_id"], "analysis_ref": kernel["ref"]},
        )
    if any(q.get("query", {}).get("operation") == "literature-search" for q in research["queries"]):
        mark_site_research_milestone(bridge, execution_id, "focused-research")
    if any(
        str(card.get("card_id", "")).startswith("passage-")
        for query in research["queries"]
        for card in query["cards"]
    ):
        mark_site_research_milestone(bridge, execution_id, "decision-relevant-reading")
    return site_research_state(bridge, execution_id)


def site_research_state(
    bridge: Phase2Bridge, execution_id: str
) -> SiteResearchExecutionState:
    """Read the current state from durable events and verified evidence only."""
    from .evidence_research import EvidenceResearch

    _current_execution(bridge, execution_id)
    lifecycle_rows = bridge.store.db.execute(
        "SELECT payload FROM events WHERE thread=? AND kind='site-research-lifecycle' "
        "AND json_extract(payload,'$.execution_id')=? ORDER BY seq",
        (bridge.thread, execution_id),
    ).fetchall()
    lifecycle = [json.loads(row[0]) for row in lifecycle_rows]
    present = {row["milestone"] for row in lifecycle}
    milestones = [item for item in MILESTONE_ORDER if item in present]
    current = milestones[-1] if milestones else "initialized"
    kernel = _kernel_record(bridge, execution_id)
    research = EvidenceResearch(bridge).snapshot(execution_id=execution_id)
    queries = research["queries"]
    focused_passages = {
        card["card_id"]
        for query in queries
        for card in query["cards"]
        if str(card.get("card_id", "")).startswith("passage-")
    }
    scientific = bridge.store.db.execute(
        "SELECT COUNT(*) FROM events WHERE thread=? AND kind='model-call' "
        "AND json_extract(payload,'$.role')='site' "
        "AND json_extract(payload,'$.execution_id')=?",
        (bridge.thread, execution_id),
    ).fetchone()[0]
    auxiliary = bridge.store.db.execute(
        "SELECT COUNT(*) FROM events WHERE thread=? AND kind='auxiliary-model-call' "
        "AND json_extract(payload,'$.role')='site' "
        "AND json_extract(payload,'$.execution_id')=?",
        (bridge.thread, execution_id),
    ).fetchone()[0]
    finalization = next(
        (
            row
            for row in reversed(lifecycle)
            if row["milestone"] in {
                "finalization-pending",
                "budget-exhausted-with-open-uncertainty",
            }
        ),
        None,
    )
    dossier = bridge.thread_latest("site-evidence-dossier")
    handoff_ref = (
        dossier.get("ref")
        if dossier is not None and dossier.get("execution_id") == execution_id
        else None
    )
    return SiteResearchExecutionState(
        execution_id=execution_id,
        milestones=milestones,
        current_phase=current,
        kernel_card_id=kernel["card_id"] if kernel else None,
        kernel_ref=kernel["ref"] if kernel else None,
        research_query_count=len(queries),
        literature_discovery_count=sum(
            q.get("query", {}).get("operation") == "literature-search" for q in queries
        ),
        focused_passage_count=len(focused_passages),
        scientific_model_calls=scientific,
        auxiliary_model_calls=auxiliary,
        total_provider_calls=scientific + auxiliary,
        finalization_reason=finalization.get("reason") if finalization else None,
        handoff_ref=handoff_ref,
    )


def _ensure_kernel_view(
    bridge: Phase2Bridge, execution_id: str, kernel: dict[str, Any]
) -> str:
    ref = f"/result-{str(kernel['ref']['sha256'])[:32]}.json"
    with bridge.store.db:
        row = bridge.store.db.execute(
            "SELECT 1 FROM events WHERE thread=? AND kind='tool-view' "
            "AND json_extract(payload,'$.role')='site' "
            "AND json_extract(payload,'$.execution_id')=? "
            "AND json_extract(payload,'$.ref')=? LIMIT 1",
            (bridge.thread, execution_id, ref),
        ).fetchone()
        if row is None:
            bridge.store.db.execute(
                "INSERT INTO events(thread,kind,payload) VALUES(?, 'tool-view', ?)",
                (
                    bridge.thread,
                    compact(
                        {
                            "role": "site",
                            "execution_id": execution_id,
                            "ref": ref,
                            "artifact": kernel["ref"],
                            "tool_call_id": "runtime-receptor-kernel-projection",
                            "judge_binding": None,
                            "projection_authority": "runtime",
                        }
                    ),
                ),
            )
    mark_site_research_milestone(
        bridge,
        execution_id,
        "receptor-kernel-projected",
        details={"card_id": kernel["card_id"], "ref": ref},
    )
    return ref


def receptor_kernel_message(
    bridge: Phase2Bridge, execution_id: str
) -> HumanMessage | None:
    """Project the already-computed kernel without a model-selected tool round trip."""
    kernel = _kernel_record(bridge, execution_id)
    if kernel is None:
        return None
    ref = _ensure_kernel_view(bridge, execution_id, kernel)
    projection = _compact_receptor_kernel(
        receptor_research_projection(kernel["value"], kernel["card_id"])
    )
    return HumanMessage(
        content=compact(
            {
                "runtime_receptor_kernel": projection,
                "full_result": ref,
                "authority": "Deterministic current-Target Runtime projection. It supplies "
                "identity, mapping, topology, geometry and candidate membership; it does not "
                "rank candidates or imply Scientist approval.",
            }
        )
    )


def _compact_receptor_kernel(projection: dict[str, Any]) -> dict[str, Any]:
    """Deduplicate one exact Site working view without changing the durable kernel.

    The full receptor artifact remains addressable through ``full_result``.  This view keeps
    every candidate, candidate residue row, mapping qualification and scientific assessment;
    it removes whole-receptor tables that are not needed to compare the supplied candidates
    and moves repeated table metadata to one shared declaration.
    """
    result = dict(projection)
    result.pop("fields", None)
    result.pop("query_scope", None)
    result.pop("declared_scope_complete", None)
    result.pop("scope_limits", None)
    identity = result.get("identity")
    if isinstance(identity, dict):
        result["identity"] = {key: value for key, value in identity.items() if key != "chains"}
    mapping = result.get("approved_design_mapping")
    if isinstance(mapping, dict):
        result["approved_design_mapping"] = {
            key: value for key, value in mapping.items() if key != "facts_table"
        }

    shared_columns: list[str] | None = None
    shared_original_columns: list[str] | None = None
    shared_constant_indexes: list[int] = []
    shared_variable_indexes: list[int] = []
    shared_constants: dict[str, Any] = {}
    overview = result.get("candidate_overview")
    if isinstance(overview, dict):
        tables = [
            candidate["residue_table"]
            for candidates in overview.values()
            if isinstance(candidates, list)
            for candidate in candidates
            if isinstance(candidate, dict)
            and isinstance(candidate.get("residue_table"), dict)
            and isinstance(candidate["residue_table"].get("columns"), list)
            and isinstance(candidate["residue_table"].get("rows"), list)
        ]
        if tables and all(table["columns"] == tables[0]["columns"] for table in tables):
            original_columns = list(tables[0]["columns"])
            all_rows = [row for table in tables for row in table["rows"]]
            if all_rows and all(len(row) == len(original_columns) for row in all_rows):
                shared_constant_indexes = [
                    index
                    for index in range(len(original_columns))
                    if all(row[index] == all_rows[0][index] for row in all_rows)
                ]
                shared_variable_indexes = [
                    index
                    for index in range(len(original_columns))
                    if index not in shared_constant_indexes
                ]
                shared_columns = [original_columns[index] for index in shared_variable_indexes]
                shared_original_columns = original_columns
                shared_constants = {
                    original_columns[index]: all_rows[0][index]
                    for index in shared_constant_indexes
                }
        compact_overview: dict[str, Any] = {}
        for mode, candidates in overview.items():
            if not isinstance(candidates, list):
                compact_overview[mode] = candidates
                continue
            compact_candidates: list[Any] = []
            for candidate in candidates:
                if not isinstance(candidate, dict):
                    compact_candidates.append(candidate)
                    continue
                item = dict(candidate)
                # The root citation contract applies to every candidate.
                item.pop("citable_evidence_card_ids", None)
                membership = item.get("approved_design_membership")
                if isinstance(membership, dict):
                    item["approved_design_membership"] = {
                        key: value for key, value in membership.items() if key != "authority"
                    }
                claims = item.get("kernel_claims")
                if isinstance(claims, list):
                    item["kernel_claims"] = [
                        {
                            key: value
                            for key, value in claim.items()
                            if key != "detail" or value != claim.get("claim")
                        }
                        if isinstance(claim, dict)
                        else claim
                        for claim in claims
                    ]
                table = item.get("residue_table")
                if isinstance(table, dict) and isinstance(table.get("columns"), list):
                    columns = table["columns"]
                    if shared_columns is None:
                        shared_columns = list(columns)
                        shared_original_columns = list(columns)
                        shared_variable_indexes = list(range(len(columns)))
                    if not shared_constants and columns == shared_original_columns:
                        # No cross-candidate constants were found.
                        item["residue_table"] = {
                            "columns_ref": "candidate_residue_columns",
                            "rows": table.get("rows", []),
                        }
                    elif columns == shared_original_columns:
                        item["residue_table"] = {
                            "columns_ref": "candidate_residue_columns",
                            "constant_columns_ref": "candidate_residue_constants",
                            "rows": [
                                [row[index] for index in shared_variable_indexes]
                                for row in table.get("rows", [])
                            ],
                        }
                    else:
                        item["residue_table"] = {
                            "columns": columns,
                            "rows": table.get("rows", []),
                        }
                compact_candidates.append(item)
            compact_overview[mode] = compact_candidates
        result["candidate_overview"] = compact_overview
    if shared_columns is not None:
        result["candidate_residue_columns"] = shared_columns
        if shared_constants:
            result["candidate_residue_constants"] = shared_constants
        result["candidate_residue_encoding"] = (
            "Every source member remains in order. Each residue_table row follows the shared "
            "variable columns; candidate_residue_constants applies to every row and retains "
            "exact common values. source_* values are provenance; "
            "approved_design_membership contains the usable design labels."
        )
    result["working_view_scope"] = (
        "Exact candidate comparison view with no reranking. Full receptor chain rows, the "
        "approved mapping facts table, topology arrays and provenance remain in full_result. "
        "source_* numbers are provenance, not design labels; use approved_design_membership. "
        "Never infer a global offset. Kernel candidates and confidence are scoped heuristics, "
        "not curated epitopes, measured effects, full-VHH access, efficacy or approval."
    )
    return result


def _evidence_card_view(card: dict[str, Any], *, operation: str | None) -> dict[str, Any]:
    if operation and operation.endswith("search"):
        # Discovery results are leads, not evidence. Keep every selectable lead and its stable
        # identifiers, but do not replay snippets or provisional limitations after each read.
        lead_keys = (
            "card_id",
            "provider",
            "identifier",
            "resolved_identifier",
            "title",
            "year",
            "doi",
            "pmcid",
            "evidence_level",
            "primary_eligible",
        )
        return {
            key: scientific_projection(card[key]) for key in lead_keys if key in card
        }
    keys = (
        "card_id",
        "provider",
        "identifier",
        "resolved_identifier",
        "title",
        "year",
        "doi",
        "pmcid",
        "evidence_level",
        "primary_eligible",
        "limitations",
        "does_not_support",
        "source_verified",
    )
    result = {key: scientific_projection(card[key]) for key in keys if key in card}
    result["allowed_strengths"] = (
        ["E1", "E2", "E3", "E4"]
        if card.get("primary_eligible") is True
        else ["E3", "E4"]
    )
    card_id = str(card.get("card_id", ""))
    passage = card.get("passage")
    if card_id.startswith("passage-") and isinstance(passage, str):
        # Exact text is required by citation validation; never summarize it here.
        result["passage"] = passage
    if card.get("corpus_ref"):
        result["full_source_acquired"] = True
        result["focused_passage_required_for_claim"] = True
    return result


def _scientific_notes(messages: list[Any]) -> list[str]:
    notes: list[str] = []
    for message in reversed(messages):
        if not isinstance(message, AIMessage) or not message.text:
            continue
        note = message.text.strip()
        if not note or note in notes:
            continue
        notes.append(note[:1000])
        if len(notes) == 2:
            break
    return list(reversed(notes))


def site_handoff_repair_outline(value: Any) -> dict[str, Any] | None:
    """Keep exact handoff choices for repair without replaying rejected scientific prose."""
    if not isinstance(value, dict):
        return None
    candidates = [
        {
            key: candidate.get(key)
            for key in (
                "name",
                "role",
                "origin",
                "hotspot_label_seq_ids",
                "evidence_card_ids",
            )
        }
        for candidate in value.get("candidates", [])
        if isinstance(candidate, dict)
    ]
    questions = []
    for question in value.get("decision_questions", []):
        if not isinstance(question, dict):
            continue
        questions.append(
            {
                "question": question.get("question"),
                "status": question.get("status"),
                "query_ids": question.get("query_ids", []),
                "evidence_refs": [
                    {
                        key: use.get(key)
                        for key in ("card_id", "relation", "strength")
                    }
                    for use in question.get("evidence", [])
                    if isinstance(use, dict)
                ],
            }
        )
    return {
        "kind": "rejected-site-handoff-repair-outline-v1",
        "candidates": candidates,
        "decision_questions": questions,
        "contradiction_search_query_ids": value.get(
            "contradiction_search_query_ids", []
        ),
        "unresolved_questions": value.get("unresolved_questions", []),
        "instruction": "Preserve these exact choices and identifiers. Rebuild concise prose and "
        "exact excerpts from the Runtime finalization packet; do not copy rejected wording.",
    }


def site_research_working_packet(
    bridge: Phase2Bridge,
    execution_id: str,
    messages: list[Any],
    *,
    reading_closed: bool,
) -> dict[str, Any]:
    """Build one bounded decision view from durable evidence, never the raw transcript."""
    from .evidence_research import EvidenceResearch

    state = refresh_site_research_activity(bridge, execution_id)
    research = EvidenceResearch(bridge).snapshot(execution_id=execution_id)
    site_context = bridge.read_site_evidence(FocusedSiteQuery())
    site_context.pop("research", None)
    kernel = _kernel_record(bridge, execution_id)
    kernel_view = None
    kernel_ref = None
    if kernel is not None:
        kernel_ref = _ensure_kernel_view(bridge, execution_id, kernel)
        kernel_view = _compact_receptor_kernel(
            receptor_research_projection(kernel["value"], kernel["card_id"])
        )
    inquiries = []
    evidence_card_catalog: dict[str, dict[str, Any]] = {}
    lead_columns = (
        "card_id",
        "provider",
        "identifier",
        "title",
        "year",
    )
    discovery_lead_rows: list[list[Any]] = []
    discovery_lead_ids: set[str] = set()
    for query in research["queries"]:
        operation = query.get("query", {}).get("operation")
        cards = [
            card
            for card in query["cards"]
            if card.get("provider") != "EasyDesign GPCR kernel"
        ]
        card_ids: list[str] = []
        for card in cards:
            view = _evidence_card_view(card, operation=operation)
            card_id = str(view.get("card_id", card.get("card_id", "")))
            if not card_id:
                continue
            card_ids.append(card_id)
            if operation and operation.endswith("search"):
                if card_id not in discovery_lead_ids:
                    discovery_lead_rows.append([view.get(key) for key in lead_columns])
                    discovery_lead_ids.add(card_id)
            else:
                evidence_card_catalog.setdefault(card_id, view)
        inquiries.append(
            {
                "query_id": query["query_id"],
                "topic": query.get("topic"),
                "question": query.get("question"),
                "operation": operation,
                "status": query.get("status"),
                "errors": query.get("errors", []),
                "discovery_lead_count": (
                    len(cards)
                    if operation and operation.endswith("search")
                    else None
                ),
                "evidence_card_ids": card_ids,
            }
        )
    packet: dict[str, Any] = {
        "runtime_site_research_packet": "v1",
        "reading_closed": reading_closed,
        "execution_state": state.model_dump(mode="json"),
        "approved_target_and_site_context": scientific_projection(site_context),
        "receptor_kernel": kernel_view,
        "receptor_kernel_full_result": kernel_ref,
        "research_inquiries": inquiries,
        "evidence_card_catalog": list(evidence_card_catalog.values()),
        "discovery_lead_table": {
            "columns": list(lead_columns),
            "rows": discovery_lead_rows,
            "authority": "Discovery metadata only, not citable evidence. Acquire and read a "
            "source before using it for a claim.",
        },
        "specialist_working_notes": _scientific_notes(messages),
        "instruction": (
            "Reading is closed. Submit one concise SiteResearchHandoff. Preserve exact card and "
            "query IDs, exact quoted passage text, material counterevidence and unresolved "
            "questions. Every decision_questions item must include question, decision_impact, "
            "query_ids, status, evidence and limitations. unresolved_questions is a list of "
            "plain strings. If reading closed before Runtime issued any research query, keep "
            "each material decision question typed with query_ids=[], status NOT_SEARCHED or "
            "UNRESOLVED, and evidence=[]; also preserve the evidence gap in stopping_reason "
            "and unresolved_questions. Never invent a sentinel or source ID. This empty-ID "
            "form is invalid once Runtime has issued any query. Each evidence card's "
            "allowed_strengths is an immutable "
            "Runtime ceiling: never assign E1/E2 to a primary_eligible=false source. "
            "Use such sources only as E3/E4 context/scope, or keep the claim unresolved. "
            "Do not request another action."
            if reading_closed
            else "Continue only work that can change candidate order, a hard constraint or a "
            "major risk. Exact facts and source text come from this Runtime packet; specialist "
            "notes are fallible interpretation. Submit SiteResearchHandoff as soon as evidence "
            "is sufficient."
        ),
        "authority": "Complete evidence and raw source artifacts remain durable. This packet "
        "deduplicates their decision-relevant projection; it creates no scientific fact, "
        "ranking or approval.",
    }
    # Fallible notes are the only optional prose. Preserve exact focused passages, kernel
    # membership and approved Target facts if the packet is unusually large.
    if len(compact(packet)) > 56000:
        packet["specialist_working_notes"] = packet["specialist_working_notes"][-1:]
    packet["packet_chars"] = len(compact(packet))
    return packet


def site_research_packet_message(
    bridge: Phase2Bridge,
    execution_id: str,
    messages: list[Any],
    *,
    reading_closed: bool,
) -> HumanMessage:
    return HumanMessage(
        content=compact(
            site_research_working_packet(
                bridge, execution_id, messages, reading_closed=reading_closed
            )
        )
    )
