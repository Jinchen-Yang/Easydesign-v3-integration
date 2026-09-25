"""Bounded structured scientific calls using the existing model/context/budget ledger."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from time import perf_counter
from typing import Any, TypeVar

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.utils.function_calling import convert_to_openai_tool
from pydantic import BaseModel, Field, ValidationError, create_model
from pydantic_core import PydanticUndefined

from .context_policy import context_usage
from .contracts import AgentBoundaryError, JudgeFactClaim
from .models import ModelConfig, Role
from .session_store import compact, identity

OpinionT = TypeVar("OpinionT", bound=BaseModel)


def _patch_schema(schema: type[BaseModel]) -> type[BaseModel]:
    """Same tool identity, optional replacement fields; final validation uses the original."""
    fields: dict[str, Any] = {}
    for name, field in schema.model_fields.items():
        optional = deepcopy(field)
        optional.default = None
        optional.default_factory = None
        fields[name] = (field.annotation, optional)
    return create_model(schema.__name__, __config__=schema.model_config, **fields)


def _ranking_schema(schema: type[BaseModel], packet: dict[str, Any]) -> type[BaseModel]:
    """Explicit native wire contract; persisted opinion and final validators stay unchanged."""
    fields: dict[str, Any] = {}
    for name, field in schema.model_fields.items():
        required = deepcopy(field)
        required.default = PydanticUndefined
        required.default_factory = None
        fields[name] = (field.annotation, required)
    count = packet["candidate_count"]
    fields["candidate_order"] = (
        list[str],
        Field(
            description=f"Exactly {count} distinct PASS candidate_id references, strongest first. "
            "Include every matrix row once; check the count before submission.",
            min_length=count,
            max_length=count,
        ),
    )
    fields["candidate_rankings"] = (
        schema.model_fields["candidate_rankings"].annotation,
        Field(
            description="Detailed objects for the top 3 in candidate_order and EVERY ID in "
            "supporting_candidate_ids, plus material tradeoffs; at most 12 objects. "
            "Each object needs candidate_id, rationale, risks and metric_refs.",
            max_length=12,
        ),
    )
    return create_model(
        schema.__name__,
        __config__=schema.model_config,
        __doc__="Submit a complete compact ranked proposal. All fields are required, "
        "including ranked_arm_ids, arm_recovery and empty arrays when applicable. "
        "Use short explanations; rationale must be under 450 characters.",
        **fields,
    )


class StructuredOpinionUnavailable(AgentBoundaryError):
    def __init__(self, categories: list[str], retained_warnings: list[str]):
        super().__init__("Structured scientific opinion unavailable: " + ", ".join(categories))
        self.categories = categories
        self.retained_warnings = retained_warnings


class ReviewFactConflict(AgentBoundaryError):
    """An unresolved explicit fact conflict is never an unavailable-review fallback."""

    def __init__(
        self,
        message: str,
        *,
        retained_warnings: list[str] | None = None,
        attempts: int = 1,
    ):
        super().__init__(message)
        self.categories = ["FACT_CONFLICT"]
        self.retained_warnings = retained_warnings or []
        self.attempts = attempts


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
    delta_repair: bool = False,
    resume_across_executions: bool = False,
) -> OpinionT:
    """One opinion, at most two compact repairs; no action tools or hidden model calls."""
    from anthropic import APIConnectionError as AnthropicConnectionError
    from anthropic import InternalServerError as AnthropicServerError
    from anthropic import RateLimitError as AnthropicRateLimit
    from openai import APIConnectionError as OpenAIConnectionError
    from openai import InternalServerError as OpenAIServerError
    from openai import RateLimitError as OpenAIRateLimit

    from .phase3_capacity import SUBMISSION_PROTOCOL, VIEW_VERSION, ranking_submission_model

    native_decision = (
        delta_repair and role == "pilot-diagnosis" and packet.get("version") == VIEW_VERSION
    )
    binding = identity(
        {
            "packet": packet,
            "role": role,
            "schema": schema.__name__,
            **({"prompt_sha256": identity(prompt)} if resume_across_executions else {}),
            **({"submission_protocol": SUBMISSION_PROTOCOL} if native_decision else {}),
        }
    )
    previous = [
        e["payload"]
        for e in bridge.store.events(bridge.thread)
        if e["kind"] == "phase34-model-attempt"
        and e["payload"].get("binding") == binding
        and (
            e["payload"].get("execution_id") == execution_id
            or (resume_across_executions and e["payload"].get("opinion") is not None)
        )
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
    call_model = ranking_submission_model(model, config) if native_decision else model
    for attempt in range(len(previous), 3):
        use_patch = (
            delta_repair
            and role == "pilot-diagnosis"
            and attempt > 0
            and isinstance(last_submission, dict)
            and bool(last_submission)
            and not (set(last_submission) - set(schema.model_fields))
        )
        full_wire_schema = _ranking_schema(schema, packet) if native_decision else schema
        native_selection = (
            delta_repair
            and role == "final-selection"
            and packet.get("ranking_protocol") == "native-global-comparison-v1"
        )
        if native_selection:
            from .phase4_ranking import comparison_schema

            full_wire_schema = comparison_schema(schema, packet)
        wire_schema: type[BaseModel] = (
            _patch_schema(full_wire_schema) if use_patch else full_wire_schema
        )
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
        if delta_repair and role == "pilot-diagnosis" and attempt > 0:
            from .phase3_capacity import ranking_repair_context

            repair_context = ranking_repair_context(
                last_submission if isinstance(last_submission, dict) else {},
                diagnostic,
                packet if native_decision else None,
            )
            if not use_patch:
                repair_context["instruction"] = (
                    "Return ONLY the complete corrected structured opinion. "
                    "The previous submission cannot be merged; all required fields are needed."
                )
            recovery = {
                "repair": categories[-1],
                "delta_repair" if use_patch else "compact_recovery": repair_context,
            }
        if delta_repair and role == "final-selection" and attempt > 0:
            recovery = {
                "repair": categories[-1],
                "diagnostic": compact(diagnostic)[:1500],
                "previous_submission_excerpt": compact(last_submission)[:1500],
                "instruction": "Submit the complete corrected structured output only. "
                "Allowed IDs and all scientific facts remain in candidate_matrix. "
                "Keep explanations short; do not repeat facts or add a preamble.",
            }
        messages = [
            SystemMessage(content=prompt),
            HumanMessage(content=compact({**packet, **recovery})),
        ]
        usage = context_usage(
            model,
            config,
            role,
            messages,
            len(compact(convert_to_openai_tool(wire_schema))),
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
                "delta_repair": use_patch,
                "submission_protocol": SUBMISSION_PROTOCOL if native_decision else None,
            },
        )
        start = perf_counter()
        response = None
        category = "NO_SUBMISSION"
        try:
            response = await call_model.bind_tools(
                [wire_schema], tool_choice=schema.__name__ if native_decision else "auto"
            ).ainvoke(messages)
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
        wire_submission = None
        if response is not None:
            stop = response.response_metadata.get("stop_reason") or response.response_metadata.get(
                "finish_reason"
            )
            if stop in {"max_tokens", "length"}:
                category = "MAX_TOKENS"
            calls = [c for c in response.tool_calls if c["name"] == schema.__name__]
            if len(calls) == 1 and len(response.tool_calls) == 1:
                wire_submission = calls[0]["args"]
                submission = (
                    {**last_submission, **wire_submission}
                    if use_patch
                    and isinstance(wire_submission, dict)
                    and isinstance(last_submission, dict)
                    else wire_submission
                )
        opinion: OpinionT | None = None
        if isinstance(submission, dict):
            # A malformed opinion must not hide a readable hard-fact conflict in fallback.
            try:
                if use_patch or native_decision or native_selection:
                    wire_schema.model_validate(wire_submission)
                if role == "judge":
                    warnings = submission.get("warnings", [])
                    if isinstance(warnings, list):
                        retained.extend(w for w in warnings if isinstance(w, str))
                    validate_review_facts(submission, packet.get("facts", {}))
                opinion = schema.model_validate(submission)
                if delta_repair and role == "pilot-diagnosis":
                    from .phase3_capacity import validate_compact_ranking_output

                    if packet.get("version") == VIEW_VERSION:
                        if packet.get("candidate_count") and not submission.get("candidate_order"):
                            raise AgentBoundaryError(
                                "The decision view requires candidate_order for all PASS IDs; "
                                "candidate_rankings is only for bounded detailed notes"
                            )
                        validate_compact_ranking_output(submission)
                if validate:
                    validate(opinion)
            except ValidationError as error:
                opinion = None
                if category != "MAX_TOKENS":
                    category = "SCHEMA_ERROR"
                diagnostic = error.errors(
                    include_input=False, include_url=False, include_context=False
                )
            except AgentBoundaryError as error:
                opinion = None
                category = (
                    "FACT_CONFLICT"
                    if isinstance(error, ReviewFactConflict)
                    else "MAX_TOKENS"
                    if category == "MAX_TOKENS"
                    else "SCHEMA_ERROR"
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
                "wire_submission": wire_submission if use_patch else None,
                "delta_repair": use_patch,
                "diagnostic": diagnostic,
                "retained_warnings": list(dict.fromkeys(retained)),
            },
        )
        if opinion is not None:
            return opinion
        last_submission = submission
        categories.append(category)
    if "FACT_CONFLICT" in categories:
        raise ReviewFactConflict(
            "Independent review has an unresolved structured fact conflict",
            retained_warnings=list(dict.fromkeys(retained)),
            attempts=len(categories),
        )
    raise StructuredOpinionUnavailable(categories, list(dict.fromkeys(retained)))
