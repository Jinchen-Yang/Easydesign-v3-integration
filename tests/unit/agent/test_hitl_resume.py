from typing import Any

import pytest

from easydesign.agent.cli import run_session
from easydesign.agent.contracts import AgentBoundaryError
from easydesign.agent.session_store import SessionStore
from easydesign.agent.tools import TargetBridge
from tests.agent_support import scripted_config, scripted_models


@pytest.mark.asyncio
@pytest.mark.parametrize("decision", ["approve", "reject"])
async def test_real_saver_reopens_same_thread_and_gate(bridge: Any, decision: str) -> None:
    config, models = scripted_config(), scripted_models()
    pending = await run_session(bridge, config, models, "Prepare local input; I want chain A.")
    assert pending["status"] == "awaiting-human-approval", pending
    root, _ = bridge.run()
    assert not list(root.glob("decisions/*/record.*.json"))
    reopened = SessionStore(bridge.project)
    resumed_bridge = TargetBridge(bridge.project, bridge.thread, reopened)
    try:
        unchanged = await run_session(
            resumed_bridge, config, scripted_models(), "Prepare local input; I want chain A."
        )
        assert unchanged["card"] == pending["card"]
        result = await run_session(
            resumed_bridge,
            config,
            scripted_models(),
            "Prepare local input; I want chain A.",
            decision=decision,
            card_id=pending["card"]["card_id"],
            user="real-test-user",
        )
        assert result["status"] == ("finished" if decision == "approve" else "rejected"), result
        assert len(resumed_bridge._jobs()) == (2 if decision == "approve" else 1)
        duplicate = await run_session(
            resumed_bridge,
            config,
            scripted_models(),
            "Prepare local input; I want chain A.",
            decision=decision,
            card_id=pending["card"]["card_id"],
            user="real-test-user",
        )
        assert duplicate["status"] == "already-delivered"
        with pytest.raises(AgentBoundaryError):
            await run_session(
                resumed_bridge,
                config,
                scripted_models(),
                "Prepare local input; I want chain A.",
                decision=decision,
                card_id="wrong",
                user="real-test-user",
            )
    finally:
        reopened.close()


@pytest.mark.asyncio
async def test_resume_recovers_persisted_response_intent(bridge: Any) -> None:
    from tests.unit.agent.test_command_recovery import Crash, crash_at

    pending = await run_session(bridge, scripted_config(), scripted_models(), "Prepare chain A")
    crash_at(bridge, "after_response_intent")
    with pytest.raises(Crash):
        await run_session(
            bridge,
            scripted_config(),
            scripted_models(),
            "Prepare chain A",
            decision="approve",
            card_id=pending["card"]["card_id"],
            user="test-human",
        )
    bridge.failpoint = lambda _: None
    done = await run_session(bridge, scripted_config(), scripted_models(), "Prepare chain A")
    assert done["status"] == "finished"
    assert len(bridge._jobs()) == 2
