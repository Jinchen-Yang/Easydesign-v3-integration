from collections.abc import Iterator
from typing import Any

import pytest

pytest.importorskip("deepagents")

from tests.agent_support import make_project


@pytest.fixture
def bridge(tmp_path: Any, monkeypatch: Any) -> Iterator[Any]:
    value = make_project(tmp_path, monkeypatch)
    yield value
    value.store.close()


@pytest.fixture
def site_bridge(tmp_path: Any, monkeypatch: Any) -> Iterator[Any]:
    from easydesign.agent.phase2 import Phase2Bridge
    from tests.agent_support import terminal

    target = make_project(tmp_path, monkeypatch, chains="A")
    target.prepare_target()
    terminal(target)
    assert target.read_evidence()["status"] == "succeeded"
    value = Phase2Bridge(target.project, target.thread, target.store)
    yield value
    value.store.close()
