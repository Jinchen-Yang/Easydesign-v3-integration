"""One public DeepAgents assembly, isolated scientific specialists and LangGraph HITL."""

from __future__ import annotations

import json
from importlib import metadata, resources
from pathlib import Path
from typing import Any, cast

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
    DecisionOutcome,
    EvidenceBinding,
    EvidenceCursorQueryMismatch,
    InvalidFieldProjection,
    JudgeVerdict,
    SourceSelectionRequired,
    TargetInterpretation,
    TargetTask,
)
from .design import BINDER_EVIDENCE, DesignBridge
from .design_contracts import BinderIntent
from .evidence_output import output_message, read_query, verified_result
from .models import ModelConfig, Role
from .phase2 import SITE_EVIDENCE, Phase2Bridge
from .phase2_tools import DESIGN_ALLOWED, PHASE2_ALLOWED, phase2_tools
from .session_store import compact, confined, identity
from .site_contracts import ScientificTask, SiteIntent
from .target_assessment import (
    HardFactContradiction,
    check_fact_claims,
    check_interpretation,
    register_target,
)
from .tools import JUDGE_EVIDENCE, TargetBridge, build_tools

EXCLUDED_TOOLS = frozenset(
    {"execute", "write_file", "edit_file", "delete_file", "ls", "glob", "grep", "write_todos"}
)
SKILLS = {"target": "target-intelligence", "judge": "evidence-judge"}
PHASE2_SKILLS = {**SKILLS, "site": "site-mechanism"}
DESIGN_SKILLS = {**PHASE2_SKILLS, "binder": "binder-strategy"}
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
An explicitly DISCOURAGED recommendation, including a negative/reject opinion, can also be put
on a warning card for human revision or override; it is not permission for ordinary approval.
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
The runtime card accepts APPROVE, REVISE, REJECT and explicit OVERRIDE from a real human.
After revision-requested, delegate to target-intelligence with the trusted revision instruction,
reuse valid upstream evidence, then obtain a fresh Judge opinion and a new card at the same gate.
The instruction can correct a chain preference while the original research goal remains immutable.
Do not restart the input pipeline or reuse an old assessment as a new proposal. REVISE is not
project failure; REJECT leaves the scientific gate pending. You cannot manufacture either action.
Scientific discouragement is an opinion, not a hard constraint: show warnings and the alternative
on the card; only the human may explicitly override. Missing/ineligible options remain blocked.
"""


PHASE2_COORDINATOR = """You are EasyDesign's Design Scientist. Work only on the bound project.
Use read_scientific_state for verified progress; the immutable research goal is not replaced by
current messages or trusted revision instructions. Delegate science to the owning specialist.
Each task description MUST be one short scientific question, under 600 characters. Do not
copy evidence, IDs, paths, schemas, user goals or tool instructions into it: the trusted runtime
automatically supplies these. Never invent specialist tool names or request repository access.
Use the verified next_specialist field to continue. Never repeat Target after target-ready.
If target preparation is missing, delegate target-intelligence; for a chain decision ask the
independent evidence-judge, then request_scientific_decision with the exact eligible chain option.
Once Gate 1 is resolved, delegate site-mechanism to interpret real tools/evidence and propose
mapped hotspots. Do not perform its analysis yourself or ask Target to choose sites.
After the Site specialist returns, delegate evidence-judge. It reviews the runtime-bound current
Site proposal, not a description you invent. Then call request_scientific_decision using its
trusted assessment_id and option_id=site. Only that tool creates a real human interrupt.
Never substitute prose confirmation for a card or claim approval from chat. A warning/reject
opinion about a testable DISCOURAGED site can be presented for human revision or explicit
OVERRIDE. Runtime BLOCKED constraints cannot be overridden. Do not manufacture authority.
On revision-requested, return to the named owner with the trusted revision instruction and
valid upstream evidence. Site revisions preserve Target; get a fresh Site and Judge proposal,
then a new Gate 2 card. A rejection stops this proposal without making the project a failure.
Use scientific questions, evidence, uncertainty and meaningful alternatives in user output.
After hotspot-approved, read_scientific_state. Stop if next_specialist=none. Do not launch pilot,
scale, prediction, filtering or wet-lab work. No shell, arbitrary file writes, repository access,
Stage agents, workbench or model-invented residue numbering are available.
When the requested scope is design and the verified next_specialist is binder-strategy, delegate
it to propose HOW to design against the approved hotspot. Then delegate evidence-judge and
request_scientific_decision with option_id=design. Gate 3 freezes the specification without pilot.
Gate 3 revisions normally return to binder-strategy and preserve Target/Site. Only if the trusted
human revision changes WHERE to bind, call reopen_site_decision with the scientific reason,
then delegate Site and obtain a fresh Judge/Gate 2 approval before any further Binder work.
Do not reopen Site for ordinary CDR, crop, arm or pilot-scope changes.
"""


def skill_root() -> Path:
    return Path(str(resources.files("easydesign.agent").joinpath("skills")))


def fingerprint(config: ModelConfig) -> str:
    return identity(
        {
            "contract": "phase2-design-1",
            "models": config.model_dump(mode="json"),
            "skills": {
                str(path.relative_to(skill_root())): path.read_text()
                for path in sorted(skill_root().rglob("*.md"))
            },
            "harness": Path(__file__).read_text(),
            "contracts": Path(__file__).with_name("contracts.py").read_text(),
            "tools": Path(__file__).with_name("tools.py").read_text(),
            "phase2": {
                p.name: p.read_text()
                for p in sorted(
                    [
                        *Path(__file__).parent.glob("*site*.py"),
                        *Path(__file__).parent.glob("*design*.py"),
                    ]
                )
            },
            "phase2_bridge": Path(__file__).with_name("phase2.py").read_text(),
            "phase2_tools": Path(__file__).with_name("phase2_tools.py").read_text(),
            "evidence_research": Path(__file__).with_name("evidence_research.py").read_text(),
            "evidence_corpus": Path(__file__).with_name("evidence_corpus.py").read_text(),
            "evidence_output": Path(__file__).with_name("evidence_output.py").read_text(),
            "target_identity": Path(__file__).with_name("target_identity.py").read_text(),
            "target_assessment": Path(__file__).with_name("target_assessment.py").read_text(),
            "native_strategy": Path(__file__).with_name("native_strategy.py").read_text(),
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
        revision: DecisionOutcome | None = None,
    ) -> None:
        self.bridge, self.role, self.config, self.goal = bridge, role, config, goal
        self.current_user_message = current_user_message or goal
        self.execution_id = execution_id
        self.revision = revision
        self.structured_output = self.role != "coordinator"
        self.output_schema = {
            "target": TargetInterpretation,
            "site": SiteIntent,
            "binder": BinderIntent,
            "judge": JudgeVerdict,
        }.get(role)
        self.skills = (
            DESIGN_SKILLS
            if isinstance(bridge, DesignBridge)
            else PHASE2_SKILLS
            if isinstance(bridge, Phase2Bridge)
            else SKILLS
        )
        self.allowed = (
            DESIGN_ALLOWED[role]
            if isinstance(bridge, DesignBridge)
            else PHASE2_ALLOWED[role]
            if isinstance(bridge, Phase2Bridge)
            else ALLOWED[role]
        )

    async def awrap_model_call(self, request: Any, handler: Any) -> Any:
        available = [t for t in request.tools if getattr(t, "name", None) in self.allowed]
        # Fail closed even if a future profile merge adds unexpected middleware tools.
        if {getattr(t, "name", None) for t in available} != self.allowed:
            raise AgentBoundaryError(f"Unexpected final tool surface for {self.role}")
        # An absent job cannot advance by observation. Tool availability follows the
        # original runtime receipt; this does not schedule work or choose science.
        if (
            self.role == "target"
            and "get_job_status" in self.allowed
            and self.bridge.get_job_status()["status"] == "no-bound-job"
        ):
            available = [t for t in available if t.name != "get_job_status"]
        if isinstance(self.bridge, Phase2Bridge):
            # The checkpoint retains every message. The model sees a working set of
            # recent detailed tool views; older archived results remain addressable.
            detailed = [
                i
                for i, m in enumerate(request.messages)
                if isinstance(m, ToolMessage) and '"full_result"' in str(m.content)
            ]
            messages = list(request.messages)
            retained = 1 if self.role == "judge" else 4
            for i in detailed[:-retained]:
                value = json.loads(messages[i].content)
                messages[i] = messages[i].model_copy(
                    update={
                        "content": compact(
                            {
                                "archived_result": value["full_result"],
                                "partial": True,
                                "note": (
                                    "Earlier detailed view retained; retrieve a field when needed."
                                ),
                            }
                        )
                    }
                )
            request = request.override(messages=messages)
        from langchain_core.utils.function_calling import convert_to_openai_tool

        tool_schemas = [convert_to_openai_tool(t) for t in available]
        if self.structured_output:
            output_schema = self.output_schema
            assert output_schema is not None
            tool_schemas.append(convert_to_openai_tool(output_schema))
        tool_chars = len(compact(tool_schemas))
        if self.execution_id is None:
            raise AgentBoundaryError("Model call requires a persisted agent execution")
        for attempt in range(3):
            chars = len(str(request.system_message)) + sum(
                len(str(m.content)) for m in request.messages
            )
            if chars > self.config.max_input_chars:
                raise AgentBoundaryError("Model context budget exceeded; worker remains detached")
            self.bridge.store.reserve_model_call(
                self.bridge.thread, self.role, self.config.max_model_calls, self.execution_id
            )
            self.bridge.store.event(
                self.bridge.thread,
                "model-context",
                {
                    "role": self.role,
                    "execution_id": self.execution_id,
                    "context_chars": chars,
                    "tool_schema_chars": tool_chars,
                    "estimated_input_chars_with_schemas": chars + tool_chars,
                    "context_metric": "system and message content; tool schemas separately",
                    "limit": self.config.max_input_chars,
                    "message_count": len(request.messages),
                    "tool_message_chars": sum(
                        len(str(m.content)) for m in request.messages if isinstance(m, ToolMessage)
                    ),
                    "repair_attempt": attempt,
                },
            )
            response = await handler(request.override(tools=available))
            if not self.structured_output:
                return response
            schema = self.output_schema
            assert schema is not None
            calls = [call for m in response.result for call in getattr(m, "tool_calls", [])]
            if any(call["name"] not in self.allowed | {schema.__name__} for call in calls):
                raise AgentBoundaryError("Rejected: tool is outside this role's permissions")
            invalid = [
                call for m in response.result for call in getattr(m, "invalid_tool_calls", [])
            ]
            if any(call.get("name") != schema.__name__ for call in invalid):
                raise AgentBoundaryError("Malformed non-submission tool call remains fatal")
            diagnostic = ""
            if invalid:
                diagnostic = "INVALID_STRUCTURED_SUBMISSION: malformed tool JSON: " + compact(
                    invalid
                )
            elif response.structured_response is not None:
                # LangChain parsed the typed submission. The runtime validates known facts
                # before the callback can persist it or the Coordinator can see it.
                if len(calls) != 1:
                    diagnostic = (
                        "INVALID_STRUCTURED_SUBMISSION: submit one final opinion "
                        "without concurrent action tools."
                    )
                else:
                    try:
                        if self.role == "target":
                            check_interpretation(
                                response.structured_response,
                                self.bridge.target_submission_evidence(),
                            )
                        elif self.role != "judge":
                            check_fact_claims(
                                response.structured_response.model_dump(mode="json"),
                                self.bridge.target_submission_evidence(),
                            )
                        elif response.structured_response.verdict in {"ready-to-ask", "assessed"}:
                            snapshot = self.bridge.judge_evidence()
                            facts = snapshot.get("hard_facts", snapshot.get("target_facts"))
                            if facts is not None:
                                check_fact_claims(
                                    response.structured_response.model_dump(mode="json"),
                                    {"hard_facts": facts},
                                )
                    except HardFactContradiction as error:
                        diagnostic = str(error)
                        self.bridge.store.event(
                            self.bridge.thread,
                            "scientific-consistency-finding",
                            {
                                "role": self.role,
                                "execution_id": self.execution_id,
                                "code": "HARD_FACT_CONTRADICTION",
                                "findings": error.findings,
                                "rejected_submission": response.structured_response.model_dump(
                                    mode="json"
                                ),
                            },
                        )
                if not diagnostic:
                    return response
            elif any(isinstance(m, ToolMessage) for m in response.result):
                # ToolStrategy already returned an exact schema error through the bounded
                # error callback. Let the framework deliver it and continue its native loop.
                return response
            elif any(getattr(m, "tool_calls", []) for m in response.result):
                return response
            else:
                diagnostic = (
                    f"MISSING_TYPED_SUBMISSION: call {schema.__name__}; explanatory prose, "
                    "pure JSON text and fenced JSON are not accepted submissions."
                )
            self.contract_error(diagnostic)
            self.bridge.store.event(
                self.bridge.thread,
                "rejected-submission",
                {
                    "role": self.role,
                    "execution_id": self.execution_id,
                    "diagnostic": diagnostic[:6000],
                    "model_text": [
                        m.text[:24000] for m in response.result if isinstance(m, AIMessage)
                    ],
                },
            )
            from langchain_core.messages import SystemMessage

            request = request.override(
                system_message=SystemMessage(
                    content=(
                        request.system_message.text
                        + "\nCorrection required: "
                        + diagnostic[:6000]
                        + f"\nSubmit a corrected {schema.__name__} tool call. "
                        "No scientific work was repeated."
                    )
                )
            )
        raise AgentBoundaryError("Scientific output could not be validated")

    def contract_error(self, error: Any) -> str:
        from langchain.agents.structured_output import (
            MultipleStructuredOutputsError,
            StructuredOutputValidationError,
        )

        if not isinstance(
            error, (str, MultipleStructuredOutputsError, StructuredOutputValidationError)
        ):
            raise error
        if self.execution_id is None:
            raise AgentBoundaryError("Structured correction requires an execution")
        diagnostic = str(error)
        self.bridge.store.reserve_contract_repair(
            self.bridge.thread,
            self.role,
            self.execution_id,
            diagnostic,
        )
        return (
            "INVALID_STRUCTURED_SUBMISSION: "
            + diagnostic[:6000]
            + " Correct only the final typed submission."
        )

    async def awrap_tool_call(self, request: Any, handler: Any) -> Any:
        name, args = request.tool_call["name"], request.tool_call["args"]
        if name not in self.allowed:
            raise AgentBoundaryError("Rejected: tool is outside this role's permissions")
        token = None
        if name == "read_file":
            path = args.get("file_path", "")
            expected = f"/skills/{self.skills.get(self.role, '')}/SKILL.md"
            own_reference = self.role == "site" and path in {
                "/skills/site-mechanism/references/membrane.md",
                "/skills/site-mechanism/references/shielding.md",
                "/skills/site-mechanism/references/research.md",
            }
            own_result = (
                path.startswith("/result-") and path.endswith(".json") and path.count("/") == 1
            )
            if (
                not own_result
                and not own_reference
                and not (self.role in self.skills and path == expected)
            ):
                raise AgentBoundaryError("File is not an allowed skill or bounded result reference")
            if own_result and isinstance(self.bridge, Phase2Bridge):
                raise AgentBoundaryError("Use read_evidence_result for scoped offload fields")
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
            if specialist not in self.skills.values():
                raise AgentBoundaryError(
                    "Only the registered scientific specialists can be delegated"
                )
            description = args.get("description", "")
            if not isinstance(description, str) or not description or len(description) > 1500:
                return ToolMessage(
                    content=(
                        "Delegation was not executed: submit one scientific question under 600 "
                        "characters (hard limit 1500). Do not copy evidence, paths or identities; "
                        "runtime supplies the bound snapshot, original goal and revision."
                    ),
                    status="error",
                    tool_call_id=request.tool_call["id"],
                    name=name,
                )
            evidence = None
            task_type: Any = TargetTask
            extra: dict[str, Any] = {}
            if isinstance(self.bridge, Phase2Bridge):
                if specialist == "site-mechanism":
                    evidence = self.bridge.read_site_evidence()
                    token = SITE_EVIDENCE.set(
                        EvidenceBinding.model_validate(
                            {key: evidence[key] for key in EvidenceBinding.model_fields}
                        )
                    )
                elif specialist == "binder-strategy":
                    assert isinstance(self.bridge, DesignBridge)
                    evidence = self.bridge.read_design_evidence()
                    token = BINDER_EVIDENCE.set(
                        EvidenceBinding.model_validate(
                            {key: evidence[key] for key in EvidenceBinding.model_fields}
                        )
                    )
                elif specialist == "evidence-judge":
                    evidence = self.bridge.judge_evidence()
                elif self.revision:
                    evidence = self.bridge.read_evidence()
                task_type = ScientificTask
                extra = {
                    "current_gate": "site-hotspot"
                    if specialist == "site-mechanism"
                    else (evidence or {}).get("gate_type", "target-structure"),
                    "scientific_context": {
                        "scope": self.bridge.through,
                        "revision_owner": self.bridge.store.card(
                            self.bridge.thread, self.revision.card_id
                        ).owner_specialist
                        if self.revision
                        else None,
                    },
                }
            elif specialist == "evidence-judge" or self.revision:
                evidence = self.bridge.read_evidence()
            task = task_type(
                question=description,
                user_goal=self.goal,
                current_user_message=self.current_user_message,
                current_revision_instruction=self.revision.human_instruction
                if self.revision
                else None,
                revision_of_card_id=self.revision.card_id if self.revision else None,
                project_id=self.bridge.project_id,
                run_id=None if evidence is None else evidence["run_id"],
                evidence_id=None if evidence is None else evidence["evidence_id"],
                evidence_refs=[] if evidence is None else evidence["evidence_refs"],
                **extra,
            )
            payload = task.model_dump(mode="json")
            if evidence is not None and specialist == "evidence-judge":
                token = JUDGE_EVIDENCE.set(
                    EvidenceBinding.model_validate(
                        {name: evidence[name] for name in EvidenceBinding.model_fields}
                    )
                )
            request = request.override(
                tool_call={**request.tool_call, "args": {**args, "description": compact(payload)}}
            )
        try:
            try:
                if name == "read_evidence_result":
                    # Do this before StructuredTool validation can return an unbudgeted
                    # schema error. Foreign/tampered references remain fatal even when
                    # their projection syntax is also wrong.
                    if self.execution_id is None:
                        raise AgentBoundaryError("Result read requires an execution")
                    verified_result(
                        self.bridge, self.role, args.get("ref"), execution_id=self.execution_id
                    )
                    read_query(args)
                result = await handler(request)
            except InvalidFieldProjection as error:
                if (
                    (
                        name != "read_evidence_result"
                        and not (
                            name == "retrieve_evidence"
                            and isinstance(error, EvidenceCursorQueryMismatch)
                        )
                    )
                    or not isinstance(self.bridge, Phase2Bridge)
                    or self.execution_id is None
                ):
                    raise AgentBoundaryError("Projection repair is outside this tool") from error
                attempt = self.bridge.store.reserve_tool_argument_repair(
                    self.bridge.thread, self.role, self.execution_id
                )
                result = ToolMessage(
                    content=compact(
                        {**error.result(), "repair_attempt": attempt, "repair_limit": 2}
                    ),
                    status="error",
                    tool_call_id=request.tool_call["id"],
                    name=name,
                )
            except SourceSelectionRequired as error:
                # Only this proven sequencing error is repairable. Hard boundary and
                # artifact/authority failures still escape, including from delegated tasks.
                if (
                    name != "research_evidence"
                    or self.role not in {"target", "site"}
                    or not isinstance(self.bridge, Phase2Bridge)
                    or self.execution_id is None
                ):
                    raise AgentBoundaryError(
                        "Source-selection repair is outside this role"
                    ) from error
                required = error.result()
                attempt = self.bridge.store.reserve_prerequisite_repair(
                    self.bridge.thread, self.role, self.execution_id, required["source_id"]
                )
                result = ToolMessage(
                    content=compact({**required, "repair_attempt": attempt, "repair_limit": 2}),
                    status="error",
                    tool_call_id=request.tool_call["id"],
                    name=name,
                )
            raw_chars = len(str(result.content)) if isinstance(result, ToolMessage) else None
            if isinstance(self.bridge, Phase2Bridge) and self.execution_id:
                result = output_message(self.bridge, self.role, self.execution_id, result)
            supplied_cards = 0
            if (
                name in {"retrieve_evidence", "read_evidence_result"}
                and isinstance(result, ToolMessage)
                and isinstance(result.content, str)
            ):
                value = json.loads(result.content)
                page = value.get("cards", value.get("value", []))
                if isinstance(page, dict):
                    page = page.get("cards", [page])
                if isinstance(page, list):
                    supplied_cards = sum(
                        isinstance(card, dict)
                        and str(card.get("card_id", "")).startswith("passage-")
                        for card in page
                    )
            # Counts only, never raw provider requests or tool I/O in event telemetry.
            self.bridge.store.event(
                self.bridge.thread,
                "tool",
                {
                    "role": self.role,
                    "name": name,
                    "execution_id": self.execution_id,
                    "raw_result_chars": raw_chars,
                    "focused_cards_in_model_result": supplied_cards,
                    "model_result_chars": len(str(result.content))
                    if isinstance(result, ToolMessage)
                    else None,
                },
            )
            return result
        finally:
            if token is not None:
                if name == "task" and args.get("subagent_type") == "site-mechanism":
                    SITE_EVIDENCE.reset(token)
                elif name == "task" and args.get("subagent_type") == "binder-strategy":
                    BINDER_EVIDENCE.reset(token)
                else:
                    JUDGE_EVIDENCE.reset(token)

    async def aafter_agent(self, state: Any, runtime: Any) -> Any:
        if self.role == "coordinator":
            return None
        last = next(
            (
                m
                for m in reversed(state["messages"])
                if isinstance(m, AIMessage) and (m.text or "structured_response" in state)
            ),
            None,
        )
        if last is None:
            raise AgentBoundaryError("Specialist produced no assessment")
        structured = state.get("structured_response")
        if (
            structured is None
            or self.output_schema is None
            or not isinstance(structured, self.output_schema)
        ):
            raise AgentBoundaryError("Specialist must finish through its typed submission tool")
        parsed = structured.model_dump(mode="json")
        if self.role == "judge":
            result = self.bridge.register_judge(JudgeVerdict.model_validate(parsed)).model_dump(
                mode="json", exclude={"evidence_refs", "request_identity", "source_role"}
            )
        elif self.role == "binder":
            assert isinstance(self.bridge, DesignBridge)
            proposal = self.bridge.register_design(
                BinderIntent.model_validate(parsed), self.revision
            )
            result = {
                "status": "design-proposed",
                "objective": proposal["proposal"]["objective"],
                "scientific_status": proposal["evaluation"]["status"],
                "next": "Independent Evidence Judge, then Gate 3",
            }
        elif self.role == "site":
            assert isinstance(self.bridge, Phase2Bridge)
            proposal = self.bridge.register_site(SiteIntent.model_validate(parsed), self.revision)
            result = {
                "status": "site-proposed",
                "site": proposal["proposal"]["selected_site"],
                "scientific_status": proposal["evaluation"]["status"],
                "next": "Independent Evidence Judge review, then Gate 2",
            }
        else:
            result = register_target(
                self.bridge, TargetInterpretation.model_validate(parsed), self.revision
            )
        updates: dict[str, Any] = {
            "messages": [
                AIMessage(id=last.id, content=self.bridge.store.offload(self.bridge.thread, result))
            ]
        }
        if self.structured_output:
            updates["structured_response"] = result
        return updates


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
    revision: DecisionOutcome | None = None,
) -> Any:
    skills = (
        DESIGN_SKILLS
        if isinstance(bridge, DesignBridge)
        else PHASE2_SKILLS
        if isinstance(bridge, Phase2Bridge)
        else SKILLS
    )
    for role in ("coordinator", *skills):
        key = config.for_role(cast(Role, role)).harness_key
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
    from langchain.agents.structured_output import ToolStrategy

    specialists: list[SubAgent] = []
    for role, name in skills.items():
        structured_output = True
        schema = (
            JudgeVerdict
            if role == "judge"
            else SiteIntent
            if role == "site"
            else BinderIntent
            if role == "binder"
            else TargetInterpretation
        )
        prompt = (
            f"You are {name}, an isolated EasyDesign specialist. "
            f"Read /skills/{name}/SKILL.md first. "
            "Use only your available typed tools. Keep text fields concise (under 300 characters). "
            "Do not repeat whole evidence tables. "
            + f"Submit the final opinion using the {schema.__name__} structured output tool. "
            "All rationale and approach fields are strings, not objects. "
            "Runtime owns hard facts; do not reproduce sequence lengths, mappings or identities "
            "as authoritative data in your interpretation. "
            "Judge independently compares opinions with facts."
        )
        boundary = RoleBoundary(
            bridge, role, config, goal, current_user_message, execution_id, revision
        )
        specialists.append(
            {
                "name": name,
                "description": f"Independent {name} scientific reasoning with bounded tools",
                "model": models[role],
                "mode": "isolated",
                "system_prompt": prompt,
                "tools": phase2_tools(bridge, role)
                if isinstance(bridge, Phase2Bridge)
                else build_tools(bridge, role),
                "skills": [f"/skills/{name}/"],
                "middleware": [boundary],
                "interrupt_on": {},
            }
        )
        if structured_output:
            specialists[-1]["response_format"] = ToolStrategy(
                schema, handle_errors=boundary.contract_error
            )
    return create_deep_agent(
        model=models["coordinator"],
        system_prompt=(PHASE2_COORDINATOR if isinstance(bridge, Phase2Bridge) else COORDINATOR)
        + "\nTrusted thread intent: "
        + compact(
            {
                "research_goal": goal,
                "current_user_message": current_user_message or goal,
                "current_revision": revision.model_dump(mode="json") if revision else None,
            }
        )
        + (
            "\nTechnical details were explicitly requested; verified references may be shown."
            if technical_details
            else (
                "\nUse a short final answer (normally under 220 words) in the user's language: "
                "scientific outcome, selected site or actual frozen design constraints, and "
                "meaningful uncertainty. Never print internal next_specialist/tool state, SHA, "
                "assessment IDs, ledger/manifest details. Only give a viewer link if a tool "
                "actually returned it; no Design Viewer is implemented. Distinguish verified "
                "official scaffold loop bounds from untested cross-scaffold geometric equivalence. "
                "The final read_scientific_state frozen_design contains verified actual settings; "
                "do not call modified CDR3 settings defaults. Preserve warnings without promoting "
                "an earlier model's contradictory interpretation above verified runtime facts."
                if isinstance(bridge, Phase2Bridge)
                else "\nUse a short plain-language final answer: outcome, selected chain, "
                "meaningful "
                "limitations and viewer link. Do not print SHA/checksums, manifest revisions, "
                "assessment IDs, internal job identifiers or provenance implementation fields. "
                "When fallback_used is false, no fallback was used; "
                "do not speculate that it occurred."
            )
        ),
        tools=phase2_tools(bridge, "coordinator")
        if isinstance(bridge, Phase2Bridge)
        else build_tools(bridge, "coordinator"),
        subagents=specialists,
        backend=backend,
        checkpointer=saver,
        middleware=[
            RoleBoundary(
                bridge, "coordinator", config, goal, current_user_message, execution_id, revision
            )
        ],
        name="easydesign-scientist"
        if isinstance(bridge, Phase2Bridge)
        else "easydesign-target-agent",
    )
