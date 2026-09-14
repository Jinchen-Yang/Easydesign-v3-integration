"""Translate bounded scientific intent into the existing ResearchStrategy/compiler contract."""

from __future__ import annotations

import hashlib
from importlib import resources
from typing import Any

import yaml  # type: ignore[import-untyped]

from easydesign.orchestration.research import ResearchStrategy, StrategyVariant
from easydesign.stages.s03_boltzgen_configuration.capabilities import load_boltzgen_capabilities
from easydesign.stages.s03_boltzgen_configuration.compiler import (
    ASSET_PACKAGE,
    EXPECTED_ASSET_SHA256,
    SCAFFOLD_IDS,
)
from easydesign.stages.s03_boltzgen_configuration.scaffold_templates import (
    GPCR_MANIFEST_SHA256,
    GPCR_TEMPLATE,
    ScaffoldTemplate,
    gpcr_template,
)

from .contracts import AgentBoundaryError
from .design_contracts import BinderIntent
from .session_store import identity


def design_constraints(target_kind: str = "unknown") -> dict[str, Any]:
    root = resources.files(ASSET_PACKAGE)
    scaffolds = []
    for name in SCAFFOLD_IDS:
        raw = root.joinpath(f"{name}.yaml").read_bytes()
        if hashlib.sha256(raw).hexdigest() != EXPECTED_ASSET_SHA256[f"{name}.yaml"]:
            raise AgentBoundaryError("Official scaffold specification changed")
        spec = yaml.safe_load(raw)
        scaffolds.append(
            {
                "name": name,
                "designed_residue_ranges": spec["design"][0]["chain"]["res_index"],
                "cdr_insertion_ranges": [
                    r["insertion"]["num_residues"] for r in spec["design_insertions"]
                ],
            }
        )
    capability = load_boltzgen_capabilities()
    result: dict[str, Any] = {
        "binder": "VHH",
        "scaffold_policy": "all seven official VHH scaffolds per design arm",
        "first_pilot_candidates_per_scaffold": 40,
        "first_pilot_candidates_per_arm": 280,
        "generation_in_this_phase": "not available; validate/freeze specification only",
        "scaffolds": scaffolds,
        "backend": capability.backend,
        "version": capability.version,
        "supports": {
            field: getattr(capability.supports, field)
            for field in ("binding", "not_binding", "target_crop", "cdr_override")
        },
        "scaffold_evidence_authority": {
            "official_asset_checksums_verified": True,
            "residue_indices": "Exact design.res_index values from all seven official VHH assets",
            "numbering_scope": "Compiler scaffold residue indices, not target/canonical numbering",
            "limits": "Matching loop bounds does not establish geometric equivalence or binding",
            "default_design_semantics": "Each listed design.res_index region is designable. "
            "The three insertion ranges are design_insertions.num_residues for CDR1, "
            "CDR2 and CDR3: counts of inserted residues, NOT final CDR loop lengths. "
            "Final loop length also depends on the retained/excluded template residues; "
            "neither insertion count nor design.res_index establishes geometric reach. Keeping "
            "default bounds does not freeze loop sequence or length; the standard "
            "seven-scaffold plan is not a CDR3-only controlled experiment.",
        },
        "limitations": [
            (
                "Native expert input requires trusted import, approved target/hotspot"
                " binding and backend validation."
            ),
            "A crop/avoid list is not docking clearance or a simulated glycan/membrane barrier.",
            "Fixed first-pilot coverage can be reduced only by choosing fewer meaningful arms.",
            (
                "Sequence mutation, CDR insertion and crop must pass the existing "
                "compiler and backend."
            ),
        ],
    }
    result["default_scaffold_template"] = (
        GPCR_TEMPLATE if target_kind == "gpcr" else "official-vhh7-v1"
    )
    result["scaffold_templates"] = {
        "official-vhh7-v1": {"scaffolds": scaffolds, "owner": "binder-strategy"}
    }
    if target_kind == "gpcr":
        result["scaffolds"] = template_scaffolds(GPCR_TEMPLATE)
        result["scaffold_evidence_authority"]["residue_indices"] = (
            "Exact design.res_index values from the default GPCR Skill templates; "
            "explicit alternative templates have their own bounds below"
        )
        result["scaffold_templates"][GPCR_TEMPLATE] = {
            "owner": "binder-strategy",
            "skill_asset": "assets/gpcr-vhh7-v1",
            "manifest_sha256": GPCR_MANIFEST_SHA256,
            "scaffolds": result["scaffolds"],
            "policy": "Preferred GPCR VHH prior, not a hard rule. Each arm may explicitly "
            "select the official template or supply justified CDR/conditioning changes. "
            "Use the supplied complete configurations; do not replace their insertion "
            "counts with a uniform 3..50 or infer final CDR lengths from the archive name.",
        }
    return result


def template_scaffolds(template: ScaffoldTemplate) -> list[dict[str, Any]]:
    if template == "official-vhh7-v1":
        return list(design_constraints()["scaffolds"])
    scaffolds = []
    for name in SCAFFOLD_IDS:
        spec, digest = gpcr_template(name)
        scaffolds.append(
            {
                "name": name,
                "source_sha256": digest,
                "designed_residue_ranges": spec["design"][0]["chain"]["res_index"],
                "cdr_insertion_ranges": [
                    r["insertion"]["num_residues"] for r in spec["design_insertions"]
                ],
                "insertion_positions": [
                    r["insertion"]["res_index"] for r in spec["design_insertions"]
                ],
                "exclude": spec["exclude"],
            }
        )
    return scaffolds


def resolve_design_intent(
    intent: BinderIntent, evidence: dict[str, Any]
) -> BinderIntent:
    """Resolve Skill defaults before evaluation, persistence and independent review."""
    default = evidence["constraints"]["default_scaffold_template"]
    return intent.model_copy(
        update={
            "arms": [
                arm.model_copy(
                    update={
                        "scaffold_template": arm.scaffold_template or default,
                        "avoid_label_seq_ids": sorted(
                            set(arm.avoid_label_seq_ids) | set(evidence["approved_exclusions"])
                        ),
                    }
                )
                for arm in intent.arms
            ]
        }
    )


def strategy_from_intent(
    intent: BinderIntent, site: dict[str, Any], evidence_refs: list[str]
) -> ResearchStrategy:
    selected = site["hotspots"]["hotspot_sets"][0]
    variants = []
    for index, arm in enumerate(intent.arms, start=1):
        variants.append(
            StrategyVariant(
                id=f"arm-{index}",
                hotspot_set_id=selected["id"] if not arm.binding_label_seq_ids else None,
                binding_label_seq_ids=tuple(arm.binding_label_seq_ids)
                if arm.binding_label_seq_ids
                else None,
                avoid_label_seq_ids=tuple(arm.avoid_label_seq_ids),
                scaffold_ids=SCAFFOLD_IDS,
                scaffold_template=arm.scaffold_template or "official-vhh7-v1",
                target_crop=arm.target_crop,
                cdr_overrides=tuple(arm.cdr_overrides),
                candidates=arm.candidates_per_scaffold,
                hypothesis_id="hyp-" + identity({"statement": arm.hypothesis})[:24],
                hypothesis_statement=arm.hypothesis,
                hypothesis_basis=arm.rationale,
                role=arm.role,
                evidence_refs=tuple(evidence_refs),
                changed_factors=tuple(arm.changed_factors),
                held_constant=tuple(arm.held_constant),
                rationale=arm.rationale,
                expected_result=arm.expected_result,
                failure_interpretation=arm.failure_interpretation,
            )
        )
    return ResearchStrategy(
        schema_version="1.3",
        foundation=site["run_id"],
        protocol_kind="first-pilot",
        variants=tuple(variants),
    )


def evaluate_design(
    intent: BinderIntent,
    approved_labels: list[int],
    mapped_labels: set[int],
    upstream_warnings: list[str],
    upstream_discouraged: bool = False,
) -> dict[str, Any]:
    blockers = []
    warnings: list[str] = []
    signatures = []
    cdr_verification = []
    for arm in intent.arms:
        binding = arm.binding_label_seq_ids or approved_labels
        avoid = arm.avoid_label_seq_ids
        if not set(binding).issubset(approved_labels):
            blockers.append(f"{arm.name}: conditioning includes residues not approved at Gate 2")
        if not set(avoid).issubset(mapped_labels):
            blockers.append(f"{arm.name}: excluded residues are absent from approved mapping")
        if set(binding) & set(avoid):
            blockers.append(f"{arm.name}: binding and exclusion constraints conflict")
        if any(values != sorted(set(values)) for values in (binding, avoid)):
            blockers.append(f"{arm.name}: residue selections must be sorted and unique")
        if arm.candidates_per_scaffold != 40:
            blockers.append(f"{arm.name}: first-pilot protocol requires 40 candidates per scaffold")
        if arm.target_crop:
            crop = arm.target_crop
            if crop.end > max(mapped_labels) or any(
                n < crop.start or n > crop.end for n in [*binding, *avoid]
            ):
                blockers.append(f"{arm.name}: crop loses conditioning/exclusion or exceeds target")
            if (crop.start, crop.end) != (1, max(mapped_labels)):
                warnings.append(
                    f"{arm.name}: cropping can introduce artificial termini/context loss"
                )
        if arm.cdr_overrides:
            # A named CDR override cannot silently turn into framework redesign.
            # Bounds belong to the selected, SHA-verified Skill template.
            for override in arm.cdr_overrides:
                within_all_loops = True
                for scaffold in template_scaffolds(
                    arm.scaffold_template or "official-vhh7-v1"
                ):
                    declared = scaffold["designed_residue_ranges"].split(",")[override.cdr - 1]
                    low, high = (int(n) for n in declared.split(".."))
                    for segment in (override.design_res_index or declared).split(","):
                        values = [int(n) for n in segment.split("..")]
                        if not low <= values[0] <= values[-1] <= high:
                            within_all_loops = False
                            blockers.append(
                                f"{arm.name}: CDR{override.cdr} design leaves the declared loop "
                                f"of selected scaffold {scaffold['name']}"
                            )
                            break
                cdr_verification.append(
                    {
                        "arm": arm.name,
                        "cdr": override.cdr,
                        "design_res_index": override.design_res_index,
                        "insertion_num_residues": override.insertion_num_residues,
                        "within_declared_loop_of_all_seven_scaffolds": within_all_loops,
                        "scaffold_template": arm.scaffold_template or "official-vhh7-v1",
                        "authority": "Runtime verification against selected scaffold loop bounds",
                        "scientific_limit": "Geometry and future binding remain untested",
                    }
                )
            warnings.append(f"{arm.name}: altered CDR geometry is untested for this approved site")
        signatures.append(
            identity(
                {
                    "binding": binding,
                    "avoid": avoid,
                    "crop": arm.target_crop.model_dump() if arm.target_crop else None,
                    "cdr": [c.model_dump() for c in arm.cdr_overrides],
                    "scaffold_template": arm.scaffold_template or "official-vhh7-v1",
                }
            )
        )
    if len(signatures) != len(set(signatures)):
        warnings.append("Some arms have identical executable factors; their comparison is weak")
    discouraged = bool(
        warnings or intent.risks or upstream_discouraged or intent.recommendation == "DISCOURAGED"
    )
    warnings = list(dict.fromkeys([*upstream_warnings, *warnings, *intent.risks]))
    return {
        "status": "BLOCKED" if blockers else "DISCOURAGED" if discouraged else "SUPPORTED",
        "hard_constraints": "failed" if blockers else "passed",
        "blockers": blockers,
        "warnings": warnings,
        "planned_candidates": sum(a.candidates_per_scaffold * 7 for a in intent.arms),
        "arm_count": len(intent.arms),
        "cdr_template_validation": cdr_verification,
        "planned_strategy_count": len(intent.arms) * 7,
        "effective_arms": [arm.model_dump(mode="json") for arm in intent.arms],
        "compiler_validation": "not performed by this preflight tool",
        "generation_started": False,
    }
