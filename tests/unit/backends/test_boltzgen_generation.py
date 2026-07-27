from __future__ import annotations

import subprocess
import time
from pathlib import Path

from pytest import MonkeyPatch

from easydesign.backends.boltzgen import (
    BoltzGenCheckAdapter,
    BoltzGenGenerationAdapter,
    BoltzGenGenerationRequest,
)


def test_generation_command_freezes_full_nanobody_pipeline_parameters(
    tmp_path: Path,
) -> None:
    adapter = BoltzGenGenerationAdapter(
        check_adapter=BoltzGenCheckAdapter(
            executable=Path("/runtime/boltzgen"),
            repository_root=Path("/runtime/repository"),
            cache_root=Path("/runtime/cache"),
        ),
        data_loader_workers=3,
    )
    request = BoltzGenGenerationRequest(
        design_specification=tmp_path / "design.yaml",
        output_directory=tmp_path / "output",
        requested_candidates=17,
        physical_device=1,
        stdout_path=tmp_path / "stdout.log",
        stderr_path=tmp_path / "stderr.log",
    )

    command = adapter.build_command(request)

    assert command[:3] == (
        "/runtime/boltzgen",
        "run",
        str(request.design_specification),
    )
    assert "--steps" not in command
    assert command[command.index("--protocol") + 1] == "nanobody-anything"
    assert command[command.index("--num_designs") + 1] == "17"
    assert command[command.index("--inverse_fold_num_sequences") + 1] == "1"
    assert command[command.index("--budget") + 1] == "30"
    assert command[command.index("--alpha") + 1] == "0.001"
    assert command[command.index("--filter_biased") + 1] == "true"
    assert command[command.index("--devices") + 1] == "1"
    assert "CUDA_VISIBLE_DEVICES" not in command


def test_generation_emits_process_heartbeats_without_counting_candidates(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    adapter = BoltzGenGenerationAdapter(
        check_adapter=BoltzGenCheckAdapter(
            executable=Path("/runtime/boltzgen"),
            repository_root=Path("/runtime/repository"),
            cache_root=Path("/runtime/cache"),
        ),
        heartbeat_interval_seconds=0.005,
    )
    design = tmp_path / "design.yaml"
    design.write_text("entities: []\n", encoding="utf-8")
    request = BoltzGenGenerationRequest(
        design_specification=design,
        output_directory=tmp_path / "output",
        requested_candidates=2,
        physical_device=0,
        stdout_path=tmp_path / "stdout.log",
        stderr_path=tmp_path / "stderr.log",
    )
    observed: list[float] = []

    monkeypatch.setattr(BoltzGenGenerationAdapter, "probe", lambda self: {})

    def fake_run(*_: object, **__: object) -> subprocess.CompletedProcess[str]:
        time.sleep(0.025)
        return subprocess.CompletedProcess(("boltzgen",), 0)

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = adapter.execute(
        request,
        heartbeat_callback=lambda item: observed.append(item.elapsed_seconds),
    )

    assert result.return_code == 0
    assert observed
    assert all(value > 0 for value in observed)
