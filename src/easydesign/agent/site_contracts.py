"""Scientific site intent and user-supplied biology, without model-authored identities."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, model_validator

from .contracts import ShortText, StrictDTO, TargetTask

Labels = Annotated[list[int], Field(min_length=1, max_length=40)]


class SiteSelection(StrictDTO):
    name: ShortText
    hotspot_label_seq_ids: Labels
    rationale: ShortText

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


class SiteQuery(StrictDTO):
    label_seq_ids: list[int] = Field(default_factory=list, max_length=40)
    offset: int = Field(default=0, ge=0)


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
