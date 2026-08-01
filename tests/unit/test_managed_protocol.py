from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from easydesign.core import ConfigurationError
from easydesign.managed_protocol import (
    ManagedJobRevision,
    ManagedWorkerProbe,
    RemoteJobBundle,
)
from easydesign.orchestration.remote_execution import (
    require_managed_probe_compatible,
)

FIXTURES = Path(__file__).parents[1] / "fixtures" / "managed_protocol"


@pytest.mark.parametrize(
    ("name", "model_type"),
    (
        ("bundle-v0.2.json", RemoteJobBundle),
        ("probe-v0.2.json", ManagedWorkerProbe),
        ("revision-v0.1.json", ManagedJobRevision),
    ),
)
def test_managed_protocol_golden_json(name: str, model_type: type) -> None:
    payload = json.loads((FIXTURES / name).read_text(encoding="utf-8"))

    restored = model_type.model_validate(payload)

    assert restored.model_dump(mode="json", exclude_none=False) == payload


def test_managed_bundle_rejects_single_stage_or_shell_field() -> None:
    payload = json.loads((FIXTURES / "bundle-v0.2.json").read_text(encoding="utf-8"))
    payload["stage_range"] = [4]
    with pytest.raises(ValidationError, match="04→05"):
        RemoteJobBundle.model_validate(payload)

    payload["stage_range"] = [4, 5]
    payload["command"] = "rm -rf /"
    with pytest.raises(ValidationError, match="Extra inputs"):
        RemoteJobBundle.model_validate(payload)


def test_managed_bundle_accepts_manifest_closed_empty_file() -> None:
    payload = json.loads((FIXTURES / "bundle-v0.2.json").read_text(encoding="utf-8"))

    bundle = RemoteJobBundle.model_validate(payload)

    empty = next(item for item in bundle.inputs if item.size_bytes == 0)
    assert empty.sha256 == (
        "e3b0c44298fc1c149afbf4c8996fb924"
        "27ae41e4649b934ca495991b7852b855"
    )


def test_managed_probe_ready_requires_both_chains_and_every_backend() -> None:
    payload = json.loads((FIXTURES / "probe-v0.2.json").read_text(encoding="utf-8"))
    assert ManagedWorkerProbe.model_validate(payload).ready is True

    payload["backends"][2]["ready"] = False
    assert ManagedWorkerProbe.model_validate(payload).ready is False

    payload["backends"][2]["ready"] = True
    payload["gpu_count"] = 7
    assert ManagedWorkerProbe.model_validate(payload).ready is False


def test_controller_fails_closed_for_version_or_capability_mismatch() -> None:
    payload = json.loads((FIXTURES / "probe-v0.2.json").read_text(encoding="utf-8"))
    require_managed_probe_compatible(ManagedWorkerProbe.model_validate(payload))

    payload["easydesign_version"] = "0.1.0.dev34"
    with pytest.raises(ConfigurationError, match="版本不一致"):
        require_managed_probe_compatible(ManagedWorkerProbe.model_validate(payload))

    payload["easydesign_version"] = "0.1.0.dev35"
    payload["supported_stage_ranges"] = [[4, 5]]
    with pytest.raises(ConfigurationError, match="missing_stage_ranges"):
        require_managed_probe_compatible(ManagedWorkerProbe.model_validate(payload))
