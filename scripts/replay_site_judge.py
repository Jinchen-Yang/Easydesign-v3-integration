"""Replay only the production Judge on verified saved final-exam inputs, in a new ledger.

Original projects/checkpoints are read and hashed, never opened as mutable Agent sessions.
The optional Gate card is a development artifact, not approval or Golden acceptance.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import yaml
from deepagents.middleware import subagents
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import messages_from_dict, messages_to_dict
from langchain_core.utils.function_calling import convert_to_openai_tool
from langgraph.checkpoint.memory import InMemorySaver

from easydesign.agent.contracts import ApplyDecision, EvidenceBinding, JudgeVerdict
from easydesign.agent.harness import create_harness, fingerprint, skill_root
from easydesign.agent.judge_packet import build_judge_packet
from easydesign.agent.models import ModelConfig, create_models
from easydesign.agent.phase2 import Phase2Bridge
from easydesign.agent.session_store import SessionStore, compact
from easydesign.agent.tools import JUDGE_EVIDENCE


def save(out: Path, name: str, value: Any) -> None:
    (out / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class InputCaptured(Exception):
    pass


class CaptureInput(AgentMiddleware):
    def __init__(self, out: Path, dry: bool):
        self.out, self.dry, self.inputs = out, dry, []

    async def awrap_model_call(self, request, handler):
        self.inputs.append(
            {
                "system": request.system_message.text,
                "messages": messages_to_dict(request.messages),
                "schemas": [convert_to_openai_tool(t) for t in request.tools]
                + [convert_to_openai_tool(JudgeVerdict)],
            }
        )
        save(self.out, "complete-model-inputs.json", self.inputs)
        if self.dry:
            raise InputCaptured()
        return await handler(request)


class SavedJudgeBridge(Phase2Bridge):
    """Validation-only adapter: no controller, Research or scientific execution capability."""

    def __init__(self, project, store, packet, snapshot, proposal):
        self.project, self.store, self.thread = project, store, "saved-judge-review"
        self.project_id, self.through = packet["project_id"], "site"
        self.packet, self.snapshot, self.proposal = packet, snapshot, proposal

    def judge_evidence(self):
        return self.packet

    def read_evidence(self, *args, **kwargs):
        return {
            "request_identity": None,
            "hard_facts": self.packet["approved_target"]["hard_facts"],
        }

    def current_site(self):
        return self.proposal

    def site_snapshot(self, proposal, *, for_judge=False):
        return self.packet if for_judge else self.snapshot


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=Path("config/llm.yaml"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    out = args.output.absolute()
    if out.exists():
        raise ValueError("Replay output must be a new directory; never overwrite evidence")
    manifest = json.loads(args.manifest.read_text())
    original_root = Path(manifest["source_repository"])
    originals = {original_root / row["path"]: row["sha256"] for row in manifest["payload"]}
    for path, checksum in originals.items():
        assert path.is_file() and not path.is_symlink() and sha(path) == checksum, str(path)

    def read(name):
        return json.loads((args.evidence_dir / name).read_text())

    for name in [
        "SITE_DOSSIER.json",
        "SITE_DECISION.json",
        "JUDGE_EVIDENCE_RAW.json",
        "SITE_FACTS.json",
        "JUDGE_CHECKPOINT_MESSAGES.json",
        "SITE_PROPOSAL_EVENT.json",
    ]:
        assert (args.evidence_dir / name).absolute() in originals, name
    checkpoint = read("JUDGE_CHECKPOINT_MESSAGES.json")
    message_rows = checkpoint["messages"]
    task = json.loads(message_rows[0]["content"])
    snapshot, dossier = read("JUDGE_EVIDENCE_RAW.json"), read("SITE_DOSSIER.json")
    packet = build_judge_packet(
        snapshot,
        dossier,
        read("SITE_FACTS.json"),
        goal=task["user_goal"],
        decision=read("SITE_DECISION.json"),
    )
    config_bytes = args.config.read_bytes()
    config = ModelConfig.model_validate(yaml.safe_load(config_bytes))
    out.mkdir(parents=True)
    save(out, "packet.json", packet)
    save(
        out,
        "source-provenance.json",
        {
            "manifest_sha256": sha(args.manifest),
            "checkpoint": {k: v for k, v in checkpoint.items() if k != "messages"},
            "verified_original_files": len(originals),
            "original_final_exam_preserved": True,
            "new_research_calls": 0,
            "scope": "Saved Judge only; production middleware/DTO and Gate card logic.",
        },
    )
    # Keep the original delegated question and completed read call IDs. Replace only the
    # updated Skill and the new authoritative evidence view at their existing tool messages.
    skill = (skill_root() / "evidence-judge/SKILL.md").read_text()
    for row in message_rows:
        if row.get("name") == "read_file":
            row["content"] = "\n".join(
                f"{i:3}  {line}" for i, line in enumerate(skill.splitlines(), 1)
            )
        elif row.get("name") == "read_scientific_evidence":
            row["content"] = compact(packet)
    messages = messages_from_dict([{"type": row["type"], "data": row} for row in message_rows])
    provider_requests = []
    models = create_models(config, request_observer=provider_requests.append)
    project = out / "replay-project"
    project.mkdir()
    store = SessionStore(project)
    bridge = SavedJudgeBridge(project, store, packet, snapshot, read("SITE_PROPOSAL_EVENT.json"))
    store.thread(bridge.thread, fingerprint(config), task["user_goal"])
    execution = store.begin_execution(bridge.thread, task["current_user_message"])
    capture = CaptureInput(out, args.dry_run)
    original_factory = subagents.create_sub_agent
    compiled = {}

    def compile_and_capture(spec, **kwargs):
        if spec["name"] == "evidence-judge":
            spec = {**spec, "middleware": [*spec.get("middleware", []), capture]}
        runnable = original_factory(spec, **kwargs)
        compiled[spec["name"]] = runnable
        return runnable

    token = JUDGE_EVIDENCE.set(
        EvidenceBinding.model_validate({k: packet[k] for k in EvidenceBinding.model_fields})
    )
    report = {"status": "RUNNING", "dry_run": args.dry_run, "scientific_golden_pass": False}
    try:
        # Capture the actual compiled production specialist, after DeepAgents installs its
        # standard middlewares. Never invoke the coordinator or any other specialist.
        with patch.object(subagents, "create_sub_agent", compile_and_capture):
            create_harness(
                bridge,
                models,
                config,
                InMemorySaver(),
                task["user_goal"],
                current_user_message=task["current_user_message"],
                execution_id=execution["execution_id"],
            )
        assert "evidence-judge" in compiled
        result = await asyncio.wait_for(
            compiled["evidence-judge"].ainvoke({"messages": messages}, {"recursion_limit": 12}),
            timeout=900,
        )
        verdict = result["structured_response"]
        save(out, "judge.json", verdict)
        if verdict["verdict"] == "ready-to-ask":
            card = bridge.decision_card(
                ApplyDecision(assessment_id=verdict["assessment_id"], option_id="site")
            )
            save(out, "reviewable-gate2-card.json", card.model_dump(mode="json"))
            report["reviewable_gate2"] = True
            report["gate2_status"] = card.judge_status
        report.update(
            status="COMPLETED",
            verdict=verdict["verdict"],
            site_claim_corrections=verdict.get("site_claim_corrections", []),
        )
    except InputCaptured:
        assert args.dry_run and not provider_requests
        report["status"] = "DRY_INPUT_VERIFIED_NO_INFERENCE"
    except Exception as error:
        report.update(status="FAILED", error=repr(error))
        raise
    finally:
        JUDGE_EVIDENCE.reset(token)
        events = store.events(bridge.thread)
        save(out, "events.json", events)
        report["model_contexts"] = [e["payload"] for e in events if e["kind"] == "model-context"]
        report["provider_requests"] = provider_requests
        report["registered_assessments"] = store.db.execute(
            "SELECT count(*) FROM assessments"
        ).fetchone()[0]
        report["source_unchanged"] = all(
            sha(path) == checksum for path, checksum in originals.items()
        )
        report["config_unchanged"] = args.config.read_bytes() == config_bytes
        save(out, "report.json", report)
        store.close()
        print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
        assert report["source_unchanged"] and report["config_unchanged"]


if __name__ == "__main__":
    asyncio.run(main())
