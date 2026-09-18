#!/usr/bin/env python3
"""Run one Figure 2 Gate 2 control in a dedicated frozen project clone."""

from __future__ import annotations

import argparse
import asyncio
import fcntl
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]
from deepagents.backends import FilesystemBackend
from langchain_core.messages import HumanMessage

from easydesign.agent.benchmark_controls import (
    create_base_binder_control,
    create_base_llm_tools_control,
    create_generic_binder_control,
    create_generic_site_control,
    register_control_site,
    resolve_control_site_selection,
    validate_base_tool_packet,
)
from easydesign.agent.benchmark_trace import collect_trace_metrics
from easydesign.agent.contracts import ApplyDecision, EvidenceBinding, JudgeVerdict
from easydesign.agent.design import BINDER_EVIDENCE, DesignBridge
from easydesign.agent.models import ModelConfig, create_models
from easydesign.agent.phase2 import SITE_EVIDENCE, Phase2Bridge
from easydesign.agent.session_store import SessionStore, compact, confined, identity
from easydesign.agent.site_dossier import SiteResearchHandoff
from easydesign.agent.tools import JUDGE_EVIDENCE


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    result.add_argument("method", choices=("base_llm_tools", "generic_agent"))
    result.add_argument("project", type=Path)
    result.add_argument("--thread", required=True)
    result.add_argument("--goal", required=True)
    result.add_argument("--models", type=Path, required=True)
    result.add_argument("--base-packet", type=Path)
    result.add_argument("--site-candidate")
    result.add_argument("--output", type=Path, required=True)
    return result


def review_and_approve(
    bridge: Phase2Bridge,
    *,
    option_id: str,
    execution_id: str,
    selected_option_id: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Use one shared deterministic Gate adapter, then the declared Codex repair operator."""
    packet = bridge.judge_evidence()
    binding = EvidenceBinding.model_validate(
        {key: packet[key] for key in EvidenceBinding.model_fields}
    )
    token = JUDGE_EVIDENCE.set(binding)
    try:
        assessment = bridge.register_judge(
            JudgeVerdict(
                verdict="ready-to-ask",
                reasons=[
                    "Shared Runtime hard-fact, mapping and compiler checks permit review."
                ],
                limitations=[
                    "This benchmark Gate adapter is deterministic and is not an independent "
                    "scientific Judge opinion."
                ],
            )
        )
    finally:
        JUDGE_EVIDENCE.reset(token)
    card = bridge.decision_card(
        ApplyDecision(assessment_id=assessment.assessment_id, option_id=option_id)
    )
    selected_option_id = resolve_control_site_selection(card.options, selected_option_id)
    bridge.store.event(
        bridge.thread,
        "figure2-control-gate-adapter",
        {
            "execution_id": execution_id,
            "gate_type": card.gate_type,
            "assessment_id": assessment.assessment_id,
            "operator": "OpenAI Codex",
            "operator_role": "human_repair",
            "scientific_judge": False,
        },
    )
    bridge.store.respond(
        bridge.thread,
        card.card_id,
        "approve",
        "OpenAI Codex human-repair operator",
        selected_option_id=selected_option_id,
    )
    outcome = bridge.apply_decision(card)
    return card.model_dump(mode="json"), outcome


async def run(arguments: argparse.Namespace) -> dict[str, Any]:
    if arguments.method == "base_llm_tools" and arguments.base_packet is None:
        raise ValueError("base_llm_tools requires --base-packet")
    if arguments.method == "generic_agent" and arguments.base_packet is not None:
        raise ValueError("generic_agent does not accept a prebuilt packet")
    project = arguments.project.resolve(strict=True)
    output = arguments.output.resolve(strict=False)
    if output.exists():
        raise FileExistsError(output)
    config = ModelConfig.model_validate(yaml.safe_load(arguments.models.read_text()))
    store = SessionStore(project)
    try:
        control_fingerprint = identity(
            {
                "contract": "figure2-pilot-ready-control-v1",
                "method": arguments.method,
                "models": config.model_dump(mode="json"),
            }
        )
        store.thread(arguments.thread, control_fingerprint, arguments.goal)
        bridge = Phase2Bridge(project, arguments.thread, store, through="design")
        if bridge.current_site() is not None:
            raise ValueError("Control clone must stop after approved Target and before Site")
        target_evidence = bridge.read_site_evidence()
        binding = EvidenceBinding.model_validate(
            {key: target_evidence[key] for key in EvidenceBinding.model_fields}
        )
        token = SITE_EVIDENCE.set(binding)
        try:
            prior_events = store.events(arguments.thread)
            after_seq = prior_events[-1]["seq"] if prior_events else 0
            started_at = datetime.now(UTC)
            started_clock = time.monotonic()
            execution = store.begin_execution(arguments.thread, arguments.goal, followup=True)
            execution_id = execution["execution_id"]
            store.event(
                arguments.thread,
                "figure2-control-method",
                {
                    "method": arguments.method,
                    "execution_id": execution_id,
                    "models_sha256": identity(config.model_dump(mode="json")),
                    "goal_sha256": identity(arguments.goal),
                },
            )
            models = create_models(config)
            if arguments.method == "base_llm_tools":
                packet = validate_base_tool_packet(json.loads(arguments.base_packet.read_text()))
                if packet["goal"] != arguments.goal:
                    raise ValueError("Base packet goal differs from this run")
                agent = create_base_llm_tools_control(
                    bridge,
                    models["site"],
                    config,
                    arguments.goal,
                    arguments.goal,
                    execution_id,
                )
                content = compact(
                    {
                        "goal": arguments.goal,
                        "approved_target": target_evidence,
                        "frozen_tool_packet": packet,
                    }
                )
            else:
                backend = FilesystemBackend(
                    root_dir=confined(
                        store.root,
                        store.root / "agent-work" / arguments.thread,
                    ),
                    virtual_mode=True,
                )
                agent = create_generic_site_control(
                    bridge,
                    models["site"],
                    config,
                    backend,
                    arguments.goal,
                    arguments.goal,
                    execution_id,
                )
                content = compact({"goal": arguments.goal, "approved_target": target_evidence})
            result = await agent.ainvoke(
                {"messages": [HumanMessage(content=content)]},
                {"recursion_limit": max(100, 2 * config.max_model_calls + 10)},
            )
            handoff = SiteResearchHandoff.model_validate(result["structured_response"])
            site_proposal = register_control_site(bridge, handoff, execution_id)
            site_card, site_outcome = review_and_approve(
                bridge,
                option_id="site",
                execution_id=execution_id,
                selected_option_id=arguments.site_candidate,
            )
            design_bridge = DesignBridge(project, arguments.thread, store)
            design_evidence = design_bridge.read_design_evidence()
            design_binding = EvidenceBinding.model_validate(
                {key: design_evidence[key] for key in EvidenceBinding.model_fields}
            )
            design_token = BINDER_EVIDENCE.set(design_binding)
            try:
                if arguments.method == "base_llm_tools":
                    binder_agent = create_base_binder_control(
                        design_bridge,
                        models["binder"],
                        config,
                        arguments.goal,
                        arguments.goal,
                        execution_id,
                    )
                    binder_content = compact(
                        {
                            "goal": arguments.goal,
                            "approved_site_and_design_constraints": design_evidence,
                        }
                    )
                else:
                    binder_agent = create_generic_binder_control(
                        design_bridge,
                        models["binder"],
                        config,
                        arguments.goal,
                        arguments.goal,
                        execution_id,
                    )
                    binder_content = compact(
                        {
                            "goal": arguments.goal,
                            "approved_site": site_outcome,
                        }
                    )
                binder_result = await binder_agent.ainvoke(
                    {"messages": [HumanMessage(content=binder_content)]},
                    {"recursion_limit": max(100, 2 * config.max_model_calls + 10)},
                )
            finally:
                BINDER_EVIDENCE.reset(design_token)
            design = design_bridge.current_design()
            if design is None:
                raise ValueError("Control Binder did not produce a current Design proposal")
            design_card, design_outcome = review_and_approve(
                design_bridge,
                option_id="design",
                execution_id=execution_id,
            )
            binder_intent = binder_result["structured_response"]
            finished_at = datetime.now(UTC)
            wall_seconds = time.monotonic() - started_clock
            trace = collect_trace_metrics(
                project / "metadata/agent.sqlite",
                thread=arguments.thread,
                execution_id=execution_id,
                after_seq=after_seq,
                source_label="metadata/agent.sqlite",
            )
            record = {
                "schema_version": "figure2-pilot-ready-control-result-v1",
                "method": arguments.method,
                "thread": arguments.thread,
                "execution_id": execution_id,
                "handoff": handoff.model_dump(mode="json"),
                "site_proposal": site_proposal,
                "site_card": site_card,
                "site_outcome": site_outcome,
                "binder_intent": binder_intent.model_dump(mode="json"),
                "design_proposal": design_bridge.design_snapshot(design),
                "design_card": design_card,
                "design_outcome": design_outcome,
                "pilot_ready": design_outcome.get("status") == "design-frozen",
                "measurement": {
                    "started_at": started_at.isoformat(),
                    "finished_at": finished_at.isoformat(),
                    "wall_seconds": wall_seconds,
                    "source_snapshot_id": target_evidence["evidence_id"],
                    "first_pass_valid": design_outcome.get("status") == "design-frozen",
                    "human_correction_count": 0,
                    "active_human_repair_seconds": 0.0,
                    "repair_policy_id": "figure2-codex-human-repair-v1",
                    "repair_operator_type": "codex",
                    "repair_operator_id": "OpenAI Codex",
                    "trace": trace,
                },
            }
            record["result_sha256"] = identity(record)
            output.parent.mkdir(parents=True, exist_ok=True)
            with output.open("x") as handle:
                json.dump(record, handle, indent=2, sort_keys=True)
                handle.write("\n")
            return record
        finally:
            SITE_EVIDENCE.reset(token)
    finally:
        store.close()


def main() -> None:
    arguments = parser().parse_args()
    lock = confined(
        arguments.project.resolve(strict=True),
        arguments.project.resolve(strict=True) / "metadata/figure2-control.lock",
    )
    lock.parent.mkdir(parents=True, exist_ok=True)
    with lock.open("a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = asyncio.run(run(arguments))
    print(json.dumps({key: result[key] for key in ("method", "result_sha256")}, indent=2))


if __name__ == "__main__":
    main()
