"""One public DeepAgents assembly point, two isolated experts, public LangGraph HITL."""

from __future__ import annotations

import json
from importlib import metadata, resources
from pathlib import Path
from typing import Any

from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend, FilesystemBackend
from deepagents.middleware.subagents import SubAgent
from deepagents.profiles import (
    GeneralPurposeSubagentProfile,
    HarnessProfile,
    register_harness_profile,
)
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage, ToolMessage

from .contracts import (
    AgentBoundaryError,
    EvidenceBinding,
    JudgeVerdict,
    TargetAssessment,
    TargetTask,
)
from .models import ModelConfig
from .session_store import compact, confined, identity
from .tools import JUDGE_EVIDENCE, TargetBridge, build_tools

EXCLUDED_TOOLS = frozenset(
    {"execute", "write_file", "edit_file", "delete_file", "ls", "glob", "grep", "write_todos"}
)
SKILLS = {"target": "target-intelligence", "judge": "evidence-judge"}
ALLOWED = {
    "coordinator": {
        "task",
        "read_file",
        "read_target_evidence",
        "get_job_status",
        "apply_target_decision",
    },
    "target": {"read_file", "read_target_evidence", "get_job_status", "prepare_target"},
    "judge": {"read_file", "read_target_evidence"},
}
REGISTERED: set[str] = set()

COORDINATOR = """You are EasyDesign's target-preparation coordinator.
Work only on the CLI-bound project.
Delegate target preparation to target-intelligence using task; do not prepare it yourself.
Each task description is a concise question.
Runtime supplies the real project, user goal and evidence.
After target-intelligence finishes, call read_target_evidence then task with evidence-judge.
For pending chain selection: explain option differences without claiming a biological identity.
If the user has no preferred chain, ask which chain they want in a final message.
If the user explicitly requested a chain, use the actual matching eligible option. Only a trusted
evidence-judge assessment_id with verdict ready-to-ask may be passed to apply_target_decision.
The runtime displays a real human approval card. Never invent an assessment ID or human approval.
When the preferred chain is already explicit, confirmation MUST use that runtime card: first read
the pending evidence, delegate evidence-judge, then call apply_target_decision. Do not finish with
a prose confirmation question or wait for a chat reply before these calls. The tool interrupts
before applying anything; requesting the card is not approval. Target recommendations are advisory
and cannot replace this Judge-to-card sequence.
After approval, use get_job_status and read_target_evidence.
Then delegate a final evidence-judge assessment.
Report the verified target bundle, mapping/provenance, identity limitations and viewer reference.
Then stop. A refusal means keep the scientific request pending and stop.
A worker failure is not a negative scientific result.
No Stage 02 onward, site/binder design, storage migration, Workbench or Figure 2 work is available.
Only read files explicitly referenced by tools; do not call shell or write files.
Keep your final report concise and in the user's language. Retain all structural-only limitations.
The research goal is immutable. Treat the current user message as a clarification within that goal,
not its replacement; previous conversation messages remain context, not new scientific evidence.
For completed targets, approval lineage is outside the Judge snapshot. Do not ask the final Judge
to certify human authority or infer approval history from selected_chain.
"""


def skill_root() -> Path:
    return Path(str(resources.files("easydesign.agent").joinpath("skills")))


def fingerprint(config: ModelConfig) -> str:
    return identity(
        {
            "contract": "phase1.1-1",
            "models": config.model_dump(mode="json"),
            "skills": {
                name: (skill_root() / name / "SKILL.md").read_text() for name in SKILLS.values()
            },
            "harness": Path(__file__).read_text(),
            "contracts": Path(__file__).with_name("contracts.py").read_text(),
            "tools": Path(__file__).with_name("tools.py").read_text(),
            "session_store": Path(__file__).with_name("session_store.py").read_text(),
            "cli": Path(__file__).with_name("cli.py").read_text(),
            "versions": {
                name: metadata.version(name)
                for name in (
                    "deepagents",
                    "langchain",
                    "langchain-core",
                    "langgraph",
                    "langgraph-checkpoint-sqlite",
                )
            },
        }
    )


def parse_assessment(text: str) -> Any:
    if len(text.encode()) > 24000:
        raise AgentBoundaryError("Specialist assessment exceeds the bounded contract")
    text = text.strip()
    if text.startswith("```json") and text.endswith("```"):
        text = text[7:-3].strip()
    return json.loads(text)


class RoleBoundary(AgentMiddleware[Any, Any, Any]):
    """Schema filtering plus execution checks. Role provenance is a closure, not a model field."""

    def __init__(
        self,
        bridge: TargetBridge,
        role: str,
        config: ModelConfig,
        goal: str,
        current_user_message: str | None = None,
        execution_id: str | None = None,
    ) -> None:
        self.bridge, self.role, self.config, self.goal = bridge, role, config, goal
        self.current_user_message = current_user_message or goal
        self.execution_id = execution_id
        self.allowed = ALLOWED[role]

    async def awrap_model_call(self, request: Any, handler: Any) -> Any:
        available = [t for t in request.tools if getattr(t, "name", None) in self.allowed]
        # Fail closed even if a future profile merge adds unexpected middleware tools.
        if {getattr(t, "name", None) for t in available} != self.allowed:
            raise AgentBoundaryError(f"Unexpected final tool surface for {self.role}")
        chars = len(str(request.system_message)) + sum(
            len(str(m.content)) for m in request.messages
        )
        if chars > self.config.max_input_chars:
            raise AgentBoundaryError("Model context budget exceeded; worker remains detached")
        if self.execution_id is None:
            raise AgentBoundaryError("Model call requires a persisted agent execution")
        self.bridge.store.reserve_model_call(
            self.bridge.thread, self.role, self.config.max_model_calls, self.execution_id
        )
        return await handler(request.override(tools=available))

    async def awrap_tool_call(self, request: Any, handler: Any) -> Any:
        name, args = request.tool_call["name"], request.tool_call["args"]
        if name not in self.allowed:
            return ToolMessage(
                content="Rejected: tool is outside this role's permissions",
                status="error",
                tool_call_id=request.tool_call["id"],
                name=name,
            )
        token = None
        if name == "read_file":
            path = args.get("file_path", "")
            expected = f"/skills/{SKILLS.get(self.role, '')}/SKILL.md"
            own_result = (
                path.startswith("/result-") and path.endswith(".json") and path.count("/") == 1
            )
            if not own_result and not (self.role in SKILLS and path == expected):
                raise AgentBoundaryError("File is not an allowed skill or bounded result reference")
            if own_result:
                confined(
                    self.bridge.store.root,
                    self.bridge.store.root / "agent-work" / self.bridge.thread / path[1:],
                )
            if args.get("limit", 100) > 120:
                args = {**args, "limit": 120}
                request = request.override(tool_call={**request.tool_call, "args": args})
        if name == "task":
            specialist = args.get("subagent_type")
            if specialist not in SKILLS.values():
                raise AgentBoundaryError(
                    "Only Target Intelligence and Evidence Judge can be delegated"
                )
            description = args.get("description", "")
            if not isinstance(description, str) or not description or len(description) > 1500:
                raise AgentBoundaryError("Delegation must contain one bounded question")
            evidence = self.bridge.read_evidence() if specialist == "evidence-judge" else None
            task = TargetTask(
                question=description,
                user_goal=self.goal,
                current_user_message=self.current_user_message,
                project_id=self.bridge.project_id,
                run_id=None if evidence is None else evidence["run_id"],
                evidence_id=None if evidence is None else evidence["evidence_id"],
                evidence_refs=[] if evidence is None else evidence["evidence_refs"],
            )
            payload = task.model_dump(mode="json")
            if evidence is not None:
                token = JUDGE_EVIDENCE.set(
                    EvidenceBinding.model_validate(
                        {name: evidence[name] for name in EvidenceBinding.model_fields}
                    )
                )
            request = request.override(
                tool_call={**request.tool_call, "args": {**args, "description": compact(payload)}}
            )
        try:
            result = await handler(request)
            # Never persist raw provider requests, internal specialist histories or full tool I/O.
            self.bridge.store.event(self.bridge.thread, "tool", {"role": self.role, "name": name})
            return result
        finally:
            if token is not None:
                JUDGE_EVIDENCE.reset(token)

    async def aafter_agent(self, state: Any, runtime: Any) -> Any:
        if self.role == "coordinator":
            return None
        last = next(
            (m for m in reversed(state["messages"]) if isinstance(m, AIMessage) and m.text), None
        )
        if last is None:
            raise AgentBoundaryError("Specialist produced no assessment")
        parsed = parse_assessment(last.text)
        if self.role == "judge":
            result = self.bridge.register_judge(JudgeVerdict.model_validate(parsed)).model_dump(
                mode="json", exclude={"evidence_refs", "request_identity", "source_role"}
            )
        else:
            result = TargetAssessment.model_validate(parsed).model_dump(mode="json")
            self.bridge.store.event(self.bridge.thread, "target-assessment", result)
        return {
            "messages": [
                AIMessage(id=last.id, content=self.bridge.store.offload(self.bridge.thread, result))
            ]
        }


def create_harness(
    bridge: TargetBridge,
    models: dict[str, Any],
    config: ModelConfig,
    saver: Any,
    goal: str,
    *,
    current_user_message: str | None = None,
    execution_id: str | None = None,
    technical_details: bool = False,
) -> Any:
    for role in ("coordinator", "target", "judge"):
        key = config.for_role(role).harness_key
        if key not in REGISTERED:
            register_harness_profile(
                key,
                HarnessProfile(
                    excluded_tools=EXCLUDED_TOOLS,
                    general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False),
                ),
            )
            REGISTERED.add(key)
    directory = confined(bridge.store.root, bridge.store.root / "agent-work" / bridge.thread)
    directory.mkdir(parents=True, exist_ok=True)
    backend = CompositeBackend(
        default=FilesystemBackend(root_dir=directory, virtual_mode=True),
        routes={"/skills/": FilesystemBackend(root_dir=skill_root(), virtual_mode=True)},
    )
    specialists: list[SubAgent] = []
    for role, name in SKILLS.items():
        schema = JudgeVerdict if role == "judge" else TargetAssessment
        prompt = (
            f"You are {name}, an isolated EasyDesign specialist. "
            f"Read /skills/{name}/SKILL.md first. "
            "Use only your available typed tools. Return ONLY a JSON object with this schema: "
            + compact(schema.model_json_schema())
        )
        specialists.append(
            {
                "name": name,
                "description": f"Bounded {name} for local target preparation",
                "model": models[role],
                "mode": "isolated",
                "system_prompt": prompt,
                "tools": build_tools(bridge, role),
                "skills": [f"/skills/{name}/"],
                "middleware": [
                    RoleBoundary(bridge, role, config, goal, current_user_message, execution_id)
                ],
                "interrupt_on": {},
            }
        )
    return create_deep_agent(
        model=models["coordinator"],
        system_prompt=COORDINATOR
        + "\nTrusted thread intent: "
        + compact(
            {
                "research_goal": goal,
                "current_user_message": current_user_message or goal,
            }
        )
        + (
            "\nTechnical details were explicitly requested; verified references may be shown."
            if technical_details
            else "\nUse a short plain-language final answer: outcome, selected chain, meaningful "
            "limitations and viewer link. Do not print SHA/checksums, manifest revisions, "
            "assessment IDs, internal job identifiers or provenance implementation fields. "
            "When fallback_used is false, no fallback was used; do not speculate that it occurred."
        ),
        tools=build_tools(bridge, "coordinator"),
        subagents=specialists,
        backend=backend,
        checkpointer=saver,
        middleware=[
            RoleBoundary(bridge, "coordinator", config, goal, current_user_message, execution_id)
        ],
        name="easydesign-target-agent",
    )
