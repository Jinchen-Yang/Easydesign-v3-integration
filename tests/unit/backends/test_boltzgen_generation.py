from __future__ import annotations

from pathlib import Path

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
