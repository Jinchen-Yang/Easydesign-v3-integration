"""ChatPyMol-compatible PML Skill routing.

The source texts are vendored from ChatPyMol commit
43517d2dc0795357f35f93a2bde8cfc442f568c5.  EasyDesign intentionally keeps
the original keyword router: safe-pml is always included and at most two
additional skills are selected from the current user message.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import NamedTuple


class PmlSkill(NamedTuple):
    skill_id: str
    title: str
    instructions: str


_SKILL_ROOT = Path(__file__).with_name("pml_skill_library")
_SKILL_INDEX: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("safe-pml", ()),
    ("ligand-pocket", ("配体", "口袋", "ligand", "pocket", "结合位点", "活性位点")),
    ("chain-coloring", ("按链", "链着色", "chain", "color", "颜色", "配色")),
    (
        "publication-figure",
        (
            "论文",
            "发表",
            "publication",
            "figure",
            "白底",
            "高清",
            "出图",
            "好看",
            "美观",
            "高级",
            "配色方案",
            "视觉",
            "标签方案",
        ),
    ),
    (
        "structure-alignment",
        ("比对", "叠合", "对齐", "align", "super", "cealign", "merge", "合并"),
    ),
    ("interface-analysis", ("界面", "interface", "接触", "相互作用", "蛋白复合物")),
)


def _strip_front_matter(source: str) -> tuple[str, str]:
    lines = source.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("PML Skill 缺少 YAML front matter")
    try:
        end = lines.index("---", 1)
    except ValueError as error:
        raise ValueError("PML Skill front matter 未闭合") from error
    metadata: dict[str, str] = {}
    for line in lines[1:end]:
        key, separator, value = line.partition(":")
        if separator:
            metadata[key.strip()] = value.strip()
    title = metadata.get("title")
    skill_id = metadata.get("id")
    if not title or not skill_id:
        raise ValueError("PML Skill 必须声明 id 和 title")
    return title, "\n".join(lines[end + 1 :]).strip()


@lru_cache(maxsize=1)
def load_pml_skills() -> dict[str, PmlSkill]:
    result: dict[str, PmlSkill] = {}
    for skill_id, _keywords in _SKILL_INDEX:
        source = (_SKILL_ROOT / skill_id / "SKILL.md").read_text(encoding="utf-8")
        title, instructions = _strip_front_matter(source)
        result[skill_id] = PmlSkill(
            skill_id=skill_id,
            title=title,
            instructions=instructions,
        )
    return result


def select_pml_skills(message: str) -> tuple[PmlSkill, ...]:
    all_skills = load_pml_skills()
    text = str(message).lower()
    selected = [all_skills["safe-pml"]]
    for skill_id, keywords in _SKILL_INDEX[1:]:
        if any(keyword.lower() in text for keyword in keywords):
            selected.append(all_skills[skill_id])
    return tuple(selected[:3])


def render_pml_skills(skills: tuple[PmlSkill, ...]) -> str:
    return "\n\n".join(
        f"### 技能：{skill.title}（{skill.skill_id}）\n{skill.instructions}"
        for skill in skills
    )
