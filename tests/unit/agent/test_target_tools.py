from typing import Any

import pytest

from easydesign.agent.contracts import AgentBoundaryError
from easydesign.core import load_model
from easydesign.orchestration.decisions import load_pending_decision
from easydesign.stages.s01_target_preparation.models import TargetBundle
from tests.agent_support import judge_card, terminal


def test_real_gate_then_old_bundle_and_mapping(bridge: Any) -> None:
    bridge.prepare_target()
    terminal(bridge)
    initial = bridge.read_evidence()
    assert initial["status"] == "awaiting-human-approval"
    assert [c["auth_chain"] for c in initial["chains"]] == ["A", "B"]
    assert "bundle" not in initial
    card = judge_card(bridge)
    bridge.store.respond(bridge.thread, card.card_id, "approve", "test-human")
    bridge.apply_decision(card)
    transition = bridge.read_evidence()
    assert transition["status"] == "running"
    assert transition["request_identity"] is None
    assert transition["decision_transition"] == "recorded-awaiting-resume"
    terminal(bridge)
    result = bridge.read_evidence()
    assert result["run_id"] == initial["run_id"]
    assert result["bundle"]["producer_attempt"] == "attempt-0002"
    assert result["identity"]["auth_chain"] == "A"
    assert result["mapping"]["entries"] == 6
    assert result["viewer"]["status"] == "verified", result["viewer"]
    root, _ = bridge.run()
    ref = next(r for r in result["evidence_refs"] if "target-bundle.json#" in r)
    bundle = load_model(root / ref.split("#")[0], TargetBundle)
    assert result["bundle"]["sequence_sha256"] == bundle.sequence_sha256
    assert result["mapping"]["sha256"] == bundle.residue_mapping.sha256
    assert not (root / "02-hotspot-discovery").exists()


def test_tampered_frozen_evidence_is_rejected(bridge: Any) -> None:
    bridge.prepare_target()
    terminal(bridge)
    root, _ = bridge.run()
    from easydesign.orchestration.workspace import load_resolved_run_config

    resolved, _ = load_resolved_run_config(root)
    path = resolved.input_snapshot.verify(root)
    path.write_bytes(path.read_bytes() + b"REMARK tampered fixture\n")
    with pytest.raises(Exception, match="SHA|大小|Artifact"):
        bridge.read_evidence()


def test_reject_does_not_write_scientific_record(bridge: Any) -> None:
    bridge.prepare_target()
    terminal(bridge)
    card = judge_card(bridge)
    with pytest.raises(AgentBoundaryError, match="human"):
        bridge.apply_decision(card)
    bridge.store.respond(bridge.thread, card.card_id, "reject", "test-human")
    assert bridge.apply_decision(card)["status"] == "rejected"
    root, _ = bridge.run()
    request, path = load_pending_decision(root)
    assert not (path.parent / f"record.v{request.revision:04d}.json").exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["target", "coordinator"])
async def test_unprepared_inspection_is_read_only(bridge: Any, role: str) -> None:
    import json

    from easydesign.agent.tools import build_tools

    tool = next(t for t in build_tools(bridge, role) if t.name == "read_target_evidence")
    result = json.loads(await tool.ainvoke({}))
    assert result["status"] == "not-prepared"
    assert result["evidence_refs"] == []
    assert len(result["source_input"]["sha256"]) == 64
    assert result["source_input"]["deposited_entities"]["status"] in {
        "reported",
        "not-reported-in-input",
    }
    assert "official source" in result["next_action"]
    assert "evidence_id" not in result and "bundle" not in result
    assert not bridge._jobs()
    assert bridge.store.db.execute("SELECT count(*) FROM commands").fetchone()[0] == 0
    invalid = json.loads(await tool.ainvoke({"run_id": bridge.project_id}))
    assert invalid == {
        "allowed_run_id": None,
        "next_action": (
            "Call read_target_evidence without run_id to use the sole current project-bound "
            "Target run. Do not use a project ID as a run ID."
        ),
        "provided_run_id": bridge.project_id,
        "status": "invalid-run-id",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["target", "coordinator"])
async def test_project_id_run_argument_is_repaired_without_weakening_binding(
    bridge: Any, role: str
) -> None:
    import json

    from easydesign.agent.tools import build_tools

    bridge.prepare_target()
    terminal(bridge)
    current = bridge.read_evidence()["run_id"]
    tool = next(t for t in build_tools(bridge, role) if t.name == "read_target_evidence")
    repaired = json.loads(await tool.ainvoke({"run_id": bridge.project_id}))
    assert repaired["run_id"] == current
    assert repaired["argument_repair"] == {
        "kind": "project-id-used-as-run-id",
        "provided_run_id": bridge.project_id,
        "resolved_run_id": current,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["target", "coordinator"])
async def test_active_target_job_returns_retryable_evidence_state(
    bridge: Any, role: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json

    from easydesign.agent.tools import build_tools

    bridge.prepare_target()
    terminal(bridge)
    monkeypatch.setattr(
        bridge,
        "get_job_status",
        lambda: {"status": "running", "job_id": "job-active", "phase": "prepare"},
    )
    monkeypatch.setattr(
        bridge,
        "read_evidence",
        lambda *_args, **_kwargs: pytest.fail("active evidence must not be read"),
    )
    tool = next(t for t in build_tools(bridge, role) if t.name == "read_target_evidence")
    result = json.loads(await tool.ainvoke({}))
    assert result["status"] == "job-active"
    assert result["job_id"] == "job-active"
    assert "get_job_status" in result["next_action"]


@pytest.mark.asyncio
async def test_judge_project_id_run_argument_repairs_to_delegated_evidence(bridge: Any) -> None:
    import json

    from easydesign.agent.contracts import EvidenceBinding
    from easydesign.agent.tools import JUDGE_EVIDENCE, build_tools

    bridge.prepare_target()
    terminal(bridge)
    current = bridge.read_evidence()
    delegated = EvidenceBinding.model_validate(
        {name: current[name] for name in EvidenceBinding.model_fields}
    )
    token = JUDGE_EVIDENCE.set(delegated)
    try:
        tool = next(t for t in build_tools(bridge, "judge") if t.name == "read_target_evidence")
        repaired = json.loads(await tool.ainvoke({"run_id": bridge.project_id}))
    finally:
        JUDGE_EVIDENCE.reset(token)
    assert repaired["run_id"] == current["run_id"]
    assert repaired["argument_repair"]["kind"] == "project-id-used-as-run-id"
    assert repaired["argument_repair"]["resolved_run_id"] == current["run_id"]
