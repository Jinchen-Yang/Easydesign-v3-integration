from __future__ import annotations

from pathlib import Path

from easydesign.stages.s04_pilot_generation import collect_boltzgen_candidates


def _output(root: Path) -> Path:
    output = root / "04-pilot-generation/attempt-0001/tasks/task/attempt-0001/backend-output"
    metrics = output / "final_ranked_designs/all_designs_metrics.csv"
    metrics.parent.mkdir(parents=True)
    metrics.write_text(
        "id,file_name,pass_filters,design_to_target_iptm\n"
        "backend_0,backend_0.cif,True,0.61\n"
        "backend_1,backend_1.cif,False,0.42\n"
        "backend_missing,backend_missing.cif,True,0.99\n",
        encoding="utf-8",
    )
    originals = output / "intermediate_designs_inverse_folded"
    refolds = originals / "refold_cif"
    refolds.mkdir(parents=True)
    for candidate in ("backend_0", "backend_1"):
        (originals / f"{candidate}.cif").write_text(
            f"data_{candidate}\n#\n",
            encoding="utf-8",
        )
        (refolds / f"{candidate}.cif").write_text(
            f"data_{candidate}_refold\n#\n",
            encoding="utf-8",
        )
    return output


def test_collector_requires_metric_original_and_refold_structure(
    tmp_path: Path,
) -> None:
    output = _output(tmp_path)

    candidates = collect_boltzgen_candidates(
        run_root=tmp_path,
        backend_output=output,
        strategy_id="generic-strategy",
        task_id="pilot-generic-strategy",
        task_attempt_number=1,
        stage_attempt_id="attempt-0001",
        ordinal_start=1,
        maximum_candidates=3,
    )

    assert len(candidates) == 2
    assert tuple(item.candidate_id for item in candidates) == (
        "generic-strategy-candidate-0001",
        "generic-strategy-candidate-0002",
    )
    assert candidates[0].pass_filters is True
    assert candidates[1].pass_filters is False
    assert candidates[0].metrics["design_to_target_iptm"] == 0.61
    assert candidates[0].original_structure.verify(tmp_path).is_file()
    assert candidates[0].refolded_structure.verify(tmp_path).is_file()
