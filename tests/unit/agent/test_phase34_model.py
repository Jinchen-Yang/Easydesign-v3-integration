import asyncio
import subprocess
import sys
from types import SimpleNamespace

import anthropic
import httpx
import openai
import pytest
from langchain_core.messages import AIMessage

from easydesign.agent.contracts import AgentBoundaryError
from easydesign.agent.phase34_model import (
    ReviewFactConflict,
    StructuredOpinionUnavailable,
    structured_opinion,
)
from easydesign.agent.phase34_opinions import DownstreamJudgeOpinion
from easydesign.agent.session_store import SessionStore
from tests.agent_support import scripted_config


class Responses:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.tool_choices = []

    def bind_tools(self, tools, **kwargs):
        assert tools == [DownstreamJudgeOpinion]
        self.tool_choices.append(kwargs.get("tool_choice"))
        return self

    async def ainvoke(self, messages):
        self.calls.append(messages)
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


def good(**changes):
    args = dict(
        review="NO_MATERIAL_ISSUE",
        brief_rationale="Extracellular accessibility remains uncertain.",
        uncertainties=["No experimental binding evidence."],
        fact_refs=["arm-1"],
    )
    args.update(changes)
    return AIMessage(
        content="", tool_calls=[dict(name="DownstreamJudgeOpinion", args=args, id="result")]
    )


@pytest.fixture
def runtime(tmp_path):
    store = SessionStore(tmp_path)
    store.thread("test", "config", "validation")
    execution = store.begin_execution("test", "validation")
    yield SimpleNamespace(store=store, thread="test", execution_id=execution["execution_id"])
    store.close()


async def call(runtime, model, *, packet=None):
    return await structured_opinion(
        bridge=runtime,
        model=model,
        config=scripted_config(),
        execution_id=runtime.execution_id,
        role="judge",
        schema=DownstreamJudgeOpinion,
        packet=packet if packet is not None else {"facts": {"arm-1": {"predicted": 2}}},
        prompt="Provide a compact independent critique.",
    )


@pytest.mark.asyncio
async def test_real_contract_submission_and_truncation_recovery(runtime):
    model = Responses(
        [AIMessage(content="unfinished", response_metadata={"stop_reason": "max_tokens"}), good()]
    )
    result = await call(runtime, model)
    assert result.brief_rationale.startswith("Extracellular")
    assert len(model.calls) == 2
    assert model.tool_choices == ["auto", "DownstreamJudgeOpinion"]
    assert "Return ONLY" in model.calls[1][-1].content
    assert await call(runtime, Responses([])) == result
    assert len([e for e in runtime.store.events(runtime.thread) if e["kind"] == "model-call"]) == 2


@pytest.mark.asyncio
async def test_truncated_empty_tool_submission_retains_token_exhaustion_cause(runtime):
    truncated = AIMessage(
        content="",
        response_metadata={"stop_reason": "max_tokens"},
        tool_calls=[dict(name="DownstreamJudgeOpinion", args={}, id="truncated")],
    )
    await call(runtime, Responses([truncated, good()]))
    attempts = [
        e["payload"]
        for e in runtime.store.events(runtime.thread)
        if e["kind"] == "phase34-model-attempt"
    ]
    assert [a["category"] for a in attempts] == ["MAX_TOKENS", "SUCCESS"]


@pytest.mark.asyncio
async def test_review_unavailability_is_bounded_and_durable(runtime):
    model = Responses([AIMessage(content="no structured output")] * 3)
    with pytest.raises(StructuredOpinionUnavailable) as error:
        await call(runtime, model)
    assert error.value.categories == ["NO_SUBMISSION"] * 3
    with pytest.raises(StructuredOpinionUnavailable):
        await call(runtime, Responses([]))
    assert len(model.calls) == 3


@pytest.mark.asyncio
async def test_malformed_negative_opinion_retained_for_unavailable_card(runtime):
    bad = good(warnings=["A material confounder remains."], uncertainties=[])
    model = Responses([bad, AIMessage(content="failed"), AIMessage(content="failed")])
    with pytest.raises(StructuredOpinionUnavailable) as error:
        await call(runtime, model)
    assert error.value.retained_warnings == ["A material confounder remains."]


@pytest.mark.asyncio
async def test_hard_fact_conflict_cannot_turn_into_unavailable_review(runtime):
    model = Responses(
        [
            good(fact_claims=[dict(fact_ref="arm-1", field="predicted", value=20)]),
            AIMessage(content="failed"),
            AIMessage(content="failed"),
        ]
    )
    with pytest.raises(ReviewFactConflict, match="unresolved structured fact conflict") as error:
        await call(runtime, model)
    assert error.value.categories == ["FACT_CONFLICT"]
    assert error.value.attempts == 3


@pytest.mark.asyncio
async def test_hard_fact_repair_can_return_a_valid_critique(runtime):
    model = Responses(
        [good(fact_claims=[dict(fact_ref="arm-1", field="predicted", value=20)]), good()]
    )
    result = await call(runtime, model)
    assert result.review == "NO_MATERIAL_ISSUE"
    assert len(model.calls) == 2


@pytest.mark.asyncio
async def test_shared_model_budget_not_reset_by_recovery(runtime):
    cfg = scripted_config().model_copy(update={"max_model_calls": 1})
    with pytest.raises(AgentBoundaryError, match="budget exhausted"):
        await structured_opinion(
            bridge=runtime,
            model=Responses([AIMessage(content="failed")]),
            config=cfg,
            execution_id=runtime.execution_id,
            role="judge",
            schema=DownstreamJudgeOpinion,
            packet={},
            prompt="Review.",
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", [openai, anthropic], ids=["openai", "anthropic"])
@pytest.mark.parametrize("failure", ["connection", "timeout", "server"])
async def test_unknown_provider_outcome_is_not_automatically_repeated(runtime, provider, failure):
    request = httpx.Request("POST", "https://fixture.invalid/messages")
    if failure == "server":
        error = provider.InternalServerError(
            "fixture failure", response=httpx.Response(503, request=request), body=None
        )
    elif failure == "timeout":
        error = provider.APITimeoutError(request=request)
    else:
        error = provider.APIConnectionError(request=request)
    model = Responses([error, good()])
    with pytest.raises(StructuredOpinionUnavailable) as caught:
        await call(runtime, model)
    assert caught.value.categories == ["PROVIDER_UNAVAILABLE"]
    assert len(model.calls) == 1
    # Reopening the real durable store must not spend the remaining repair budget.
    path = runtime.store.project_root
    runtime.store.close()
    runtime.store = SessionStore(path)
    replay = Responses([good()])
    with pytest.raises(StructuredOpinionUnavailable):
        await call(runtime, replay)
    assert replay.calls == []
    events = runtime.store.events(runtime.thread)
    assert len([event for event in events if event["kind"] == "model-call"]) == 1
    attempt = [event["payload"] for event in events if event["kind"] == "phase34-model-attempt"][-1]
    assert attempt["transport_status"] == "outcome_unknown"
    assert attempt["transport_terminal"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", [openai, anthropic], ids=["openai", "anthropic"])
async def test_explicit_rate_limit_waits_and_keeps_existing_call_limit(
    runtime, provider, monkeypatch
):
    waits = []

    async def sleep(seconds):
        waits.append(seconds)

    monkeypatch.setattr(asyncio, "sleep", sleep)
    request = httpx.Request("POST", "https://fixture.invalid/messages")
    error = provider.RateLimitError(
        "fixture limit",
        response=httpx.Response(429, request=request, headers={"Retry-After": "2"}),
        body=None,
    )
    model = Responses([error] * 3)
    with pytest.raises(StructuredOpinionUnavailable) as caught:
        await call(runtime, model)
    assert len(waits) == 2
    assert all(0 < seconds <= 2 for seconds in waits)
    assert len(model.calls) == 3
    assert caught.value.transport_status == "rate_limited"
    assert "rate_limited" in str(caught.value)
    events = runtime.store.events(runtime.thread)
    assert len([event for event in events if event["kind"] == "model-call"]) == 3
    attempts = [event["payload"] for event in events if event["kind"] == "phase34-model-attempt"]
    assert all(attempt["transport_status"] == "rate_limited" for attempt in attempts)
    assert all(attempt["transport_status"] != "outcome_unknown" for attempt in attempts)


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", [openai, anthropic], ids=["openai", "anthropic"])
@pytest.mark.parametrize(
    "header", [None, "", "0", "31", "999999", "NaN", "-1", "Wed, 21 Oct 2037 07:28:00 GMT"]
)
async def test_unsafe_rate_limit_delay_returns_explicit_terminal_limit(
    runtime, provider, header, monkeypatch
):
    async def sleep(seconds):
        pytest.fail("An unsupported Retry-After must not guess a delay")

    monkeypatch.setattr(asyncio, "sleep", sleep)
    request = httpx.Request("POST", "https://fixture.invalid/messages")
    error = provider.RateLimitError(
        "fixture limit",
        response=httpx.Response(
            429, request=request, headers={} if header is None else {"Retry-After": header}
        ),
        body=None,
    )
    model = Responses([error, good()])
    with pytest.raises(StructuredOpinionUnavailable) as caught:
        await call(runtime, model)
    assert len(model.calls) == 1
    assert caught.value.transport_status == "rate_limited"
    assert "rate_limited" in str(caught.value)
    before = runtime.store.events(runtime.thread)
    with pytest.raises(StructuredOpinionUnavailable):
        await call(runtime, model)
    assert len(model.calls) == 1
    assert runtime.store.events(runtime.thread) == before


@pytest.mark.asyncio
async def test_interrupted_rate_limit_wait_is_durable_and_does_not_rewrite_attempt(
    runtime, monkeypatch
):
    from easydesign.agent import phase34_model

    monkeypatch.setattr(phase34_model, "time", lambda: 1000.0)

    async def interrupted_sleep(seconds):
        assert seconds == 2.0
        raise asyncio.CancelledError

    monkeypatch.setattr(asyncio, "sleep", interrupted_sleep)
    request = httpx.Request("POST", "https://fixture.invalid/messages")
    error = openai.RateLimitError(
        "fixture limit",
        response=httpx.Response(429, request=request, headers={"Retry-After": "2"}),
        body=None,
    )
    model = Responses([error, good()])
    with pytest.raises(asyncio.CancelledError):
        await call(runtime, model)
    before = runtime.store.events(runtime.thread)
    assert len(model.calls) == 1
    path = runtime.store.project_root
    runtime.store.close()
    runtime.store = SessionStore(path)
    waits = []

    async def resumed_sleep(seconds):
        waits.append(seconds)

    monkeypatch.setattr(phase34_model, "time", lambda: 1001.0)
    monkeypatch.setattr(asyncio, "sleep", resumed_sleep)
    assert await call(runtime, model)
    assert waits == [1.0]
    assert len(model.calls) == 2
    assert runtime.store.events(runtime.thread)[: len(before)] == before


@pytest.mark.asyncio
@pytest.mark.parametrize("new_context", ["binding", "execution"])
async def test_transport_terminal_is_scoped_to_its_binding_and_execution(runtime, new_context):
    request = httpx.Request("POST", "https://fixture.invalid/messages")
    with pytest.raises(StructuredOpinionUnavailable):
        await call(runtime, Responses([openai.APIConnectionError(request=request)]))
    packet = None
    if new_context == "binding":
        packet = {"facts": {"arm-1": {"predicted": 2}}, "independent_intent": True}
    else:
        runtime.execution_id = runtime.store.begin_execution(runtime.thread, "new explicit turn")[
            "execution_id"
        ]
    model = Responses([good()])
    assert await call(runtime, model, packet=packet)
    assert len(model.calls) == 1


@pytest.mark.asyncio
async def test_unknown_transport_cannot_hide_previous_fact_conflict_or_warnings(runtime):
    request = httpx.Request("POST", "https://fixture.invalid/messages")
    model = Responses(
        [
            good(
                fact_claims=[dict(fact_ref="arm-1", field="predicted", value=20)],
                warnings=["Retain this scientific concern."],
            ),
            openai.APIConnectionError(request=request),
            good(),
        ]
    )
    with pytest.raises(ReviewFactConflict) as caught:
        await call(runtime, model)
    assert caught.value.attempts == 2
    assert caught.value.retained_warnings == ["Retain this scientific concern."]
    assert len(model.calls) == 2
    with pytest.raises(ReviewFactConflict):
        await call(runtime, model)
    assert len(model.calls) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("interruption", ["cancel", "process_exit"])
async def test_unclosed_provider_call_is_not_reissued_after_restart(runtime, interruption):
    if interruption == "cancel":
        model = Responses([asyncio.CancelledError()])
        with pytest.raises(asyncio.CancelledError):
            await call(runtime, model)
        assert len(model.calls) == 1
    else:
        child = subprocess.run(
            [
                sys.executable,
                "-c",
                "import asyncio, os, sys\n"
                "from pathlib import Path\n"
                "from types import SimpleNamespace\n"
                "from easydesign.agent.session_store import SessionStore\n"
                "from tests.unit.agent.test_phase34_model import Responses, call\n"
                "class InterruptedProvider(Responses):\n"
                "    async def ainvoke(self, messages):\n"
                "        os._exit(57)\n"
                "runtime = SimpleNamespace(store=SessionStore(Path(sys.argv[1])), "
                "thread='test', execution_id=sys.argv[2])\n"
                "asyncio.run(call(runtime, InterruptedProvider([])))\n",
                str(runtime.store.project_root),
                runtime.execution_id,
            ],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        assert child.returncode == 57, child.stderr
    before = runtime.store.events(runtime.thread)
    assert len([event for event in before if event["kind"] == "model-context"]) == 1
    assert not [event for event in before if event["kind"] == "phase34-model-attempt"]
    path = runtime.store.project_root
    runtime.store.close()
    runtime.store = SessionStore(path)
    replay = Responses([good()])
    with pytest.raises(StructuredOpinionUnavailable) as caught:
        await call(runtime, replay)
    assert caught.value.transport_status == "outcome_unknown"
    assert replay.calls == []
    after = runtime.store.events(runtime.thread)
    assert after[: len(before)] == before
    assert not [event for event in after if event["kind"] == "phase34-model-attempt"]
    assert len([event for event in after if event["kind"] == "model-call"]) == 1
    assert (
        len([event for event in after if event["kind"] == "phase34-model-transport-terminal"]) == 1
    )
    with pytest.raises(StructuredOpinionUnavailable):
        await call(runtime, replay)
    assert replay.calls == []
    assert runtime.store.events(runtime.thread) == after
