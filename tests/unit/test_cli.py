from __future__ import annotations

import json
from pathlib import Path

import pytest

from easydesign import cli
from easydesign.orchestration.research_models import CommandResult, NextAction


def test_parser_exposes_agent_native_local_commands_and_retires_step() -> None:
    help_text = cli._parser().format_help()

    for command in (
        "project",
        "target",
        "site",
        "strategy",
        "pilot",
        "scale",
        "select",
        "job",
        "view",
    ):
        assert command in help_text
    assert "step" not in help_text
    assert "remote" not in help_text
    assert "setup" not in help_text
    assert "ui" not in help_text


def test_runtime_parser_supports_fresh_component_install_without_remote_surface() -> None:
    planned = cli._parser().parse_args(["runtime", "plan", "protenix-v2"])
    assert planned.runtime_command == "plan"
    assert planned.component == "protenix-v2"

    installed = cli._parser().parse_args(
        [
            "runtime",
            "install",
            "protenix-v2",
            "--conda",
            "/data/Easydesign/runtime/tools/miniforge3/bin/conda",
            "--detach",
        ]
    )
    assert installed.runtime_command == "install"
    assert installed.detach is True
    assert installed.bundle is None

    openfold3 = cli._parser().parse_args(
        ["runtime", "install", "openfold3", "--bundle", "/data/of3-bundle"]
    )
    assert openfold3.bundle == Path("/data/of3-bundle")


def test_json_uses_stage_free_typed_result_model(
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = CommandResult(
        status="target-and-site-ready",
        phase="strategize",
        project_id="apoe",
        run_id="foundation-1",
        manifest=Path("/tmp/run-1/manifest.json"),
        next_actions=(
            NextAction(
                command="easydesign strategy draft apoe",
                description="讨论策略",
            ),
        ),
    )

    cli._print_result(result, as_json=True)

    payload = json.loads(capsys.readouterr().out)
    assert payload == result.model_dump(mode="json")
    assert "step" not in payload


@pytest.mark.parametrize(
    "argv",
    (
        ["pilot", "run", "apoe", "--strategy", "strategy-r000001"],
        ["scale", "run", "apoe", "--selection", "selection-1"],
        ["select", "run", "apoe", "--run", "production-1"],
    ),
)
def test_scientific_run_commands_default_to_unconfirmed(argv: list[str]) -> None:
    parsed = cli._parser().parse_args(argv)
    assert parsed.confirm is False
    assert parsed.detach is False


def test_view_defaults_to_researcher_port_8000() -> None:
    parsed = cli._parser().parse_args(["view", "workspace/projects/apoe"])
    assert parsed.port == 8000


def test_target_bundle_and_source_run_are_a_valid_project_init_pair() -> None:
    parsed = cli._parser().parse_args(
        [
            "project",
            "init",
            "workspace/projects/imported",
            "--target-bundle",
            "bundle.json",
            "--source-run-root",
            "examples/apoe-ui-demo/evidence-runs/example",
        ]
    )

    assert parsed.target_bundle == Path("bundle.json")
    assert parsed.source_run_root == Path("examples/apoe-ui-demo/evidence-runs/example")


@pytest.mark.parametrize(
    ("arguments", "expected"),
    (
        (["--target", "target.pse"], Path("target.pse")),
        (["--target", "target.cif"], Path("target.cif")),
        (["--target", "target.fasta"], Path("target.fasta")),
        (["--pdb-id", "1ABC"], "1ABC"),
        (["--uniprot", "P02649"], "P02649"),
        (["--uniprot-query", "apoe", "--taxon-id", "9606"], "apoe"),
    ),
)
def test_project_init_preserves_all_research_source_routes(
    arguments: list[str], expected: Path | str
) -> None:
    parsed = cli._parser().parse_args(
        ["project", "init", "workspace/projects/source-route", *arguments]
    )
    observed = parsed.target or parsed.pdb_id or parsed.uniprot or parsed.uniprot_query
    assert observed == expected
