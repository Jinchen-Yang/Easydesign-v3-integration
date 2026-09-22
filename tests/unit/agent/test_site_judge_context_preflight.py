"""Site Judge capacity preflight is narrow, verified and provider-free."""

from copy import deepcopy
from typing import Any

import pytest
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.utils.function_calling import convert_to_openai_tool

from easydesign.agent.context_policy import ModelContextCapacityError, context_usage
from easydesign.agent.contracts import (
    AgentBoundaryError,
    ApplyDecision,
    EvidenceBinding,
    JudgeVerdict,
)
from easydesign.agent.session_store import compact
from easydesign.agent.site_fact_integrity import fact_revision
from easydesign.agent.site_judge import (
    SiteJudgeVerdict,
    create_site_aware_judge,
    review_input,
    review_prompt,
)
from easydesign.agent.site_review_availability import evidence_binding, matching_failure
from easydesign.agent.tools import JUDGE_EVIDENCE
from tests.agent_support import scripted_config
from tests.unit.agent.test_judge_packet import packet_case as base_packet_case
from tests.unit.agent.test_site_judge import CompactJudgeModel


@pytest.fixture
def packet_case(site_bridge):
    return base_packet_case.__wrapped__(site_bridge)


def _request_usage(model: Any, packet: dict[str, Any]) -> dict[str, Any]:
    schema_chars = len(compact([convert_to_openai_tool(SiteJudgeVerdict)]))
    return context_usage(
        model,
        scripted_config(),
        "judge",
        [
            SystemMessage(content=review_prompt()),
            HumanMessage(content=compact(review_input(packet))),
        ],
        schema_chars,
        enforce=False,
    )


def _packet_with_exact_request_chars(bridge: Any, model: Any, target_chars: int) -> dict[str, Any]:
    packet = deepcopy(bridge.judge_evidence())
    requirements = packet.setdefault("objective_requirements", {})
    requirements["context_capacity_test_padding"] = ""
    for _ in range(3):
        current = _request_usage(model, packet)["input_chars_with_schemas"]
        delta = target_chars - current
        if delta == 0:
            break
        padding = requirements["context_capacity_test_padding"]
        if delta > 0:
            requirements["context_capacity_test_padding"] = padding + "X" * delta
        else:
            requirements["context_capacity_test_padding"] = padding[:delta]
    packet["fact_revision"] = fact_revision(packet)
    assert _request_usage(model, packet)["input_chars_with_schemas"] == target_chars
    return packet


async def _invoke_site(
    bridge: Any,
    packet: dict[str, Any],
    model: Any,
    monkeypatch: Any,
) -> dict[str, Any]:
    execution = bridge.store.latest_execution(bridge.thread)["execution_id"]
    monkeypatch.setattr(bridge, "judge_evidence", lambda: packet)

    async def never_legacy(state: Any) -> Any:
        raise AssertionError("Dossier-backed Site must not use the legacy Judge")

    token = JUDGE_EVIDENCE.set(
        EvidenceBinding.model_validate({key: packet[key] for key in EvidenceBinding.model_fields})
    )
    try:
        return await create_site_aware_judge(
            bridge, model, scripted_config(), execution, never_legacy
        ).ainvoke({"messages": [HumanMessage(content="Review.")]})
    finally:
        JUDGE_EVIDENCE.reset(token)


def _judge_attempt_events(bridge: Any) -> list[dict[str, Any]]:
    execution = bridge.store.latest_execution(bridge.thread)["execution_id"]
    return [
        event
        for event in bridge.store.events(bridge.thread)
        if event["payload"].get("role") == "judge"
        and event["payload"].get("execution_id") == execution
        and event["kind"]
        in {
            "model-call",
            "model-context",
            "model-response",
            "contract-repair",
            "rejected-submission",
        }
    ]


@pytest.mark.asyncio
async def test_egfr_sized_100068_request_uses_full_judge_packet(packet_case, monkeypatch):
    bridge = packet_case["bridge"]
    model = CompactJudgeModel(role="judge")
    packet = _packet_with_exact_request_chars(bridge, model, 100_068)
    await _invoke_site(bridge, packet, model, monkeypatch)
    events = bridge.store.events(bridge.thread)
    contexts = [
        event["payload"]
        for event in events
        if event["kind"] == "model-context" and event["payload"].get("role") == "judge"
    ]
    assert len(contexts) == 1
    assert contexts[0]["input_chars_with_schemas"] == 100_068
    assert contexts[0]["hard_limit_chars"] == 250_000
    assert model.calls == 1
    assert any(event["kind"] == "judge-assessment" for event in events)
    assert not any(event["kind"] == "site-judge-context-preflight-failed" for event in events)
    assert matching_failure(bridge, packet) is None


@pytest.mark.asyncio
async def test_char_capacity_preflight_yields_gate_without_model_or_repairs(
    packet_case, monkeypatch
):
    bridge = packet_case["bridge"]
    model = CompactJudgeModel(role="judge")
    packet = _packet_with_exact_request_chars(bridge, model, 250_001)
    result = await _invoke_site(bridge, packet, model, monkeypatch)
    failure = matching_failure(bridge, packet)
    assert failure is not None and failure["failure_mode"] == "context-capacity-preflight"
    assert result["structured_response"] is None
    assert model.calls == 0
    assert _judge_attempt_events(bridge) == []
    events = bridge.store.events(bridge.thread)
    assert not any(event["kind"] == "judge-assessment" for event in events)
    assert sum(event["kind"] == "site-judge-context-preflight-failed" for event in events) == 1
    card = bridge.decision_card(
        ApplyDecision(review_failure_id=failure["record_id"], option_id="site")
    )
    assert card.assessment_id is None and card.judge_status is None


@pytest.mark.asyncio
async def test_model_token_capacity_preflight_is_provider_free(packet_case, monkeypatch):
    bridge = packet_case["bridge"]
    config = scripted_config()
    model = CompactJudgeModel(
        role="judge",
        profile={"max_input_tokens": config.for_role("judge").max_output_tokens + 1},
    )
    packet = bridge.judge_evidence()
    assert _request_usage(model, packet)["input_chars_with_schemas"] < config.hard_input_chars
    await _invoke_site(bridge, packet, model, monkeypatch)
    failure = matching_failure(bridge, packet)
    assert failure is not None and failure["failure_mode"] == "context-capacity-preflight"
    assert model.calls == 0
    assert _judge_attempt_events(bridge) == []
    preflight = next(
        event["payload"]
        for event in bridge.store.events(bridge.thread)
        if event["kind"] == "site-judge-context-preflight-failed"
    )
    usage = preflight["usage"]
    assert usage["input_chars_with_schemas"] < usage["hard_limit_chars"]
    assert usage["estimated_input_tokens"] > usage["model_profile_token_guard"]


@pytest.mark.asyncio
async def test_ordinary_boundary_error_is_not_reclassified(packet_case, monkeypatch):
    import easydesign.agent.site_judge as site_judge

    bridge = packet_case["bridge"]
    packet = bridge.judge_evidence()

    def ordinary_error(*args: Any, **kwargs: Any) -> Any:
        raise AgentBoundaryError("SYNTHETIC ordinary boundary failure")

    monkeypatch.setattr(site_judge, "context_usage", ordinary_error)
    with pytest.raises(AgentBoundaryError, match="ordinary boundary failure"):
        await _invoke_site(bridge, packet, CompactJudgeModel(role="judge"), monkeypatch)
    assert matching_failure(bridge, packet) is None


@pytest.mark.asyncio
async def test_recovery_capacity_error_remains_hard(packet_case, monkeypatch):
    bridge = packet_case["bridge"]
    packet = bridge.judge_evidence()
    execution = bridge.store.latest_execution(bridge.thread)["execution_id"]
    bridge.store.event(
        bridge.thread,
        "rejected-submission",
        {
            "role": "judge",
            "execution_id": execution,
            "binding": evidence_binding(packet),
            "diagnostic": "MISSING_OR_INVALID_TYPED_SUBMISSION",
            "schema_diagnostic": None,
            "submitted_opinion": None,
            "schema_valid": False,
            "substantive_finding": False,
        },
    )
    config = scripted_config()
    model = CompactJudgeModel(
        role="judge",
        profile={"max_input_tokens": config.for_role("judge").max_output_tokens + 1},
    )
    with pytest.raises(ModelContextCapacityError, match="hard context guard"):
        await _invoke_site(bridge, packet, model, monkeypatch)
    assert model.calls == 0
    assert matching_failure(bridge, packet) is None
    assert not any(
        event["kind"] == "site-judge-context-preflight-failed"
        for event in bridge.store.events(bridge.thread)
    )


@pytest.mark.asyncio
async def test_hard_packet_rebuild_error_is_not_reclassified(packet_case, monkeypatch):
    bridge = packet_case["bridge"]
    packet = bridge.judge_evidence()
    execution = bridge.store.latest_execution(bridge.thread)["execution_id"]

    async def never_legacy(state: Any) -> Any:
        raise AssertionError("Legacy route must not run")

    def hard_failure() -> Any:
        raise AgentBoundaryError("HARD_FACT_CONTRADICTION synthetic source binding")

    monkeypatch.setattr(bridge, "judge_evidence", hard_failure)
    with pytest.raises(AgentBoundaryError, match="HARD_FACT_CONTRADICTION"):
        await create_site_aware_judge(
            bridge,
            CompactJudgeModel(role="judge"),
            scripted_config(),
            execution,
            never_legacy,
        ).ainvoke({"messages": [HumanMessage(content="Review.")]})
    assert not any(
        event["kind"] == "site-judge-unavailable" for event in bridge.store.events(bridge.thread)
    )
    assert packet["gate_type"] == "site-hotspot"


@pytest.mark.asyncio
async def test_binding_mismatch_is_not_reclassified(packet_case, monkeypatch):
    bridge = packet_case["bridge"]
    packet = bridge.judge_evidence()
    execution = bridge.store.latest_execution(bridge.thread)["execution_id"]

    async def never_legacy(state: Any) -> Any:
        raise AssertionError("Legacy route must not run")

    token = JUDGE_EVIDENCE.set(None)
    try:
        with pytest.raises(AgentBoundaryError, match="current delegated binding"):
            await create_site_aware_judge(
                bridge,
                CompactJudgeModel(role="judge"),
                scripted_config(),
                execution,
                never_legacy,
            ).ainvoke({"messages": [HumanMessage(content="Review.")]})
    finally:
        JUDGE_EVIDENCE.reset(token)
    assert matching_failure(bridge, packet) is None


@pytest.mark.asyncio
async def test_fact_error_remains_substantive_and_cannot_degrade(packet_case, monkeypatch):
    bridge = packet_case["bridge"]
    packet = bridge.judge_evidence()
    model = CompactJudgeModel(role="judge", invalid_fact=True)
    with pytest.raises(AgentBoundaryError, match="unresolved substantive findings"):
        await _invoke_site(bridge, packet, model, monkeypatch)
    assert model.calls == 3
    assert matching_failure(bridge, packet) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("prior_state", ["substantive", "assessment"])
async def test_prior_scientific_outcome_forbids_preflight_degradation(
    packet_case, monkeypatch, prior_state
):
    bridge = packet_case["bridge"]
    model = CompactJudgeModel(role="judge")
    packet = _packet_with_exact_request_chars(bridge, model, 250_001)
    execution = bridge.store.latest_execution(bridge.thread)["execution_id"]
    if prior_state == "substantive":
        bridge.store.event(
            bridge.thread,
            "rejected-submission",
            {
                "role": "judge",
                "execution_id": execution,
                "binding": evidence_binding(packet),
                "diagnostic": "JUDGE_FACT_CONFLICT synthetic",
                "schema_diagnostic": None,
                "submitted_opinion": None,
                "schema_valid": False,
                "substantive_finding": True,
            },
        )
    else:
        monkeypatch.setattr(bridge, "judge_evidence", lambda: packet)
        token = JUDGE_EVIDENCE.set(
            EvidenceBinding.model_validate(
                {key: packet[key] for key in EvidenceBinding.model_fields}
            )
        )
        try:
            bridge.register_judge(
                JudgeVerdict(
                    verdict="ready-to-ask",
                    reasons=["SYNTHETIC review already completed."],
                    limitations=["SYNTHETIC downstream validation remains."],
                )
            )
        finally:
            JUDGE_EVIDENCE.reset(token)
    with pytest.raises(AgentBoundaryError):
        await _invoke_site(bridge, packet, model, monkeypatch)
    assert matching_failure(bridge, packet) is None
    assert model.calls == 0
