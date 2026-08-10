from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from easydesign import cli
from easydesign.orchestration.research_models import CommandResult, NextAction
from easydesign.orchestration.setup_jobs import SetupJobProgress, SetupJobProjection


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
    workspace = Path.cwd()
    conda = workspace / "runtime/tools/miniforge3/bin/conda"
    bundle = workspace / "runtime/imports/openfold3-bundle"
    planned = cli._parser().parse_args(["runtime", "plan", "protenix-v2"])
    assert planned.runtime_command == "plan"
    assert planned.component == "protenix-v2"

    planned_all = cli._parser().parse_args(["runtime", "plan", "all"])
    assert planned_all.component == "all"

    miniforge = cli._parser().parse_args(["runtime", "install", "miniforge"])
    assert miniforge.runtime_command == "install"
    assert miniforge.component == "miniforge"
    assert miniforge.detach is False
    assert miniforge.source == "auto"

    installed = cli._parser().parse_args(
        [
            "runtime",
            "install",
            "protenix-v2",
            "--conda",
            str(conda),
            "--detach",
        ]
    )
    assert installed.runtime_command == "install"
    assert installed.detach is True
    assert installed.bundle is None

    china = cli._parser().parse_args(
        ["runtime", "install", "boltzgen", "--source", "china", "--detach"]
    )
    assert china.source == "china"

    installed_all = cli._parser().parse_args(
        ["runtime", "install", "all", "--detach"]
    )
    assert installed_all.component == "all"
    assert installed_all.detach is True

    openfold3 = cli._parser().parse_args(
        ["runtime", "install", "openfold3", "--bundle", str(bundle)]
    )
    assert openfold3.bundle == bundle

    watched = cli._parser().parse_args(
        ["runtime", "jobs", "--job-id", "setup-fixture", "--watch"]
    )
    assert watched.watch is True
    assert watched.interval == 1.0

    with pytest.raises(SystemExit):
        cli._parser().parse_args(["runtime", "link", "/another/runtime"])


def test_runtime_job_progress_renders_step_bytes_rate_and_eta() -> None:
    now = datetime.now(tz=UTC)
    projection = SetupJobProjection(
        job_id="setup-fixture",
        status="running",
        pid=123,
        started_at=now,
        minimal=False,
        component="boltzgen",
        pip_index_url="https://pypi.org/simple",
        stdout_relative_path=Path("runtime/logs/setup.stdout.log"),
        stderr_relative_path=Path("runtime/logs/setup.stderr.log"),
        progress=SetupJobProgress(
            job_id="setup-fixture",
            phase="asset",
            message="正在下载并校验资产",
            completed_steps=1,
            total_steps=4,
            current_item="fixture-model",
            current_step_fraction=0.5,
            bytes_completed=512,
            bytes_total=1024,
            bytes_per_second=256,
            eta_seconds=2,
            updated_at=now,
        ),
    )

    rendered = cli._format_setup_job_progress(projection)

    assert "37.5%" in rendered
    assert "512 B/1.0 KiB" in rendered
    assert "256 B/s" in rendered
    assert "ETA 2s" in rendered


def test_runtime_job_watch_ctrl_c_only_stops_observing(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    context = cli.WorkspaceContext.from_root(Path(__file__).resolve().parents[2])
    now = datetime.now(tz=UTC)
    projection = SetupJobProjection(
        job_id="setup-fixture",
        status="running",
        pid=123,
        started_at=now,
        minimal=False,
        component="pymol-pse",
        pip_index_url="https://pypi.org/simple",
        stdout_relative_path=Path("runtime/logs/setup.stdout.log"),
        stderr_relative_path=Path("runtime/logs/setup.stderr.log"),
    )
    monkeypatch.setattr(cli, "read_setup_job", lambda _context, _job_id: projection)
    monkeypatch.setattr(
        cli.time,
        "sleep",
        lambda _interval: (_ for _ in ()).throw(KeyboardInterrupt),
    )

    observed = cli._watch_setup_job(context, "setup-fixture", interval=0.01)

    assert observed is projection
    assert "后台安装任务仍在运行" in capsys.readouterr().out


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
