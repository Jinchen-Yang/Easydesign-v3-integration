from typing import Any

import pytest
from langchain_core.messages import AIMessage, ToolMessage

from easydesign.agent.cli import run_session
from easydesign.agent.session_store import SessionStore
from easydesign.agent.tools import TargetBridge
from tests.agent_support import ScriptedModel, judge_card, scripted_config


class ChatConfirmationModel(ScriptedModel):
    def answer(self, messages: Any) -> AIMessage:
        if self.role == "coordinator" and any(isinstance(m, ToolMessage) for m in messages):
            return AIMessage(content="Please confirm chain A. I am waiting for approval. Finished.")
        return super().answer(messages)


@pytest.mark.asyncio
async def test_prose_confirmation_cannot_finish_an_authoritative_gate(
    bridge: Any, monkeypatch: Any
) -> None:
    models = {r: ChatConfirmationModel(role=r) for r in ("coordinator", "target", "judge")}
    goal = "Prepare local chain A with a formal scientific decision."
    result = await run_session(bridge, scripted_config(), models, goal)
    assert result["status"] == "incomplete-turn"
    assert result["scientific_state"] == "awaiting-human-approval"
    assert "Finished" not in result["message"]
    assert bridge.store.db.execute("SELECT count(*) FROM cards").fetchone()[0] == 0
    assert bridge.read_evidence()["request_identity"] is not None
    before = [e for e in bridge.store.events(bridge.thread) if e["kind"] == "model-call"]
    reopened = SessionStore(bridge.project)
    try:
        resumed = TargetBridge(bridge.project, bridge.thread, reopened)
        # A stale/misleading thread-bound receipt cannot overrule the real scientific manifest.
        monkeypatch.setattr(resumed, "get_job_status", lambda: {"status": "succeeded"})
        again = await run_session(resumed, scripted_config(), models, goal)
        assert again["status"] == "incomplete-turn"
        assert again["scientific_state"] == "awaiting-human-approval"
        assert [e for e in reopened.events(bridge.thread) if e["kind"] == "model-call"] == before
        card = judge_card(resumed)
        assert resumed.terminal_result("User approved in chat")["status"] == "incomplete-turn"
        reopened.respond(bridge.thread, card.card_id, "approve", "synthetic-human")
        # A durable human intent alone has not applied/resolved the scientific gate.
        assert resumed.terminal_result("We have approval now")["status"] == "incomplete-turn"
        assert len(resumed._jobs()) == 1
    finally:
        reopened.close()
