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

from .contracts import AgentBoundaryError
from .models import ModelConfig, Role
from .session_store import compact


def context_usage(
    model: Any, config: ModelConfig, role: Role, messages: list[Any], tool_chars: int = 0
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
    if chars > config.hard_input_chars or (token_limit is not None and tokens > token_limit):
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
            self.bridge.store.reserve_model_call(
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

    @property
    def name(self) -> str:
        # DeepAgents replaces middleware by name. Preserve its single summary
        # slot: two wrappers would apply the shared checkpoint cutoff twice.
        return "SummarizationMiddleware"

    def __init__(self, model: Any, *, retained_tokens: int, **kwargs: Any) -> None:
        super().__init__(model=model, keep=("tokens", retained_tokens), **kwargs)
        self.retained_tokens = retained_tokens

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
    bridge: Any, config: ModelConfig, model: Any, backend: Any, execution_id: str | None
) -> SummarizationMiddleware:
    # A public model copy preserves the provider, adapter and reasoning settings.
    summary_model = model.model_copy(
        update={"callbacks": [SummaryAccounting(bridge, config, "site", execution_id, model)]}
    )
    profile_limit = (getattr(model, "profile", None) or {}).get("max_input_tokens")
    # The soft target is telemetry, not a demand to summarize each crossing.
    # Use framework memory between the working target and the independent guard.
    trigger = (config.max_input_chars + config.hard_input_chars) // 8
    if isinstance(profile_limit, int) and profile_limit > 0:
        trigger = min(
            trigger, max(1000, (profile_limit - config.for_role("site").max_output_tokens) // 2)
        )
    return ResearchMemory(
        model=summary_model,
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
        summary_prompt=DEEPAGENTS_DEFAULT_SUMMARY_PROMPT + "\n"
        "Keep this working summary within 1200 words. Retain the current scientific questions, "
        "provisional ranking, contradiction-check result, consequential findings/unknowns "
        "and exact query/passage identifiers needed "
        "for a decision or the next necessary inquiry. Preserve why more search would or would not "
        "change ranking, constraints or major risk; do not expand a topic checklist. "
        "Do not reproduce full tool bodies, residue tables, "
        "sequences, schemas or Skill text: their original verified artifacts are durable and "
        "are rehydrated independently for final synthesis. "
        "This is fallible research working memory, not verified source evidence, a Site "
        "proposal or approval. Preserve source/card identifiers, failed access, opposing "
        "evidence, numbering qualifications and unresolved questions. Never infer missing "
        "facts or turn a failed search into global absence. Final synthesis receives a "
        "separate runtime-built dossier from original verified artifacts, not this summary.",
    )
