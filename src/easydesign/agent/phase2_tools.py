"""Role-bound scientific tools, reusing the single Phase 1 interrupt/response handler."""

from __future__ import annotations

from typing import Any

from .contracts import AgentBoundaryError, EmptyArguments, EvidenceBinding, ShortText, StrictDTO
from .design import DesignBridge
from .design_contracts import BinderIntent
from .design_evidence import evaluate_design, resolve_design_intent
from .evidence_corpus import corpus_tools
from .evidence_output import result_tool
from .evidence_research import identity_comparison_tool, receptor_analysis_tool, research_tool
from .phase2 import Phase2Bridge
from .site_contracts import CanonicalMappingQuery, FocusedSiteQuery, SiteQuery
from .target_identity import canonical_tool
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
    "target": {
        "read_file",
        "read_target_evidence",
        "get_job_status",
        "prepare_target",
        "research_evidence",
        "compare_reference_identity",
    },
    "site": {
        "read_file",
        "read_canonical_mapping",
        "read_site_evidence",
        "evaluate_candidate_site",
        "research_evidence",
        "compare_reference_identity",
        "analyze_receptor_context",
    },
    "judge": {"read_file", "read_scientific_evidence"},
}


DESIGN_ALLOWED = {
    **PHASE2_ALLOWED,
    "coordinator": PHASE2_ALLOWED["coordinator"] | {"reopen_site_decision"},
    "binder": {"read_file", "read_design_evidence", "evaluate_design_constraints"},
}


class ReopenSite(StrictDTO):
    reason: ShortText


def _scientific_tools(bridge: Phase2Bridge, role: str) -> list[Any]:
    from langchain_core.tools import StructuredTool

    if role == "target":
        return [
            *build_tools(bridge, role),
            canonical_tool(bridge),
            research_tool(bridge, role),
            *corpus_tools(bridge),
            identity_comparison_tool(bridge),
        ]
    if role == "coordinator":
        result = []
        for tool in build_tools(bridge, role):
            if tool.name == "apply_target_decision":
                tool = tool.model_copy(
                    update={
                        "name": "request_scientific_decision",
                        "description": (
                            "Present the current scientific decision using its trusted Judge "
                            "assessment, a verified unavailable-review record at Site Gate 2 or "
                            "Design Gate 3, or the explicit Runtime optional-review policy at "
                            "ranked Site Gate 2. "
                            "Use actual chain option IDs at Gate 1, option_id=site at "
                            "Gate 2 and option_id=design at Gate 3. "
                            "Human steering interrupts before execution."
                        ),
                    }
                )
            result.append(tool)

        async def state() -> str:
            value = {
                key: item for key, item in bridge.scientific_state().items() if key != "proposal"
            }
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
                    "Read verified approval state and next specialist. Delegate to that "
                    "specialist; the independent Judge receives the full proposal and "
                    "scoped scientific evidence."
                ),
            )
        )
        if isinstance(bridge, DesignBridge):

            async def reopen(reason: str) -> str:
                return bridge.store.offload(bridge.thread, bridge.reopen_site(reason))

            result.append(
                StructuredTool.from_function(
                    name="reopen_site_decision",
                    coroutine=reopen,
                    args_schema=ReopenSite,
                    description=(
                        "Only when trusted Gate 3 REVISE changes WHERE to bind: invalidate"
                        " Site/Design, preserve Target, then delegate Site and seek a new "
                        "Gate 2. Not for ordinary HOW/CDR revisions."
                    ),
                )
            )
        if hasattr(bridge, "downstream_scope"):
            from .phase34_tools import downstream_tools

            result.extend(downstream_tools(bridge))
        return result
    if role == "binder":
        if not isinstance(bridge, DesignBridge):
            raise AgentBoundaryError("Binder is outside this thread's scientific scope")

        async def read_design(label_seq_ids: list[int] | None = None, offset: int = 0) -> str:
            query = (
                SiteQuery(label_seq_ids=label_seq_ids or [], offset=offset)
                if label_seq_ids or offset
                else None
            )
            return bridge.store.offload(bridge.thread, bridge.read_design_evidence(query))

        async def binder_validate(**arguments: Any) -> str:
            intent = resolve_design_intent(
                BinderIntent.model_validate(arguments), bridge.read_design_evidence()
            )
            site = bridge.approved_site()
            if site is None:
                raise AgentBoundaryError("No approved hotspot")
            _, facts, _ = bridge.site_facts()
            return bridge.store.offload(
                bridge.thread,
                evaluate_design(
                    intent,
                    list(site["hotspots"]["hotspot_sets"][0]["label_seq_ids"]),
                    {r["label_seq_id"] for r in facts["observed_facts"]["mapping"]},
                    site["warnings"],
                    upstream_discouraged=site["outcome"]["action"] == "OVERRIDE",
                ),
            )

        return [
            StructuredTool.from_function(
                name="read_design_evidence",
                coroutine=read_design,
                args_schema=SiteQuery,
                description=(
                    "Read approved hotspot, upstream warnings, mapped context and "
                    "exact supported VHH/scaffold/CDR/compiler constraints. Optional "
                    "mapped residue page; no site changes or generation."
                ),
            ),
            StructuredTool.from_function(
                name="evaluate_design_constraints",
                coroutine=binder_validate,
                args_schema=BinderIntent,
                description=(
                    "Check scientific design intent against approved hotspots, "
                    "mapping, crop/exclusion and fixed first-pilot coverage. Pure "
                    "validation; final runtime callback compiles and validates YAML."
                ),
            ),
        ]
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

        async def mapping(canonical_positions: list[int]) -> str:
            return bridge.store.offload(
                bridge.thread,
                bridge.read_canonical_mapping(
                    CanonicalMappingQuery(canonical_positions=canonical_positions)
                ),
            )

        async def read(label_seq_ids: list[int] | None = None) -> str:
            return bridge.store.offload(
                bridge.thread,
                bridge.read_site_evidence(FocusedSiteQuery(label_seq_ids=label_seq_ids or [])),
            )

        async def evaluate(label_seq_ids: list[int], offset: int = 0) -> str:
            return bridge.store.offload(
                bridge.thread,
                bridge.evaluate_candidate(SiteQuery(label_seq_ids=label_seq_ids, offset=offset)),
            )

        return [
            research_tool(bridge, role),
            *corpus_tools(bridge),
            identity_comparison_tool(bridge),
            receptor_analysis_tool(bridge),
            StructuredTool.from_function(
                name="read_canonical_mapping",
                coroutine=mapping,
                args_schema=CanonicalMappingQuery,
                description=(
                    "Look up canonical annotation positions in the already approved Target "
                    "mapping before choosing design labels. Returns all exact matching rows, "
                    "ambiguity/nulls and observed design labels, including missing-coordinate "
                    "and no-correspondence results. No new alignment or approval."
                ),
            ),
            StructuredTool.from_function(
                name="read_site_evidence",
                coroutine=read,
                args_schema=FocusedSiteQuery,
                description=(
                    "Read approved Target mapping, existing SASA/geometry, declared biology "
                    "and limitations. Omit labels for the overview; otherwise supply up to "
                    "40 exact design labels and receive the complete requested patch. "
                    "No pagination offset, inferred numbering, or Site approval."
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


for _role in PHASE2_ALLOWED:
    PHASE2_ALLOWED[_role] = PHASE2_ALLOWED[_role] | {"read_evidence_result"}
PHASE2_ALLOWED["target"] |= {"propose_canonical_identity"}
for _role in ("target", "site"):
    PHASE2_ALLOWED[_role] |= {"select_evidence", "retrieve_evidence", "continue_evidence"}
DESIGN_ALLOWED.update(PHASE2_ALLOWED)
DESIGN_ALLOWED["coordinator"] = PHASE2_ALLOWED["coordinator"] | {"reopen_site_decision"}
DESIGN_ALLOWED["binder"] |= {"read_evidence_result"}


def phase2_tools(bridge: Phase2Bridge, role: str) -> list[Any]:
    return [*_scientific_tools(bridge, role), result_tool(bridge, role)]
