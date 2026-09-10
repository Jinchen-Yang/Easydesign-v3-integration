from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import easydesign.orchestration.research as research_module
from easydesign.core import ConfigurationError, DecisionOption, DecisionRequest, sha256_file
from easydesign.orchestration.application import RunSummary
from easydesign.orchestration.decisions import publish_decision_request
from easydesign.orchestration.local_project import (
    STAGE_FILENAMES,
)
from easydesign.orchestration.project import initialize_project
from easydesign.orchestration.research import (
    ProjectDescriptor,
    ResearchStrategy,
    _append_strategy_research_events,
    _latest_pending_target_run,
    _latest_target_run,
    _site_fragment_from_file,
    _validate_first_pilot_strategy,
    initialize_research_project,
    pilot_review,
    project_status,
)
from easydesign.orchestration.research_graph import load_research_events
from easydesign.stages.s03_boltzgen_configuration import SCAFFOLD_IDS


def test_stage01_prediction_fragment_rebases_precomputed_inputs(
    tmp_path: Path,
) -> None:
    paired = tmp_path / "paired.a3m"
    paired.write_text(">query\nACDE\n", encoding="utf-8")
    templates = tmp_path / "templates.json"
    templates.write_text("[]\n", encoding="utf-8")
    fragment = tmp_path / "stage01-prediction.yaml"
    fragment.write_text(
        f"""
backend: openfold3-af3-jax
target_msa: {{mode: disabled}}
target_paired_msa:
  mode: precomputed
  path: paired.a3m
  sha256: {hashlib.sha256(paired.read_bytes()).hexdigest()}
target_templates:
  mode: precomputed
  data_path: templates.json
  data_sha256: {hashlib.sha256(templates.read_bytes()).hexdigest()}
""".lstrip(),
        encoding="utf-8",
    )

    config = research_module._load_stage01_prediction_config(fragment)

    assert config.backend == "openfold3-af3-jax"
    assert config.target_msa.mode == "disabled"
    assert config.target_paired_msa.path == paired.resolve()
    assert config.target_templates.data_path == templates.resolve()


def _workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "easydesign-workspace.yaml").write_text(
        'schema_version: "0.1"\nworkspace_id: local-research-test\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("EASYDESIGN_WORKSPACE", str(tmp_path))
    return tmp_path


def test_agent_native_project_is_compact_and_status_is_the_resume_entry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _workspace(tmp_path, monkeypatch)
    target = root / "target.fasta"
    target.write_text(">target\nACDEFGHIKLMNPQRSTVWY\n", encoding="utf-8")
    project = root / "workspace/projects/agent-native"

    initialized = initialize_research_project(project_root=project, target=target)
    status = project_status(project)

    assert initialized.status == "initialized"
    assert initialized.phase == "prepare"
    assert status.status == "target-not-started"
    assert status.phase == "prepare"
    assert {item.name for item in project.iterdir()} >= {
        "PROJECT.yaml",
        "DECISIONS.md",
        "strategy-draft.yaml",
        "inputs",
        "strategies",
        "config-revisions",
        "CONFIG_CURRENT",
    }
    assert all(not (project / name).exists() for name in STAGE_FILENAMES.values())
    assert status.next_actions[0].command.startswith("easydesign target prepare")
    assert "--prediction-backend" not in status.next_actions[0].command
    assert "--prediction-backend" in status.next_actions[0].description
    assert "step" not in status.model_dump_json()


def test_target_prepare_freezes_explicit_msa_and_passes_receipt_to_stage01(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _workspace(tmp_path, monkeypatch)
    target = root / "target.fasta"
    target.write_text(">target\nACDEFGHIKLMNPQRSTVWY\n", encoding="utf-8")
    a3m = root / "provided.a3m"
    a3m.write_text(
        ">query\nACDEFGHIKLMNPQRSTVWY\n>homolog\nACDEFGHIKLMNPQ-STVWY\n",
        encoding="utf-8",
    )
    project = root / "workspace/projects/msa-project"
    initialize_research_project(project_root=project, target=target)
    captured: dict[str, object] = {}

    def fake_launch(
        launch_root: Path,
        **values: object,
    ) -> tuple[research_module.CommandResult, SimpleNamespace]:
        captured.update(values)
        return (
            research_module.CommandResult(
                status="succeeded",
                phase="prepare",
                project_id="msa-project",
                run_id="run-msa",
            ),
            SimpleNamespace(
                status="succeeded",
                run_id="run-msa",
                run_root=None,
            ),
        )

    monkeypatch.setattr(research_module, "_launch", fake_launch)

    result = research_module.target_prepare(
        project,
        prediction_backend="openfold3-af3-jax",
        msa_a3m=a3m,
    )

    config = captured["config"]
    prediction = config.structure_prediction
    assert prediction is not None
    assert prediction.target_msa.mode == "precomputed"
    assert prediction.target_msa.source_receipt_path is not None
    assert prediction.target_paired_msa.mode == "disabled"
    assert prediction.target_templates.mode == "disabled"
    snapshot_a3m = project / prediction.target_msa.path
    snapshot_receipt = project / prediction.target_msa.source_receipt_path
    assert snapshot_a3m.read_bytes() == a3m.read_bytes()
    receipt = json.loads(snapshot_receipt.read_text(encoding="utf-8"))
    assert receipt["type"] == "precomputed-file"
    assert receipt["paired_msa"] == "empty"
    assert receipt["template_mode"] == "disabled"
    assert {snapshot_a3m, snapshot_receipt}.issubset(result.artifacts)


def test_pending_stage01_decision_is_discoverable_before_stage_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_root = tmp_path / "workspace/runs/example/run-one"
    publish_decision_request(
        run_root,
        DecisionRequest(
            decision_id="stage01-structure-selection",
            stage_id="01-target-preparation",
            gate="structure-selection",
            created_at="2026-08-12T00:00:00Z",
            message="Choose prediction or an experimental structure.",
            options=(
                DecisionOption(
                    option_id="predict-openfold3-af3-jax",
                    label="AFO",
                    description="Predict with AFO.",
                ),
            ),
        ),
    )
    summary = RunSummary(
        project_id="example",
        run_id="run-one",
        path=run_root,
        status="running",
        latest_manifest=run_root / "manifests/run-manifest.v0002.json",
        manifest_revision=2,
        completed_stages=(),
    )
    monkeypatch.setattr(research_module, "_runs", lambda _root: (summary,))

    assert _latest_pending_target_run(tmp_path) == summary


def test_failed_stage01_run_is_not_reused_as_completed_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failed = RunSummary(
        project_id="example",
        run_id="run-failed",
        path=tmp_path / "workspace/runs/example/run-failed",
        status="failed",
        latest_manifest=tmp_path / "failed-manifest.json",
        manifest_revision=3,
        completed_stages=("01-target-preparation",),
    )
    succeeded = RunSummary(
        project_id="example",
        run_id="run-succeeded",
        path=tmp_path / "workspace/runs/example/run-succeeded",
        status="succeeded",
        latest_manifest=tmp_path / "succeeded-manifest.json",
        manifest_revision=2,
        completed_stages=("01-target-preparation",),
    )
    monkeypatch.setattr(research_module, "_runs", lambda _root: (failed, succeeded))
    monkeypatch.setattr(research_module, "_has_internal_stage", lambda _summary, _number: True)

    assert _latest_target_run(tmp_path) == succeeded


def test_legacy_project_descriptor_drops_default_backend() -> None:
    descriptor = ProjectDescriptor.model_validate(
        {
            "project_id": "legacy",
            "target_id": "target",
            "source_type": "local-file",
            "prediction_backend": "protenix-v2",
            "created_at": "2026-08-13T00:00:00Z",
        }
    )

    assert descriptor.prediction_selection_mode == "explicit-per-stage"
    assert "prediction_backend" not in descriptor.model_dump()


def test_legacy_seven_yaml_project_is_read_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _workspace(tmp_path, monkeypatch)
    target = root / "target.fasta"
    target.write_text(">target\nACDEFGHIKLMNPQRSTVWY\n", encoding="utf-8")
    project = root / "workspace/projects/legacy"
    initialize_project(project_root=project, target=target)
    (project / "CONFIG_CURRENT").write_text("easydesign.yaml\n", encoding="utf-8")
    for filename in STAGE_FILENAMES.values():
        (project / filename).write_text("legacy: true\n", encoding="utf-8")

    status = project_status(project)

    assert status.status == "legacy-stage-project"
    assert "只读" in status.warnings[0]
    assert all((project / name).is_file() for name in STAGE_FILENAMES.values())


def test_strategy_schema_supports_explicit_variants_and_native_identity() -> None:
    native = "entities: []\n"
    strategy = ResearchStrategy.model_validate(
        {
            "schema_version": "1.0",
            "foundation": "current",
            "variants": [
                {
                    "id": "cropped-cdr3",
                    "hotspot_set_id": "A",
                    "binding_label_seq_ids": [10, 11],
                    "scaffold_ids": ["7eow", "7xl0"],
                    "target_crop": {"start": 5, "end": 80},
                    "cdr_overrides": [
                        {
                            "cdr": 3,
                            "design_res_index": "98..116",
                            "insertion_num_residues": "3..12",
                        }
                    ],
                    "candidates": 40,
                    "rationale": "test explicit experiment",
                    "expected_result": "compare two scaffolds",
                },
                {
                    "id": "expert-native",
                    "scaffold_ids": ["7eow"],
                    "native_boltzgen_yaml": "inputs/native.yaml",
                    "native_boltzgen_sha256": hashlib.sha256(native.encode("utf-8")).hexdigest(),
                    "candidates": 40,
                    "rationale": "expert controlled design",
                    "expected_result": "backend validation",
                },
            ],
        }
    )

    assert strategy.variants[0].target_crop is not None
    assert strategy.variants[0].cdr_overrides[0].cdr == 3
    assert strategy.variants[1].native_boltzgen_sha256 is not None


def test_strategy_schema_rejects_unknown_scaffold_and_ambiguous_native() -> None:
    with pytest.raises(ValueError, match="未知 scaffold"):
        ResearchStrategy.model_validate(
            {
                "variants": [
                    {
                        "id": "bad",
                        "hotspot_set_id": "A",
                        "scaffold_ids": ["unknown"],
                        "rationale": "invalid",
                        "expected_result": "reject",
                    }
                ]
            }
        )
    with pytest.raises(ValueError, match="provenance scaffold"):
        ResearchStrategy.model_validate(
            {
                "variants": [
                    {
                        "id": "bad-native",
                        "scaffold_ids": ["7eow", "7xl0"],
                        "native_boltzgen_yaml": "inputs/native.yaml",
                        "native_boltzgen_sha256": "a" * 64,
                        "rationale": "invalid",
                        "expected_result": "reject",
                    }
                ]
            }
        )


def _schema_1_1_strategy(
    *,
    scaffold_ids: tuple[str, ...] = SCAFFOLD_IDS,
    candidates: int = 40,
) -> ResearchStrategy:
    return ResearchStrategy.model_validate(
        {
            "schema_version": "1.1",
            "foundation": "current",
            "variants": [
                {
                    "id": "baseline",
                    "hypothesis_id": "h-baseline",
                    "role": "baseline",
                    "evidence_refs": ["run:foundation", "registry:official-vhh7-v1"],
                    "changed_factors": ["scaffold_id"],
                    "held_constant": ["site", "crop", "cdr_design"],
                    "hotspot_set_id": "A",
                    "scaffold_ids": list(scaffold_ids),
                    "candidates": candidates,
                    "rationale": "measure scaffold-specific compatibility",
                    "expected_result": "compare held-constant scaffold groups",
                    "failure_interpretation": "one failure does not reject the site",
                }
            ],
        }
    )


def test_first_pilot_requires_complete_vhh7_baseline_and_40_per_group() -> None:
    strategy = _schema_1_1_strategy()

    _validate_first_pilot_strategy(strategy)
    assert sum(item.candidates * len(item.scaffold_ids) for item in strategy.variants) == 280

    with pytest.raises(ConfigurationError, match="缺少 official-vhh7-v1 scaffold"):
        _validate_first_pilot_strategy(_schema_1_1_strategy(scaffold_ids=SCAFFOLD_IDS[:-1]))
    with pytest.raises(ConfigurationError, match="必须生成 40 candidates"):
        _validate_first_pilot_strategy(_schema_1_1_strategy(candidates=39))


def test_first_pilot_stops_if_canonical_registry_is_not_exactly_seven(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    strategy = _schema_1_1_strategy()
    monkeypatch.setattr(research_module, "SCAFFOLD_IDS", SCAFFOLD_IDS[:-1])

    with pytest.raises(ConfigurationError, match="精确包含 7 个唯一 scaffold"):
        _validate_first_pilot_strategy(strategy)


def test_schema_1_1_rejects_missing_experiment_contract() -> None:
    with pytest.raises(ValueError, match="完整 experiment contract"):
        ResearchStrategy.model_validate(
            {
                "schema_version": "1.1",
                "variants": [
                    {
                        "id": "incomplete",
                        "hotspot_set_id": "A",
                        "rationale": "missing causal metadata",
                        "expected_result": "must be rejected",
                    }
                ],
            }
        )


def test_strategy_1_2_remains_readable_and_new_hypothesis_fields_are_optional() -> None:
    payload = _schema_1_1_strategy().model_dump(mode="json")
    payload.update(
        {
            "schema_version": "1.2",
            "protocol_kind": "first-pilot",
            "prior_research_event_ids": [],
        }
    )

    strategy = ResearchStrategy.model_validate(payload)

    assert strategy.schema_version == "1.2"
    assert strategy.variants[0].hypothesis_statement is None
    assert strategy.variants[0].hypothesis_basis is None


def test_structured_hypothesis_fields_project_to_distinct_event_content(
    tmp_path: Path,
) -> None:
    strategy = _schema_1_1_strategy().model_copy(
        update={
            "variants": (
                _schema_1_1_strategy()
                .variants[0]
                .model_copy(
                    update={
                        "hypothesis_statement": "The approved site is permissive.",
                        "hypothesis_basis": "The site is exposed in the approved structure.",
                    }
                ),
            )
        }
    )
    strategy_path = tmp_path / "strategy-r000001.yaml"
    strategy_path.write_text("strategy fixture\n", encoding="utf-8")

    _append_strategy_research_events(
        tmp_path,
        strategy=strategy,
        strategy_path=strategy_path,
        foundation_sha256="a" * 64,
        plan_sha256_value="b" * 64,
    )
    hypothesis = load_research_events(tmp_path)[0]

    assert hypothesis.event_type == "hypothesis"
    assert hypothesis.statement == "The approved site is permissive."
    assert hypothesis.mechanism == "The site is exposed in the approved structure."


def test_site_proposal_cannot_embed_or_bypass_human_approval(tmp_path: Path) -> None:
    config = tmp_path / "site.yaml"
    config.write_text(
        """mode: user-provided
methods: []
automatic: null
annotations:
  uniprot: if_available
user_regions:
  source:
    type: residue-list
    numbering: label
    regions:
      - id: A
        residues: ['10']
  approval:
    approved_by: researcher
    acknowledge_user_provided_regions: true
    acknowledge_evidence_limitations: true
    selections:
      - id: A
        design_goal: exploratory
        biological_rationale: known test rationale
        structural_rationale: known test structure
""",
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError, match="site approve --confirm"):
        _site_fragment_from_file(config)


def test_project_status_recovers_an_incomplete_pilot_without_stage_language(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _workspace(tmp_path, monkeypatch)
    target = root / "target.fasta"
    target.write_text(">target\nACDEFGHIKLMNPQRSTVWY\n", encoding="utf-8")
    project = root / "workspace/projects/agent-native"
    initialize_research_project(project_root=project, target=target)
    summary = RunSummary(
        project_id="agent-native",
        run_id="pilot-20260808-000000-example",
        path=root / "workspace/runs/agent-native/pilot-20260808-000000-example",
        status="running",
        latest_manifest=root / "manifest.json",
        manifest_revision=4,
        completed_stages=("01-target-preparation", "02-hotspot-discovery", "03-config"),
    )
    monkeypatch.setattr(research_module, "_runs", lambda _project: (summary,))
    monkeypatch.setattr(research_module, "_semantic_evidence", lambda _project: ())
    monkeypatch.setattr(research_module, "_latest_foundation", lambda _project: None)
    monkeypatch.setattr(
        research_module,
        "_has_internal_stage",
        lambda _summary, number: number in {1, 2, 3, 4},
    )

    status = project_status(project)

    assert status.status == "pilot-resume-ready"
    assert status.phase == "pilot"
    assert status.next_actions[0].command.startswith("easydesign job resume")
    assert "Stage" not in status.model_dump_json()


def test_negative_pilot_review_does_not_offer_illegal_promotion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report = tmp_path / "pilot-filter-report.json"
    report.write_text(
        json.dumps(
            {
                "status": "stopped-no-tier-a",
                "candidate_records": [],
                "strategy_summaries": [],
                "promoted_strategy_ids": [],
            }
        ),
        encoding="utf-8",
    )
    run = RunSummary(
        project_id="example",
        run_id="pilot-negative",
        path=tmp_path / "run",
        status="succeeded",
        latest_manifest=tmp_path / "manifest.json",
        manifest_revision=5,
        completed_stages=("05-pilot-filtering",),
    )
    monkeypatch.setattr(
        research_module,
        "resolve_project_path",
        lambda path, *, must_exist: path.resolve(),
    )
    monkeypatch.setattr(research_module, "_run_by_id", lambda _root, _run_id: run)
    monkeypatch.setattr(research_module, "_has_internal_stage", lambda _run, number: number == 5)

    def artifact(_root: Path, artifact_id: str) -> tuple[object, Path]:
        if artifact_id == "pilot-filter-report":
            return SimpleNamespace(sha256="a" * 64), report
        raise ConfigurationError("missing fixture artifact")

    monkeypatch.setattr(research_module, "_artifact", artifact)

    result = pilot_review(tmp_path, run_id=run.run_id)

    assert len(result.next_actions) == 1
    assert "easydesign view" in result.next_actions[0].command
    assert result.next_actions[0].intent is not None
    assert result.next_actions[0].intent.action_type == "review-status"


def test_completed_zero_pass_pilot_persists_a_scoped_observation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report = tmp_path / "pilot-filter-report.json"
    report.write_text(
        json.dumps(
            {
                "status": "stopped-no-tier-a",
                "profile_version": "nanobody-filter-standard-v1.6",
                "candidate_records": [
                    {
                        "candidate_id": "candidate-1",
                        "strategy_id": "baseline",
                        "eligible_unique_pass": False,
                        "hard_gate_decisions": [{"rule_id": "target-ca-rmsd", "passed": False}],
                    }
                ],
                "strategy_summaries": [],
                "promoted_strategy_ids": [],
            }
        ),
        encoding="utf-8",
    )
    manifest = tmp_path / "run-manifest.json"
    manifest.write_text('{"status":"succeeded"}\n', encoding="utf-8")
    run = RunSummary(
        project_id="example",
        run_id="pilot-zero",
        path=tmp_path / "run",
        status="succeeded",
        latest_manifest=manifest,
        manifest_revision=5,
        completed_stages=("05-pilot-filtering",),
    )
    monkeypatch.setattr(
        research_module,
        "resolve_project_path",
        lambda path, *, must_exist: path.resolve(),
    )
    monkeypatch.setattr(research_module, "_run_by_id", lambda _root, _run_id: run)
    monkeypatch.setattr(research_module, "_has_internal_stage", lambda _run, number: number == 5)

    def artifact(_root: Path, artifact_id: str) -> tuple[object, Path]:
        if artifact_id == "pilot-filter-report":
            return SimpleNamespace(sha256=sha256_file(report)), report
        raise ConfigurationError("missing fixture artifact")

    monkeypatch.setattr(research_module, "_artifact", artifact)

    result = pilot_review(tmp_path, run_id=run.run_id)
    events = load_research_events(tmp_path)

    assert len(result.artifacts) == 1
    assert len(events) == 1
    assert events[0].event_type == "observation"
    assert events[0].denominator == 1
    assert events[0].passing_count == 0
    assert events[0].claim.assertion_domain == "computational-metric"
    assert result.next_actions[0].intent is not None
    assert result.next_actions[0].intent.action_type == "interpret-pilot"


def test_operationally_failed_pilot_does_not_become_scientific_observation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report = tmp_path / "pilot-filter-report.json"
    report.write_text(
        json.dumps(
            {
                "status": "stopped-no-tier-a",
                "candidate_records": [
                    {
                        "candidate_id": "candidate-1",
                        "strategy_id": "baseline",
                        "eligible_unique_pass": False,
                        "hard_gate_decisions": [],
                    }
                ],
                "promoted_strategy_ids": [],
            }
        ),
        encoding="utf-8",
    )
    manifest = tmp_path / "run-manifest.json"
    manifest.write_text('{"status":"failed"}\n', encoding="utf-8")
    run = RunSummary(
        project_id="example",
        run_id="pilot-operational-failure",
        path=tmp_path / "run",
        status="failed",
        latest_manifest=manifest,
        manifest_revision=5,
        completed_stages=("05-pilot-filtering",),
    )
    monkeypatch.setattr(
        research_module,
        "resolve_project_path",
        lambda path, *, must_exist: path.resolve(),
    )
    monkeypatch.setattr(research_module, "_run_by_id", lambda _root, _run_id: run)
    monkeypatch.setattr(research_module, "_has_internal_stage", lambda _run, number: number == 5)
    monkeypatch.setattr(
        research_module,
        "_artifact",
        lambda _root, artifact_id: (
            (SimpleNamespace(sha256=sha256_file(report)), report)
            if artifact_id == "pilot-filter-report"
            else (_ for _ in ()).throw(ConfigurationError("missing fixture artifact"))
        ),
    )

    result = pilot_review(tmp_path, run_id=run.run_id)

    assert not result.artifacts
    assert not load_research_events(tmp_path)
    assert result.next_actions[0].intent is not None
    assert result.next_actions[0].intent.action_type == "review-status"
