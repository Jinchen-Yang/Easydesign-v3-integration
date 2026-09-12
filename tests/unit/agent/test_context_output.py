import json
from typing import Any

import pytest

from easydesign.agent.contracts import AgentBoundaryError
from easydesign.agent.harness import fingerprint, skill_root
from tests.agent_support import scripted_config


def test_large_summary_offloads_without_structure_copy(bridge: Any) -> None:
    value = {"limitations": ["x" * 9000], "evidence_refs": ["existing/target.json#sha256=abc"]}
    output = bridge.store.offload(bridge.thread, value)
    assert len(output.encode()) < 8192
    ref = json.loads(output)["ref"]
    path = bridge.store.root / "agent-work" / bridge.thread / ref[1:]
    assert json.loads(path.read_text()) == value
    with pytest.raises(AgentBoundaryError, match="large"):
        bridge.store.offload(bridge.thread, {"data": "x" * 260000})


def test_config_and_budget_survive_reopen(bridge: Any) -> None:
    from easydesign.agent.session_store import SessionStore

    bridge.store.thread(bridge.thread, fingerprint(scripted_config()), "Prepare chain A")
    execution = bridge.store.begin_execution(bridge.thread, "Prepare chain A")
    bridge.store.reserve_model_call(bridge.thread, "target", 1, execution["execution_id"])
    second = SessionStore(bridge.project)
    try:
        assert second.thread(bridge.thread, fingerprint(scripted_config())) == "Prepare chain A"
        with pytest.raises(AgentBoundaryError, match="budget"):
            second.reserve_model_call(bridge.thread, "judge", 1, execution["execution_id"])
        next_execution = second.begin_execution(bridge.thread, "Explain the remaining limits")
        second.reserve_model_call(bridge.thread, "judge", 1, next_execution["execution_id"])
        assert [
            e["payload"]["lifetime_call"]
            for e in second.events(bridge.thread)
            if e["kind"] == "model-call"
        ] == [1, 2]
        with pytest.raises(AgentBoundaryError, match="Incompatible"):
            second.thread(bridge.thread, "changed-model")
    finally:
        second.close()
    assert (skill_root() / "target-intelligence/SKILL.md").is_file()
    assert (skill_root() / "evidence-judge/SKILL.md").is_file()


def test_reasoning_view_preserves_evidence_and_user_turns_without_mutating_checkpoint() -> None:
    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

    from easydesign.agent.evidence_output import reasoning_working_view

    user = HumanMessage(content="Find a falsifiable binding hypothesis; no approval.")
    assistant = AIMessage(
        content=[
            {
                "type": "thinking",
                "thinking": "private deliberation " * 1000,
                "signature": "original-signed-block",
            }
        ],
        tool_calls=[
            {
                "id": "read-1",
                "name": "retrieve_evidence",
                "args": {"need": "KNOWN_EPITOPE", "question": "scoped source"},
                "type": "tool_call",
            }
        ],
    )
    evidence = {
        "passage": "Exact source quote with counterevidence.",
        "source_id": "test-source",
        "mapping": [{"label": 9, "canonical": None, "status": "ambiguous"}],
        "limitations": ["unknown efficacy", "state mismatch"],
        "full_result": "/result-aabb.json",
    }
    result = ToolMessage(
        name="retrieve_evidence", tool_call_id="read-1", content=json.dumps(evidence)
    )
    second_user = HumanMessage(content="Retain the state mismatch.")
    messages = [user, assistant, result, second_user]
    original = [m.model_dump() for m in messages]
    view = reasoning_working_view(messages)
    assert [m.model_dump() for m in messages] == original
    assert view[0] is user and view[-1] is second_user
    assert "private deliberation" not in str(view) and "original-signed-block" not in str(view)
    record = json.loads(view[1].content)["runtime_history"]
    assert record[0]["requested_tools"] == assistant.tool_calls
    assert record[1]["content"] == evidence
    assert record[1]["status"] == "success"
    assert len(str(view)) < len(str(messages)) / 4
    assert reasoning_working_view([user, assistant]) == [user, assistant]
    assert reasoning_working_view([user, result]) == [user, result]
