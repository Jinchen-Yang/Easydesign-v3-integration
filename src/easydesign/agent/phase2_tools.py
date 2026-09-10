"""Role-bound scientific tools, reusing the single Phase 1 interrupt/response handler."""

from __future__ import annotations

from typing import Any

from .contracts import AgentBoundaryError, EmptyArguments, EvidenceBinding
from .phase2 import Phase2Bridge
from .site_contracts import SiteQuery
from .tools import JUDGE_EVIDENCE, build_tools

PHASE2_ALLOWED = {
    "coordinator": {
        "task",
        "read_file",
        "read_target_evidence",
        "get_job_status",
        "request_scientific_decision",
        "read_scientific_state",
    },
    "target": {"read_file", "read_target_evidence", "get_job_status", "prepare_target"},
    "site": {"read_file", "read_site_evidence", "evaluate_candidate_site"},
    "judge": {"read_file", "read_scientific_evidence"},
}


def phase2_tools(bridge: Phase2Bridge, role: str) -> list[Any]:
    from langchain_core.tools import StructuredTool

    if role == "target":
        return build_tools(bridge, role)
    if role == "coordinator":
        result = []
        for tool in build_tools(bridge, role):
            if tool.name == "apply_target_decision":
                tool = tool.model_copy(
                    update={
                        "name": "request_scientific_decision",
                        "description": (
                            "Present the current scientific decision using its trusted Judge "
                            "assessment. Use actual chain option IDs at Gate 1, option_id=site at "
                            "Gate 2. Human steering interrupts before execution."
                        ),
                    }
                )
            result.append(tool)

        async def state() -> str:
            value = bridge.scientific_state()
            if "site" in value:
                value["site"] = {
                    "selected": value["site"]["hotspots"]["hotspot_sets"],
                    "warnings": value["site"]["warnings"],
                }
            return bridge.store.offload(bridge.thread, value)

        result.append(
            StructuredTool.from_function(
                name="read_scientific_state",
                coroutine=state,
                args_schema=EmptyArguments,
                description=(
                    "Read verified target/site approval state and the current scientific question."
                ),
            )
        )
        return result
    if role == "judge":

        async def judge_read() -> str:
            evidence = bridge.judge_evidence()
            binding = EvidenceBinding.model_validate(
                {k: evidence[k] for k in EvidenceBinding.model_fields}
            )
            if binding != JUDGE_EVIDENCE.get():
                raise AgentBoundaryError("Judge may read only the exact runtime-delegated snapshot")
            return bridge.store.offload(bridge.thread, evidence)

        return [
            StructuredTool.from_function(
                name="read_scientific_evidence",
                coroutine=judge_read,
                args_schema=EmptyArguments,
                description=(
                    "Read only the bound target or Site proposal snapshot; scientific "
                    "facts, metrics and interpretation remain separate."
                ),
            )
        ]
    if role == "site":

        async def read(label_seq_ids: list[int] | None = None, offset: int = 0) -> str:
            return bridge.store.offload(
                bridge.thread,
                bridge.read_site_evidence(
                    SiteQuery(label_seq_ids=label_seq_ids or [], offset=offset)
                ),
            )

        async def evaluate(label_seq_ids: list[int], offset: int = 0) -> str:
            return bridge.store.offload(
                bridge.thread,
                bridge.evaluate_candidate(SiteQuery(label_seq_ids=label_seq_ids, offset=offset)),
            )

        return [
            StructuredTool.from_function(
                name="read_site_evidence",
                coroutine=read,
                args_schema=SiteQuery,
                description=(
                    "Read approved target mapping, existing SASA/geometry, declared biology"
                    " and limitations. At most 40 residues per page; optional exact labels "
                    "or offset. Does not approve a site."
                ),
            ),
            StructuredTool.from_function(
                name="evaluate_candidate_site",
                coroutine=evaluate,
                args_schema=SiteQuery,
                description=(
                    "Evaluate explicit approved label_seq_ids with existing mapping, "
                    "coordinate and region geometry validators. Returns hard blockers "
                    "separately from scientific warnings. No approval or target change."
                ),
            ),
        ]
    raise AgentBoundaryError("Unknown Phase 2 specialist")
