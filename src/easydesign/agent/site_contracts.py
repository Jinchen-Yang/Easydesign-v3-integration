"""Scientific site intent and user-supplied biology, without model-authored identities."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, model_validator

from .contracts import ShortText, StrictDTO, TargetTask
from .evidence_research import ResearchConclusion, ResearchTopic

Labels = Annotated[list[int], Field(min_length=1, max_length=40)]


class SiteSelection(StrictDTO):
    name: ShortText
    hotspot_label_seq_ids: Labels = Field(
        description="Exact approved Target design labels, taken from the supplied mapping's "
        "label_seq_id column. Canonical positions, construct positions and original source "
        "labels are different namespaces. Put the mapped values in this array, not only in "
        "the rationale; never apply an inferred offset."
    )
    rationale: ShortText
    origin: Literal["scan-derived", "literature-derived"] = "scan-derived"
    role: Literal["primary", "backup", "avoid", "unresolved"] = "primary"
    evidence_card_ids: list[str] = Field(default_factory=list, max_length=6)

    @model_validator(mode="after")
    def unique_residues(self) -> SiteSelection:
        if any(n < 1 for n in self.hotspot_label_seq_ids):
            raise ValueError("Residue labels must be positive")
        if len(set(self.hotspot_label_seq_ids)) != len(self.hotspot_label_seq_ids):
            raise ValueError("Residue labels must be unique")
        return self


class SiteIntent(StrictDTO):
    """The specialist proposes meaning and mapped labels; runtime owns the binding."""

    selected_site: SiteSelection
    positive_evidence: list[ShortText] = Field(min_length=1, max_length=5)
    mechanistic_rationale: ShortText
    accessibility_rationale: ShortText
    binder_approach: ShortText
    risks: list[ShortText] = Field(default_factory=list, max_length=5)
    uncertainty: list[ShortText] = Field(min_length=1, max_length=5)
    alternatives: list[SiteSelection] = Field(default_factory=list, max_length=2)
    recommendation: Literal["SUPPORTED", "DISCOURAGED"]
    scope: Literal["structural-exploration", "mechanistic"] = "structural-exploration"
    material_questions: list[ResearchTopic] = Field(default_factory=list, max_length=9)
    research_conclusions: list[ResearchConclusion] = Field(default_factory=list, max_length=9)

    @model_validator(mode="after")
    def research_scope(self) -> SiteIntent:
        topics = [c.topic for c in self.research_conclusions]
        if len(topics) != len(set(topics)):
            raise ValueError("One current conclusion per scientific topic")
        if not set(self.material_questions).issubset(topics):
            missing = sorted(set(self.material_questions) - set(topics))
            raise ValueError(
                "Every material question needs an explicit evidence state. Missing "
                "research_conclusions for topics: "
                + ", ".join(missing)
                + ". Add a conclusion with the exact topic, actual research status, "
                "evidence and limitations for each. Keep material questions explicit; "
                "do not add unrelated unsearched topics or invent source support."
            )
        if self.scope == "mechanistic" and not self.material_questions:
            raise ValueError("Mechanistic site selection requires active evidence research")
        return self


class SiteQuery(StrictDTO):
    label_seq_ids: list[int] = Field(default_factory=list, max_length=40)
    offset: int = Field(default=0, ge=0)


class FocusedSiteQuery(StrictDTO):
    label_seq_ids: list[int] = Field(
        default_factory=list,
        max_length=40,
        description="Omit for the approved Target and scan overview. Otherwise provide the "
        "complete exact design-label set for a scientific patch (up to forty); all requested "
        "rows are returned together. Use mapped literature or supplied scan labels. "
        "No offset: each request identifies its own complete label set.",
    )


class CanonicalMappingQuery(StrictDTO):
    canonical_positions: list[Annotated[int, Field(strict=True, ge=1)]] = Field(
        min_length=1,
        max_length=6,
        description="Up to six exact canonical positions from verified literature/database "
        "annotations. Read all corresponding rows in the already approved Target mapping; "
        "these are not design labels and no new alignment is computed.",
    )

    @model_validator(mode="after")
    def unique_positions(self) -> CanonicalMappingQuery:
        if len(set(self.canonical_positions)) != len(self.canonical_positions):
            raise ValueError("Canonical positions must be unique")
        return self


class TopologyResidue(StrictDTO):
    label_seq_id: int = Field(ge=1)
    segment: str = Field(pattern=r"^(TM[1-7]|ECL[1-3]|ICL[1-3]|N-term|C-term|ECD)$")


class BiologyFeature(StrictDTO):
    kind: Literal["glycan", "ptm", "functional", "interface", "variant", "conservation", "exclude"]
    label_seq_ids: Labels
    description: ShortText
    source: ShortText


class BiologyContext(StrictDTO):
    """Explicit scientific input, never writable by a specialist or inferred from its prose."""

    target_auth_chain: str = Field(min_length=1, max_length=16)
    target_kind: Literal["soluble", "membrane", "gpcr", "unknown"] = "unknown"
    structural_state: ShortText = "unresolved"
    state_source: ShortText = "not supplied; no state assignment from surface geometry"
    topology_source: ShortText = "not supplied"
    topology: list[TopologyResidue] = Field(default_factory=list, max_length=3000)
    features: list[BiologyFeature] = Field(default_factory=list, max_length=40)
    limitations: list[ShortText] = Field(default_factory=list, max_length=8)

    @model_validator(mode="after")
    def unique_topology(self) -> BiologyContext:
        labels = [r.label_seq_id for r in self.topology]
        if len(labels) != len(set(labels)):
            raise ValueError("A residue cannot have mutually exclusive topology assignments")
        return self


class ScientificTask(TargetTask):
    current_gate: Literal["target-structure", "site-hotspot", "design-specification"]
    scientific_context: dict[str, object] = Field(default_factory=dict)
