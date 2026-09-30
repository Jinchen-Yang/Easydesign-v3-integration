"""Release-only compatibility witnesses never rewrite scientific authority."""

import pytest

from easydesign.agent.contracts import AgentBoundaryError
from easydesign.agent.session_store import SessionStore


def test_explicit_release_upgrade_preserves_original_thread_and_rejects_other_models(tmp_path):
    store = SessionStore(tmp_path)
    try:
        old, new = "a" * 64, "b" * 64
        store.thread("thread", old, "Immutable scientific goal")
        original = tuple(store.db.execute("SELECT * FROM threads").fetchone())
        with pytest.raises(AgentBoundaryError, match="Incompatible"):
            store.thread("thread", new)
        assert store.approve_harness_upgrade("thread", previous=old, target=new, release="c" * 40)
        assert store.thread("thread", new) == "Immutable scientific goal"
        assert store.thread("thread", old) == "Immutable scientific goal"
        assert not store.approve_harness_upgrade(
            "thread", previous=old, target=new, release="c" * 40
        )
        assert tuple(store.db.execute("SELECT * FROM threads").fetchone()) == original
        with pytest.raises(AgentBoundaryError, match="Incompatible"):
            store.thread("thread", "d" * 64)
        with pytest.raises(AgentBoundaryError, match="Incompatible"):
            store.approve_harness_upgrade(
                "thread", previous="d" * 64, target="e" * 64, release="c" * 40
            )
        with pytest.raises(AgentBoundaryError, match="immutable"):
            store.thread("thread", new, "Different goal")
        events = store.events("thread")
        assert [e["kind"] for e in events] == ["user", "harness-upgrade-approved"]
    finally:
        store.close()
