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
