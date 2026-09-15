from __future__ import annotations

from collections import Counter
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SCENARIOS = ROOT / "tests/skill_evals/vhh_scenarios.yaml"
ROUTING = ROOT / "tests/skill_evals/routing_cases.yaml"
RESEARCH_SKILL = ROOT / ".agents/skills/easydesign-research"
DEVELOPMENT_SKILL = ROOT / ".agents/skills/easydesign-development"


def test_scientific_suite_is_16_executable_packets_with_hidden_rubrics() -> None:
    payload = yaml.safe_load(SCENARIOS.read_text(encoding="utf-8"))
    scenarios = payload["scenarios"]
    contract = payload["evaluation_contract"]

    assert payload["schema_version"] == "2.0"
    assert len(scenarios) == 16
    assert len({item["id"] for item in scenarios}) == 16
    assert Counter(item["phase"] for item in scenarios) == {
        "prepare": 5,
        "strategize": 5,
        "pilot": 4,
        "scale-select": 2,
    }
    assert sum(item["high_risk_daily_model"] for item in scenarios) == 6
    assert len(contract["scoring_dimensions"]) == 7
    assert contract["score_range_per_dimension"] == [0, 2]
    assert contract["reference_signal"]["automatic_promotion"] is False

    visible = set(contract["solver_visible_fields"])
    assert "rubric" not in visible
    assert contract["judge_only_fields"] == ["rubric"]
    for item in scenarios:
        assert len(item["user_prompt"]) >= 80
        assert item["controlled_inputs"]
        assert len(item["required_deliverables"]) >= 4
        assert item["tool_policy"]["mutation"] == "forbidden"
        assert item["deterministic_checks"]
        rubric = item["rubric"]
        assert len(rubric["expected_reasoning_obligations"]) >= 3
        assert len(rubric["forbidden_conclusions"]) >= 2
        assert rubric["critical_if"]


def test_suite_directly_covers_product_policy_and_backend_default() -> None:
    payload = yaml.safe_load(SCENARIOS.read_text(encoding="utf-8"))
    by_id = {item["id"]: item for item in payload["scenarios"]}
    first = by_id["first-pilot-seven-scaffold-yaml"]
    matrix = by_id["enzyme-pocket-long-cdr3-matrix"]
    assert "exact_official_vhh7_v1_scaffolds" in first["deterministic_checks"]
    assert "forty_candidates_per_expanded_strategy" in first["deterministic_checks"]
    assert "exact_condition_count_x" in first["deterministic_checks"]
    assert "exact_total_280_times_x" in first["deterministic_checks"]
    assert (
        "every_first_pilot_condition_is_exactly_7_times_40"
        in matrix["deterministic_checks"]
    )
    assert "total_is_exactly_280_times_x" in matrix["deterministic_checks"]
    forbidden = "\n".join(
        conclusion
        for scenario in (first, matrix)
        for conclusion in scenario["rubric"]["forbidden_conclusions"]
    ).lower()
    assert "two favored scaffolds" in forbidden
    assert "twenty candidates per scaffold" in forbidden or "20 candidates" in forbidden

    scientific_text = SCENARIOS.read_text(encoding="utf-8").lower()
    for token in (
        "nanobody-filter-standard-v1.6",
        "protenix-v2",
        "official-vhh7-v1",
        "scale-select",
        "literature_search: required",
        "unsupported-field-claimed-valid",
    ):
        assert token in scientific_text


def test_live_references_are_one_hop_reachable_and_long_files_have_toc() -> None:
    skill_text = (RESEARCH_SKILL / "SKILL.md").read_text(encoding="utf-8")
    references = sorted((RESEARCH_SKILL / "references").glob("*.md"))
    assert len(references) == 16
    for reference in references:
        assert f"references/{reference.name}" in skill_text
        if len(reference.read_text(encoding="utf-8").splitlines()) > 100:
            assert "## 目录" in reference.read_text(encoding="utf-8")


def test_live_uses_protenix_v16_as_default_and_openfold_only_conditionally() -> None:
    text = "\n".join(
        path.read_text(encoding="utf-8").lower()
        for path in sorted(RESEARCH_SKILL.rglob("*.md"))
    )
    assert "stage 05 默认filter：`nanobody-filter-standard-v1.6`" in text
    assert "stage 05 默认full-target backend：`protenix-v2`" in text
    assert "当前标准profile：`nanobody-filter-standard-v1.7`" not in text
    assert "stage 05 filter：`nanobody-filter-standard-v1.7`" not in text
    assert "不是默认升级或 fallback" in text
    assert "not-exposed-in-pilot-filter-report" in text


def test_claim_ledger_contains_corrected_primary_source_metadata() -> None:
    claims = (RESEARCH_SKILL / "references/scientific-claims.md").read_text(
        encoding="utf-8"
    )
    for expected in (
        "Gupta et al., Nature Communications 2023",
        "Jiang et al., PNAS 2016",
        "Joest et al., Chemical Science 2021",
        "Klein et al., Chemical Science 2018",
        "Koromyslova & Hansman, PLOS Pathogens 2017",
        "10.1371/journal.ppat.1006636",
    ):
        assert expected in claims
    for stale in (
        "Oyen et al., Nature Communications 2023",
        "Kumar et al., PNAS 2016",
        "Kusch et al., Chemical Science 2022",
        "Traenkle et al., Angewandte",
        "10.1128/JVI.01503-17",
    ):
        assert stale not in claims


def test_live_exposes_scenario_critical_guardrails() -> None:
    text = "\n".join(
        path.read_text(encoding="utf-8").lower()
        for path in sorted(RESEARCH_SKILL.rglob("*.md"))
    )
    required = (
        "auth_seq_id",
        "label_seq_id",
        "sasa",
        "scannet",
        "active-state",
        "intracellular",
        "glycan",
        "crop-edge",
        "长 cdr3",
        "framework",
        "target-ca-rmsd",
        "hotspot-coverage",
        "interface-bsa",
        "missing reason",
        "scientific stop",
        "integrated-alternative",
        "pi-first-pilot-001",
    )
    for token in required:
        assert token in text


def test_live_requires_parseable_artifacts_and_verified_source_identity() -> None:
    skill = (RESEARCH_SKILL / "SKILL.md").read_text(encoding="utf-8").lower()
    evidence = (RESEARCH_SKILL / "references/evidence-and-numbering.md").read_text(
        encoding="utf-8"
    ).lower()

    for token in (
        "parser 成功读取",
        "validation_status: not_run",
        "parse_valid",
        "schema_valid",
        "project_bound",
        "backend_validated",
    ):
        assert token in skill
    for token in (
        "title + journal + year + doi/pmid",
        "source_metadata_status: provisional",
        "不得从不同搜索结果拼接",
        "source identity drift",
    ):
        assert token in evidence


def test_routing_suite_covers_required_categories_without_broad_collision() -> None:
    payload = yaml.safe_load(ROUTING.read_text(encoding="utf-8"))
    cases = payload["cases"]
    categories = {item["category"] for item in cases}
    assert categories == {
        "positive-trigger",
        "near-neighbor-trigger",
        "negative-trigger",
        "ambiguous-request",
        "multi-skill-handoff",
    }

    research = (RESEARCH_SKILL / "SKILL.md").read_text(encoding="utf-8").lower()
    development = (DEVELOPMENT_SKILL / "SKILL.md").read_text(encoding="utf-8").lower()
    assert "不用于仓库开发" in research
    assert "repository development" in research
    assert "protein-binder research execution" in development
    assert "repository engineering" in development
    assert "project status" in research
    assert "scripts/dev.py context" in development
    by_id = {item["id"]: item for item in cases}
    for case_id in ("stage05-dashboard-review", "stage07-dashboard-review"):
        assert by_id[case_id]["expected_skill"] == "easydesign-research"
        assert "result-review" not in by_id[case_id]["expected_skill"]


def test_research_owns_core_stage05_and_stage07_dashboard_contracts() -> None:
    skill = (RESEARCH_SKILL / "SKILL.md").read_text(encoding="utf-8")
    pilot = (RESEARCH_SKILL / "references/pilot-diagnosis.md").read_text(
        encoding="utf-8"
    )
    scale = (RESEARCH_SKILL / "references/scale-and-selection.md").read_text(
        encoding="utf-8"
    )

    assert "easydesign view PROJECT --run RUN --report stage05" in skill
    assert "easydesign view PROJECT --run RUN --report stage07" in skill
    for text, report_kind in ((pilot, "stage05"), (scale, "stage07")):
        assert f"easydesign report build PROJECT --run RUN --report {report_kind}" in text
        assert "display-only" in text
        assert "data_sha256" in text
        assert "3Dmol.js" in text
    assert "Review cohort" in scale
    assert "最多 200" in scale
    assert "AFO" in pilot and "Protenix" in pilot
    assert "AFO" in scale and "Protenix" in scale


def test_live_description_keeps_bilingual_development_negative_boundary() -> None:
    research = (RESEARCH_SKILL / "SKILL.md").read_text(encoding="utf-8").lower()

    assert "不用于仓库开发" in research
    assert "repository development" in research
