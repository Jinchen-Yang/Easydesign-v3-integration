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
