"""Capacity-aware scientific comparison over every eligible native Scale candidate.

Runtime determines membership and capacity, never a scientific score. Large populations
use recorded model comparisons; hierarchy is an approximation, not an exhaustive global rank.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.utils.function_calling import convert_to_openai_tool
from pydantic import BaseModel, Field, create_model

from .context_policy import context_usage
from .contracts import AgentBoundaryError, Identifier, StrictDTO
from .models import ModelConfig
from .phase34_model import structured_opinion
from .phase34_opinions import FinalSelectionOpinion
from .session_store import compact, identity

PROTOCOL = "native-global-comparison-v1"
REPAIR_RESERVE = 6000


class ScaleRankingOpinion(StrictDTO):
    """Compare ALL supplied candidates; retain leaders and scientifically useful tradeoffs."""

    candidate_order: list[Identifier] = Field(min_length=1)
    advance_candidate_ids: list[Identifier] = Field(min_length=1)
    tradeoff_candidate_ids: list[Identifier] = Field(default_factory=list)
    rationale: list[Annotated[str, Field(min_length=1, max_length=240)]] = Field(
        min_length=1, max_length=6
    )


def shared_ranking_reference() -> str:
    return (Path(__file__).with_name("skills") / "shared/candidate-ranking.md").read_text()


def compact_selection_packet(packet: dict[str, Any], ids: tuple[str, ...]) -> dict[str, Any]:
    """Lossless dictionary encoding of the decision view, with raw dossiers referenced."""
    facts = packet["facts"]
    columns = sorted({key for cid in ids for key in facts[cid]})
    # Fact values remain exact. Repeated profiles, risks, sequences and vectors appear once.
    tables: dict[str, list[Any]] = {key: [] for key in columns}
    lookups: dict[str, dict[str, int]] = {key: {} for key in columns}
    rows = []
    for cid in ids:
        row: list[Any] = [cid]
        for key in columns:
            value = facts[cid].get(key)
            encoded = compact(value)
            if encoded not in lookups[key]:
                lookups[key][encoded] = len(tables[key])
                tables[key].append(value)
            row.append(lookups[key][encoded])
        rows.append(row)
    return {
        **{key: value for key, value in packet.items() if key != "facts"},
        "ranking_protocol": PROTOCOL,
        "candidate_count": len(ids),
        "candidate_columns": ["candidate_id", *columns],
        "value_tables": tables,
        "candidate_matrix": rows,
        "matrix_semantics": "First cell is candidate_id; every other cell indexes that "
        "column's value_tables array (zero-based). Null is missing, never zero. "
        "All rows are native PASS under their own recorded profiles. Compare raw metric "
        "values and scope using the shared scientific reference. Development rank is "
        "historical engineering order, not a prior for your ranking. Equal sequences can "
        "have different poses/evidence; review them before choosing a panel representative.",
    }


def comparison_schema(schema: type[BaseModel], packet: dict[str, Any]) -> type[BaseModel]:
    """Bound output as well as input; keep the existing public tool and stored DTO."""
    if schema.__name__ != "FinalSelectionOpinion":
        return schema
    brief = Annotated[str, Field(min_length=1, max_length=160)]
    fields: dict[str, Any] = {
        "primary_candidate_ids": (
            list[Identifier],
            Field(min_length=1, max_length=packet["requested_primary_count"]),
        ),
        "backup_candidate_ids": (
            list[Identifier],
            Field(default_factory=list, max_length=packet["requested_backup_count"]),
        ),
        "selection_gap_reason": (brief | None, None),
    }
    for name in (
        "selection_rationale",
        "major_risks",
        "diversity_coverage",
        "unresolved_questions",
    ):
        fields[name] = (list[brief], Field(min_length=1, max_length=3))
    return create_model(schema.__name__, __config__=schema.model_config, **fields)


def call_fits(
    packet: dict[str, Any], prompt: str, schema: type[StrictDTO], model: Any, config: ModelConfig
) -> bool:
    """Account for prompt/schema, bounded repairs, provider context and output headroom."""
    try:
        usage = context_usage(
            model,
            config,
            "final-selection",
            [
                SystemMessage(content=prompt),
                HumanMessage(content=compact(packet)),
                HumanMessage(content="x" * REPAIR_RESERVE),
            ],
            len(compact(convert_to_openai_tool(comparison_schema(schema, packet)))),
        )
    except AgentBoundaryError:
        return False
    if usage["input_chars_with_schemas"] > min(config.max_input_chars, config.hard_input_chars):
        return False
    # Conservative planning estimate, not provider billing. Long ID lists are bounded by
    # this budget too; input capacity alone must not admit an unfinishable ranking output.
    ids = [row[0] for row in packet["candidate_matrix"]]
    output_chars = 2700 + (max(map(len, ids), default=0) + 4) * (
        packet["requested_primary_count"] + packet["requested_backup_count"]
    )
    if schema is ScaleRankingOpinion:
        output_chars = 2200 + 3 * sum(len(cid) + 4 for cid in ids)
    return bool((output_chars + 1) // 2 <= config.for_role("final-selection").max_output_tokens)


def validate_ranking(opinion: ScaleRankingOpinion, ids: tuple[str, ...], advance: int) -> None:
    if len(opinion.candidate_order) != len(ids) or set(opinion.candidate_order) != set(ids):
        raise AgentBoundaryError("candidate_order must contain EVERY supplied ID exactly once")
    selected = opinion.advance_candidate_ids
    if len(selected) != advance or len(set(selected)) != advance or not set(selected) <= set(ids):
        raise AgentBoundaryError("advance_candidate_ids must meet the exact supplied capacity")
    if opinion.candidate_order[0] not in selected:
        raise AgentBoundaryError("The leading candidate must advance")
    if not set(opinion.tradeoff_candidate_ids) <= set(selected):
        raise AgentBoundaryError("Material tradeoff candidates must be retained in the advance set")
    if len(set(opinion.tradeoff_candidate_ids)) != len(opinion.tradeoff_candidate_ids):
        raise AgentBoundaryError("Tradeoff candidate IDs must be unique")
    if any(not reason or len(reason) > 240 for reason in opinion.rationale):
        raise AgentBoundaryError("Each ranking rationale must contain 1..240 characters")


def capacity_groups(
    packet: dict[str, Any],
    ids: tuple[str, ...],
    prompt: str,
    model: Any,
    config: ModelConfig,
    panel_count: int,
) -> list[tuple[str, ...]]:
    """Partition by actual call size, independent of source batches or RMSD ranks."""
    # Stable hash mixing prevents original batch/Arm blocks becoming scientific cohorts.
    ordered = tuple(sorted(ids, key=lambda cid: hashlib.sha256(cid.encode()).hexdigest()))
    groups: list[tuple[str, ...]] = []
    pending = [ordered]
    while pending:
        group = pending.pop(0)
        view = compact_selection_packet(packet, group)
        view["advance_count"] = min(len(group), max(panel_count, (len(group) + 1) // 2))
        if call_fits(view, prompt, ScaleRankingOpinion, model, config):
            groups.append(group)
        elif len(group) <= 1:
            raise AgentBoundaryError("A single candidate exceeds the ranking context budget")
        else:
            mid = len(group) // 2
            pending[0:0] = [group[:mid], group[mid:]]
    return groups


async def select_native_panel(
    *,
    bridge: Any,
    model: Any,
    config: ModelConfig,
    execution_id: str,
    packet: dict[str, Any],
    prompt: str,
    validate: Callable[[FinalSelectionOpinion], Any],
    still_current: Callable[[], None],
) -> tuple[FinalSelectionOpinion, dict[str, Any]]:
    """Every PASS is compared; only scientific opinions narrow oversized populations."""
    reference = shared_ranking_reference()
    prompt = prompt + "\n" + reference
    packet = {
        **packet,
        "ranking_reference_sha256": hashlib.sha256(reference.encode()).hexdigest(),
        "ranking_config_sha256": identity(config.model_dump(mode="json")),
        "ranking_implementation_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    source_ids = tuple(sorted(packet["facts"]))
    ids = source_ids
    panel_count = packet["requested_primary_count"] + packet["requested_backup_count"]
    steps: list[dict[str, Any]] = []
    coverage: set[str] = set()
    round_index = 0
    ranking_prompt = reference + (
        "\nYou are the Final Selection Specialist performing a capacity-limited comparison. "
        "Submit ScaleRankingOpinion immediately; no prose. Rank EVERY supplied candidate "
        "once in candidate_order. Advance exactly advance_count distinct IDs: retain the "
        "leader and useful scientific tradeoffs, complementary interfaces or diversity. "
        "tradeoff_candidate_ids is a subset of the advancing IDs, not extra capacity. "
        "Use at most six rationales, each under 240 characters. No per-batch quota, new "
        "filter, fixed weighted score or RMSD-only order. This is provisional local "
        "comparison; subsequent rounds compare survivors globally."
    )
    while True:
        view = compact_selection_packet(packet, ids)
        view["comparison_scope"] = {
            "source_candidate_count": len(source_ids),
            "reviewed_candidate_count": len(coverage),
            "round": round_index,
            "mode": "global-direct" if not steps else "hierarchical",
            "limitation": "Hierarchy is approximate; all source rows were reviewed, but "
            "a candidate excluded by an earlier scientific comparison is not reconsidered here."
            if steps
            else "All eligible source candidates are present in this call.",
        }
        if call_fits(view, prompt, FinalSelectionOpinion, model, config):

            def validate_final(
                opinion: FinalSelectionOpinion, allowed: tuple[str, ...] = ids
            ) -> Any:
                selected = opinion.primary_candidate_ids + opinion.backup_candidate_ids
                if not set(selected) <= set(allowed):
                    raise AgentBoundaryError("Final panel cites an ID outside this comparison")
                sequences = [packet["facts"][cid]["sequence"] for cid in selected]
                if len(sequences) != len(set(sequences)):
                    raise AgentBoundaryError(
                        "Choose only one representative of each exact sequence"
                    )
                return validate(opinion)

            still_current()
            opinion = await structured_opinion(
                bridge=bridge,
                model=model,
                config=config,
                execution_id=execution_id,
                role="final-selection",
                schema=FinalSelectionOpinion,
                packet=view,
                prompt=prompt,
                validate=validate_final,
                delta_repair=True,
                resume_across_executions=True,
            )
            coverage.update(ids)
            if coverage != set(source_ids):
                raise AgentBoundaryError("Scientific comparison coverage is incomplete")
            return opinion, {
                "protocol": PROTOCOL,
                "evidence_id": packet["evidence_id"],
                "global_pool_sha256": packet["global_pool_sha256"],
                "reference_sha256": packet["ranking_reference_sha256"],
                "mode": "hierarchical" if steps else "global-direct",
                "source_candidate_ids": source_ids,
                "reviewed_candidate_ids": sorted(coverage),
                "final_comparison_ids": ids,
                "steps": steps,
                "limitation": view["comparison_scope"]["limitation"],
            }
        groups = capacity_groups(packet, ids, ranking_prompt, model, config, panel_count)
        if sum(min(len(g), max(panel_count, (len(g) + 1) // 2)) for g in groups) >= len(ids):
            raise AgentBoundaryError(
                "Ranking budget cannot retain the requested panel capacity; increase the "
                "context/output budget or request a smaller panel"
            )
        advanced = []
        for index, group in enumerate(groups):
            advance = min(len(group), max(panel_count, (len(group) + 1) // 2))
            group_view = compact_selection_packet(packet, group)
            group_view.update(
                advance_count=advance,
                comparison_round=round_index,
                comparison_group=index,
                source_candidate_count=len(source_ids),
            )

            def check(
                opinion: ScaleRankingOpinion, members: tuple[str, ...] = group, count: int = advance
            ) -> None:
                validate_ranking(opinion, members, count)

            still_current()
            ranked = await structured_opinion(
                bridge=bridge,
                model=model,
                config=config,
                execution_id=execution_id,
                role="final-selection",
                schema=ScaleRankingOpinion,
                packet=group_view,
                prompt=ranking_prompt,
                validate=check,
                delta_repair=True,
                resume_across_executions=True,
            )
            coverage.update(group)
            advanced.extend(ranked.advance_candidate_ids)
            step = {
                "round": round_index,
                "group": index,
                "input_ids": group,
                "opinion": ranked.model_dump(mode="json"),
            }
            steps.append(step)
            bridge.store.event(
                bridge.thread,
                "phase4-ranking-comparison",
                {
                    "evidence_id": packet["evidence_id"],
                    **step,
                },
            )
        if len(advanced) >= len(ids):
            raise AgentBoundaryError(
                "Ranking budget cannot reduce the population while retaining panel capacity; "
                "increase context/output budget or request a smaller panel"
            )
        ids = tuple(sorted(advanced))
        round_index += 1
