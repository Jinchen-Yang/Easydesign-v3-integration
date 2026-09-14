"""Bounded structured scientific calls using the existing model/context/budget ledger."""

from __future__ import annotations

from collections.abc import Callable
from time import perf_counter
from typing import Any, TypeVar

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.utils.function_calling import convert_to_openai_tool
from pydantic import BaseModel, ValidationError

from .context_policy import context_usage
from .contracts import AgentBoundaryError, JudgeFactClaim
from .models import ModelConfig, Role
from .session_store import compact, identity

OpinionT = TypeVar("OpinionT", bound=BaseModel)


class StructuredOpinionUnavailable(AgentBoundaryError):
    def __init__(self, categories: list[str], retained_warnings: list[str]):
        super().__init__("Structured scientific opinion unavailable: " + ", ".join(categories))
        self.categories = categories
        self.retained_warnings = retained_warnings


class ReviewFactConflict(AgentBoundaryError):
    """An unresolved explicit fact conflict is never an unavailable-review fallback."""


def validate_review_facts(raw: dict[str, Any], facts: dict[str, Any]) -> None:
    """Check addressed JSON objects only; ordinary scientific prose stays unrestricted."""
    refs = raw.get("fact_refs", [])
    claims = raw.get("fact_claims", [])
    if not isinstance(refs, list) or not isinstance(claims, list):
        raise AgentBoundaryError("Fact references and claims must be arrays")
    for ref in refs:
        if not isinstance(ref, str):
            raise AgentBoundaryError("Fact references must be strings")
        if ref not in facts:
            raise ReviewFactConflict("Independent review cites an unknown runtime fact")
    for value in claims:
        claim = JudgeFactClaim.model_validate(value)
        if claim.fact_ref not in facts:
            raise ReviewFactConflict("Independent review asserts an unknown runtime fact")
        fact = facts[claim.fact_ref]
        if claim.field is not None:
            if not isinstance(fact, dict) or claim.field not in fact:
                raise ReviewFactConflict("Independent review asserts an unknown structured field")
            fact = fact[claim.field]
        if compact(claim.value) != compact(fact):
            raise ReviewFactConflict("Independent review contradicts a structured runtime fact")


async def structured_opinion(
    *,
    bridge: Any,
    model: Any,
    config: ModelConfig,
    execution_id: str,
    role: Role,
    schema: type[OpinionT],
    packet: dict[str, Any],
    prompt: str,
    validate: Callable[[OpinionT], Any] | None = None,
) -> OpinionT:
    """One opinion, at most two compact repairs; no action tools or hidden model calls."""
    from anthropic import APIConnectionError as AnthropicConnectionError
    from anthropic import InternalServerError as AnthropicServerError
    from anthropic import RateLimitError as AnthropicRateLimit
    from openai import APIConnectionError as OpenAIConnectionError
    from openai import InternalServerError as OpenAIServerError
    from openai import RateLimitError as OpenAIRateLimit

    binding = identity({"packet": packet, "role": role, "schema": schema.__name__})
    previous = [
        e["payload"]
        for e in bridge.store.events(bridge.thread)
        if e["kind"] == "phase34-model-attempt"
        and e["payload"].get("binding") == binding
        and e["payload"].get("execution_id") == execution_id
    ]
    for attempt in previous:
        if attempt.get("opinion") is not None:
            recovered = schema.model_validate(attempt["opinion"])
            if validate:
                validate(recovered)
            return recovered
    categories = [p["category"] for p in previous]
    retained = [w for p in previous for w in p.get("retained_warnings", [])]
    diagnostic = previous[-1].get("diagnostic") if previous else None
    last_submission = previous[-1].get("submission") if previous else None
    for attempt in range(len(previous), 3):
        recovery = (
            {}
            if attempt == 0
            else {
                "repair": categories[-1],
                "diagnostic": diagnostic,
                "previous_unvalidated_submission": last_submission,
                "instruction": "Return ONLY the compact structured opinion. No preamble. "
                "Correct the specified field; keep valid observations and critical warnings.",
            }
        )
        messages = [
            SystemMessage(content=prompt),
            HumanMessage(content=compact({**packet, **recovery})),
        ]
        usage = context_usage(
            model, config, role, messages, len(compact(convert_to_openai_tool(schema)))
        )
        bridge.store.reserve_model_call(bridge.thread, role, config.max_model_calls, execution_id)
        bridge.store.event(
            bridge.thread,
            "model-context",
            {
                "role": role,
                "execution_id": execution_id,
                "binding": binding,
                **usage,
                "repair_attempt": attempt,
                "structured_output_tool": schema.__name__,
                "offered_action_tools": [],
            },
        )
        start = perf_counter()
        response = None
        category = "NO_SUBMISSION"
        try:
            response = await model.bind_tools([schema], tool_choice="auto").ainvoke(messages)
        except (
            AnthropicConnectionError,
            AnthropicServerError,
            AnthropicRateLimit,
            OpenAIConnectionError,
            OpenAIServerError,
            OpenAIRateLimit,
        ):
            category = "PROVIDER_UNAVAILABLE"
        bridge.store.event(
            bridge.thread,
            "model-response",
            {
                "role": role,
                "execution_id": execution_id,
                "latency_seconds": perf_counter() - start,
                "responses": []
                if response is None
                else [
                    {
                        "usage": response.usage_metadata,
                        "stop_reason": response.response_metadata.get("stop_reason")
                        or response.response_metadata.get("finish_reason"),
                        "tool_names": [c["name"] for c in response.tool_calls],
                    }
                ],
            },
        )
        submission = None
        if response is not None:
            stop = response.response_metadata.get("stop_reason") or response.response_metadata.get(
                "finish_reason"
            )
            if stop in {"max_tokens", "length"}:
                category = "MAX_TOKENS"
            calls = [c for c in response.tool_calls if c["name"] == schema.__name__]
            if len(calls) == 1 and len(response.tool_calls) == 1:
                submission = calls[0]["args"]
        opinion: OpinionT | None = None
        if isinstance(submission, dict):
            # A malformed opinion must not hide a readable hard-fact conflict in fallback.
            try:
                if role == "judge":
                    warnings = submission.get("warnings", [])
                    if isinstance(warnings, list):
                        retained.extend(w for w in warnings if isinstance(w, str))
                    validate_review_facts(submission, packet.get("facts", {}))
                opinion = schema.model_validate(submission)
                if validate:
                    validate(opinion)
            except ValidationError as error:
                opinion = None
                category = "SCHEMA_ERROR"
                diagnostic = error.errors(
                    include_input=False, include_url=False, include_context=False
                )
            except AgentBoundaryError as error:
                opinion = None
                category = (
                    "FACT_CONFLICT" if isinstance(error, ReviewFactConflict) else "SCHEMA_ERROR"
                )
                diagnostic = str(error)
        bridge.store.event(
            bridge.thread,
            "phase34-model-attempt",
            {
                "binding": binding,
                "execution_id": execution_id,
                "role": role,
                "attempt": attempt + 1,
                "category": "SUCCESS" if opinion else category,
                "opinion": opinion.model_dump(mode="json") if opinion else None,
                "submission": submission,
                "diagnostic": diagnostic,
                "retained_warnings": list(dict.fromkeys(retained)),
            },
        )
        if opinion is not None:
            return opinion
        last_submission = submission
        categories.append(category)
    if "FACT_CONFLICT" in categories:
        raise ReviewFactConflict("Independent review has an unresolved structured fact conflict")
    raise StructuredOpinionUnavailable(categories, list(dict.fromkeys(retained)))
