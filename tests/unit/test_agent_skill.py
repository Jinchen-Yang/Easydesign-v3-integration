from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / ".agents/skills/easydesign-research"


def test_research_skill_has_exact_flat_reference_set_and_valid_frontmatter() -> None:
    skill_text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    _, frontmatter, body = skill_text.split("---", maxsplit=2)
    metadata = yaml.safe_load(frontmatter)

    assert metadata["name"] == "easydesign-research"
    assert "protein-binder" in metadata["description"]
    assert body.strip()
    assert {path.name for path in (SKILL / "references").glob("*.md")} == {
        "target-and-site.md",
        "strategy-yaml.md",
        "pilot-diagnosis.md",
        "scale-and-selection.md",
    }
    assert {path.name for path in SKILL.iterdir()} == {"SKILL.md", "references"}


def test_skill_routes_one_reference_per_phase_and_stays_on_current_host() -> None:
    skill_text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    complete = "\n".join(
        [
            skill_text,
            *(
                path.read_text(encoding="utf-8")
                for path in sorted((SKILL / "references").glob("*.md"))
            ),
        ]
    ).lower()

    for reference in (
        "target-and-site.md",
        "strategy-yaml.md",
        "pilot-diagnosis.md",
        "scale-and-selection.md",
    ):
        assert skill_text.count(reference) == 1
    assert "exactly one reference" in skill_text
    assert "scripts/dev.py context" in skill_text
    assert "Never call" in skill_text
    assert "easydesign remote" not in complete
    assert "never invoke remote executors" in complete
    assert "easydesign-workspace.yaml" in complete
    assert "current clone" in complete
    assert "local linux gpu host" in complete


def test_experience_promotion_requires_human_review_and_evidence_fields() -> None:
    text = (SKILL / "SKILL.md").read_text(encoding="utf-8").lower()
    for requirement in (
        "scope",
        "evidence run ids",
        "counterexamples",
        "confidence",
        "reviewer",
        "review date",
    ):
        assert requirement in text
    assert "researcher-approved" in text


def test_agents_routes_research_away_from_development_context() -> None:
    text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert "蛋白设计任务" in text
    assert "不要运行开发 context" in text
    assert "easydesign project status PROJECT --json" in text
    assert "$easydesign-research" in text
