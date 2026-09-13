"""Bounded real-model contract replay on verified saved evidence; no new research or Gate.

This validation-only reader never changes the source project or its checkpoints.
A completed Judge critique is a contract result, not scientific Golden acceptance.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sqlite3
import subprocess
from pathlib import Path
from time import perf_counter

import yaml
from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware
from langchain.agents.structured_output import ToolStrategy
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.utils.function_calling import convert_to_openai_tool

from easydesign.agent.context_policy import context_usage
from easydesign.agent.contracts import (
    AgentBoundaryError,
    EvidenceBinding,
    JudgeVerdict,
    ResearchConclusionMismatch,
)
from easydesign.agent.evidence_research import EvidenceResearch
from easydesign.agent.harness import site_synthesis_prompt, skill_root
from easydesign.agent.models import ModelConfig, create_models
from easydesign.agent.phase2 import SITE_EVIDENCE, Phase2Bridge
from easydesign.agent.session_store import SessionStore, compact, identity
from easydesign.agent.site_contracts import CanonicalMappingQuery, SiteQuery
from easydesign.agent.site_decision import (
    SiteDecision,
    candidate_name,
    compile_site_decision,
    decision_working_set,
)
from easydesign.agent.site_dossier import SiteResearchHandoff, site_dossier


def save(out, name, value):
    (out / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


class ReplayUsage(BaseCallbackHandler):
    """Persist provider outcome metadata even if native structured parsing fails."""

    def on_llm_end(self, response, **kwargs):
        for batch in response.generations:
            for generation in batch:
                message = getattr(generation, "message", None)
                if isinstance(message, AIMessage):
                    print(
                        "MODEL_OUTCOME",
                        compact(
                            {
                                "stop_reason": message.response_metadata.get("stop_reason")
                                or message.response_metadata.get("finish_reason"),
                                "usage": message.usage_metadata,
                                "tool_names": [c["name"] for c in message.tool_calls],
                            }
                        ),
                        flush=True,
                    )


class ReplayBoundary(AgentMiddleware):
    """Read-only harness analogue: at most three calls, exact hydration and shared input policy."""

    def __init__(self, schema, config, role, validator):
        self.schema, self.config, self.role, self.validator = schema, config, role, validator
        self.calls = 0
        self.findings = []
        self.responses = []

    async def awrap_model_call(self, request, handler):
        while self.calls < 3:
            context_usage(
                request.model,
                self.config,
                self.role,
                [request.system_message, *request.messages],
                len(compact(convert_to_openai_tool(self.schema))),
            )
            self.calls += 1
            response = await handler(request)
            self.responses.extend(
                {
                    "stop_reason": m.response_metadata.get("stop_reason")
                    or m.response_metadata.get("finish_reason"),
                    "usage": m.usage_metadata,
                    "tool_names": [c["name"] for c in m.tool_calls],
                }
                for m in response.result
                if isinstance(m, AIMessage)
            )
            if response.structured_response is not None:
                try:
                    if self.validator is not None:
                        self.validator(response.structured_response)
                    return response
                except ResearchConclusionMismatch as error:
                    diagnostic = str(error)
            elif any(isinstance(m, ToolMessage) for m in response.result):
                diagnostic = "\n".join(
                    str(m.content) for m in response.result if isinstance(m, ToolMessage)
                )[:6000]
            else:
                # Match RoleBoundary: an unfinished answer is not appended as new evidence.
                diagnostic = (
                    f"MISSING_TYPED_SUBMISSION: call {self.schema.__name__}; "
                    "explanatory prose and incomplete output are not accepted submissions."
                )
            finding = {
                "call": self.calls,
                "diagnostic": diagnostic,
                "rejected_submission": response.structured_response.model_dump(mode="json")
                if response.structured_response is not None
                else None,
            }
            self.findings.append(finding)
            print("REPLAY_REJECTION", compact(finding), flush=True)
            request = request.override(
                system_message=SystemMessage(
                    content=request.system_message.text
                    + "\nCorrection required: "
                    + diagnostic[:6000]
                    + f"\nSubmit a corrected {self.schema.__name__} tool call. "
                    "No scientific work was repeated."
                )
            )
        raise AgentBoundaryError("Replay exhausted the product's two contract corrections")


async def inference(model, schema, prompt, payload, config, role, validator=None):
    boundary = ReplayBoundary(schema, config, role, validator)
    agent = create_agent(
        model=model,
        tools=[],
        system_prompt=prompt,
        middleware=[boundary],
        response_format=ToolStrategy(schema, handle_errors=True),
    )
    started = perf_counter()
    state = await asyncio.wait_for(
        agent.ainvoke(
            {"messages": [HumanMessage(content=compact(payload))]},
            {"recursion_limit": 3, "callbacks": [ReplayUsage()]},
        ),
        timeout=900,
    )
    result = state.get("structured_response")
    assert isinstance(result, schema), "No typed structured result"
    return result, {
        "latency_seconds": perf_counter() - started,
        "responses": boundary.responses,
        "contract_corrections": boundary.findings,
        "public_result_chars": len(compact(result.model_dump(mode="json"))),
    }


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-case", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--resume-from",
        type=Path,
        help="Reuse validated decisions only if their complete working set and hydration match",
    )
    parser.add_argument(
        "--offline", action="store_true", help="Validate saved evidence without model calls"
    )
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(exist_ok=False)
    source = json.loads((args.source_case / "inherited-target.json").read_text())
    project = Path(source["project"])
    thread = source["continuation_thread"]
    os.environ["EASYDESIGN_WORKSPACE"] = str(project.parents[2] / "easydesign-workspace.yaml")
    store = object.__new__(SessionStore)
    store.project_root = project
    store.root = project / "metadata"
    store.path = store.root / "agent.sqlite"
    store.db = sqlite3.connect(f"file:{store.path}?mode=ro", uri=True)
    store.db.row_factory = sqlite3.Row
    bridge = Phase2Bridge(project, thread, store)
    event = bridge.thread_latest("site-evidence-dossier")
    assert event is not None
    previous = bridge.document(event["ref"])
    handoff = SiteResearchHandoff.model_validate(
        {
            "candidates": [c["research_hypothesis"] for c in previous["candidate_comparison"]],
            "decision_questions": [
                {key: value for key, value in question.items() if key != "topic"}
                for question in previous["decision_questions"]
            ],
            **previous["research_opinions"],
        }
    )
    target = bridge.read_site_evidence()
    token = SITE_EVIDENCE.set(
        EvidenceBinding.model_validate({k: target[k] for k in EvidenceBinding.model_fields})
    )
    try:
        dossier = site_dossier(bridge, handoff)
        working = decision_working_set(dossier)
        goal = store.db.execute("SELECT goal FROM threads WHERE id=?", (thread,)).fetchone()[0]
        config = ModelConfig.model_validate(yaml.safe_load(Path("config/llm.yaml").read_text()))
        save(out, "runtime-dossier.json", dossier)
        save(out, "decision-working-set.json", working)
        if args.offline:
            assert dossier["reference_annotations"], "Missing approved official source facts"
            for candidate in dossier["candidate_comparison"]:
                assert candidate["location"]["sequence_topology"]
            save(
                out,
                "report.json",
                {
                    "kind": "SAVED_EVIDENCE_OFFLINE_CONTRACT_REPLAY",
                    "model_calls": 0,
                    "source_read_only": True,
                    "source_dossier_ref": event["ref"],
                    "new_research_calls": 0,
                    "handoff_dossier": "PASS",
                    "official_sources": len(dossier["reference_annotations"]),
                    "working_set_chars": len(compact(working)),
                },
            )
            return
        models = create_models(config)
        results = []
        for trial in range(2):
            if args.resume_from and (args.resume_from / f"decision-{trial + 1}.json").exists():
                prior = args.resume_from
                assert working == json.loads((prior / "decision-working-set.json").read_text())
                decision = SiteDecision.model_validate_json(
                    (prior / f"decision-{trial + 1}.json").read_text()
                )
                assert compile_site_decision(dossier, decision).model_dump(
                    mode="json"
                ) == json.loads((prior / f"intent-{trial + 1}.json").read_text())
                usage = json.loads((prior / f"usage-{trial + 1}.json").read_text())
                usage.update(reused_validated_result=str(prior.resolve()), new_model_calls=0)
            else:
                decision, usage = await inference(
                    models["site"],
                    SiteDecision,
                    site_synthesis_prompt(),
                    {
                        "original_goal": goal,
                        "current_user_message": goal,
                        "trusted_revision": None,
                        "dossier": working,
                    },
                    config,
                    "site",
                    validator=lambda choice: compile_site_decision(dossier, choice),
                )
                usage["new_model_calls"] = len(usage["responses"])
            save(out, f"decision-{trial + 1}.json", decision.model_dump(mode="json"))
            save(out, f"usage-{trial + 1}.json", usage)
            print("SYNTHESIS_REPLAY", trial + 1, compact(usage), flush=True)
            intent = compile_site_decision(dossier, decision)
            # The source project's dossier event is historical and remains untouched.
            # Validate the translated Handoff and current runtime hydration explicitly;
            # never ask the live registration path to adopt that historical event.
            EvidenceResearch(bridge).validate_questions(handoff.decision_questions)
            save(out, f"intent-{trial + 1}.json", intent.model_dump(mode="json"))
            results.append(usage)
        mapping = bridge.read_canonical_mapping(CanonicalMappingQuery(canonical_positions=[286]))
        matched = mapping["matches"][0]
        assert matched["observed_design_labels"] == [414], matched
        mapping_handoff = handoff.model_copy(
            update={
                "candidates": [
                    handoff.candidates[0].model_copy(
                        update={
                            "name": "REPLAY ONLY: nonidentity canonical correspondence",
                            "hotspot_label_seq_ids": [414],
                            "origin": "scan-derived",
                            "evidence_card_ids": [],
                        }
                    )
                ]
            }
        )
        mapping_dossier = site_dossier(bridge, mapping_handoff)
        mapping_decision = decision.model_copy(
            update={
                "selected_candidate_id": mapping_dossier["candidate_comparison"][0]["candidate_id"],
                "alternative_candidate_ids": [],
            }
        )
        mapped_intent = compile_site_decision(mapping_dossier, mapping_decision)
        assert mapped_intent.selected_site.hotspot_label_seq_ids == [414]
        save(
            out,
            "nonidentity-mapping.json",
            {
                "source": mapping,
                "intent_labels": mapped_intent.selected_site.hotspot_label_seq_ids,
                "scope": "Replay fixture, not a recommended site",
            },
        )
        judge_evidence = {
            "gate_type": "site-hotspot",
            "target_facts": bridge.read_evidence()["hard_facts"],
            "runtime_status": dossier["runtime_status"],
            "approach_validation": dossier["approach_validation"],
            "reference_annotations": dossier["reference_annotations"],
            "residue_constraints": dossier["residue_constraints"],
            "runtime_candidate_facts": {
                "trusted_residue_facts": dossier["trusted_residue_facts"],
                "candidates": [
                    {
                        "candidate_id": c["candidate_id"],
                        "name": candidate_name(c),
                        "design_labels": c["research_hypothesis"]["hotspot_label_seq_ids"],
                        "location": c["location"],
                    }
                    for c in dossier["candidate_comparison"]
                ],
                "authority": "Verified approved canonical/design correspondence and topology.",
            },
            "proposal": intent.model_dump(mode="json"),
            "evaluation": bridge.evaluate_candidate(
                SiteQuery(label_seq_ids=intent.selected_site.hotspot_label_seq_ids)
            ),
            "alternative_evaluations": [
                bridge.evaluate_candidate(SiteQuery(label_seq_ids=c.hotspot_label_seq_ids))
                for c in intent.alternatives
            ],
            "scientific_context": dossier["scientific_context"],
            "receptor_context": dossier["receptor_context"],
            "research_evidence": {
                "source_cards": dossier["focused_passages"],
                "decision_questions": [
                    {"question": q["question"]} for q in dossier["decision_questions"]
                ],
            },
            "authority": "Read-only verified evidence and runtime hydration; "
            "no registered proposal, Judge receipt or Gate approval.",
        }
        save(out, "judge-input.json", judge_evidence)
        judge, usage = await inference(
            models["judge"],
            JudgeVerdict,
            (skill_root() / "evidence-judge/SKILL.md").read_text()
            + "\nFor this bounded replay, the complete delegated evidence is supplied below. "
            "No reading or research tools are available. Return an independent JudgeVerdict. "
            "Use insufficient/reject if the proposal cannot be scientifically supported.",
            {"user_goal": goal, "evidence": judge_evidence},
            config,
            "judge",
        )
        save(out, "judge.json", judge.model_dump(mode="json"))
        if judge.recommendation is not None:
            assert judge.recommendation.option_id == "site", (
                "Judge recommendation must address the Site Gate option"
            )
        report = {
            "kind": "REAL_MODEL_CONTRACT_REPLAY_NOT_GOLDEN_ACCEPTANCE",
            "source_thread": thread,
            "source_dossier_ref": event["ref"],
            "source_read_only": True,
            "new_research_calls": 0,
            "head": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
            "working_set_chars": len(compact(working)),
            "source_dossier_chars": len(compact(previous)),
            "Test_A": {"typed_decisions": len(results), "runs": results},
            "Test_B": {"canonical": 286, "design": 414, "status": "PASS"},
            "Test_C": {"contract": "PASS", "scientific_verdict": judge.verdict, "usage": usage},
            "Test_D": "Separate native checkpoint/restart targeted test; see test reports",
            "scientific_golden_pass": False,
            "hydrated_intent_sha256": identity(intent.model_dump(mode="json")),
        }
        save(out, "report.json", report)
        print(compact(report), flush=True)
    finally:
        SITE_EVIDENCE.reset(token)
        store.close()


if __name__ == "__main__":
    asyncio.run(main())
