"""Scientific site intent and user-supplied biology, without model-authored identities."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import Field, SerializerFunctionWrapHandler, model_serializer, model_validator

from .contracts import ShortText, StrictDTO, TargetTask

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


class SitePortfolioEntry(StrictDTO):
    """Runtime-bound membership with the Site specialist's relative interpretation."""

    candidate_id: str
    rank: Literal["A", "B", "C"] | None
    selectable: bool
    site: SiteSelection
    why_ranked: ShortText
    mechanistic_rationale: ShortText
    approach_rationale: ShortText
    supporting_evidence: list[ShortText] = Field(min_length=1, max_length=3)
    major_risks: list[ShortText] = Field(default_factory=list, max_length=4)
    uncertainty: list[ShortText] = Field(min_length=1, max_length=4)
    confidence: Literal["low", "medium", "high"]
    hard_block: str | None = None
    preference_group: int | None = Field(default=None, ge=1, le=3)
    tied_with_candidate_id: str | None = None
    tie_reason: ShortText | None = None

    @model_validator(mode="after")
    def consistent_eligibility(self) -> SitePortfolioEntry:
        if self.selectable != (self.rank is not None) or self.selectable == bool(self.hard_block):
            raise ValueError("Only hard-valid candidates have a rank and are selectable")
        return self


class SiteIntent(StrictDTO):
    """Runtime hydration of the SiteDecision; research opinions live only in its dossier."""

    portfolio: list[SitePortfolioEntry] | None = Field(default=None, min_length=1, max_length=3)
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
    avoid_label_seq_ids: list[int] = Field(default_factory=list, max_length=40)

    @model_serializer(mode="wrap")
    def serialize_portfolio(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        value: dict[str, Any] = handler(self)
        if self.portfolio is None:
            value.pop("portfolio", None)
        return value

    @model_validator(mode="after")
    def exclusion_constraints(self) -> SiteIntent:
        if self.portfolio is not None:
            ids = [entry.candidate_id for entry in self.portfolio]
            ranked = [entry for entry in self.portfolio if entry.selectable]
            if len(ids) != len(set(ids)) or [entry.rank for entry in ranked] != list(
                "ABC"[: len(ranked)]
            ):
                raise ValueError("Portfolio IDs are unique and selectable ranks are consecutive")
            if ranked and ranked[0].site != self.selected_site:
                raise ValueError("Default Site must be the first ranked candidate")
            if any(
                set(entry.site.hotspot_label_seq_ids) & set(self.avoid_label_seq_ids)
                for entry in ranked
            ):
                raise ValueError("Selectable candidate violates an explicit exclusion")
            return self
        if set(self.selected_site.hotspot_label_seq_ids) & set(self.avoid_label_seq_ids):
            raise ValueError("Selected hotspot conflicts with declared avoid-residue constraint")
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
    required_site_compartment: Literal["extracellular", "intracellular"] | None = None
    topology_source: ShortText = "not supplied"
    topology: list[TopologyResidue] = Field(default_factory=list, max_length=3000)
    features: list[BiologyFeature] = Field(default_factory=list, max_length=40)
    limitations: list[ShortText] = Field(default_factory=list, max_length=8)

    @model_serializer(mode="wrap")
    def serialize_compartment(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        value: dict[str, Any] = handler(self)
        if self.required_site_compartment is None:
            value.pop("required_site_compartment", None)
        return value

    @model_validator(mode="after")
    def unique_topology(self) -> BiologyContext:
        labels = [r.label_seq_id for r in self.topology]
        if len(labels) != len(set(labels)):
            raise ValueError("A residue cannot have mutually exclusive topology assignments")
        return self


class ScientificTask(TargetTask):
    current_gate: Literal["target-structure", "site-hotspot", "design-specification"]
    scientific_context: dict[str, object] = Field(default_factory=dict)
