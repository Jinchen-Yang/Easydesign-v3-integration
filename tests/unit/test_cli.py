from __future__ import annotations

import json
from pathlib import Path

import pytest

from easydesign import cli
from easydesign.orchestration.local_steps import StepCommandResult


def test_parser_exposes_only_local_product_commands() -> None:
    help_text = cli._parser().format_help()

    assert "runtime" in help_text
    assert "doctor" in help_text
    assert "step" in help_text
    assert "remote" not in help_text
    assert "setup" not in help_text
    assert "ui" not in help_text


def test_step_json_uses_the_typed_result_model(capsys: pytest.CaptureFixture[str]) -> None:
    result = StepCommandResult(
        status="valid",
        project_id="apoe",
        run_id="run-1",
        step=2,
        run_root=Path("/tmp/run-1"),
        next_actions=("next",),
    )

    cli._print_result(result, as_json=True)

    payload = json.loads(capsys.readouterr().out)
    assert payload == result.model_dump(mode="json")


def test_stage_four_requires_explicit_confirmation_flag() -> None:
    parsed = cli._parser().parse_args(
        ["step", "run", "4", "workspace/projects/apoe"]
    )
    assert parsed.confirm is False
    assert parsed.detach is False


def test_stage_view_defaults_to_researcher_port_8000() -> None:
    parsed = cli._parser().parse_args(
        ["step", "view", "workspace/projects/apoe"]
    )
    assert parsed.port == 8000


def test_target_bundle_and_source_run_are_a_valid_cli_pair() -> None:
    parsed = cli._parser().parse_args(
        [
            "step",
            "init",
            "workspace/projects/imported",
            "--target-bundle",
            "bundle.json",
            "--source-run-root",
            "examples/apoe-ui-demo/evidence-runs/example",
        ]
    )

    assert parsed.target_bundle == Path("bundle.json")
    assert parsed.source_run_root == Path(
        "examples/apoe-ui-demo/evidence-runs/example"
    )
