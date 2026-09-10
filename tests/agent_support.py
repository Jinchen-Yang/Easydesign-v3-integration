from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult


def structure(chains: str = "AB") -> str:
    rows = []
    serial = 1
    for chain_index, chain in enumerate(chains):
        for residue_id, residue in enumerate(("ALA", "GLY", "SER", "LEU", "VAL", "LYS"), start=1):
            for atom, offset, element in (
                ("N", 0.0, "N"),
                ("CA", 1.0, "C"),
                ("C", 2.0, "C"),
                ("O", 2.5, "O"),
            ):
                rows.append(
                    f"ATOM  {serial:5d} {atom:^4s} {residue} {chain}{residue_id:4d}    "
                    f"{residue_id * 3.0 + offset:8.3f}{chain_index * 15.0:8.3f}{0.0:8.3f}"
                    f"  1.00 20.00          {element:>2s}"
                )
                serial += 1
        rows.append("TER")
    return "\n".join(rows) + "\nEND\n"


def make_project(tmp_path: Path, monkeypatch: Any, chains: str = "AB") -> Any:
    from easydesign.agent.session_store import SessionStore
    from easydesign.agent.tools import TargetBridge
    from easydesign.orchestration.research import initialize_research_project
    from easydesign.workspace_context import WorkspaceContext

    (tmp_path / "easydesign-workspace.yaml").write_text(
        'schema_version: "0.1"\nworkspace_id: agent-test\n'
    )
    monkeypatch.setenv("EASYDESIGN_WORKSPACE", str(tmp_path))
    context = WorkspaceContext.from_root(tmp_path)
    context.ensure_layout()
    from easydesign.orchestration.profile import initialize_runtime_profile

    initialize_runtime_profile(context.profile_path)
    source = tmp_path / "runtime/tmp/input.pdb"
    source.write_text(structure(chains))
    project = context.projects_root / "target-test"
    initialize_research_project(project_root=project, target=source)
    store = SessionStore(project)
    return TargetBridge(project, "test-thread", store)


def terminal(bridge: Any, timeout: float = 40) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = bridge.get_job_status()
        if result["status"] not in {"queued", "running", "drain-requested"}:
            assert result["status"] in {"awaiting-human-approval", "succeeded"}, result
            return result
        time.sleep(0.1)
    raise AssertionError("Worker did not reach the expected boundary")


def judge_card(bridge: Any, option: str = "chain-a") -> Any:
    from easydesign.agent.contracts import ApplyDecision, JudgeVerdict
    from easydesign.agent.tools import JUDGE_EVIDENCE

    evidence = bridge.read_evidence()
    token = JUDGE_EVIDENCE.set(evidence["evidence_id"])
    try:
        assessment = bridge.register_judge(
            JudgeVerdict(
                evidence_id=evidence["evidence_id"],
                request_identity=evidence["request_identity"],
                evidence_refs=evidence["evidence_refs"],
                verdict="ready-to-ask",
                reasons=["The frozen local structure declares two selectable chains."],
                limitations=["Biological identity is unconfirmed; reference completeness unknown."],
            )
        )
    finally:
        JUDGE_EVIDENCE.reset(token)
    return bridge.decision_card(
        ApplyDecision(assessment_id=assessment.assessment_id, option_id=option)
    )


class ScriptedModel(BaseChatModel):
    model_name: str = "phase1-scripted"
    role: str

    @property
    def _llm_type(self) -> str:
        return "openai"

    def _get_ls_params(self, stop: Any = None, **kwargs: Any) -> dict[str, Any]:
        return {"ls_provider": "openai", "ls_model_name": self.model_name, "ls_model_type": "chat"}

    def bind_tools(self, tools: Any, **kwargs: Any) -> Any:
        names = {t.name for t in tools}
        from easydesign.agent.harness import ALLOWED

        assert names == ALLOWED[self.role], names
        return self

    def _generate(
        self, messages: Any, stop: Any = None, run_manager: Any = None, **kwargs: Any
    ) -> ChatResult:
        return ChatResult(generations=[ChatGeneration(message=self.answer(messages))])

    @staticmethod
    def call(name: str, **args: Any) -> AIMessage:
        return AIMessage(
            content="", tool_calls=[{"name": name, "args": args, "id": f"call-{uuid4().hex}"}]
        )

    def answer(self, messages: Any) -> AIMessage:
        calls = {c["id"]: c for m in messages if isinstance(m, AIMessage) for c in m.tool_calls}
        results = [
            (calls.get(m.tool_call_id, {}), m) for m in messages if isinstance(m, ToolMessage)
        ]
        for _, message in results:
            assert message.status != "error", message.content
        if self.role != "coordinator" and not results:
            name = "target-intelligence" if self.role == "target" else "evidence-judge"
            return self.call("read_file", file_path=f"/skills/{name}/SKILL.md")
        named = [(c.get("name"), c, m) for c, m in results]
        if self.role == "target":
            if not any(n == "prepare_target" for n, _, _ in named):
                return self.call("prepare_target")
            status = [m for n, _, m in named if n in {"prepare_target", "get_job_status"}][-1]
            if json.loads(status.content)["status"] in {
                "queued",
                "running",
                "detached",
                "no-bound-job",
            }:
                return self.call("get_job_status")
            evidence = [m for n, _, m in named if n == "read_target_evidence"]
            if not evidence:
                return self.call("read_target_evidence")
            value = json.loads(evidence[-1].content)
            return AIMessage(
                content=json.dumps(
                    {
                        "observed_facts": ["Frozen local structure was inspected."],
                        "unresolved_identity": ["Canonical identity unconfirmed"],
                        "selectable_options": [o["option_id"] for o in value.get("options", [])],
                        "evidence_refs": value["evidence_refs"],
                        "limitations": value["limitations"],
                        "recommended_action": "Ask the user to confirm chain A"
                        if value.get("options")
                        else "Report the target bundle",
                    }
                )
            )
        if self.role == "judge":
            evidence = [m for n, _, m in named if n == "read_target_evidence"]
            if not evidence:
                return self.call("read_target_evidence")
            value = json.loads(evidence[-1].content)
            return AIMessage(
                content=json.dumps(
                    {
                        "evidence_id": value["evidence_id"],
                        "request_identity": value["request_identity"],
                        "evidence_refs": value["evidence_refs"],
                        "verdict": "ready-to-ask" if value["request_identity"] else "assessed",
                        "reasons": [
                            "Verified input and chain options support a human choice; "
                            "the actual biological identity is still unknown."
                        ],
                        "limitations": value["limitations"],
                    }
                )
            )
        delegated = [(c["args"]["subagent_type"], m) for n, c, m in named if n == "task"]
        if not delegated:
            return self.call(
                "task",
                subagent_type="target-intelligence",
                description="Prepare the local target and compare chain choices.",
            )
        judges = [m for role, m in delegated if role == "evidence-judge"]
        if not judges:
            return self.call(
                "task",
                subagent_type="evidence-judge",
                description="Assess the frozen chain selection question.",
            )
        first = json.loads(judges[0].content)
        decisions = [m for n, _, m in named if n == "apply_target_decision"]
        if not decisions and first["verdict"] == "ready-to-ask":
            return self.call(
                "apply_target_decision", assessment_id=first["assessment_id"], option_id="chain-a"
            )
        if decisions:
            value = json.loads(decisions[-1].content)
            if value["status"] == "rejected":
                return AIMessage(content="Selection rejected. Scientific request remains pending.")
            statuses = [m for n, _, m in named if n == "get_job_status"]
            if not statuses or json.loads(statuses[-1].content)["status"] in {"queued", "running"}:
                return self.call("get_job_status")
            if len(judges) < 2:
                return self.call(
                    "task",
                    subagent_type="evidence-judge",
                    description="Assess the bundle, mapping, provenance and identity.",
                )
        return AIMessage(
            content="Target preparation verified. Canonical identity is unconfirmed; "
            "reference completeness unknown. No later stage was started."
        )


def scripted_config() -> Any:
    from easydesign.agent.models import LLMConfig, ModelConfig

    return ModelConfig(
        default=LLMConfig(provider="openai", model="phase1-scripted", secret_env="TEST_API_KEY")
    )


def scripted_models() -> dict[str, ScriptedModel]:
    return {role: ScriptedModel(role=role) for role in ("coordinator", "target", "judge")}
