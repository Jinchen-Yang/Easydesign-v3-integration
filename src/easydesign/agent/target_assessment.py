"""Runtime Target facts and narrow checks of explicit numerical identity claims."""

from __future__ import annotations

import re
from typing import Any

from .contracts import AgentBoundaryError, TargetAssessment, TargetFacts, TargetInterpretation
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

    text = " ".join(strings(value))
    findings = []
    canonical_patterns = [
        r"\bcanonical(?:[ _-](?:protein|sequence|target|precursor))?(?:[ _-]length)?"
        r"\s*(?:(?:is|of|contains|has|comprises|equals|length)\s*|[=:]\s*)*(\d+(?:/\d+)*)",
        r"\b(\d+(?:/\d+)*)[ -](?:residue|aa|amino[ -]acid)s?\s+canonical\b",
        r"canonical\s*(?:长度|序列长度|蛋白长度)\s*(?:为|是|：|:|=)?\s*(\d+(?:/\d+)*)",
    ]
    if facts.canonical_length is not None:
        for pattern in canonical_patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                if any(int(n) != facts.canonical_length for n in match[1].split("/")):
                    findings.append(
                        {
                            "field": "canonical_length",
                            "expected": facts.canonical_length,
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
            pattern = (
                rf"\bchain\s+{re.escape(chain.auth_chain)}\s*[,;:]?\s+"
                rf"{label}(?:\s+length)?\s*(?:(?:is|has|of|contains)\s*|[=:]\s*)*(\d+)"
            )
            for match in re.finditer(pattern, text, re.IGNORECASE):
                if int(match[1]) != expected:
                    findings.append(
                        {
                            "field": f"chain.{chain.auth_chain}.{label}_length",
                            "expected": expected,
                            "claimed": match[1],
                            "statement": match[0],
                        }
                    )
    if findings:
        raise HardFactContradiction(findings)


def check_interpretation(value: TargetInterpretation, evidence: dict[str, Any]) -> None:
    check_fact_claims(value.model_dump(mode="json"), evidence)
    if value.recommended_option and not any(
        o["option_id"] == value.recommended_option and o["eligible"]
        for o in evidence.get("options", [])
    ):
        raise AgentBoundaryError("Target recommendation names a missing/ineligible option")


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
    sentences = re.split(r"(?<=[.!?。！？])\s*|\n", result.get("message", ""))
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
