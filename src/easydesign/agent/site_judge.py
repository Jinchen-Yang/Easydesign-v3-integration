"""Bounded Site review: small typed opinion, runtime-owned facts and failure records."""

from __future__ import annotations

from time import perf_counter
from typing import Annotated, Any, Literal

from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware
from langchain.agents.structured_output import ToolStrategy
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.utils.function_calling import convert_to_openai_tool
from pydantic import Field

from .context_policy import context_usage
from .contracts import (
    AgentBoundaryError,
    EvidenceBinding,
    JudgeVerdict,
    OptionRecommendation,
    SiteClaimCorrection,
    StrictDTO,
)
from .models import ModelConfig
from .session_store import compact, identity
from .site_fact_integrity import fact_paths, validate_fact_references
from .tools import JUDGE_EVIDENCE

Brief = Annotated[
    str,
    Field(
        min_length=1,
        max_length=300,
        description="Interpretation only. No numbers, sequences or topology terms, including "
        "extracellular, intracellular, transmembrane, ECL or TM. Say selected candidate or "
        "alternative candidate. Put supporting facts in fact_refs, never in this prose field.",
    ),
]


class CompactClaimCorrection(SiteClaimCorrection):
    qualification: Brief


class SiteJudgeVerdict(StrictDTO):
    """A short early-stage review; runtime binds citations and renders hard facts."""

    verdict: Literal["ready-to-ask", "insufficient", "reject"]
    recommendation: Literal["SUPPORTED", "DISCOURAGED"]
    reasons: list[Brief] = Field(min_length=1, max_length=2)
    uncertainties: list[Brief] = Field(min_length=1, max_length=3)
    warnings: list[Brief] = Field(default_factory=list, max_length=3)
    alternative: Brief | None = Field(
        default=None,
        description="A conditional next step or alternative, not a certified better site. "
        "Point exposure does not prove whole-binder access. Contact with a disulfide-forming "
        "cysteine is not evidence of disrupting the bond, folding or trafficking; describe "
        "it as a risk to evaluate, never as a demonstrated goal violation.",
    )
    corrections: list[CompactClaimCorrection] = Field(
        default_factory=list,
        max_length=3,
        description="Qualify material overclaims in either the selected or alternative Site. "
        "Claims of whole-binder impossibility from point burial, or direct trafficking "
        "conflict from cysteine contact alone, need qualification rather than repetition.",
    )
    fact_refs: list[str] = Field(
        default_factory=list,
        max_length=4,
        description="Optional short supplied references such as candidate:0 or source:2. "
        "Do not copy hashes or facts into prose. Runtime supplies the evidence revision.",
    )


class RecoverySiteJudgeVerdict(SiteJudgeVerdict):
    """After truncation, prioritize a minimal submission within the same repair budget."""

    reasons: list[Brief] = Field(min_length=1, max_length=1)
    uncertainties: list[Brief] = Field(min_length=1, max_length=2)
    fact_refs: list[str] = Field(default_factory=list, max_length=1)


def review_prompt(*, recovery: bool = False) -> str:
    return (
        "Independently review this pending Site/Hotspot proposal for a Scientist decision. "
        "This is early selection, not proof of binder efficacy. Runtime owns identity, exact "
        "mapping, membership, source provenance and topology. Treat the supplied Site opinion "
        "as unapproved. Return only the offered structured review tool, without a preamble. "
        "Focus on whether the current hypothesis is usable, its major risk, and uncertainty. "
        "Use reject for hard contradiction; insufficient only when a meaningful current-stage "
        "decision is impossible. Unperformed docking, whole-binder access and functional assays "
        "normally remain uncertainty. Qualify material overclaims in the selected or alternative "
        "site using short exact claim excerpts. Point burial does not prove whole-binder "
        "impossibility; cysteine contact does not prove trafficking damage. A discouraged but "
        "reviewable hypothesis can be ready-to-ask, with a warning and an alternative. "
        "Keep interpretation in ordinary words: no digits, sequences, chain labels or topology "
        "classification literals. In prose say 'selected candidate' or 'alternative candidate'; "
        "do not write ECL, ICL, TM, extracellular, intracellular, cytoplasmic, transmembrane, "
        "outer_pore, core_pore or chain labels. Do not restate counts, including spelled-out "
        "counts, or recalculate comparisons from them. Express implications instead. "
        "For example, 'Limited exposure raises an access concern; full-binder feasibility "
        "requires validation.' This is a writing example, not a conclusion for this case. "
        "Put supporting short fact IDs in fact_refs; runtime expands "
        "them separately. Exact correction claim quotations alone may contain factual literals. "
        "Do not recalculate facts, audit every residue, enumerate all caveats, or repeat sources. "
        + (
            "The previous response was truncated or did not submit. Use the recovery schema: "
            "exactly one reason, at most two uncertainties, and at most one fact_ref. "
            "When a prior typed opinion is supplied, correct that opinion instead of restarting "
            "the review. Fix ALL prose fields: reasons, uncertainties, warnings, alternative "
            "and correction qualifications. Do not echo topology labels from the source text; "
            "even the word extracellular is forbidden outside an exact claim quotation. "
            "Keep each prose item to one short sentence. Complete the "
            "structured submission now. Retain any negative finding; do not change verdict "
            "to satisfy formatting."
            if recovery
            else "One or two short reasons are sufficient; prioritize completing the typed opinion."
        )
    )


def review_input(packet: dict[str, Any]) -> dict[str, Any]:
    """Exact scientific working set; omit transport/navigation instructions, not evidence."""
    keys = (
        "user_objective",
        "approved_target",
        "runtime_status",
        "residue_facts",
        "residue_constraints",
        "candidate_facts",
        "candidate_evaluation_scope",
        "reference_annotations",
        "receptor_context",
        "prepared_target_context",
        "final_site_decision",
        "decision_evidence",
        "downstream_validation",
        "authority",
        "avoid_design_labels",
        "peptide_reference",
        "peptide_facts",
        "peptide_overlaps",
    )
    return {
        **{key: packet[key] for key in keys if key in packet},
        "reference_collections": packet["fact_references"],
        "reference_usage": "Use collection_name:zero_based_index in fact_refs. "
        "Source passages expand source_group through decision_evidence.source_metadata. "
        "Their exact original passages and qualifiers are retained.",
    }


def normalize_opinion(opinion: SiteJudgeVerdict, packet: dict[str, Any]) -> JudgeVerdict:
    refs = fact_paths(packet)
    reasons = list(opinion.reasons)
    for short in dict.fromkeys(opinion.fact_refs):
        key = f"{packet['fact_revision']}:{short}"
        if key not in refs:
            raise AgentBoundaryError("Invalid Site Judge fact reference")
        reasons.append(f"Supporting runtime fact: [fact:{key}]")
    result = JudgeVerdict(
        verdict=opinion.verdict,
        reasons=reasons,
        limitations=list(opinion.uncertainties),
        recommendation=OptionRecommendation(
            option_id="site",
            status=opinion.recommendation,
            warnings=list(opinion.warnings),
            alternative=opinion.alternative,
        ),
        site_claim_corrections=list(opinion.corrections),
    )
    validate_fact_references(result, packet)
    return result


class SiteJudgeUnavailable(AgentBoundaryError):
    """Only a classified operational failure, never a scientific verdict."""


class SiteJudgeBoundary(AgentMiddleware[Any, Any, Any]):
    def __init__(self, bridge: Any, config: ModelConfig, execution_id: str):
        self.bridge, self.config, self.execution_id = bridge, config, execution_id
        self.schema_diagnostic: str | None = None

    def schema_error(self, error: Any) -> str:
        from langchain.agents.structured_output import (
            MultipleStructuredOutputsError,
            StructuredOutputValidationError,
        )

        if not isinstance(error, (MultipleStructuredOutputsError, StructuredOutputValidationError)):
            raise error
        self.schema_diagnostic = str(error)[:6000]
        message = error.ai_message
        self.bridge.store.event(
            self.bridge.thread,
            "structured-output-error",
            {
                "role": "judge",
                "execution_id": self.execution_id,
                "diagnostic": self.schema_diagnostic,
                "tool_calls": message.tool_calls,
                "invalid_tool_calls": message.invalid_tool_calls,
                "usage": message.usage_metadata,
                "stop_reason": message.response_metadata.get("stop_reason"),
                "usage_scope": "Counted once in model-response; reasoning text is not stored.",
            },
        )
        return self.schema_diagnostic

    def bound_packet(self) -> dict[str, Any]:
        packet: dict[str, Any] = self.bridge.judge_evidence()
        binding = EvidenceBinding.model_validate(
            {key: packet[key] for key in EvidenceBinding.model_fields}
        )
        if packet.get("gate_type") != "site-hotspot" or JUDGE_EVIDENCE.get() != binding:
            raise AgentBoundaryError("Site Judge lacks a current delegated binding")
        if "fact_references" not in packet:
            raise AgentBoundaryError("Compact Site Judge requires a dossier-backed proposal")
        return packet

    async def awrap_model_call(self, request: Any, handler: Any) -> Any:
        from .judge_packet import validate_judge_corrections, validate_judge_stage

        packet = self.bound_packet()
        binding = {key: packet[key] for key in EvidenceBinding.model_fields}
        previous = [
            e["payload"]
            for e in self.bridge.store.events(self.bridge.thread)
            if e["kind"] == "rejected-submission"
            and e["payload"].get("execution_id") == self.execution_id
            and e["payload"].get("binding") == binding
        ]
        failures = [p["diagnostic"] for p in previous]
        last_opinion = next(
            (p["submitted_opinion"] for p in reversed(previous) if p.get("submitted_opinion")),
            None,
        )
        substantive = any(p.get("substantive_finding") for p in previous)
        # Restart does not reset attempts. Normal and compact schemas share this contract.
        for attempt in range(len(previous), 3):
            if attempt:
                repairs = self.bridge.store.db.execute(
                    "SELECT COUNT(*) FROM events WHERE thread=? AND kind='contract-repair' "
                    "AND json_extract(payload,'$.execution_id')=? AND "
                    "(json_extract(payload,'$.contract') IS NULL OR "
                    "json_extract(payload,'$.contract')='JudgeVerdict')",
                    (self.bridge.thread, self.execution_id),
                ).fetchone()[0]
                if repairs >= 2:
                    break
                self.bridge.store.reserve_contract_repair(
                    self.bridge.thread,
                    "judge",
                    self.execution_id,
                    failures[-1],
                    contract="JudgeVerdict",
                )
            current = self.bound_packet()
            if identity(current) != identity(packet):
                raise AgentBoundaryError("Site Judge snapshot changed during review")
            recovery = attempt > 0
            schema = RecoverySiteJudgeVerdict if recovery else SiteJudgeVerdict
            working = review_input(packet)
            if recovery:
                working["submission_correction"] = {
                    "failure": failures[-1],
                    "prior_unvalidated_submission_to_correct": last_opinion,
                    "schema_diagnostic": self.schema_diagnostic
                    or next(
                        (
                            p.get("schema_diagnostic")
                            for p in reversed(previous)
                            if p.get("schema_diagnostic")
                        ),
                        None,
                    ),
                    "instruction": "Correct the submission; failed output is not evidence.",
                }
            messages = [HumanMessage(content=compact(working))]
            system = SystemMessage(content=review_prompt(recovery=recovery))
            schema_chars = len(compact([convert_to_openai_tool(schema)]))
            usage = context_usage(
                request.model, self.config, "judge", [system, *messages], schema_chars
            )
            self.bridge.store.reserve_model_call(
                self.bridge.thread, "judge", self.config.max_model_calls, self.execution_id
            )
            self.bridge.store.event(
                self.bridge.thread,
                "model-context",
                {
                    "role": "judge",
                    "execution_id": self.execution_id,
                    "binding": binding,
                    **usage,
                    "context_chars": usage["input_chars_with_schemas"] - schema_chars,
                    "estimated_input_chars_with_schemas": usage["input_chars_with_schemas"],
                    "context_metric": "system and message content; tool schemas separately",
                    "limit": self.config.hard_input_chars,
                    "tool_schema_chars": schema_chars,
                    "repair_attempt": attempt,
                    "tool_mode": "site-judge-recovery" if recovery else "site-judge",
                    "structured_output_tool": schema.__name__,
                    "offered_action_tools": [],
                },
            )
            call = request.override(
                system_message=system,
                messages=messages,
                tools=[],
                response_format=ToolStrategy(schema, handle_errors=self.schema_error),
            )
            self.schema_diagnostic = None
            started = perf_counter()
            from anthropic import APIConnectionError as AnthropicConnectionError
            from anthropic import APITimeoutError as AnthropicTimeout
            from anthropic import InternalServerError as AnthropicServerError
            from anthropic import RateLimitError as AnthropicRateLimit
            from openai import APIConnectionError as OpenAIConnectionError
            from openai import APITimeoutError as OpenAITimeout
            from openai import InternalServerError as OpenAIServerError
            from openai import RateLimitError as OpenAIRateLimit

            transport_failure = None
            try:
                response = await handler(call)
            except (AnthropicTimeout, OpenAITimeout):
                response = None
                transport_failure = "PROVIDER_TIMEOUT"
            except (
                AnthropicConnectionError,
                AnthropicServerError,
                AnthropicRateLimit,
                OpenAIConnectionError,
                OpenAIServerError,
                OpenAIRateLimit,
            ):
                response = None
                transport_failure = "PROVIDER_UNAVAILABLE"
            raw = [m for m in response.result if isinstance(m, AIMessage)] if response else []
            records = [
                {
                    "stop_reason": m.response_metadata.get("stop_reason")
                    or m.response_metadata.get("finish_reason"),
                    "usage": m.usage_metadata,
                    "tool_names": [c["name"] for c in m.tool_calls],
                    "invalid_tool_names": [c.get("name") for c in m.invalid_tool_calls],
                }
                for m in raw
            ]
            self.bridge.store.event(
                self.bridge.thread,
                "model-response",
                {
                    "role": "judge",
                    "execution_id": self.execution_id,
                    "latency_seconds": perf_counter() - started,
                    "responses": records,
                    "transport_failure": transport_failure,
                },
            )
            opinion = response.structured_response if response else None
            submitted = (
                opinion.model_dump(mode="json")
                if isinstance(opinion, SiteJudgeVerdict)
                else next(
                    (
                        c["args"]
                        for m in raw
                        for c in m.tool_calls
                        if c["name"] in {"SiteJudgeVerdict", "RecoverySiteJudgeVerdict"}
                        and isinstance(c.get("args"), dict)
                    ),
                    None,
                )
            )
            if submitted is not None:
                last_opinion = submitted
            if isinstance(opinion, SiteJudgeVerdict):
                try:
                    normalized = normalize_opinion(opinion, packet)
                    validate_judge_stage(normalized, packet)
                    validate_judge_corrections(normalized, packet)
                except (AgentBoundaryError, ValueError) as error:
                    substantive = True
                    diagnostic = type(error).__name__ + ": " + str(error)
                else:
                    self.bridge.store.event(
                        self.bridge.thread,
                        "submission-preflight-passed",
                        {
                            "role": "judge",
                            "execution_id": self.execution_id,
                            "review_contract": schema.__name__,
                            "binding": binding,
                        },
                    )
                    return response
            else:
                substantive |= any(
                    isinstance(c.get("args"), dict)
                    and c["args"].get("verdict") in {"reject", "insufficient"}
                    for m in raw
                    for c in m.tool_calls
                )
                diagnostic = transport_failure or (
                    "OUTPUT_TRUNCATED"
                    if any(r["stop_reason"] in {"max_tokens", "length"} for r in records)
                    else "MISSING_OR_INVALID_TYPED_SUBMISSION"
                )
            failures.append(diagnostic)
            self.bridge.store.event(
                self.bridge.thread,
                "rejected-submission",
                {
                    "role": "judge",
                    "execution_id": self.execution_id,
                    "binding": binding,
                    "diagnostic": diagnostic,
                    "schema_diagnostic": self.schema_diagnostic,
                    "submitted_opinion": submitted,
                    "schema_valid": isinstance(opinion, SiteJudgeVerdict),
                    "substantive_finding": substantive,
                },
            )
        if substantive:
            raise AgentBoundaryError("Site Judge review contains unresolved substantive findings")
        raise SiteJudgeUnavailable("; ".join(failures))

    async def aafter_agent(self, state: Any, runtime: Any) -> Any:
        opinion = state.get("structured_response")
        if not isinstance(opinion, SiteJudgeVerdict):
            raise AgentBoundaryError("Site Judge did not finish with a valid typed opinion")
        packet = self.bound_packet()
        assessment = self.bridge.register_judge(normalize_opinion(opinion, packet))
        self.bridge.store.event(
            self.bridge.thread,
            "site-judge-submission",
            {
                "execution_id": self.execution_id,
                "assessment_id": assessment.assessment_id,
                "raw_opinion": opinion.model_dump(mode="json"),
                "fact_revision": packet["fact_revision"],
            },
        )
        return {
            "messages": [
                AIMessage(
                    content=compact(
                        {
                            "assessment_id": assessment.assessment_id,
                            "verdict": assessment.verdict,
                        }
                    )
                )
            ]
        }


def create_site_judge(bridge: Any, model: Any, config: ModelConfig, execution_id: str) -> Any:
    boundary = SiteJudgeBoundary(bridge, config, execution_id)
    return create_agent(
        model=model,
        system_prompt=review_prompt(),
        tools=[],
        middleware=[boundary],
        response_format=ToolStrategy(
            SiteJudgeVerdict | RecoverySiteJudgeVerdict, handle_errors=boundary.schema_error
        ),
        name="site-independent-judge",
    )


def create_site_aware_judge(
    bridge: Any, model: Any, config: ModelConfig, execution_id: str | None, legacy: Any
) -> Any:
    """Use the compact contract only for dossier-backed Gate 2; other Gates retain theirs."""
    from typing import TypedDict

    from langgraph.graph import END, START, StateGraph

    class State(TypedDict):
        messages: list[Any]
        structured_response: Any

    async def route(state: Any) -> str:
        packet = bridge.judge_evidence()
        return (
            "site"
            if packet.get("gate_type") == "site-hotspot" and "fact_references" in packet
            else "legacy"
        )

    async def site(state: Any, config: RunnableConfig) -> Any:
        if execution_id is None:
            raise AgentBoundaryError("Site Judge requires a persisted execution")
        try:
            return await create_site_judge(bridge, model, model_config, execution_id).ainvoke(
                {"messages": [HumanMessage(content="Review the current delegated Site proposal.")]},
                config,
            )
        except SiteJudgeUnavailable:
            from .site_review_availability import record_unavailable

            failure = record_unavailable(bridge, execution_id)
            return {
                "messages": [
                    AIMessage(
                        content=compact(
                            {
                                "review_availability": "unavailable",
                                "review_failure_id": failure["record_id"],
                                "next": "Scientist review required; assessment unavailable",
                            }
                        )
                    )
                ],
                "structured_response": None,
            }

    model_config = config
    graph = StateGraph(State)
    graph.add_node("site", site)
    graph.add_node("legacy", legacy)
    graph.add_conditional_edges(START, route, {"site": "site", "legacy": "legacy"})
    graph.add_edge("site", END)
    graph.add_edge("legacy", END)
    return graph.compile(name="independent-judge-boundary")
