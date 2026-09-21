"""Runtime Target facts and narrow checks of explicit numerical identity claims."""

from __future__ import annotations

import re
from typing import Any

from .contracts import (
    TargetAssessment,
    TargetFacts,
    TargetInterpretation,
    TargetRecommendationMismatch,
)
from .session_store import compact


class HardFactContradiction(RuntimeError):
    """Scientific inconsistency; a rejected proposal, not a security violation."""

    def __init__(self, findings: list[dict[str, Any]]) -> None:
        self.findings = findings
        super().__init__("HARD_FACT_CONTRADICTION: " + compact(findings))


def check_fact_claims(value: Any, evidence: dict[str, Any]) -> None:
    """Narrow Target count checks on owner prose; not a general fact verifier.

    Structured facts cannot be supplied by the model. These patterns detect explicit count
    restatements; independent Judge/Golden review remains required for other scientific claims.
    """
    facts = TargetFacts.model_validate(evidence["hard_facts"])

    def strings(item: Any) -> list[str]:
        if isinstance(item, str):
            return [item]
        if isinstance(item, dict):
            return [s for child in item.values() for s in strings(child)]
        if isinstance(item, list):
            return [s for child in item for s in strings(child)]
        return []

    texts = strings(value)
    findings = []
    count = r"(\d+(?:/\d+)*)(?![\d/])"
    units = r"(?:residues?|aa|amino[ -]acids?)\b"
    canonical = r"\bcanonical(?:[ _-](?:protein|sequence|target|precursor))?"
    copula = r"\s*(?:(?:is|of|contains|has|comprises|equals)\s*|[=:]\s*)*"
    canonical_patterns = [
        canonical + r"[ _-]length" + copula + count,
        canonical + copula + count + r"[ -]*" + units,
        r"\b" + count + r"[ -]" + units + r"\s+canonical\b",
        r"canonical\s*(?:长度|序列长度|蛋白长度)\s*(?:为|是|：|:|=)?\s*" + count,
    ]
    for pattern in canonical_patterns:
        for match in (
            match for text in texts for match in re.finditer(pattern, text, re.IGNORECASE)
        ):
            claimed = [int(number) for number in match[1].split("/")]
            if facts.canonical_length is None or any(
                number != facts.canonical_length for number in claimed
            ):
                findings.append(
                    {
                        "field": "canonical_length",
                        "expected": facts.canonical_length
                        if facts.canonical_length is not None
                        else "unresolved",
                        "claimed": match[1],
                        "statement": match[0],
                    }
                )
    for chain in facts.chains:
        for label, expected in (
            ("construct", chain.construct_length),
            ("observed", chain.observed_length),
        ):
            if expected is None:
                continue
            prefix = rf"\bchain\s+{re.escape(chain.auth_chain)}\s*[,;:]?\s+{label}"
            patterns = [
                prefix + r"\s+length" + copula + count,
                prefix + copula + count + r"[ -]*" + units,
            ]
            for match in (
                match
                for pattern in patterns
                for text in texts
                for match in re.finditer(pattern, text, re.IGNORECASE)
            ):
                if any(int(n) != expected for n in match[1].split("/")):
                    findings.append(
                        {
                            "field": f"chain.{chain.auth_chain}.{label}_length",
                            "expected": expected,
                            "claimed": match[1],
                            "statement": match[0],
                        }
                    )
    options = [option for option in evidence.get("options", []) if option.get("eligible")]
    recommended_option = None
    if isinstance(value, dict):
        recommended_option = value.get("recommended_option")
        recommendation = value.get("recommendation")
        if recommended_option is None and isinstance(recommendation, dict):
            recommended_option = recommendation.get("option_id")
    resolutions: dict[str, float] = {}
    summaries: dict[str, dict[str, Any]] = {}
    option_tokens: dict[str, set[str]] = {}
    for option in options:
        option_id = str(option.get("option_id"))
        summary = option.get("payload", {}).get("candidate_summary", {})
        summaries[option_id] = summary
        resolution = summary.get("resolution_angstrom")
        if isinstance(resolution, int | float) and not isinstance(resolution, bool):
            resolutions[option_id] = float(resolution)
        tokens = {option_id.lower()}
        pdb_id = option.get("payload", {}).get("pdb_id")
        if isinstance(pdb_id, str):
            tokens.add(pdb_id.lower())
        option_tokens[option_id] = tokens
    resolution_superlative = re.compile(
        r"\b(?:best|highest|finest|top)[ -](?:nominal[ -])?resolution\b|"
        r"(?:最高|最佳)(?:名义)?分辨率|分辨率(?:最高|最佳|最好)",
        re.IGNORECASE,
    )
    subset_qualifier = re.compile(
        r"\b(?:non[- ]fused|single[- ]source|clean(?:[ -]9w)?[ -]series)\b|"
        r"非融合|单一来源|干净(?:的)?(?:[ -]9w)?系列",
        re.IGNORECASE,
    )
    for text in texts:
        superlative_match = resolution_superlative.search(text)
        if superlative_match is None:
            continue
        lower_text = text.lower()
        prefix = lower_text[: superlative_match.start()]
        preceding = [
            (prefix.rfind(token), option_id)
            for option_id, tokens in option_tokens.items()
            for token in tokens
            if prefix.rfind(token) >= 0
        ]
        claimed_option: str | None
        if preceding:
            claimed_option = max(preceding)[1]
        else:
            mentioned = {
                option_id
                for option_id, tokens in option_tokens.items()
                if any(token in lower_text for token in tokens)
            }
            claimed_option = (
                next(iter(mentioned))
                if len(mentioned) == 1
                else str(recommended_option)
                if recommended_option is not None
                else None
            )
        if claimed_option not in resolutions:
            continue
        comparison = resolutions
        comparison_scope = "all eligible options"
        if subset_qualifier.search(text):
            verified_subset = {
                option_id: resolution
                for option_id, resolution in resolutions.items()
                if summaries[option_id].get("source_part_count") == 1
                and summaries[option_id].get("multiple_source_flag") != "Y"
            }
            if claimed_option in verified_subset and verified_subset:
                comparison = verified_subset
                comparison_scope = "Runtime-verified non-fused/single-source options"
        claimed_resolution = resolutions[claimed_option]
        minimum_resolution = min(comparison.values())
        if claimed_resolution > minimum_resolution + 1e-9:
            findings.append(
                {
                    "field": "structure_resolution_superlative",
                    "comparison_scope": comparison_scope,
                    "expected_minimum_angstrom": minimum_resolution,
                    "minimum_option_ids": sorted(
                        option_id
                        for option_id, resolution in comparison.items()
                        if abs(resolution - minimum_resolution) <= 1e-9
                    ),
                    "claimed_option_id": claimed_option,
                    "claimed_option_angstrom": claimed_resolution,
                    "statement": superlative_match[0],
                    "guidance": (
                        "Use the exact Runtime value and a non-superlative scientific reason "
                        "when the intended comparison subset is not deterministically represented."
                    ),
                }
            )
    if findings:
        raise HardFactContradiction(findings)


def check_interpretation(value: TargetInterpretation, evidence: dict[str, Any]) -> None:
    check_fact_claims(value.model_dump(mode="json"), evidence)
    eligible = [option["option_id"] for option in evidence.get("options", []) if option["eligible"]]
    if eligible and value.recommended_option is None:
        raise TargetRecommendationMismatch(
            "Target recommendation must name one eligible option in recommended_option"
        )
    if value.recommended_option and not any(
        o["option_id"] == value.recommended_option and o["eligible"]
        for o in evidence.get("options", [])
    ):
        raise TargetRecommendationMismatch(
            "Target recommendation names a missing/ineligible option"
        )


def register_target(bridge: Any, opinion: TargetInterpretation, revision: Any) -> dict[str, Any]:
    evidence = bridge.target_submission_evidence()
    check_interpretation(opinion, evidence)
    assessment = TargetAssessment(
        hard_facts=TargetFacts.model_validate(evidence["hard_facts"]),
        interpretation=opinion,
        source_evidence_id=evidence["source_evidence_id"],
        evidence_refs=evidence["evidence_refs"],
        selectable_options=[o["option_id"] for o in evidence.get("options", []) if o["eligible"]],
    )
    result = assessment.model_dump(mode="json")
    bridge.store.event(
        bridge.thread,
        "target-assessment",
        {
            **result,
            "revision_of_card_id": revision.card_id if revision else None,
        },
    )
    return result


def present_target(result: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
    """Display Target facts once from runtime; retain raw Coordinator prose in its event."""
    facts = TargetFacts.model_validate(evidence["hard_facts"])
    if not facts.chains:
        return result
    sentences = re.split(r"(?<=[。！？])\s*|(?<=[.!?])\s+(?=\S)|\n+", result.get("message", ""))
    commentary = [
        s
        for s in sentences
        if not re.search(
            r"\b(?:canonical|construct|observed|sequence|numbering|chain)\b|"
            r"规范序列|构建体|观测残基|序列长度",
            s,
            re.IGNORECASE,
        )
    ]
    return {
        **result,
        "message": " ".join(commentary).strip(),
        "target": {
            "facts": facts.model_dump(mode="json", exclude={"authority"}),
            "interpretation": evidence.get("target_interpretation"),
            "limitations": evidence.get("limitations", []),
        },
    }
