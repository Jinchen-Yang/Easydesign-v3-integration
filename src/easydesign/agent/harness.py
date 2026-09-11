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
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from pydantic import ValidationError

from .contracts import (
    AgentBoundaryError,
    DecisionOutcome,
    EvidenceBinding,
    EvidenceCitationMismatch,
    EvidenceCursorQueryMismatch,
    EvidenceRetrievalQueryMismatch,
    InvalidFieldProjection,
    JudgeVerdict,
    ResearchConclusionMismatch,
    ResearchQueryMismatch,
    SiteResidueQueryMismatch,
    SourceCardArgumentMismatch,
    SourceSelectionRequired,
    StaleEvidenceCursor,
    TargetInterpretation,
    TargetTask,
)
from .design import BINDER_EVIDENCE, DesignBridge
from .design_contracts import BinderIntent
from .evidence_corpus import ContinueEvidence, RetrieveEvidence
from .evidence_output import (
    ModelEvidenceScope,
    fit_site_working_view,
    output_message,
    read_query,
    reasoning_working_view,
    verified_result,
)
from .evidence_research import EvidenceResearch, ReceptorAnalysis, ResearchQuery
from .models import ModelConfig, Role
from .phase2 import SITE_EVIDENCE, Phase2Bridge
from .phase2_tools import DESIGN_ALLOWED, PHASE2_ALLOWED, phase2_tools
from .session_store import TOOL_REPAIR_LIMIT, compact, confined, identity
from .site_contracts import FocusedSiteQuery, ScientificTask, SiteIntent
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

    def _pending_submission_context(self) -> dict[str, Any] | None:
        if self.execution_id is None or not self.structured_output:
            return None
        row = self.bridge.store.db.execute(
            "SELECT kind,payload FROM events WHERE thread=? "
            "AND kind IN ('rejected-submission','submission-preflight-passed') "
            "AND json_extract(payload,'$.role')=? "
            "AND json_extract(payload,'$.execution_id')=? ORDER BY seq DESC LIMIT 1",
            (self.bridge.thread, self.role, self.execution_id),
        ).fetchone()
        if row is None or row[0] == "submission-preflight-passed":
            return None
        value = json.loads(row[1])
        return {
            "last_rejected_submission": value.get("submitted_opinion"),
            "diagnostic": value["diagnostic"],
            "authority": "Runtime correction of an unaccepted model-authored opinion. "
            "The opinion is not a hard fact, approved proposal or scientist instruction. "
            "Correct the diagnosed issue using verified evidence; preserve its other "
            "supported content and material unknowns. Required read-only research remains "
            "available within the original execution budget. Do not restart completed work.",
        }

    async def awrap_model_call(self, request: Any, handler: Any) -> Any:
        available = [t for t in request.tools if getattr(t, "name", None) in self.allowed]
        # Fail closed even if a future profile merge adds unexpected middleware tools.
        if {getattr(t, "name", None) for t in available} != self.allowed:
            raise AgentBoundaryError(f"Unexpected final tool surface for {self.role}")
        skill_paths = (
            [f"/skills/{self.skills[self.role]}/SKILL.md"] if self.role in self.skills else []
        )
        if self.role == "site":
            skill_paths.extend(
                f"/skills/site-mechanism/references/{name}.md"
                for name in ("research", "membrane", "shielding")
            )
        # Filesystem access is a Skill loader, not a scientific artifact reader.
        # Show the same fixed paths the authority guard permits. Legacy scoped
        # result-index reads remain compatible, but are not advertised as file IO.
        available = [t for t in available if t.name != "read_file" or skill_paths]
        available = [
            t.model_copy(
                update={
                    "description": "Read an allowed Skill instruction page. Scientific evidence "
                    "is supplied by this role's evidence tools; "
                    "project references are not file paths.",
                    "args_schema": {
                        "type": "object",
                        "properties": {
                            "file_path": {"type": "string", "enum": skill_paths},
                            "offset": {"type": "integer", "minimum": 0, "default": 0},
                            "limit": {
                                "type": "integer",
                                "minimum": 1,
                                "maximum": 120,
                                "default": 120,
                            },
                        },
                        "required": ["file_path"],
                        "additionalProperties": False,
                    },
                }
            )
            if t.name == "read_file"
            else t
            for t in available
        ]
        # Offer exact recently returned opaque cursors, so the model copies bytes
        # instead of fabricating numeric offsets inside them. Runtime scope and
        # integrity checks still independently reject altered/foreign cursors.
        cursors = [""]
        for message in reversed(request.messages):
            if (
                not isinstance(message, ToolMessage)
                or message.name not in {"retrieve_evidence", "continue_evidence"}
                or message.status == "error"
                or not isinstance(message.content, str)
            ):
                continue
            try:
                cursor = json.loads(message.content).get("next_cursor")
            except (ValueError, TypeError, AttributeError):
                continue
            if isinstance(cursor, str) and cursor not in cursors:
                cursors.append(cursor)
            if len(cursors) >= 5:
                break
        retrieval_schema = RetrieveEvidence.model_json_schema()
        retrieval_schema["properties"].pop("cursor")
        continuation_schema = ContinueEvidence.model_json_schema()
        continuation_schema["properties"]["cursor"]["enum"] = cursors[1:]
        available = [
            t.model_copy(update={"args_schema": retrieval_schema})
            if t.name == "retrieve_evidence"
            else t.model_copy(update={"args_schema": continuation_schema})
            if t.name == "continue_evidence"
            else t
            for t in available
            if t.name != "continue_evidence" or cursors[1:]
        ]
        if self.role == "site" and isinstance(self.bridge, Phase2Bridge):
            receptor_cards = sorted(
                {
                    c["card_id"]
                    for q in EvidenceResearch(self.bridge).snapshot()["queries"]
                    for c in q["cards"]
                    if c["provider"] == "GPCRdb" and c.get("context_ref")
                }
            )
            if receptor_cards:
                receptor_schema = ReceptorAnalysis.model_json_schema()
                receptor_schema["properties"]["gpcrdb_card_id"]["enum"] = receptor_cards
                available = [
                    t.model_copy(update={"args_schema": receptor_schema})
                    if t.name == "analyze_receptor_context"
                    else t
                    for t in available
                ]
            else:
                available = [t for t in available if t.name != "analyze_receptor_context"]
        result_schema = ModelEvidenceScope.model_json_schema()
        if isinstance(self.bridge, Phase2Bridge):
            rows = self.bridge.store.db.execute(
                "SELECT json_extract(payload,'$.ref') FROM events "
                "WHERE thread=? AND kind='tool-view' "
                "AND json_extract(payload,'$.role')=? "
                "AND json_extract(payload,'$.execution_id')=? ORDER BY seq DESC LIMIT 32",
                (self.bridge.thread, self.role, self.execution_id),
            ).fetchall()
            refs = list(dict.fromkeys(row[0] for row in rows))
            if refs:
                # Copy exact role/execution-owned handles. The read-time authority,
                # current Judge binding and checksum checks remain independent.
                result_schema["properties"]["ref"]["enum"] = refs
            else:
                # An evidence_id is an identity, not a readable file. Offer scoped
                # navigation only after this role receives a registered view.
                available = [t for t in available if t.name != "read_evidence_result"]
        available = [
            t.model_copy(
                update={
                    "args_schema": result_schema,
                    "description": "Read a full_result already supplied to this role. "
                    "Choose fields=['status','warnings'] for top-level siblings OR "
                    "path=['facts',0,'mapping'] for nested traversal. Read only a "
                    "needed missing fact; complete scientific content is already usable. "
                    "List offset is within the stored page, never a residue label.",
                }
            )
            if t.name == "read_evidence_result"
            else t
            for t in available
        ]
        if self.role == "target" and not any(
            isinstance(m, ToolMessage) and m.name == "read_file" and m.status != "error"
            for m in request.messages
        ):
            # Preparation fixes the run's identity inputs. Do not offer it in the
            # initial call that is still loading those prerequisites from the Skill.
            available = [t for t in available if t.name != "prepare_target"]
        # An absent job cannot advance by observation. Tool availability follows the
        # original runtime receipt; this does not schedule work or choose science.
        if (
            self.role == "target"
            and "get_job_status" in self.allowed
            and self.bridge.get_job_status()["status"] == "no-bound-job"
        ):
            available = [t for t in available if t.name != "get_job_status"]
        if self.role == "target" and isinstance(self.bridge, Phase2Bridge):
            from langchain_core.messages import SystemMessage

            from .target_identity import pending_canonical_source_read

            needed_source = pending_canonical_source_read(self.bridge)
            if needed_source is not None:
                available = [t for t in available if t.name != "prepare_target"]
                request = request.override(
                    system_message=SystemMessage(
                        content=request.system_message.text
                        + "\nCurrent canonical configuration changed. Before preparing, retrieve "
                        "the selected source in this new view using retrieve_evidence with "
                        "need=TARGET_IDENTITY, source_id=" + needed_source + ", a focused identity "
                        "question, and no old cursor. Source bytes are already acquired; do not "
                        "download again. This verifies current-view evidence, not a new approval."
                    )
                )
        if self.role == "site" and any(
            isinstance(m, ToolMessage) and m.name == "read_site_evidence" and m.status != "error"
            for m in request.messages
        ):
            # Once the overview exists, use explicitly scoped scientific reads. The
            # complete durable evidence remains readable through read_evidence_result.
            # This changes neither candidate ranking nor the proposed residue selection.
            available = [
                t.model_copy(
                    update={
                        "args_schema": FocusedSiteQuery,
                        "description": "Read exact approved labels for a scientific "
                        "patch/hypothesis. The overview and candidate_patches are "
                        "already supplied. Read up to twelve labels at once; "
                        "request a different exact label set for another region.",
                    }
                )
                if t.name == "read_site_evidence"
                else t
                for t in available
            ]
        coordinator_state = None
        if self.role == "coordinator" and isinstance(self.bridge, Phase2Bridge):
            coordinator_state = self.bridge.scientific_state()
            if coordinator_state["scientific_state"] == "site-not-proposed":
                # Detailed mapping belongs to Site once Target is approved. Keep
                # observation/delegation available; do not reread Target as a new gate.
                available = [
                    t
                    for t in available
                    if t.name not in {"read_target_evidence", "read_evidence_result"}
                ]
        if isinstance(self.bridge, Phase2Bridge):
            # The checkpoint retains every message. The model sees a working set of
            # recent detailed tool views; older archived results remain addressable.
            detailed = [
                i
                for i, m in enumerate(request.messages)
                if isinstance(m, ToolMessage) and '"full_result"' in str(m.content)
            ]
            messages = list(request.messages)
            retained: set[int] = set()
            scopes: set[str] = set()
            detail_chars = 0
            if self.role == "judge":
                snapshots = [
                    i
                    for i in detailed
                    if messages[i].name in {"read_scientific_evidence", "read_target_evidence"}
                ]
                if snapshots:
                    # Independent comparison needs the whole delegated snapshot in
                    # view together, even after several narrower follow-up reads.
                    retained.add(snapshots[-1])
                    detail_chars = len(str(messages[snapshots[-1]].content))
            elif self.role == "site":
                # The newest answer must reach the model even when older sources
                # occupy the working set. Otherwise a successful scoped read is
                # immediately archived and the model keeps asking for unseen facts.
                if detailed:
                    retained.add(detailed[-1])
                    detail_chars = len(str(messages[detailed[-1]].content))
                # Keep read primary/database passages alongside geometry, so recency
                # alone cannot evict the evidence needed for mechanistic synthesis.
                # Use distinct source identities, never scientific favorability/ranking.
                for tool_name in (
                    "read_site_evidence",
                    "evaluate_candidate_site",
                    "analyze_receptor_context",
                ):
                    geometry = [i for i in detailed if messages[i].name == tool_name]
                    if geometry and geometry[-1] not in retained:
                        size = len(str(messages[geometry[-1]].content))
                        if detail_chars + size <= 32000:
                            retained.add(geometry[-1])
                            detail_chars += size
                source_ids = {
                    c["source_id"]
                    for i in retained
                    if messages[i].name in {"retrieve_evidence", "continue_evidence"}
                    for c in json.loads(messages[i].content).get("cards", [])
                    if c.get("source_id")
                }
                for i in reversed(detailed):
                    if messages[i].name not in {"retrieve_evidence", "continue_evidence"}:
                        continue
                    value = json.loads(messages[i].content)
                    sources = {c.get("source_id") for c in value.get("cards", [])}
                    sources.discard(None)
                    size = len(str(messages[i].content))
                    if (
                        sources - source_ids
                        and len(source_ids) < 3
                        and len(retained) < 6
                        and detail_chars + size <= 32000
                    ):
                        retained.add(i)
                        source_ids.update(sources)
                        detail_chars += size
            for i in reversed(detailed):
                if i in retained:
                    continue
                value = json.loads(messages[i].content)
                scope = compact(
                    {k: value.get(k) for k in ("full_result", "path", "fields", "next_offset")}
                )
                size = len(str(messages[i].content))
                if scope not in scopes and len(retained) < 4 and detail_chars + size <= 32000:
                    retained.add(i)
                    scopes.add(scope)
                    detail_chars += size
            for i in detailed:
                if i in retained:
                    continue
                value = json.loads(messages[i].content)
                messages[i] = messages[i].model_copy(
                    update={
                        "content": compact(
                            {
                                "archived_result": value["full_result"],
                                "partial": True,
                                "note": (
                                    "Earlier detailed view retained; read only if a fact "
                                    "is missing from the current supplied fields."
                                ),
                            }
                        )
                    }
                )
            request = request.override(messages=messages)
        if self.role == "coordinator" and isinstance(self.bridge, Phase2Bridge):
            from langchain_core.messages import SystemMessage

            # Approval resumes the old tool call and retains earlier scientific views.
            # Refresh only verified progress, never an interpretation or a scheduler.
            assert coordinator_state is not None
            state = coordinator_state
            progress = {
                key: state[key]
                for key in ("scientific_state", "gate_type", "next_specialist")
                if key in state
            }
            request = request.override(
                system_message=SystemMessage(
                    content=request.system_message.text
                    + "\nCurrent verified runtime progress (supersedes historical progress): "
                    + compact(progress)
                    + "\nEarlier pending cards and tool views are historical after delivery. "
                    "Continue the requested scope using this state; read_scientific_state "
                    "provides its full evidence. Do not ask again for a delivered approval. "
                    "Mapping review-required is a correspondence qualification, not a pending "
                    "gate when runtime progress is site-not-proposed. Target's scoped "
                    "approval_provenance=not-in-snapshot is not a pending approval either. "
                    "Delegate detailed mapping and site research to Site; do not inspect "
                    "each mapping entry or source yourself."
                )
            )
        from langchain_core.utils.function_calling import convert_to_openai_tool

        tool_schemas = [convert_to_openai_tool(t) for t in available]
        if self.structured_output:
            output_schema = self.output_schema
            assert output_schema is not None
            tool_schemas.append(convert_to_openai_tool(output_schema))
        tool_chars = len(compact(tool_schemas))
        if self.execution_id is None:
            raise AgentBoundaryError("Model call requires a persisted agent execution")
        from langchain_core.messages import SystemMessage

        base_system = request.system_message.text
        for attempt in range(3):
            used = self.bridge.store.db.execute(
                "SELECT COUNT(*) FROM events WHERE thread=? AND kind='model-call' "
                "AND json_extract(payload,'$.execution_id')=?",
                (self.bridge.thread, self.execution_id),
            ).fetchone()[0]
            synthesize = self.role == "site" and self.config.max_model_calls - used <= 8
            call_tools = [] if synthesize else available
            call_tool_chars = (
                len(compact([convert_to_openai_tool(SiteIntent)])) if synthesize else tool_chars
            )
            request = request.override(
                system_message=SystemMessage(
                    content=base_system
                    + "\nCurrent shared execution budget: "
                    + compact(
                        {
                            "used_model_calls": used,
                            "remaining_including_this_call": self.config.max_model_calls - used,
                            "total_model_calls": self.config.max_model_calls,
                        }
                    )
                    + ". This budget includes Coordinator, all specialists and independent Judge. "
                    "Use focused scientific questions, batch independent reads, and leave capacity "
                    "for typed synthesis, independent review and the Gate. Do not exhaust it by "
                    "enumerating the target or repeating delivered pages. Missing evidence stays "
                    "explicitly unresolved; budget pressure never justifies invented support."
                    + (
                        " Site reading budget is complete. Only the SiteIntent submission tool "
                        "is offered now. Submit your concise hypothesis with every material "
                        "unknown, source limitation and meaningful alternative retained. "
                        "This creates no approval; unchanged research/fact checks and independent "
                        "Judge can reject insufficient evidence. Do not invent support."
                        if synthesize
                        else ""
                    )
                    + (
                        " Site synthesis is now due: preserve about six calls for independent "
                        "Judge and the Coordinator. Use already delivered source passages and "
                        "candidate evaluations to submit a concise SiteIntent. Investigate only "
                        "a missing fact that changes whether the hypothesis is executable. "
                        "Represent remaining mechanistic/access/assay uncertainty explicitly; "
                        "do not claim it resolved or omit a material research conclusion."
                        if self.role == "site" and self.config.max_model_calls - used <= 10
                        else ""
                    )
                )
            )
            # Keep the phase transition adjacent to the latest evidence. The original
            # checkpoint stays intact; this is a transient model-input instruction.
            # A beginning-only system addition was repeatedly ignored in long live traces.
            reasoning = self.config.for_role(cast(Role, self.role)).reasoning_effort != "none"
            call_messages = (
                reasoning_working_view(list(request.messages))
                if reasoning
                else list(request.messages)
            )
            context_suffix = []
            pending_submission = self._pending_submission_context()
            if pending_submission is not None:
                context_suffix.append(HumanMessage(content=compact(pending_submission)))
            if synthesize:
                context_suffix.append(
                    HumanMessage(
                        content="Runtime phase notice (not a scientist decision or approval): "
                        "The reading phase has ended. Submit SiteIntent now from the "
                        "evidence already delivered. Do not call previous reading tools. "
                        "Keep unknowns, conflicting evidence and alternatives explicit; "
                        "the runtime and independent Judge may reject an insufficient proposal."
                    )
                )
            call_messages.extend(context_suffix)
            chars = len(str(request.system_message)) + sum(
                len(str(m.content)) for m in call_messages
            )
            if (
                self.role == "site"
                and isinstance(self.bridge, Phase2Bridge)
                and chars > self.config.max_input_chars
            ):
                before_chars = chars
                call_messages, archived = fit_site_working_view(
                    list(request.messages),
                    reasoning=reasoning,
                    system_chars=len(str(request.system_message)),
                    max_chars=self.config.max_input_chars,
                    suffix=context_suffix,
                )
                chars = len(str(request.system_message)) + sum(
                    len(str(m.content)) for m in call_messages
                )
                self.bridge.store.event(
                    self.bridge.thread,
                    "context-compaction",
                    {
                        "role": self.role,
                        "execution_id": self.execution_id,
                        "before_chars": before_chars,
                        "after_chars": chars,
                        "archived_views": archived,
                        "original_messages_unchanged": True,
                    },
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
                    "tool_schema_chars": call_tool_chars,
                    "estimated_input_chars_with_schemas": chars + call_tool_chars,
                    "context_metric": "system and message content; tool schemas separately",
                    "limit": self.config.max_input_chars,
                    "message_count": len(call_messages),
                    "tool_message_chars": sum(
                        len(str(m.content)) for m in request.messages if isinstance(m, ToolMessage)
                    ),
                    "repair_attempt": attempt,
                    "tool_mode": "site-synthesis" if synthesize else "research",
                    "history_projection": "completed-tool-records" if reasoning else "native",
                    "offered_action_tools": [t.name for t in call_tools],
                    "structured_output_tool": self.output_schema.__name__
                    if self.output_schema
                    else None,
                },
            )
            call_request = request.override(tools=call_tools, messages=call_messages)
            if (
                synthesize
                and self.config.for_role("site").provider == "deepseek"
                and self.config.for_role("site").reasoning_effort == "none"
            ):
                # ToolStrategy binds generic required. Use the provider's documented
                # named choice only for finalization, preserving vendor budget/settings.
                settings = dict(request.model_settings)
                settings["extra_body"] = {
                    **(getattr(request.model, "extra_body", None) or {}),
                    **settings.get("extra_body", {}),
                    "tool_choice": {"type": "function", "function": {"name": "SiteIntent"}},
                }
                call_request = call_request.override(model_settings=settings)
            response = await handler(call_request)
            self.bridge.store.event(
                self.bridge.thread,
                "model-response",
                {
                    "role": self.role,
                    "execution_id": self.execution_id,
                    "responses": [
                        {
                            "stop_reason": m.response_metadata.get("stop_reason")
                            or m.response_metadata.get("finish_reason"),
                            "usage": m.usage_metadata,
                            "tool_names": [c["name"] for c in m.tool_calls],
                            "invalid_tool_names": [c.get("name") for c in m.invalid_tool_calls],
                        }
                        for m in response.result
                        if isinstance(m, AIMessage)
                    ],
                },
            )
            if not self.structured_output:
                return response
            schema = self.output_schema
            assert schema is not None
            calls = [call for m in response.result for call in getattr(m, "tool_calls", [])]
            rejected_names = sorted(
                {
                    call["name"]
                    for call in calls
                    if call["name"] not in self.allowed | {schema.__name__}
                }
            )
            if rejected_names:
                self.bridge.store.event(
                    self.bridge.thread,
                    "rejected-tool-name",
                    {
                        "role": self.role,
                        "execution_id": self.execution_id,
                        "tool_names": rejected_names,
                        "executed": False,
                    },
                )
                raise AgentBoundaryError(
                    "Rejected: tool is outside this role's permissions: " + compact(rejected_names)
                )
            invalid = [
                call for m in response.result for call in getattr(m, "invalid_tool_calls", [])
            ]
            if any(call.get("name") != schema.__name__ for call in invalid):
                raise AgentBoundaryError("Malformed non-submission tool call remains fatal")
            diagnostic = ""
            if synthesize and any(call["name"] != schema.__name__ for call in calls):
                diagnostic = (
                    "SITE_READING_BUDGET_COMPLETE: rejected "
                    + compact([c["name"] for c in calls])
                    + "; no further reading/action was executed. "
                    "Submit only SiteIntent using delivered evidence; preserve material unknowns. "
                    "The original scientific and source checks remain mandatory."
                )
            elif invalid:
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
                        if self.role == "site":
                            assert isinstance(self.bridge, Phase2Bridge)
                            self.bridge.validate_site_research(response.structured_response)
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
                    except (EvidenceCitationMismatch, ResearchConclusionMismatch) as error:
                        diagnostic = str(error)
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
                    self.bridge.store.event(
                        self.bridge.thread,
                        "submission-preflight-passed",
                        {"role": self.role, "execution_id": self.execution_id},
                    )
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
            self.bridge.store.event(
                self.bridge.thread,
                "rejected-submission",
                {
                    "role": self.role,
                    "execution_id": self.execution_id,
                    "diagnostic": diagnostic[:6000],
                    "submitted_opinion": response.structured_response.model_dump(mode="json")
                    if response.structured_response is not None
                    else None,
                    "model_text": [
                        m.text[:24000] for m in response.result if isinstance(m, AIMessage)
                    ],
                },
            )
            self.contract_error(diagnostic)
            from langchain_core.messages import SystemMessage

            request = request.override(
                system_message=SystemMessage(
                    content=(
                        base_system
                        + "\nCorrection required: "
                        + diagnostic[:6000]
                        + f"\nSubmit a corrected {schema.__name__} tool call. "
                        "No scientific work was repeated."
                    )
                )
            )
            base_system = request.system_message.text
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
                # The filesystem tool can be chosen for a displayed /result-*.json.
                # Supply only an authorized field index; never invoke the file reader or
                # return unbounded data. This read-only alias has the same role, execution,
                # Judge snapshot and checksum checks as the scoped evidence tool.
                if self.execution_id is None:
                    raise AgentBoundaryError("Result index requires an execution")
                value = verified_result(
                    self.bridge, self.role, path, execution_id=self.execution_id
                )
                return ToolMessage(
                    content=compact(
                        {
                            "status": "scoped-result-index",
                            "full_result": path,
                            "available_fields": list(value)[:30] if isinstance(value, dict) else [],
                            "instruction": (
                                "Use read_evidence_result(ref=full_result, field=<one key>) "
                                "for evidence. This index contains no scientific field values; "
                                "read_file reads Skills, not scientific result pages."
                            ),
                        }
                    ),
                    tool_call_id=request.tool_call["id"],
                    name=name,
                )
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
            if isinstance(self.bridge, Phase2Bridge):
                progress = self.bridge.scientific_state()
                if (
                    progress.get("scientific_state") == "site-not-proposed"
                    and specialist != "site-mechanism"
                ):
                    self.bridge.store.event(
                        self.bridge.thread,
                        "delegation-prerequisite",
                        {
                            "execution_id": self.execution_id,
                            "requested_specialist": specialist,
                            "scientific_state": "site-not-proposed",
                            "next_specialist": "site-mechanism",
                        },
                    )
                    return ToolMessage(
                        content=compact(
                            {
                                "status": "NOT_APPLICABLE",
                                "scientific_state": "site-not-proposed",
                                "next_specialist": "site-mechanism",
                                "message": "Target is already approved; Site has no proposal. "
                                "Delegate the requested Site question to site-mechanism. "
                                "No upstream work or premature Judge delegation was executed.",
                            }
                        ),
                        status="error",
                        tool_call_id=request.tool_call["id"],
                        name=name,
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
                if name == "research_evidence":
                    try:
                        ResearchQuery.model_validate(args)
                    except ValidationError as error:
                        raise ResearchQueryMismatch(
                            "Invalid research arguments: "
                            + compact(
                                error.errors(
                                    include_input=False, include_url=False, include_context=False
                                )
                            )
                            + ". Record/fulltext/context acquisition requires identifier, "
                            "not query (which is for search). For gpcrdb-context use the exact "
                            "receptor identifier and pdb_id when known; wait for a successful "
                            "complete context card before analyzing it. No selection, fetch, "
                            "source or scientific job was created by this invalid request."
                        ) from error
                if name in {"retrieve_evidence", "continue_evidence"}:
                    try:
                        (
                            ContinueEvidence if name == "continue_evidence" else RetrieveEvidence
                        ).model_validate(args)
                    except ValidationError as error:
                        raise EvidenceRetrievalQueryMismatch(
                            "Invalid read-only retrieval arguments: "
                            + compact(
                                error.errors(
                                    include_input=False, include_url=False, include_context=False
                                )
                            )
                            + ". Use need, question, source_id, feature_types, page_size and "
                            "cursor only. Retrieval has no numeric offset; omit cursor for a "
                            "new view, or use its exact returned cursor with unchanged query. "
                            "No source passage was returned or consumed."
                        ) from error
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
                            name == "research_evidence" and isinstance(error, ResearchQueryMismatch)
                        )
                        and not (
                            name == "read_site_evidence"
                            and isinstance(error, SiteResidueQueryMismatch)
                        )
                        and not (
                            name == "compare_reference_identity"
                            and isinstance(error, SourceCardArgumentMismatch)
                        )
                        and not (
                            name in {"retrieve_evidence", "continue_evidence"}
                            and isinstance(
                                error,
                                (
                                    EvidenceCursorQueryMismatch,
                                    StaleEvidenceCursor,
                                    EvidenceRetrievalQueryMismatch,
                                ),
                            )
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
                        {
                            **error.result(),
                            "repair_attempt": attempt,
                            "repair_limit": TOOL_REPAIR_LIMIT,
                        }
                    ),
                    status="error",
                    tool_call_id=request.tool_call["id"],
                    name=name,
                )
            except SourceSelectionRequired as error:
                # Only this proven sequencing error is repairable. Hard boundary and
                # artifact/authority failures still escape, including from delegated tasks.
                if (
                    name not in {"research_evidence", "retrieve_evidence", "continue_evidence"}
                    or self.role not in {"target", "site"}
                    or not isinstance(self.bridge, Phase2Bridge)
                    or self.execution_id is None
                ):
                    raise AgentBoundaryError(
                        "Source-selection repair is outside this role"
                    ) from error
                required = error.result()
                if name != "research_evidence":
                    required["message"] = (
                        "This source is acquired but not selected for the requested evidence_need. "
                        "No passage was read and this is not absence of scientific evidence. "
                        "If relevant, select_evidence with the supplied provider/identifier, "
                        "need=evidence_need, selection=SELECTED and your reason; then retry the "
                        "retrieval. No new acquisition is required."
                    )
                attempt = self.bridge.store.reserve_prerequisite_repair(
                    self.bridge.thread, self.role, self.execution_id, required["source_id"]
                )
                result = ToolMessage(
                    content=compact(
                        {**required, "repair_attempt": attempt, "repair_limit": TOOL_REPAIR_LIMIT}
                    ),
                    status="error",
                    tool_call_id=request.tool_call["id"],
                    name=name,
                )
            raw_chars = len(str(result.content)) if isinstance(result, ToolMessage) else None
            if isinstance(self.bridge, Phase2Bridge) and self.execution_id:
                result = output_message(self.bridge, self.role, self.execution_id, result)
            supplied_cards = 0
            if (
                name in {"retrieve_evidence", "continue_evidence", "read_evidence_result"}
                and isinstance(result, ToolMessage)
                and isinstance(result.content, str)
                and result.status != "error"
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
        if role == "target" and isinstance(bridge, Phase2Bridge):
            prompt += (
                " Before prepare_target, resolve any canonical reference requested by the "
                "user: select/acquire/read the official source, propose_canonical_identity, "
                "then read the current identity view. Preparation freezes its inputs and "
                "cannot later add or replace a canonical reference. Read your Skill before "
                "starting preparation; never parallelize those dependent operations."
            )
        if role == "judge":
            prompt += (
                " The complete delegated scientific snapshot remains in your working set. "
                "Review its actual keys: a Target gate uses hard_facts, identity_evidence, "
                "options and target_interpretation; Site/Design use their own proposal fields. "
                "Use a scoped read only for a specific missing fact. Do not enumerate fields "
                "or reread supplied tables to verify runtime-owned hashes. When the supplied "
                "facts suffice, submit your independent critique through JudgeVerdict."
            )
        if role == "site":
            prompt += (
                " Work toward a reviewable, constraint-consistent hypothesis with meaningful "
                "alternatives, rather than exhaustive residue/source enumeration. Read primary "
                "passages and evaluate the needed mapped patches, then synthesize SiteIntent. "
                "A source's limited epitope/assay detail stays an explicit limitation; searching "
                "more bibliography does not itself resolve it. Use concise evidence claims and "
                "exact short excerpts so the entire typed opinion fits the output budget. "
                "Never invent missing facts or skip required checks to finish."
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
