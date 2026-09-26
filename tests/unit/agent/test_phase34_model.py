from types import SimpleNamespace

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
        return self.responses.pop(0)


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


async def call(runtime, model):
    return await structured_opinion(
        bridge=runtime,
        model=model,
        config=scripted_config(),
        execution_id=runtime.execution_id,
        role="judge",
        schema=DownstreamJudgeOpinion,
        packet={"facts": {"arm-1": {"predicted": 2}}},
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
