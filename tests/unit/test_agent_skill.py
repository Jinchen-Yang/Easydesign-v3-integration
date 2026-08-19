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
    assert "vhh/nanobody 研究决策" in metadata["description"].lower()
    assert "不用于仓库开发" in metadata["description"]
    assert "repository development" in metadata["description"]
    assert body.strip()
    assert {path.name for path in (RESEARCH_SKILL / "references").glob("*.md")} == {
        "target-and-site.md",
        "evidence-and-numbering.md",
        "special-target-playbooks.md",
        "strategy-yaml.md",
        "vhh-geometry-priors.md",
        "boltzgen-contract.md",
        "pilot-diagnosis.md",
        "metric-guide.md",
        "failure-atlas.md",
        "scale-and-selection.md",
        "scientific-claims.md",
        "gpcr-family-playbooks.md",
        "gpcr-mechanism-and-state.md",
        "gpcr-review-schema.md",
        "gpcrdb-contract.md",
    }
    assert {path.name for path in RESEARCH_SKILL.iterdir()} == {
        "SKILL.md",
        "agents",
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
        "evidence-and-numbering.md",
        "special-target-playbooks.md",
        "strategy-yaml.md",
        "vhh-geometry-priors.md",
        "boltzgen-contract.md",
        "pilot-diagnosis.md",
        "metric-guide.md",
        "failure-atlas.md",
        "scale-and-selection.md",
        "scientific-claims.md",
    ):
        assert skill_text.count(f"references/{reference}") == 1
    assert "不要一次读取全部 references" in skill_text
    assert "不要只读顶层后凭常识继续" in skill_text
    assert "scripts/dev.py context" in skill_text
    assert "不得运行" in skill_text
    assert "easydesign remote" not in complete
    assert "不得调用 remote executor" in complete
    assert "easydesign-workspace.yaml" in complete
    assert "当前 clone" in complete
    assert "pi-first-pilot-001" in complete
    assert "official-vhh7-v1" in complete
    for scaffold in (
        "7eow",
        "7xl0",
        "8coh",
        "8z8v",
        "gontivimab",
        "isecarosmab",
        "sonelokimab",
    ):
        assert scaffold in complete
    assert "candidates: 40" in complete
    assert "7 × 40 = 280" in complete
    assert "external yaml 使用 `candidates_per_strategy`" in complete
    assert "fact" in skill_text
    assert "prior" in skill_text
    assert "hypothesis" in skill_text
    assert "decision" in skill_text


def test_research_skill_metadata_enables_implicit_routing() -> None:
    metadata = yaml.safe_load((RESEARCH_SKILL / "agents/openai.yaml").read_text(encoding="utf-8"))

    assert metadata["policy"]["allow_implicit_invocation"] is True
    assert metadata["interface"]["display_name"] == "EasyDesign VHH 研究"
    assert "$easydesign-research" in metadata["interface"]["default_prompt"]
    assert 25 <= len(metadata["interface"]["short_description"]) <= 64


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
    assert "取得研究者对 repository development 的批准" in text


def test_development_skill_is_thin_context_and_verification_entry() -> None:
    skill_text = (DEVELOPMENT_SKILL / "SKILL.md").read_text(encoding="utf-8")
    _, frontmatter, body = skill_text.split("---", maxsplit=2)
    metadata = yaml.safe_load(frontmatter)
    openai = yaml.safe_load((DEVELOPMENT_SKILL / "agents/openai.yaml").read_text(encoding="utf-8"))

    assert set(metadata) == {"name", "description"}
    assert metadata["name"] == "easydesign-development"
    assert "仓库开发" in metadata["description"]
    assert "repository engineering" in metadata["description"]
    assert "protein-binder research" in metadata["description"]
    assert "scripts/dev.py context" in body
    assert "scripts/dev.py verify" in body
    assert "docs/agent/DEVELOPMENT_AGENT.md" not in body
    assert openai["policy"]["allow_implicit_invocation"] is True
    assert "$easydesign-development" in openai["interface"]["default_prompt"]
    assert openai["interface"]["display_name"] == "EasyDesign 开发"
    assert "分级验证" in openai["interface"]["short_description"]
    assert 25 <= len(openai["interface"]["short_description"]) <= 64
    assert {path.name for path in DEVELOPMENT_SKILL.iterdir()} == {
        "SKILL.md",
        "agents",
    }


def test_only_research_and_development_skills_are_discoverable() -> None:
    discovered = {
        path.parent.name
        for path in (ROOT / ".agents/skills").glob("*/SKILL.md")
    }

    assert discovered == {"easydesign-research", "easydesign-development"}
    assert not (ROOT / ".agents/skills/easydesign-result-review").exists()


def test_skill_prose_is_chinese_first_and_machine_literals_stay_exact() -> None:
    skill_files = [
        RESEARCH_SKILL / "SKILL.md",
        *(sorted((RESEARCH_SKILL / "references").glob("*.md"))),
        DEVELOPMENT_SKILL / "SKILL.md",
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in skill_files)

    for path in skill_files:
        text = path.read_text(encoding="utf-8")
        assert sum("\u4e00" <= char <= "\u9fff" for char in text) >= 40
    for literal in (
        "easydesign project status PROJECT --json",
        "easydesign-workspace.yaml",
        "easydesign strategy freeze ... --confirm",
        "operational failure",
        "scientific stop",
        "empty result",
        ".venv/bin/python scripts/dev.py context --mode MODE --path PATH",
        ".venv/bin/python scripts/dev.py verify --mode MODE",
    ):
        assert literal in combined


def test_agents_is_research_only_and_development_guide_owns_engineering() -> None:
    text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    development = (ROOT / "docs/agent/DEVELOPMENT_AGENT.md").read_text(encoding="utf-8")
    development_index = (ROOT / "DEVELOPMENT.md").read_text(encoding="utf-8")
    philosophy = (ROOT / "docs/PRODUCT_PHILOSOPHY.md").read_text(encoding="utf-8")

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
    assert "[开发 Agent 必读](docs/agent/DEVELOPMENT_AGENT.md)" in development_index
    assert "判断研究或开发" not in philosophy
    assert "$easydesign-development" in philosophy
