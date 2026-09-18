"""Prospectively declared Figure 2 controls; never enabled by the product CLI."""

from __future__ import annotations

from typing import Any

from deepagents.backends import FilesystemBackend
from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy

from .contracts import DecisionOutcome
from .design import DesignBridge
from .design_contracts import BinderIntent
from .harness import RoleBoundary
from .models import ModelConfig
from .phase2 import Phase2Bridge
from .phase2_tools import PHASE2_ALLOWED, phase2_tools
from .session_store import identity
from .site_contracts import SiteIntent
from .site_decision import (
    RankedCandidate,
    RankedSiteDecision,
    compile_site_decision,
    hydrate_site_decision,
)
from .site_dossier import SiteResearchHandoff, persist_dossier, site_dossier

CONTROL_SCIENTIFIC_TOOLS = frozenset(PHASE2_ALLOWED["site"] - {"read_file"})


def resolve_control_site_selection(
    options: list[dict[str, Any]], requested: str | None
) -> str | None:
    """Resolve a displayed A/B/C rank without changing the control model's ordering."""
    if requested not in {"A", "B", "C"}:
        return requested
    matching = [
        option
        for option in options
        if option.get("rank") == requested and option.get("eligible") is True
    ]
    if len(matching) != 1:
        raise ValueError(f"Requested rank {requested} is not selectable")
    return str(matching[0]["option_id"])


def freeze_base_tool_packet(
    *,
    case_id: str,
    source_snapshot_id: str,
    goal: str,
    tool_records: list[dict[str, Any]],
) -> dict[str, Any]:
    """Bind a prospectively declared standard tool packet without hiding its contents."""
    frozen = []
    for ordinal, record in enumerate(tool_records, start=1):
        name = record.get("name")
        if name not in CONTROL_SCIENTIFIC_TOOLS:
            raise ValueError(f"Tool is not an allowed Site scientific tool: {name}")
        arguments = record.get("arguments")
        result = record.get("result")
        if not isinstance(arguments, dict):
            raise ValueError("Frozen tool arguments must be an object")
        frozen.append(
            {
                "ordinal": ordinal,
                "name": name,
                "arguments": arguments,
                "arguments_sha256": identity(arguments),
                "result": result,
                "result_sha256": identity(result),
            }
        )
    body = {
        "schema_version": "figure2-base-llm-tools-packet-v1",
        "case_id": case_id,
        "source_snapshot_id": source_snapshot_id,
        "goal": goal,
        "tool_records": frozen,
    }
    return {**body, "packet_sha256": identity(body)}


def validate_base_tool_packet(packet: dict[str, Any]) -> dict[str, Any]:
    """Reject a packet whose identity or per-call evidence changed after freezing."""
    required = {
        "schema_version",
        "case_id",
        "source_snapshot_id",
        "goal",
        "tool_records",
        "packet_sha256",
    }
    if set(packet) != required or packet["schema_version"] != ("figure2-base-llm-tools-packet-v1"):
        raise ValueError("Invalid Base LLM + Tools packet contract")
    records = []
    for record in packet["tool_records"]:
        records.append(
            {
                "name": record.get("name"),
                "arguments": record.get("arguments"),
                "result": record.get("result"),
            }
        )
    rebuilt = freeze_base_tool_packet(
        case_id=packet["case_id"],
        source_snapshot_id=packet["source_snapshot_id"],
        goal=packet["goal"],
        tool_records=records,
    )
    if rebuilt != packet:
        raise ValueError("Base LLM + Tools packet hash mismatch")
    return packet


GENERIC_AGENT_SITE_PROMPT = (
    "Use the available scientific evidence tools to answer the supplied Site request. "
    "Return a compact SiteResearchHandoff with up to three distinct mapped candidates in "
    "preferred order. Use verified evidence, preserve material counterevidence and unknowns, "
    "and do not invent facts or approval. This is a generic tool-calling loop: no "
    "EasyDesign specialist "
    "delegation, dossier synthesis, Judge or retry is available."
)


BASE_LLM_TOOLS_PROMPT = (
    "A deterministic benchmark script already ran the declared scientific tools and supplied "
    "their frozen outputs. Use only that packet. Return one compact SiteResearchHandoff with "
    "up to three distinct mapped candidates in preferred order. Preserve counterevidence and "
    "unknowns; do not invent facts, new tool results or approval. No autonomous tool loop, "
    "specialist, scientific state, Judge or retry is available."
)


GENERIC_AGENT_BINDER_PROMPT = (
    "Use the available approved-Site and design-constraint tools to produce one executable "
    "BinderIntent for an exploratory VHH pilot. Preserve the approved target and Site; use all "
    "seven declared scaffolds and the required candidates-per-scaffold budget. Keep alternatives "
    "only when they test a distinct scientific factor. Do not invent evidence, approval or "
    "backend capability. This is a generic tool-calling loop with no EasyDesign domain Skill, "
    "specialist decomposition, Judge or structured-output retry."
)


BASE_LLM_BINDER_PROMPT = (
    "A deterministic benchmark script supplied the approved Site and the complete runtime design "
    "constraint packet. Use only that packet. Return one executable BinderIntent for an "
    "exploratory VHH pilot, retaining all seven declared scaffolds and the required "
    "candidates-per-scaffold budget. Do not invent evidence, approval or backend capability. "
    "There is no autonomous tool loop, EasyDesign domain Skill, Judge or retry."
)


def create_base_llm_tools_control(
    bridge: Phase2Bridge,
    model: Any,
    config: ModelConfig,
    goal: str,
    current_user_message: str | None,
    execution_id: str,
    revision: DecisionOutcome | None = None,
) -> Any:
    """Create the one-inference control over a separately frozen atomic-tool packet."""
    boundary = RoleBoundary(
        bridge,
        "site",
        config,
        goal,
        current_user_message,
        execution_id,
        revision,
        site_stage="research",
        domain_skills=False,
        allow_repairs=False,
    )
    # The benchmark runner, rather than the model, executes the declared tool manifest.
    # The model receives exactly those frozen results and cannot make follow-up calls.
    boundary.allowed = set()
    return create_agent(
        model=model,
        system_prompt=BASE_LLM_TOOLS_PROMPT,
        tools=[],
        middleware=[boundary],
        response_format=ToolStrategy(SiteResearchHandoff, handle_errors=boundary.contract_error),
        name="figure2-base-llm-tools-control",
    )


def create_generic_site_control(
    bridge: Phase2Bridge,
    model: Any,
    config: ModelConfig,
    backend: FilesystemBackend,
    goal: str,
    current_user_message: str | None,
    execution_id: str,
    revision: DecisionOutcome | None = None,
) -> Any:
    """Create the generic-agent control with production evidence tools and hard guards."""
    boundary = RoleBoundary(
        bridge,
        "site",
        config,
        goal,
        current_user_message,
        execution_id,
        revision,
        site_stage="research",
        domain_skills=False,
        allow_repairs=False,
    )
    return create_agent(
        model=model,
        system_prompt=GENERIC_AGENT_SITE_PROMPT,
        tools=phase2_tools(bridge, "site"),
        middleware=[boundary],
        response_format=ToolStrategy(SiteResearchHandoff, handle_errors=boundary.contract_error),
        name="figure2-generic-agent-control",
    )


def create_base_binder_control(
    bridge: DesignBridge,
    model: Any,
    config: ModelConfig,
    goal: str,
    current_user_message: str | None,
    execution_id: str,
    revision: DecisionOutcome | None = None,
) -> Any:
    """One Binder submission from a deterministic approved-Site constraint packet."""
    boundary = RoleBoundary(
        bridge,
        "binder",
        config,
        goal,
        current_user_message,
        execution_id,
        revision,
        domain_skills=False,
        allow_repairs=False,
    )
    boundary.allowed = set()
    return create_agent(
        model=model,
        system_prompt=BASE_LLM_BINDER_PROMPT,
        tools=[],
        middleware=[boundary],
        response_format=ToolStrategy(BinderIntent, handle_errors=boundary.contract_error),
        name="figure2-base-llm-tools-binder-control",
    )


def create_generic_binder_control(
    bridge: DesignBridge,
    model: Any,
    config: ModelConfig,
    goal: str,
    current_user_message: str | None,
    execution_id: str,
    revision: DecisionOutcome | None = None,
) -> Any:
    """Generic autonomous Binder loop using the production scientific tools and guards."""
    boundary = RoleBoundary(
        bridge,
        "binder",
        config,
        goal,
        current_user_message,
        execution_id,
        revision,
        domain_skills=False,
        allow_repairs=False,
    )
    return create_agent(
        model=model,
        system_prompt=GENERIC_AGENT_BINDER_PROMPT,
        tools=phase2_tools(bridge, "binder"),
        middleware=[boundary],
        response_format=ToolStrategy(BinderIntent, handle_errors=boundary.contract_error),
        name="figure2-generic-agent-binder-control",
    )


def ranked_decision_from_control_handoff(
    dossier: dict[str, Any], handoff: SiteResearchHandoff
) -> RankedSiteDecision:
    """Adapt the control's declared order to the shared output evaluator without reranking."""
    ids = [candidate["candidate_id"] for candidate in dossier["candidate_comparison"]]
    if len(ids) != len(handoff.candidates):
        raise ValueError("Runtime dossier changed the number of generic-control candidates")
    common_unknowns = list(handoff.unresolved_questions[:4])
    candidates = []
    for candidate_id, hypothesis in zip(ids, handoff.candidates, strict=True):
        evidence = (
            ["Handoff evidence refs: " + ", ".join(hypothesis.evidence_card_ids)]
            if hypothesis.evidence_card_ids
            else ["Runtime structural candidate evaluation; no external passage cited."]
        )
        candidates.append(
            RankedCandidate(
                candidate_id=candidate_id,
                why_ranked=hypothesis.rationale,
                mechanistic_rationale=hypothesis.rationale,
                approach_rationale=hypothesis.rationale,
                supporting_evidence=evidence,
                major_risks=common_unknowns[:2],
                uncertainty=common_unknowns,
                confidence="low",
            )
        )
    return RankedSiteDecision(candidates=candidates)


def evaluate_control_handoff(bridge: Phase2Bridge, handoff: SiteResearchHandoff) -> SiteIntent:
    """Use the same deterministic Site compiler while keeping the control dossier ephemeral."""
    dossier = site_dossier(bridge, handoff)
    return compile_site_decision(dossier, ranked_decision_from_control_handoff(dossier, handoff))


def register_control_site(
    bridge: Phase2Bridge, handoff: SiteResearchHandoff, execution_id: str
) -> dict[str, Any]:
    """Persist and compile a control Site through the same dossier and Runtime validators."""
    dossier = persist_dossier(bridge, handoff, execution_id)
    decision = ranked_decision_from_control_handoff(dossier, handoff)
    intent = hydrate_site_decision(bridge, decision, execution_id)
    dossier_event = bridge.thread_latest("site-evidence-dossier")
    if dossier_event is None:
        raise ValueError("Control Site dossier was not persisted")
    bridge.store.event(
        bridge.thread,
        "site-decision",
        {
            "execution_id": execution_id,
            "decision": decision.model_dump(mode="json"),
            "dossier_ref": dossier_event["ref"],
            "hydrated_intent_sha256": identity(intent.model_dump(mode="json")),
            "authority": "Control-model ranking; shared Runtime owns candidate membership, "
            "mapping and validation. No approval.",
        },
    )
    return bridge.register_site(intent, None)
