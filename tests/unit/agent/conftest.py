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


@pytest.fixture
def design_bridge(site_bridge: Any, monkeypatch: Any, tmp_path: Any) -> Any:
    from easydesign.agent.design import DesignBridge
    from tests.agent_phase2_support import configure_offline_validation
    from tests.unit.agent.test_site_runtime import propose, reviewed_card

    propose(site_bridge)
    card = reviewed_card(site_bridge)
    site_bridge.store.respond(site_bridge.thread, card.card_id, "approve", "synthetic-scientist")
    site_bridge.apply_decision(card)
    configure_offline_validation(monkeypatch, tmp_path)
    return DesignBridge(site_bridge.project, "design-thread", site_bridge.store)
