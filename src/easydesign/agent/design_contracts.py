"""Scientific binder intent; executable YAML semantics remain in the existing compiler."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from easydesign.orchestration.research import CdrOverride, TargetCrop

from .contracts import Identifier, ShortText, StrictDTO


class DesignArm(StrictDTO):
    name: Identifier
    hypothesis: ShortText
    rationale: ShortText
    expected_result: ShortText
    failure_interpretation: ShortText
    role: Literal["baseline", "diagnostic", "integrated-alternative", "confirmatory"]
    changed_factors: list[ShortText] = Field(min_length=1, max_length=5)
    held_constant: list[ShortText] = Field(min_length=1, max_length=5)
    # Empty conditioning means the whole approved set, not an unconditioned binder.
    binding_label_seq_ids: list[int] = Field(default_factory=list, max_length=40)
    avoid_label_seq_ids: list[int] = Field(default_factory=list, max_length=40)
    target_crop: TargetCrop | None = None
    cdr_overrides: list[CdrOverride] = Field(default_factory=list, max_length=3)
    candidates_per_scaffold: int = Field(default=40, ge=1, le=2000)


class BinderIntent(StrictDTO):
    strategy_source: Literal["standard", "expert-native"] = "standard"
    binder: Literal["VHH"]
    objective: ShortText
    approach_rationale: ShortText
    context_rationale: ShortText
    scaffold_cdr_rationale: ShortText
    arms: list[DesignArm] = Field(default_factory=list, max_length=3)
    risks: list[ShortText] = Field(default_factory=list, max_length=5)
    uncertainty: list[ShortText] = Field(min_length=1, max_length=5)
    recommendation: Literal["SUPPORTED", "DISCOURAGED"]

    @model_validator(mode="after")
    def distinct_arms(self) -> BinderIntent:
        if (self.strategy_source == "standard") != bool(self.arms):
            raise ValueError(
                "Standard requires arms; expert-native must preserve imported arms unchanged"
            )
        names = [arm.name for arm in self.arms]
        if len(names) != len(set(names)):
            raise ValueError("Design arm names must be distinct")
        return self
