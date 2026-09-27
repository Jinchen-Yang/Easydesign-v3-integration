"""Recovery-authority regressions for crash-window Gate 2 approval completion.

These pin the boundary between the durable site-approve re-drive witness and
genuine staleness: an in-flight intent alone must never authorize applying an
approval whose scientific context changed, and a missing native receipt must
keep failing loudly instead of being completed or retired.
"""

from typing import Any

import pytest

from easydesign.agent.cli import run_session
from easydesign.agent.contracts import AgentBoundaryError, ReconciliationRequired
from easydesign.agent.phase2_tools import PHASE2_ALLOWED
from easydesign.agent.session_store import SessionStore
from tests.agent_support import scripted_config
from tests.unit.agent.test_command_recovery import Crash, crash_at
from tests.unit.agent.test_site_harness import SiteModel


def _models() -> dict[str, Any]:
    return {role: SiteModel(role=role) for role in PHASE2_ALLOWED}


def _invalidate_site(bridge: Any, source_card: str) -> None:
    bridge.store.event(
        bridge.thread,
        "site-invalidated",
        {
            "source_card": source_card,
            "human_instruction": "Reassess the mapped site",
            "reason": "Reassess the mapped site",
            "reported_reason": "SYNTHETIC negative regression",
            "target_binding": bridge.target_state()["binding"],
        },
    )


def _site_approved_events(store: Any, thread: str) -> int:
    return len([e for e in store.events(thread) if e["kind"] == "site-approved"])


@pytest.mark.asyncio
async def test_stale_undelivered_response_without_application_still_raises(
    site_bridge: Any,
) -> None:
    bridge = site_bridge
    goal = "Review a mapped exploratory site."
    first = await run_session(bridge, scripted_config(), _models(), goal)
    card_id = first["card"]["card_id"]
    bridge.store.respond(bridge.thread, card_id, "approve", "synthetic-scientist")
    _invalidate_site(bridge, card_id)
    reopened = SessionStore(bridge.project)
    try:
        resumed = type(bridge)(bridge.project, bridge.thread, reopened)
        with pytest.raises(AgentBoundaryError, match="stale card cannot be approved"):
            await run_session(resumed, scripted_config(), _models(), goal)
        assert _site_approved_events(reopened, bridge.thread) == 0
        assert resumed.approved_site() is None
    finally:
        reopened.close()


@pytest.mark.asyncio
async def test_inflight_site_approval_does_not_authorize_invalidated_proposal(
    site_bridge: Any,
) -> None:
    bridge = site_bridge
    goal = "Review a mapped exploratory site."
    models = _models()
    first = await run_session(bridge, scripted_config(), models, goal)
    crash_at(bridge, "after_site_approval")
    with pytest.raises(Crash):
        await run_session(
            bridge,
            scripted_config(),
            models,
            goal,
            decision="approve",
            card_id=first["card"]["card_id"],
            user="synthetic-scientist",
        )
    _invalidate_site(bridge, first["card"]["card_id"])
    reopened = SessionStore(bridge.project)
    try:
        resumed = type(bridge)(bridge.project, bridge.thread, reopened)
        with pytest.raises(AgentBoundaryError, match="current Site proposal changed"):
            await run_session(resumed, scripted_config(), models, goal)
        assert _site_approved_events(reopened, bridge.thread) == 0
        assert resumed.approved_site() is None
        saved = reopened.response(bridge.thread, first["card"]["card_id"])
        assert saved is not None and saved["response"] == "approve"
    finally:
        reopened.close()


@pytest.mark.asyncio
async def test_resume_without_native_receipt_requires_loud_reconciliation(
    site_bridge: Any,
) -> None:
    bridge = site_bridge
    goal = "Review a mapped exploratory site."
    models = _models()
    first = await run_session(bridge, scripted_config(), models, goal)
    crash_at(bridge, "before_site_approval")
    with pytest.raises(Crash):
        await run_session(
            bridge,
            scripted_config(),
            models,
            goal,
            decision="approve",
            card_id=first["card"]["card_id"],
            user="synthetic-scientist",
        )
    reopened = SessionStore(bridge.project)
    try:
        resumed = type(bridge)(bridge.project, bridge.thread, reopened)
        with pytest.raises(ReconciliationRequired):
            await run_session(resumed, scripted_config(), models, goal)
        assert _site_approved_events(reopened, bridge.thread) == 0
        assert resumed.approved_site() is None
        saved = reopened.response(bridge.thread, first["card"]["card_id"])
        assert saved is not None and saved["response"] == "approve"
    finally:
        reopened.close()
