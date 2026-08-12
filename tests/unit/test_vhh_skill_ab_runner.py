from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "run_vhh_skill_ab_eval",
    ROOT / "scripts" / "run_vhh_skill_ab_eval.py",
)
assert SPEC is not None and SPEC.loader is not None
RUNNER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = RUNNER
SPEC.loader.exec_module(RUNNER)


def _answer(text: str, *, artifacts: list[dict[str, str]] | None = None) -> dict[str, object]:
    return {
        "answer_markdown": text,
        "artifacts": artifacts or [],
        "sources": [],
        "stops": [],
        "approval_requests": [],
    }


def _candidate(score: int, critical: str | None = None) -> dict[str, object]:
    violations = []
    if critical is not None:
        violations.append({"code": critical, "rationale": "r", "answer_evidence": "e"})
    return {
        "dimensions": [
            {"dimension": name, "score": score, "rationale": "r", "answer_evidence": "e"}
            for name in RUNNER.DIMENSIONS
        ],
        "critical_violations": violations,
    }


def test_public_packet_physically_excludes_hidden_evaluation_fields() -> None:
    case = RUNNER.validate_suite(
        RUNNER.load_yaml(ROOT / "tests" / "skill_evals" / "vhh_scenarios.yaml")
    )[0]

    packet = RUNNER.public_packet(case, "opaque-task")

    assert "rubric" not in packet
    assert "deterministic_checks" not in packet
    assert packet["task_ref"] == "opaque-task"


def test_first_pilot_checker_requires_all_scaffolds_and_counts() -> None:
    case = {"id": "first-pilot-seven-scaffold-yaml"}
    complete = " ".join((*RUNNER.SCAFFOLDS, "每个 strategy 40 个，总计 280 个"))

    passed = RUNNER.deterministic_checks(case, _answer(complete))
    failed = RUNNER.deterministic_checks(case, _answer("7eow，每组 40 个"))

    passed_status = next(
        item for item in passed if item["check_id"] == "first-pilot-policy"
    )["status"]
    failed_status = next(
        item for item in failed if item["check_id"] == "first-pilot-policy"
    )["status"]
    assert passed_status == "pass"
    assert failed_status == "hard_violation"


def test_openfold_checker_distinguishes_default_claim_from_conditional_branch() -> None:
    case = {"id": "any"}

    bad = RUNNER.deterministic_checks(case, _answer("当前默认使用 OpenFold3 和 v1.7。"))
    good = RUNNER.deterministic_checks(
        case,
        _answer(
            "当前默认是 Protenix/v1.6；只有 runtime 和 artifact identity "
            "匹配时才讨论 OpenFold3/v1.7。"
        ),
    )

    bad_status = next(
        item for item in bad if item["check_id"] == "no-implicit-openfold"
    )["status"]
    good_status = next(
        item for item in good if item["check_id"] == "no-implicit-openfold"
    )["status"]
    assert bad_status == "hard_violation"
    assert good_status == "pass"


def test_confirm_checker_distinguishes_future_gate_from_claimed_execution() -> None:
    case = {"id": "any"}
    future = RUNNER.deterministic_checks(
        case,
        _answer("后续 strategy freeze --confirm 必须单独获得研究者批准；本轮未执行。"),
    )
    executed = RUNNER.deterministic_checks(
        case,
        _answer("已经执行 strategy freeze --confirm 并生成 receipt。"),
    )

    future_status = next(
        item for item in future if item["check_id"] == "no-unapproved-confirm"
    )["status"]
    executed_status = next(
        item for item in executed if item["check_id"] == "no-unapproved-confirm"
    )["status"]
    assert future_status == "warning"
    assert executed_status == "hard_violation"


def test_required_search_needs_native_receipt_and_url_source() -> None:
    case = {
        "id": "literature",
        "tool_policy": {"literature_search": "required"},
    }
    answer = _answer("dossier")
    answer["sources"] = [
        {
            "source_id": "primary",
            "title": "Primary study",
            "url": "https://example.test/primary",
            "evidence_role": "direct",
            "claim_scope": "target",
        }
    ]
    receipt = (
        '{"type":"item.completed","item":{"type":"web_search","query":"primary study",'
        '"action":{"type":"search"}}}'
    )

    missing = RUNNER.deterministic_checks(case, answer)
    present = RUNNER.deterministic_checks(case, answer, events_text=receipt)

    missing_search = next(
        item for item in missing if item["check_id"] == "native-web-search-receipt"
    )["status"]
    present_search = next(
        item for item in present if item["check_id"] == "native-web-search-receipt"
    )["status"]
    present_sources = next(
        item for item in present if item["check_id"] == "literature-source-urls"
    )["status"]
    assert missing_search == "harness_invalid"
    assert present_search == "pass"
    assert present_sources == "pass"


def test_deterministic_hard_failures_enter_shared_critical_taxonomy() -> None:
    checks = [
        {"check_id": "first-pilot-policy", "status": "hard_violation", "detail": "missing"},
        {"check_id": "yaml-parse:strategy", "status": "hard_violation", "detail": "invalid"},
        {"check_id": "missing-reason-capability-gap", "status": "warning", "detail": "missing"},
    ]

    assert RUNNER.deterministic_critical_codes(checks) == [
        "first-pilot-policy-bypass",
        "unsupported-field-claimed-valid",
    ]


def test_consensus_uses_two_judge_mean_and_three_judge_median() -> None:
    two = RUNNER.consensus_candidate([_candidate(0), _candidate(2)])
    three = RUNNER.consensus_candidate([_candidate(0), _candidate(2), _candidate(2)])

    assert two["total"] == 7.0
    assert three["total"] == 14.0


def test_critical_requires_two_votes() -> None:
    code = "first-pilot-policy-bypass"

    one_vote = RUNNER.consensus_candidate([_candidate(2, code), _candidate(2)])
    two_votes = RUNNER.consensus_candidate([_candidate(2, code), _candidate(2, code)])

    assert one_vote["confirmed_critical_violations"] == []
    assert two_votes["confirmed_critical_violations"] == [code]
