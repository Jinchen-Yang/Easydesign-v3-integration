from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
RESEARCH_SKILL = ROOT / ".agents/skills/easydesign-research"
DEVELOPMENT_SKILL = ROOT / ".agents/skills/easydesign-development"


def test_research_skill_has_exact_flat_reference_set_and_valid_frontmatter() -> None:
    skill_text = (RESEARCH_SKILL / "SKILL.md").read_text(encoding="utf-8")
    _, frontmatter, body = skill_text.split("---", maxsplit=2)
    metadata = yaml.safe_load(frontmatter)

    assert metadata["name"] == "easydesign-research"
    assert "protein-binder" in metadata["description"]
    assert body.strip()
    assert {
        path.name for path in (RESEARCH_SKILL / "references").glob("*.md")
    } == {
        "target-and-site.md",
        "strategy-yaml.md",
        "pilot-diagnosis.md",
        "scale-and-selection.md",
    }
    assert {path.name for path in RESEARCH_SKILL.iterdir()} == {
        "SKILL.md",
        "references",
    }


def test_skill_routes_one_reference_per_phase_and_stays_on_current_host() -> None:
    skill_text = (RESEARCH_SKILL / "SKILL.md").read_text(encoding="utf-8")
    complete = "\n".join(
        [
            skill_text,
            *(
                path.read_text(encoding="utf-8")
                for path in sorted((RESEARCH_SKILL / "references").glob("*.md"))
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
    text = (RESEARCH_SKILL / "SKILL.md").read_text(encoding="utf-8").lower()
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


def test_development_skill_is_thin_context_and_verification_entry() -> None:
    skill_text = (DEVELOPMENT_SKILL / "SKILL.md").read_text(encoding="utf-8")
    _, frontmatter, body = skill_text.split("---", maxsplit=2)
    metadata = yaml.safe_load(frontmatter)
    openai = yaml.safe_load(
        (DEVELOPMENT_SKILL / "agents/openai.yaml").read_text(encoding="utf-8")
    )

    assert set(metadata) == {"name", "description"}
    assert metadata["name"] == "easydesign-development"
    assert "repository engineering" in metadata["description"]
    assert "protein-binder research" in metadata["description"]
    assert "scripts/dev.py context" in body
    assert "scripts/dev.py verify" in body
    assert "docs/agent/DEVELOPMENT_AGENT.md" not in body
    assert openai["policy"]["allow_implicit_invocation"] is True
    assert "$easydesign-development" in openai["interface"]["default_prompt"]
    assert {path.name for path in DEVELOPMENT_SKILL.iterdir()} == {
        "SKILL.md",
        "agents",
    }


def test_agents_is_research_only_and_development_guide_owns_engineering() -> None:
    text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    development = (
        ROOT / "docs/agent/DEVELOPMENT_AGENT.md"
    ).read_text(encoding="utf-8")
    development_index = (ROOT / "DEVELOPMENT.md").read_text(encoding="utf-8")
    philosophy = (
        ROOT / "docs/PRODUCT_PHILOSOPHY.md"
    ).read_text(encoding="utf-8")

    assert "研究 Agent" in text
    assert "easydesign project status PROJECT --json" in text
    assert "$easydesign-research" in text
    for development_token in (
        "$easydesign-development",
        "scripts/dev.py context",
        "scripts/dev.py verify",
        "开发模式",
    ):
        assert development_token not in text
    for required in (
        "$easydesign-development",
        "scripts/dev.py context",
        "scripts/dev.py verify",
        "easydesign-local",
    ):
        assert required in development
    assert (
        "[开发 Agent 必读](docs/agent/DEVELOPMENT_AGENT.md)"
        in development_index
    )
    assert "判断研究或开发" not in philosophy
    assert "$easydesign-development" in philosophy
