from __future__ import annotations

import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

from easydesign.backends.boltzgen import BoltzGenCheckAdapter
from easydesign.backends.boltzgen.check import _verified_source_snapshot
from easydesign.core import BackendContractError
from easydesign.orchestration.git_sources import (
    GitSourceReceipt,
    directory_content_sha256,
)
from easydesign.stages.s03_boltzgen_configuration import BOLTZGEN_COMMIT, StrategyRecord


def _strategy(path: Path, strategy_id: str) -> StrategyRecord:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("entities: []\n", encoding="utf-8")
    return StrategyRecord(
        strategy_id=strategy_id,
        region_id="region",
        source_hotspot_set_id="region",
        scaffold_id="7eow",
        binding_label_seq_ids=(1, 2),
        candidates_per_strategy=40,
        design_specification_path=path.as_posix(),
        design_specification_sha256="a" * 64,
    )


def test_exported_source_snapshot_is_verified_without_git(tmp_path: Path) -> None:
    repository = tmp_path / "boltzgen"
    source = repository / "src" / "boltzgen.py"
    source.parent.mkdir(parents=True)
    source.write_text("VERSION = '0.3.2'\n", encoding="utf-8")
    marker = GitSourceReceipt(
        source="https://github.com/HannesStark/boltzgen.git",
        revision=BOLTZGEN_COMMIT,
        content_sha256=directory_content_sha256(repository),
        transport_source_id="fixture-archive",
        transport_url="https://example.test/boltzgen.tar.gz",
        archive_sha256="a" * 64,
        recorded_at=datetime(2026, 8, 11, tzinfo=UTC),
    )
    (repository / ".easydesign-source.json").write_text(
        marker.model_dump_json(),
        encoding="utf-8",
    )

    assert _verified_source_snapshot(repository) == BOLTZGEN_COMMIT

    source.write_text("VERSION = 'drift'\n", encoding="utf-8")
    with pytest.raises(BackendContractError, match="现有内容不一致"):
        _verified_source_snapshot(repository)


def test_validation_returns_failed_report_and_preserves_raw_logs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifacts = tmp_path / "artifacts"
    relative = Path("strategies/region/design.yaml")
    strategy = _strategy(artifacts / relative, "region-7eow").model_copy(
        update={"design_specification_path": relative.as_posix()}
    )
    adapter = BoltzGenCheckAdapter(
        executable=tmp_path / "boltzgen",
        repository_root=tmp_path / "repository",
        cache_root=tmp_path / "cache",
    )
    monkeypatch.setattr(
        BoltzGenCheckAdapter,
        "probe",
        lambda _self: {
            "backend": "boltzgen",
            "version": "0.3.2",
            "commit": "a3149cf18eeb58648d1abbb27539bd73f746cdda",
            "random_seed_status": "unsupported-by-boltzgen-0.3.2",
        },
    )
    monkeypatch.setattr(
        BoltzGenCheckAdapter,
        "_run",
        lambda _self, _argv, cwd=None: subprocess.CompletedProcess(
            args=(),
            returncode=2,
            stdout="invalid specification\n",
            stderr="binding error\n",
        ),
    )

    report = adapter.validate(
        artifacts_root=artifacts,
        strategies=(strategy,),
        logs_root=tmp_path / "logs",
        checked_at=datetime(2026, 7, 26, 12, 0, tzinfo=UTC),
    )

    assert report.status == "failed"
    assert report.items[0].status == "failed"
    assert report.items[0].stdout_path == "region-7eow.stdout.log"
    assert (tmp_path / "logs/region-7eow.stdout.log").read_text(
        encoding="utf-8"
    ) == "invalid specification\n"
    assert (tmp_path / "logs/region-7eow.stderr.log").read_text(
        encoding="utf-8"
    ) == "binding error\n"


def test_validation_passes_explicit_local_molecule_dataset(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifacts = tmp_path / "artifacts"
    relative = Path("strategies/region/design.yaml")
    strategy = _strategy(artifacts / relative, "region-7eow").model_copy(
        update={"design_specification_path": relative.as_posix()}
    )
    adapter = BoltzGenCheckAdapter(
        executable=tmp_path / "boltzgen",
        repository_root=tmp_path / "repository",
        cache_root=tmp_path / "cache",
    )
    monkeypatch.setattr(BoltzGenCheckAdapter, "probe", lambda _self: {})
    commands: list[tuple[str, ...]] = []

    def run(
        _self: BoltzGenCheckAdapter,
        argv: list[str],
        *,
        cwd: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        del cwd
        commands.append(tuple(argv))
        return subprocess.CompletedProcess(args=argv, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(BoltzGenCheckAdapter, "_run", run)

    report = adapter.validate(
        artifacts_root=artifacts,
        strategies=(strategy,),
        checked_at=datetime(2026, 7, 29, 12, 0, tzinfo=UTC),
    )

    assert report.status == "passed"
    command = commands[0]
    assert command[command.index("--moldir") + 1].endswith("mols.zip")
    assert not any(item.startswith("huggingface:") for item in command)
