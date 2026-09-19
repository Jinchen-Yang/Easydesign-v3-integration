"""Framework-owned working memory; runtime-owned limits and usage accounting."""

from __future__ import annotations

from time import perf_counter
from typing import Any

from deepagents.middleware.summarization import (
    DEEPAGENTS_DEFAULT_SUMMARY_PROMPT,
    SummarizationMiddleware,
)
from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.messages.utils import count_tokens_approximately
from langchain_core.utils.function_calling import convert_to_openai_tool

from .contracts import AgentBoundaryError
from .models import ModelConfig, Role, compact_summary_model
from .session_store import compact


def admit_site_research_request(
    request: Any,
    *,
    bridge: Any,
    config: ModelConfig,
    role: Role,
    execution_id: str | None,
    tool_chars: int,
) -> Any:
    """Replace an oversized Site transcript before any middleware hard guard runs."""
    from .phase2 import Phase2Bridge

    if role != "site" or execution_id is None or not isinstance(bridge, Phase2Bridge):
        return request
    messages = [request.system_message, *request.messages]
    measured = context_usage(
        request.model,
        config,
        role,
        messages,
        tool_chars,
        enforce=False,
    )
    # Reserve one observed large Site result batch plus output/repair overhead.
    # The 60k working target remains a trigger, while this deterministic boundary
    # prevents a 25-30k batch from jumping directly over the 100k hard guard.
    reserve = min(32000, max(16000, config.hard_input_chars // 3))
    admission_limit = min(
        config.max_input_chars + config.max_input_chars // 8,
        config.hard_input_chars - reserve,
    )
    if measured["input_chars_with_schemas"] <= admission_limit:
        return request
    from .site_research_runtime import site_research_packet_message

    packet = site_research_packet_message(
        bridge,
        execution_id,
        list(request.messages),
        reading_closed=False,
    )
    projected = context_usage(
        request.model,
        config,
        role,
        [request.system_message, packet],
        tool_chars,
    )
    bridge.store.event(
        bridge.thread,
        "site-research-context-admission",
        {
            "role": role,
            "execution_id": execution_id,
            "original_input_chars_with_schemas": measured["input_chars_with_schemas"],
            "projected_input_chars_with_schemas": projected["input_chars_with_schemas"],
            "admission_limit_chars": admission_limit,
            "hard_limit_chars": config.hard_input_chars,
            "reserve_chars": reserve,
            "projection": "runtime-site-research-packet-v1",
        },
    )
    return request.override(messages=[packet])


def input_context_tokens(messages: list[Any]) -> int:
    """Count actual request content without scaling from prior response usage.

    Provider usage may include hidden reasoning and generated output. Those tokens are billed,
    but they are not replayed input context and must not repeatedly trigger working-memory
    summaries. The hard request guard still accounts for the exact projected messages.
    """
    return int(count_tokens_approximately(messages))


def context_usage(
    model: Any,
    config: ModelConfig,
    role: Role,
    messages: list[Any],
    tool_chars: int = 0,
    *,
    enforce: bool = True,
) -> dict[str, Any]:
    argument_chars = sum(
        len(compact(m.tool_calls)) for m in messages if getattr(m, "tool_calls", None)
    )
    chars = sum(len(str(m.content)) for m in messages) + argument_chars + tool_chars
    tokens = int(count_tokens_approximately(messages)) + (tool_chars + 3) // 4
    profile = getattr(model, "profile", None) or {}
    maximum = profile.get("max_input_tokens")
    token_limit = (
        max(1, maximum - config.for_role(role).max_output_tokens)
        if isinstance(maximum, int) and maximum > 0
        else None
    )
    usage = {
        "input_chars_with_schemas": chars,
        "tool_call_argument_chars": argument_chars,
        "soft_target_chars": config.max_input_chars,
        "hard_limit_chars": config.hard_input_chars,
        "soft_target_exceeded": chars > config.max_input_chars,
        "estimated_input_tokens": tokens,
        "model_profile_token_guard": token_limit,
        "token_metric": "LangChain approximate count; not provider billing tokens",
    }
    if enforce and (
        chars > config.hard_input_chars or (token_limit is not None and tokens > token_limit)
    ):
        raise AgentBoundaryError("Model hard context guard exceeded: " + compact(usage))
    return usage


class SummaryAccounting(AsyncCallbackHandler):
    """Count the framework's auxiliary calls in the same persisted execution budget."""

    run_inline = True
    raise_error = True

    def __init__(
        self, bridge: Any, config: ModelConfig, role: Role, execution_id: str | None, model: Any
    ):
        self.bridge, self.config, self.role = bridge, config, role
        self.execution_id, self.model = execution_id, model
        self._started: dict[str, float] = {}

    async def on_chat_model_start(
        self, serialized: Any, messages: list[list[Any]], **kwargs: Any
    ) -> None:
        if self.execution_id is None:
            raise AgentBoundaryError("Framework summary requires a persisted execution")
        for batch in messages:
            usage = context_usage(self.model, self.config, self.role, batch)
            self.bridge.store.reserve_auxiliary_model_call(
                self.bridge.thread, self.role, self.config.max_model_calls, self.execution_id
            )
            self.bridge.store.event(
                self.bridge.thread,
                "framework-summary-call",
                {"role": self.role, "execution_id": self.execution_id, **usage},
            )
        self._started[str(kwargs.get("run_id"))] = perf_counter()

    async def on_llm_end(self, response: Any, **kwargs: Any) -> None:
        started = self._started.pop(str(kwargs.get("run_id")), None)
        self.bridge.store.event(
            self.bridge.thread,
            "framework-summary-response",
            {
                "role": self.role,
                "execution_id": self.execution_id,
                "latency_seconds": perf_counter() - started if started is not None else None,
                "usage": [
                    getattr(getattr(g, "message", None), "usage_metadata", None)
                    for batch in response.generations
                    for g in batch
                ],
            },
        )


class ResearchMemory(SummarizationMiddleware):
    """Let native summarization include a completed batch that exceeds tail retention.

    The framework moves a cutoff backward to keep tool calls and results together.
    A single large reasoning/tool batch can therefore exceed the requested keep budget.
    Once every result is present, that whole batch can instead join the native summary.
    Native history offload, checkpoint events and model accounting remain unchanged.
    """

    def _should_summarize_based_on_reported_tokens(
        self, messages: list[Any], threshold: float
    ) -> bool:
        """Ignore prior response totals when deciding whether request history needs compaction.

        Provider totals include generated output and hidden reasoning from the previous call.
        They measure cost, not the input messages currently being replayed. The explicit token
        counter and hard request guard remain authoritative for context capacity.
        """
        return False

    @property
    def name(self) -> str:
        # DeepAgents replaces middleware by name. Preserve its single summary
        # slot: two wrappers would apply the shared checkpoint cutoff twice.
        return "SummarizationMiddleware"

    def __init__(
        self,
        model: Any,
        *,
        retained_tokens: int,
        bridge: Any,
        config: ModelConfig,
        role: Role,
        execution_id: str | None,
        **kwargs: Any,
    ) -> None:
        super().__init__(model=model, keep=("tokens", retained_tokens), **kwargs)
        self.retained_tokens = retained_tokens
        self.bridge = bridge
        self.config = config
        self.role = role
        self.execution_id = execution_id

    async def awrap_model_call(self, request: Any, handler: Any) -> Any:
        """Admit a bounded Runtime packet before native summarization can hit the guard."""
        tool_chars = len(
            compact([convert_to_openai_tool(tool) for tool in getattr(request, "tools", [])])
        )
        request = admit_site_research_request(
            request,
            bridge=self.bridge,
            config=self.config,
            role=self.role,
            execution_id=self.execution_id,
            tool_chars=tool_chars,
        )
        return await super().awrap_model_call(request, handler)

    def _create_summary(self, messages_to_summarize: list[Any]) -> str:
        from .evidence_output import reasoning_working_view

        return super()._create_summary(reasoning_working_view(messages_to_summarize))

    async def _acreate_summary(self, messages_to_summarize: list[Any]) -> str:
        from .evidence_output import reasoning_working_view

        # Summary input is a transcript, not a signed provider conversation. Reuse
        # the lossless tool-record projection; private reasoning stays in the
        # original checkpoint/offload, while source results and public text remain.
        return await super()._acreate_summary(reasoning_working_view(messages_to_summarize))

    def _determine_cutoff_index(self, messages: list[Any]) -> int:
        cutoff = super()._determine_cutoff_index(messages)
        tail = messages[cutoff:]
        if not tail or not isinstance(tail[0], AIMessage):
            return cutoff
        calls = [call["id"] for call in tail[0].tool_calls]
        if (
            not calls
            or tail[0].invalid_tool_calls
            or not all(isinstance(message, ToolMessage) for message in tail[1:])
        ):
            return cutoff
        results = [message.tool_call_id for message in tail[1:]]
        if (
            len(calls) == len(results) == len(set(calls))
            and set(calls) == set(results)
            and self.token_counter(tail) > self.retained_tokens
        ):
            return len(messages)
        return cutoff


def research_memory(
    bridge: Any,
    config: ModelConfig,
    model: Any,
    backend: Any,
    execution_id: str | None,
    *,
    role: Role = "site",
) -> SummarizationMiddleware:
    # A summary is fallible working memory, not scientific reasoning. Preserve the configured
    # provider/model identity, but disable extended reasoning and cap its visible output.
    compact_model = compact_summary_model(model, config, role=role)
    summary_model = compact_model.model_copy(
        update={
            "callbacks": [SummaryAccounting(bridge, config, role, execution_id, compact_model)]
        }
    )
    profile_limit = (getattr(model, "profile", None) or {}).get("max_input_tokens")
    # Trigger near the configured working target, leaving room for one complete
    # multi-tool result batch before the independent hard guard. A high-water mark
    # near 90k characters let a normal 25-30k Site batch jump past a 100k guard
    # before the framework could summarize it.
    trigger = max(1000, config.max_input_chars // 4)
    if isinstance(profile_limit, int) and profile_limit > 0:
        trigger = min(
            trigger, max(1000, (profile_limit - config.for_role(role).max_output_tokens) // 2)
        )
    role_focus = (
        "For Target work retain canonical identity, construct relationship, chain alternatives, "
        "current preparation status, decisive limitations and exact source/result identifiers. "
        "Do not expand coordinate inventories already preserved in verified artifacts. "
        if role == "target"
        else "For Site work retain the provisional ranking, contradiction-check result and "
        "consequential findings/unknowns. "
    )
    return ResearchMemory(
        model=summary_model,
        bridge=bridge,
        config=config,
        role=role,
        execution_id=execution_id,
        backend=backend,
        # Native AND/OR trigger clauses provide a small hysteresis: after a
        # summary, accumulate more conversation before summarizing again unless
        # the high-water threshold needs the headroom. The original checkpoint
        # event supplies the effective history, including after restart.
        trigger=[
            {"tokens": trigger, "messages": 12},
            ("tokens", trigger + trigger // 8),
        ],
        # Native token retention preserves complete tool transactions. A message
        # count can retain several large batches and immediately trigger another
        # summary; leave headroom for actual research within the shared call budget.
        retained_tokens=max(200, min(trigger // 4, config.max_input_chars // 16)),
        trim_tokens_to_summarize=config.hard_input_chars // 4,
        token_counter=input_context_tokens,
        summary_prompt=DEEPAGENTS_DEFAULT_SUMMARY_PROMPT + "\n"
        "Keep this working summary within 700 words. Retain the current scientific questions. "
        + role_focus
        + "and exact query/passage identifiers needed "
        "for a decision or the next necessary inquiry. Preserve why more search would or would not "
        "change ranking, constraints or major risk; do not expand a topic checklist. "
        "Do not reproduce full tool bodies, residue tables, "
        "sequences, schemas or Skill text: their original verified artifacts are durable and "
        "are rehydrated independently for final synthesis. "
        "This is fallible research working memory, not verified source evidence, a scientific "
        "proposal or approval. Preserve source/card identifiers, failed access, opposing "
        "evidence, numbering qualifications and unresolved questions. Never infer missing "
        "facts or turn a failed search into global absence. Site synthesis receives a "
        "separate runtime-built dossier from original verified artifacts, not this summary.",
    )
