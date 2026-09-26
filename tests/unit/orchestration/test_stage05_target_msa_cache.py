from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from easydesign.orchestration.config import ResolvedProtenixMsaProviderConfig
from easydesign.orchestration.sequence_prediction import store_msa_cache
from easydesign.orchestration.stage05 import _prepare_target_msa


def test_stage05_reuses_verified_workspace_target_msa_without_remote_call(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    (tmp_path / "easydesign-workspace.yaml").write_text(
        "schema_version: '0.1'\nworkspace_id: test\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("EASYDESIGN_WORKSPACE", str(tmp_path))
    sequence = "ACDEFGHIKLMNPQRSTVWY"
    source = tmp_path / "seed.a3m"
    source.write_text(
        f">query\n{sequence}\n>homolog\n{sequence}\n",
        encoding="utf-8",
    )
    provider = ResolvedProtenixMsaProviderConfig(
        provider="colabfold-public",
        endpoint="https://api.colabfold.com",
        server_mode="colabfold",
        timeout_seconds=1800,
        max_attempts=1,
        retry_backoff_seconds=0,
    )
    store_msa_cache(
        sequence_sha256=hashlib.sha256(sequence.encode("ascii")).hexdigest(),
        sequence=sequence,
        provider=provider,
        source=source,
    )

    def no_remote_adapter(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("verified workspace cache must prevent a remote MSA call")

    destination, depth, selected = _prepare_target_msa(
        artifacts=tmp_path / "run/artifacts",
        work=tmp_path / "run/work",
        target_id="t",
        target_sequence=sequence,
        providers=(provider,),
        adapter_builder=no_remote_adapter,  # type: ignore[arg-type]
    )

    assert destination.read_text(encoding="utf-8") == source.read_text(encoding="utf-8")
    assert depth == 2
    assert selected == provider
    state = json.loads(
        (tmp_path / "run/work/target-msa/selected-provider.json").read_text(
            encoding="utf-8"
        )
    )
    assert state["a3m_sha256"]
    assert state["source_relative_path"].endswith("workspace-cache/target.a3m")
