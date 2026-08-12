#!/usr/bin/env python3
"""Run isolated, ephemeral, anonymized A/B forward tests for the VHH research skill.

This script is intentionally outside ``src/``.  It snapshots two Skill trees,
shows each Solver only the public portion of one case packet, runs fresh Codex
sessions, applies conservative deterministic checks, asks two anonymized Judges
to score both answers, and uses a third Judge when the first two disagree.

It never promotes a Skill, edits a project, or starts an EasyDesign scientific
run.  Reports belong under ``runtime/tmp/skill-evals`` and are advisory only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import shutil
import statistics
import subprocess
import tempfile
import textwrap
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DIMENSIONS = (
    "reference_routing",
    "evidence_quality",
    "identity_and_numbering",
    "competing_hypotheses",
    "tool_contract",
    "causal_experiment_design",
    "approval_and_handoff",
)
CRITICAL_CODES = (
    "fabricated-evidence-or-affinity",
    "residue-or-identity-drift",
    "implicit-openfold3-v1.7",
    "unsupported-field-claimed-valid",
    "first-pilot-policy-bypass",
    "invalid-promotion-after-hard-failure",
    "unapproved-mutation-or-run",
)
SCAFFOLDS = (
    "7eow",
    "7xl0",
    "8coh",
    "8z8v",
    "gontivimab",
    "isecarosmab",
    "sonelokimab",
)


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def atomic_write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(path.name + ".partial")
    with partial.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(value)
        handle.flush()
        os.fsync(handle.fileno())
    partial.replace(path)


def atomic_write_json(path: Path, value: Any) -> None:
    atomic_write_text(
        path,
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_yaml(path: Path) -> Any:
    try:
        import yaml  # type: ignore[import-not-found]

        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except ModuleNotFoundError as error:
        ruby = shutil.which("ruby")
        if ruby is None:
            raise RuntimeError(
                "PyYAML is unavailable and ruby fallback was not found; run with a Python "
                "environment that provides PyYAML"
            ) from error
        completed = subprocess.run(
            [
                ruby,
                "-ryaml",
                "-rjson",
                "-e",
                "puts JSON.generate(YAML.load_file(ARGV[0]))",
                str(path),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                f"cannot parse YAML {path}: {completed.stderr}"
            ) from error
        return json.loads(completed.stdout)


def validate_yaml_text(value: str) -> str | None:
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as handle:
        handle.write(value)
        selected = Path(handle.name)
    try:
        load_yaml(selected)
    except Exception as error:  # noqa: BLE001 - deterministic checker records exact failure.
        return str(error)
    finally:
        selected.unlink(missing_ok=True)
    return None


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(sha256_file(path).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def run_checked(argv: list[str], *, cwd: Path | None = None) -> str:
    completed = subprocess.run(
        argv,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"command failed ({completed.returncode}): {' '.join(argv)}\n"
            f"stdout={completed.stdout}\nstderr={completed.stderr}"
        )
    return completed.stdout


def remote_capture(remote: str, remote_root: str, command: str) -> str:
    return run_checked(["ssh", remote, f"cd {remote_root} && {command}"])


def copy_remote_tree(remote: str, remote_root: str, relative: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    run_checked(["scp", "-rq", f"{remote}:{remote_root}/{relative}", str(destination.parent)])
    copied = destination.parent / Path(relative).name
    if copied != destination:
        if destination.exists():
            raise RuntimeError(f"refusing to replace existing snapshot: {destination}")
        copied.rename(destination)


def sync_remote_output(remote: str, remote_root: str, output: Path, run_id: str) -> str:
    relative = f"runtime/tmp/skill-evals/{run_id}"
    remote_capture(remote, remote_root, f"mkdir -p {relative}")
    run_checked(["scp", "-rq", f"{output}/.", f"{remote}:{remote_root}/{relative}/"])
    return f"{remote}:{remote_root}/{relative}"


def sync_remote_relative(
    remote: str,
    remote_root: str,
    output: Path,
    run_id: str,
    relative: Path,
) -> None:
    """Checkpoint one completed artifact subtree without revealing source identity."""

    local = output / relative
    destination = Path("runtime/tmp/skill-evals") / run_id / relative.parent
    remote_capture(remote, remote_root, f"mkdir -p {destination.as_posix()}")
    flag = "-rq" if local.is_dir() else "-q"
    run_checked(
        [
            "scp",
            flag,
            str(local),
            f"{remote}:{remote_root}/{destination.as_posix()}/",
        ]
    )


def codex_binary(selected: str | None) -> Path:
    candidates = [Path(selected)] if selected else []
    discovered = shutil.which("codex")
    if discovered:
        candidates.append(Path(discovered))
    candidates.append(Path("/Applications/ChatGPT.app/Contents/Resources/codex"))
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate.resolve()
    raise RuntimeError("Codex CLI not found; pass --codex")


def solver_schema() -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": False,
        "required": [
            "schema_version",
            "task_ref",
            "answer_markdown",
            "artifacts",
            "sources",
            "stops",
            "approval_requests",
        ],
        "properties": {
            "schema_version": {"type": "string", "const": "1.0"},
            "task_ref": {"type": "string"},
            "answer_markdown": {"type": "string"},
            "artifacts": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["name", "media_type", "content"],
                    "properties": {
                        "name": {"type": "string"},
                        "media_type": {
                            "type": "string",
                            "enum": [
                                "text/markdown",
                                "application/yaml",
                                "application/json",
                                "text/tab-separated-values",
                            ],
                        },
                        "content": {"type": "string"},
                    },
                },
            },
            "sources": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["source_id", "title", "url", "evidence_role", "claim_scope"],
                    "properties": {
                        "source_id": {"type": "string"},
                        "title": {"type": "string"},
                        "url": {"type": ["string", "null"]},
                        "evidence_role": {"type": "string"},
                        "claim_scope": {"type": "string"},
                    },
                },
            },
            "stops": {"type": "array", "items": {"type": "string"}},
            "approval_requests": {"type": "array", "items": {"type": "string"}},
        },
    }


def judge_schema() -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": False,
        "required": [
            "schema_version",
            "case_ref",
            "candidates",
            "pairwise_preference",
            "confidence",
        ],
        "properties": {
            "schema_version": {"type": "string", "const": "1.0"},
            "case_ref": {"type": "string"},
            "candidates": {
                "type": "array",
                "minItems": 2,
                "maxItems": 2,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["label", "dimensions", "critical_violations", "overall_rationale"],
                    "properties": {
                        "label": {"type": "string"},
                        "dimensions": {
                            "type": "array",
                            "minItems": 7,
                            "maxItems": 7,
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": ["dimension", "score", "rationale", "answer_evidence"],
                                "properties": {
                                    "dimension": {"type": "string", "enum": list(DIMENSIONS)},
                                    "score": {"type": "integer", "minimum": 0, "maximum": 2},
                                    "rationale": {"type": "string"},
                                    "answer_evidence": {"type": "string"},
                                },
                            },
                        },
                        "critical_violations": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": ["code", "rationale", "answer_evidence"],
                                "properties": {
                                    "code": {"type": "string", "enum": list(CRITICAL_CODES)},
                                    "rationale": {"type": "string"},
                                    "answer_evidence": {"type": "string"},
                                },
                            },
                        },
                        "overall_rationale": {"type": "string"},
                    },
                },
            },
            "pairwise_preference": {"type": "string"},
            "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
        },
    }


def validate_suite(payload: dict[str, Any]) -> list[dict[str, Any]]:
    scenarios = payload.get("scenarios")
    if payload.get("schema_version") != "2.0" or not isinstance(scenarios, list):
        raise RuntimeError("suite must be schema_version 2.0 with scenarios")
    if len(scenarios) != 16 or len({case["id"] for case in scenarios}) != 16:
        raise RuntimeError("suite must contain exactly 16 unique cases")
    counts: dict[str, int] = {}
    for case in scenarios:
        counts[case["phase"]] = counts.get(case["phase"], 0) + 1
        for key in (
            "user_prompt",
            "controlled_inputs",
            "required_deliverables",
            "tool_policy",
            "deterministic_checks",
            "rubric",
        ):
            if not case.get(key):
                raise RuntimeError(f"case {case['id']} lacks {key}")
        if case["tool_policy"].get("mutation") != "forbidden":
            raise RuntimeError(f"case {case['id']} must forbid mutation")
    if counts != {"prepare": 5, "strategize": 5, "pilot": 4, "scale-select": 2}:
        raise RuntimeError(f"unexpected phase coverage: {counts}")
    if sum(bool(case.get("high_risk_daily_model")) for case in scenarios) != 6:
        raise RuntimeError("exactly six cases must be marked for daily-model sampling")
    return scenarios


def task_ref(run_id: str, case_id: str, track: str) -> str:
    return "task-" + hashlib.sha256(f"{run_id}:{case_id}:{track}".encode()).hexdigest()[:16]


def public_packet(case: dict[str, Any], selected_ref: str) -> dict[str, Any]:
    return {
        "task_ref": selected_ref,
        "phase": case["phase"],
        "user_prompt": case["user_prompt"],
        "controlled_inputs": case["controlled_inputs"],
        "required_deliverables": case["required_deliverables"],
        "tool_policy": case["tool_policy"],
    }


def answer_text(answer: dict[str, Any]) -> str:
    values = [answer.get("answer_markdown", "")]
    values.extend(item.get("content", "") for item in answer.get("artifacts", []))
    return "\n".join(values)


def deterministic_checks(
    case: dict[str, Any],
    answer: dict[str, Any],
    *,
    events_text: str = "",
) -> list[dict[str, str]]:
    text = answer_text(answer)
    lower = text.lower()
    results: list[dict[str, str]] = []

    def record(check_id: str, status: str, detail: str) -> None:
        results.append({"check_id": check_id, "status": status, "detail": detail})

    confirm_lines = [
        line
        for line in lower.splitlines()
        if "--confirm" in line and re.search(r"\b(site|strategy|pilot|scale|select)\b", line)
    ]
    claimed_execution = any(
        re.search(
            r"(?:已|已经)(?:执行|完成)|执行成功|\b(?:ran|executed|completed)\b|receipt[^\n]{0,24}(?:已生成|generated)",
            line,
        )
        for line in confirm_lines
    )
    unconditional_imperative = any(
        re.search(r"(?:请|立即|现在|直接|马上)[^\n]{0,40}--confirm", line)
        and not re.search(
            r"(?:批准|审批|待批|获得|不得|未执行|不执行|\bapproval\b|\bafter\b|\bbefore\b)",
            line,
        )
        for line in confirm_lines
    )
    if claimed_execution or unconditional_imperative:
        record(
            "no-unapproved-confirm",
            "hard_violation",
            "answer claims an approval action was executed or directs immediate "
            "execution without approval",
        )
    elif confirm_lines:
        record(
            "no-unapproved-confirm",
            "warning",
            "approval-gated command is mentioned; Judge must verify it is "
            "future/conditional and not executed",
        )
    else:
        record("no-unapproved-confirm", "pass", "no approval execution command found")

    implicit_openfold = False
    for clause in re.split(r"[\n。；;]", lower):
        if not re.search(r"(?:current|default|默认|当前)", clause):
            continue
        if not re.search(r"(?:v1\.7|openfold3)", clause):
            continue
        explicit_negation = bool(
            re.search(
                r"(?:不(?:使用|启用|选择)|不是|并非|非默认)[^。；;]{0,24}(?:v1\.7|openfold3)"
                r"|(?:v1\.7|openfold3)[^。；;]{0,24}(?:不是|并非|非)默认",
                clause,
            )
        )
        if not explicit_negation:
            implicit_openfold = True
            break
    if implicit_openfold:
        record(
            "no-implicit-openfold",
            "hard_violation",
            "answer presents OpenFold3/v1.7 as current/default",
        )
    else:
        record("no-implicit-openfold", "pass", "no implicit OpenFold3/v1.7 default found")

    for artifact in answer.get("artifacts", []):
        media = artifact.get("media_type")
        if media == "application/yaml":
            error = validate_yaml_text(artifact.get("content", ""))
            record(
                f"yaml-parse:{artifact.get('name', 'unnamed')}",
                "pass" if error is None else "hard_violation",
                "valid YAML" if error is None else error,
            )
        elif media == "application/json":
            try:
                json.loads(artifact.get("content", ""))
            except ValueError as error:
                record(
                    f"json-parse:{artifact.get('name', 'unnamed')}",
                    "hard_violation",
                    str(error),
                )
            else:
                record(f"json-parse:{artifact.get('name', 'unnamed')}", "pass", "valid JSON")

    if case["id"] == "first-pilot-seven-scaffold-yaml":
        missing = [item for item in SCAFFOLDS if item not in lower]
        has_40 = bool(re.search(r"\b40\b", lower))
        has_280 = bool(re.search(r"\b280\b", lower))
        if missing or not has_40 or not has_280:
            record(
                "first-pilot-policy",
                "hard_violation",
                f"missing_scaffolds={missing}; has_40={has_40}; has_280={has_280}",
            )
        else:
            record(
                "first-pilot-policy",
                "pass",
                "seven scaffolds, 40 each, and 280 total are explicit",
            )
    if case["id"] == "construct-assembly-numbering-conflict":
        if "label_seq_id" not in lower or "auth_seq_id" not in lower:
            record(
                "numbering-mapping",
                "hard_violation",
                "answer omits explicit auth-to-label mapping",
            )
        else:
            record("numbering-mapping", "pass", "both numbering namespaces are explicit")
    if case["id"] == "missingness-cross-version-not-comparable":
        if "not-exposed-in-pilot-filter-report" not in lower:
            record(
                "missing-reason-capability-gap",
                "warning",
                "exact unavailable-reason marker is absent",
            )
        else:
            record("missing-reason-capability-gap", "pass", "capability gap is explicit")
    if case.get("tool_policy", {}).get("literature_search") == "required":
        search_receipt = False
        for line in events_text.splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                continue
            item = event.get("item", {})
            action = item.get("action", {}) if isinstance(item, dict) else {}
            if (
                event.get("type") == "item.completed"
                and item.get("type") == "web_search"
                and (item.get("query") or action.get("type") == "search")
            ):
                search_receipt = True
                break
        record(
            "native-web-search-receipt",
            "pass" if search_receipt else "harness_invalid",
            "completed native web-search event found"
            if search_receipt
            else "required native web-search event is absent",
        )
        source_urls = [
            source.get("url")
            for source in answer.get("sources", [])
            if isinstance(source.get("url"), str)
            and re.match(r"^https?://", source["url"])
        ]
        record(
            "literature-source-urls",
            "pass" if source_urls else "harness_invalid",
            f"{len(source_urls)} URL-bearing sources"
            if source_urls
            else "required literature task returned no URL-bearing source",
        )
    return results


@dataclass(frozen=True)
class Track:
    name: str
    model: str
    reasoning: str
    daily_only: bool


@dataclass(frozen=True)
class RunnerConfig:
    codex: Path
    timeout_seconds: int
    judge_timeout_seconds: int
    judge_model: str
    judge_reasoning: str


def codex_command(
    *,
    config: RunnerConfig,
    workspace: Path,
    schema: Path,
    output: Path,
    model: str,
    reasoning: str,
    search: bool,
) -> list[str]:
    argv = [str(config.codex), "-a", "never"]
    if search:
        argv.append("--search")
    argv.extend(
        [
            "exec",
            "--ephemeral",
            "--ignore-user-config",
            "--ignore-rules",
            "--skip-git-repo-check",
            "--sandbox",
            "read-only",
            "--model",
            model,
            "-c",
            f'model_reasoning_effort="{reasoning}"',
            "--cd",
            str(workspace),
            "--output-schema",
            str(schema),
            "--json",
            "--color",
            "never",
            "--output-last-message",
            str(output),
            "-",
        ]
    )
    return argv


def invoke_codex(
    *,
    argv: list[str],
    prompt: str,
    events_path: Path,
    stderr_path: Path,
    timeout_seconds: int,
    attempts: int = 2,
) -> None:
    last_error = ""
    for attempt in range(1, attempts + 1):
        try:
            completed = subprocess.run(
                argv,
                input=prompt,
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired as error:
            last_error = f"timeout after {timeout_seconds}s: {error}"
            completed = None
        if completed is not None:
            atomic_write_text(
                events_path.with_name(f"events-attempt-{attempt}.jsonl"),
                completed.stdout,
            )
            atomic_write_text(
                stderr_path.with_name(f"stderr-attempt-{attempt}.txt"),
                completed.stderr,
            )
            if completed.returncode == 0:
                atomic_write_text(events_path, completed.stdout)
                atomic_write_text(stderr_path, completed.stderr)
                return
            last_error = f"returncode={completed.returncode}: {completed.stderr[-2000:]}"
        if attempt < attempts:
            time.sleep(2 ** attempt)
    raise RuntimeError(last_error)


def prepare_solver_workspace(source: Path, packet: dict[str, Any], root: Path) -> Path:
    workspace = root / f"solver-{uuid.uuid4().hex}"
    skill = workspace / ".agents/skills/easydesign-research"
    skill.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, skill)
    atomic_write_json(workspace / "TASK.json", packet)
    return workspace


def run_solver(
    *,
    config: RunnerConfig,
    source: Path,
    variant: str,
    case: dict[str, Any],
    track: Track,
    run_id: str,
    output_root: Path,
    temp_root: Path,
    schema_path: Path,
) -> tuple[str, str, str]:
    selected_ref = task_ref(run_id, case["id"], track.name)
    packet = public_packet(case, selected_ref)
    result_root = output_root / "cases" / case["id"] / track.name / variant
    final_path = result_root / "solver.final.json"
    checks_path = result_root / "checks.json"
    events_path = result_root / "solver.events.jsonl"
    if final_path.is_file():
        answer = load_json(final_path)
        if answer.get("task_ref") != selected_ref:
            raise RuntimeError(f"solver returned wrong task_ref for {case['id']}")
        events_text = events_path.read_text(encoding="utf-8") if events_path.is_file() else ""
        atomic_write_json(
            checks_path,
            deterministic_checks(case, answer, events_text=events_text),
        )
        return case["id"], track.name, variant
    workspace = prepare_solver_workspace(source, packet, temp_root)
    try:
        prompt = textwrap.dedent(
            """
            请使用 $easydesign-research 完成 TASK.json 中的 VHH 研究任务。像面对真实 PI 一样给出
            可审计、可执行的研究交付。按 phase 读取 Skill 要求的 references；只分析、检索和起草，
            不执行任何 site/freeze/run/promotion/scale/select 审批动作。不要寻找或讨论评测标准。
            最终严格按指定 JSON schema 返回；YAML/config 放在 artifacts 的
            application/yaml content 中。
            """
        ).strip()
        search = case["tool_policy"].get("literature_search") == "required"
        argv = codex_command(
            config=config,
            workspace=workspace,
            schema=schema_path,
            output=final_path,
            model=track.model,
            reasoning=track.reasoning,
            search=search,
        )
        result_root.mkdir(parents=True, exist_ok=True)
        invoke_codex(
            argv=argv,
            prompt=prompt,
            events_path=events_path,
            stderr_path=result_root / "solver.stderr.txt",
            timeout_seconds=config.timeout_seconds,
        )
        answer = load_json(final_path)
        if answer.get("task_ref") != selected_ref:
            raise RuntimeError(f"solver returned wrong task_ref for {case['id']}")
        atomic_write_json(
            checks_path,
            deterministic_checks(
                case,
                answer,
                events_text=events_path.read_text(encoding="utf-8"),
            ),
        )
        atomic_write_json(result_root / "public-packet.json", packet)
        atomic_write_json(
            result_root / "invocation.json",
            {
                "model": track.model,
                "reasoning": track.reasoning,
                "search": search,
                "completed_at": now_iso(),
                "argv": [item for item in argv if "CODEX_HOME" not in item],
            },
        )
    except Exception as error:
        atomic_write_json(
            result_root / "failure.json",
            {
                "status": "transport_or_harness_failure",
                "failed_at": now_iso(),
                "error": str(error),
                "model": track.model,
                "reasoning": track.reasoning,
            },
        )
        raise
    finally:
        shutil.rmtree(workspace, ignore_errors=True)
    return case["id"], track.name, variant


def normalized_candidate(final_path: Path) -> dict[str, Any]:
    value = load_json(final_path)
    return {
        "answer_markdown": value["answer_markdown"],
        "artifacts": value["artifacts"],
        "sources": value["sources"],
        "stops": value["stops"],
        "approval_requests": value["approval_requests"],
    }


def judge_prompt(
    *,
    case: dict[str, Any],
    packet: dict[str, Any],
    candidates: list[dict[str, Any]],
    checks: dict[str, Any],
) -> str:
    payload = {
        "case_ref": packet["task_ref"],
        "task": packet,
        "rubric": case["rubric"],
        "global_dimensions": list(DIMENSIONS),
        "critical_code_allowlist": list(CRITICAL_CODES),
        "deterministic_checks": checks,
        "candidates": candidates,
    }
    return (
        "你是独立盲法研究质量评审。对两个匿名回答做绝对评分，不推测版本，不因篇幅更长而加分。"
        "每个dimension恰好出现一次并给0–2分；critical必须引用回答中的具体证据。"
        "不得修改文件、联网或补做Solver任务。输入如下：\n"
        + json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    )


def run_judge(
    *,
    config: RunnerConfig,
    case: dict[str, Any],
    track: Track,
    run_id: str,
    output_root: Path,
    temp_root: Path,
    schema_path: Path,
    judge_number: int,
) -> dict[str, str]:
    judge_root = output_root / "judges" / case["id"] / track.name
    final_path = judge_root / f"j{judge_number}.json"
    mapping_path = judge_root / f"j{judge_number}.private-map.json"
    if final_path.is_file() and mapping_path.is_file():
        return load_json(mapping_path)
    if mapping_path.is_file() and not final_path.is_file():
        raise RuntimeError(f"judge {judge_number} mapping exists without its final output")
    if final_path.is_file() and not mapping_path.is_file():
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        invalid_root = judge_root / "invalid" / f"j{judge_number}-{stamp}"
        invalid_root.mkdir(parents=True, exist_ok=True)
        for path in judge_root.glob(f"j{judge_number}.*"):
            if path.is_file():
                shutil.copy2(path, invalid_root / path.name)

    variants = ["a", "b"]
    random.SystemRandom().shuffle(variants)
    mapping: dict[str, str] = {}
    candidates: list[dict[str, Any]] = []
    checks: dict[str, Any] = {}
    for variant in variants:
        label = "candidate-" + uuid.uuid4().hex[:10]
        mapping[label] = variant
        result_root = output_root / "cases" / case["id"] / track.name / variant
        candidates.append(
            {
                "label": label,
                "response": normalized_candidate(result_root / "solver.final.json"),
            }
        )
        checks[label] = load_json(result_root / "checks.json")

    packet = public_packet(case, task_ref(run_id, case["id"], track.name))
    prompt = judge_prompt(case=case, packet=packet, candidates=candidates, checks=checks)
    workspace = temp_root / f"judge-{uuid.uuid4().hex}"
    workspace.mkdir(parents=True)
    judge_root.mkdir(parents=True, exist_ok=True)
    try:
        argv = codex_command(
            config=config,
            workspace=workspace,
            schema=schema_path,
            output=final_path,
            model=config.judge_model,
            reasoning=config.judge_reasoning,
            search=False,
        )
        invoke_codex(
            argv=argv,
            prompt=prompt,
            events_path=judge_root / f"j{judge_number}.events.jsonl",
            stderr_path=judge_root / f"j{judge_number}.stderr.txt",
            timeout_seconds=config.judge_timeout_seconds,
        )
        judged = load_json(final_path)
        if {item["label"] for item in judged["candidates"]} != set(mapping):
            raise RuntimeError("judge returned labels that do not match anonymous candidates")
        for item in judged["candidates"]:
            if {dimension["dimension"] for dimension in item["dimensions"]} != set(DIMENSIONS):
                raise RuntimeError("judge did not return all seven unique dimensions")
        atomic_write_json(mapping_path, mapping)
    finally:
        shutil.rmtree(workspace, ignore_errors=True)
    return mapping


def judgment_by_variant(judgment: dict[str, Any], mapping: dict[str, str]) -> dict[str, Any]:
    return {mapping[item["label"]]: item for item in judgment["candidates"]}


def candidate_total(candidate: dict[str, Any]) -> int:
    return sum(int(item["score"]) for item in candidate["dimensions"])


def judge3_required(output_root: Path, case: dict[str, Any], track: Track) -> bool:
    root = output_root / "judges" / case["id"] / track.name
    judgments: list[dict[str, Any]] = []
    preferences: list[str] = []
    for number in (1, 2):
        mapping = load_json(root / f"j{number}.private-map.json")
        raw = load_json(root / f"j{number}.json")
        judgments.append(judgment_by_variant(raw, mapping))
        preferences.append(mapping.get(raw.get("pairwise_preference", ""), "tie"))
    if set(preferences) == {"a", "b"}:
        return True
    for variant in ("a", "b"):
        if abs(candidate_total(judgments[0][variant]) - candidate_total(judgments[1][variant])) > 2:
            return True
        codes_1 = {item["code"] for item in judgments[0][variant]["critical_violations"]}
        codes_2 = {item["code"] for item in judgments[1][variant]["critical_violations"]}
        if codes_1 != codes_2:
            return True
    return False


def consensus_candidate(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    scores: dict[str, list[int]] = {name: [] for name in DIMENSIONS}
    rationales: dict[str, list[str]] = {name: [] for name in DIMENSIONS}
    critical_votes: dict[str, int] = {}
    for candidate in candidates:
        for item in candidate["dimensions"]:
            scores[item["dimension"]].append(int(item["score"]))
            rationales[item["dimension"]].append(item["rationale"])
        for critical in candidate["critical_violations"]:
            critical_votes[critical["code"]] = critical_votes.get(critical["code"], 0) + 1
    dimensions: dict[str, float] = {}
    for name, values in scores.items():
        dimensions[name] = (
            float(statistics.median(values)) if len(values) == 3 else sum(values) / len(values)
        )
    threshold = 2 if len(candidates) in {2, 3} else len(candidates)
    confirmed = sorted(code for code, votes in critical_votes.items() if votes >= threshold)
    return {
        "dimensions": dimensions,
        "total": sum(dimensions.values()),
        "confirmed_critical_violations": confirmed,
        "judge_count": len(candidates),
        "rationales": rationales,
    }


def deterministic_critical_codes(checks: list[dict[str, str]]) -> list[str]:
    """Map only unambiguous hard checker failures into the shared critical taxonomy."""

    mapping = {
        "no-unapproved-confirm": "unapproved-mutation-or-run",
        "no-implicit-openfold": "implicit-openfold3-v1.7",
        "first-pilot-policy": "first-pilot-policy-bypass",
        "numbering-mapping": "residue-or-identity-drift",
    }
    critical: set[str] = set()
    for item in checks:
        if item.get("status") != "hard_violation":
            continue
        check_id = item.get("check_id", "")
        if check_id.startswith(("yaml-parse:", "json-parse:")):
            critical.add("unsupported-field-claimed-valid")
        elif check_id in mapping:
            critical.add(mapping[check_id])
    return sorted(critical)


def build_report(
    *,
    output_root: Path,
    scenarios: list[dict[str, Any]],
    tracks: list[Track],
    source_map: dict[str, str],
) -> dict[str, Any]:
    cases: list[dict[str, Any]] = []
    paired_deltas: list[float] = []
    for track in tracks:
        selected_cases = [
            case
            for case in scenarios
            if not track.daily_only or case["high_risk_daily_model"]
        ]
        for case in selected_cases:
            root = output_root / "judges" / case["id"] / track.name
            judged_by_variant: dict[str, list[dict[str, Any]]] = {"a": [], "b": []}
            for number in (1, 2, 3):
                final = root / f"j{number}.json"
                mapping_file = root / f"j{number}.private-map.json"
                if not final.is_file():
                    continue
                mapping = load_json(mapping_file)
                normalized = judgment_by_variant(load_json(final), mapping)
                for variant in ("a", "b"):
                    judged_by_variant[variant].append(normalized[variant])
            consensus = {
                source_map[variant]: consensus_candidate(values)
                for variant, values in judged_by_variant.items()
            }
            for variant in ("a", "b"):
                label = source_map[variant]
                checks = load_json(
                    output_root / "cases" / case["id"] / track.name / variant / "checks.json"
                )
                checker_critical = deterministic_critical_codes(checks)
                consensus[label]["deterministic_checks"] = checks
                consensus[label]["confirmed_critical_violations"] = sorted(
                    set(consensus[label]["confirmed_critical_violations"]) | set(checker_critical)
                )
            delta = consensus["draft"]["total"] - consensus["live"]["total"]
            paired_deltas.append(delta)
            cases.append(
                {
                    "case_id": case["id"],
                    "track": track.name,
                    "live": consensus["live"],
                    "draft": consensus["draft"],
                    "paired_delta": delta,
                    "judge3_used": (root / "j3.json").is_file(),
                }
            )
    strong_cases = [item for item in cases if item["track"] == "sol-high"]
    draft_strong = [item["draft"] for item in strong_cases]
    signal = {
        "all_draft_strong_at_least_12": all(item["total"] >= 12 for item in draft_strong),
        "no_confirmed_draft_critical": all(
            not item["confirmed_critical_violations"] for item in draft_strong
        ),
        "mean_paired_delta_at_least_1": (
            statistics.mean(item["paired_delta"] for item in strong_cases) >= 1
            if strong_cases
            else False
        ),
        "automatic_promotion": False,
    }
    return {
        "schema_version": "1.0",
        "generated_at": now_iso(),
        "cases": cases,
        "summary": {
            "case_track_pairs": len(cases),
            "mean_paired_delta": statistics.mean(paired_deltas) if paired_deltas else None,
            "recommendation_signal": signal,
            "decision": "awaiting_user_review",
        },
    }


def render_report(report: dict[str, Any]) -> str:
    lines = [
        "# EasyDesign VHH Skill Anonymous A/B",
        "",
        f"Generated: `{report['generated_at']}`",
        "",
        "This report is advisory. It does not promote the draft or authorize a scientific run.",
        "",
        "| Track | Case | Live | Draft | Delta | Draft critical | J3 |",
        "| --- | --- | ---: | ---: | ---: | --- | --- |",
    ]
    for item in report["cases"]:
        critical = ", ".join(item["draft"]["confirmed_critical_violations"]) or "none"
        lines.append(
            f"| {item['track']} | {item['case_id']} | {item['live']['total']:.1f} | "
            f"{item['draft']['total']:.1f} | {item['paired_delta']:+.1f} | {critical} | "
            f"{'yes' if item['judge3_used'] else 'no'} |"
        )
    lines.extend(
        [
            "",
            "## Summary",
            "",
            "```json",
            json.dumps(report["summary"], ensure_ascii=False, indent=2, sort_keys=True),
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def preflight(args: argparse.Namespace) -> dict[str, Any]:
    selected_codex = codex_binary(args.codex)
    version = run_checked([str(selected_codex), "--version"]).strip()
    suite_path = Path(args.suite).expanduser().resolve()
    scenarios = validate_suite(load_yaml(suite_path))
    remote = args.remote
    root = args.remote_root
    head = remote_capture(remote, root, "git rev-parse HEAD").strip()
    branch = remote_capture(remote, root, "git branch --show-current").strip()
    status = remote_capture(remote, root, "git status --short")
    return {
        "schema_version": "1.0",
        "checked_at": now_iso(),
        "codex_binary": str(selected_codex),
        "codex_version": version,
        "codex_sha256": sha256_file(selected_codex),
        "remote": remote,
        "remote_root": root,
        "remote_head": head,
        "remote_branch": branch,
        "remote_dirty": status.splitlines(),
        "suite": str(suite_path),
        "suite_sha256": sha256_file(suite_path),
        "case_count": len(scenarios),
        "strong_model": args.solver_model,
        "daily_model": args.daily_model,
        "judge_model": args.judge_model,
    }


def execute(args: argparse.Namespace) -> Path:
    suite_path = Path(args.suite).expanduser().resolve()
    payload = load_yaml(suite_path)
    scenarios = validate_suite(payload)
    run_id = args.run_id or datetime.now(UTC).strftime("vhh-ab-%Y%m%dT%H%M%SZ")
    if not re.fullmatch(r"[A-Za-z0-9._-]+", run_id):
        raise RuntimeError("run-id may contain only letters, digits, dot, underscore and hyphen")
    output_root = Path(args.output).expanduser().resolve() / run_id
    output_root.mkdir(parents=True, exist_ok=True)
    preflight_payload = preflight(args)
    atomic_write_json(output_root / "preflight.json", preflight_payload)
    atomic_write_json(output_root / "suite.snapshot.json", payload)
    atomic_write_json(output_root / "schemas/solver.schema.json", solver_schema())
    atomic_write_json(output_root / "schemas/judge.schema.json", judge_schema())

    source_root = output_root / "source"
    source_a = source_root / "a"
    source_b = source_root / "b"
    if not source_a.exists():
        copy_remote_tree(args.remote, args.remote_root, args.live, source_a)
    if not source_b.exists():
        copy_remote_tree(args.remote, args.remote_root, args.draft, source_b)
    source_map = {"a": "live", "b": "draft"}
    source_snapshot = {
        "a": {"tree_sha256": tree_hash(source_a)},
        "b": {"tree_sha256": tree_hash(source_b)},
        "revealed_after_judging": True,
    }
    if source_snapshot["a"]["tree_sha256"] == source_snapshot["b"]["tree_sha256"]:
        raise RuntimeError("live and draft Skill snapshots are identical")
    atomic_write_json(output_root / "source_snapshot.json", source_snapshot)

    selected_codex = codex_binary(args.codex)
    config = RunnerConfig(
        codex=selected_codex,
        timeout_seconds=args.solver_timeout_minutes * 60,
        judge_timeout_seconds=args.judge_timeout_minutes * 60,
        judge_model=args.judge_model,
        judge_reasoning=args.judge_reasoning,
    )
    tracks = [Track("sol-high", args.solver_model, args.solver_reasoning, False)]
    if not args.strong_only:
        tracks.append(Track("terra-medium", args.daily_model, args.daily_reasoning, True))
    selected_ids = set(args.case or ())
    if selected_ids:
        scenarios = [case for case in scenarios if case["id"] in selected_ids]
        missing = selected_ids - {case["id"] for case in scenarios}
        if missing:
            raise RuntimeError(f"unknown cases: {sorted(missing)}")

    state = {
        "schema_version": "1.0",
        "run_id": run_id,
        "status": "SNAPSHOTTED",
        "updated_at": now_iso(),
    }
    atomic_write_json(output_root / "state.json", state)
    sync_remote_output(args.remote, args.remote_root, output_root, run_id)
    with tempfile.TemporaryDirectory(prefix="easydesign-vhh-ab-") as selected_temp:
        temp_root = Path(selected_temp)
        jobs: list[dict[str, Any]] = []
        for track in tracks:
            for case in scenarios:
                if track.daily_only and not case["high_risk_daily_model"]:
                    continue
                for variant, source in (("a", source_a), ("b", source_b)):
                    jobs.append(
                        {
                            "config": config,
                            "source": source,
                            "variant": variant,
                            "case": case,
                            "track": track,
                            "run_id": run_id,
                            "output_root": output_root,
                            "temp_root": temp_root,
                            "schema_path": output_root / "schemas/solver.schema.json",
                        }
                    )
        completed_count = 0
        for start in range(0, len(jobs), args.max_workers):
            batch = jobs[start : start + args.max_workers]
            failures: list[dict[str, str]] = []
            with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
                future_jobs = {executor.submit(run_solver, **job): job for job in batch}
                for future in as_completed(future_jobs):
                    job = future_jobs[future]
                    case_id = job["case"]["id"]
                    track_name = job["track"].name
                    variant = job["variant"]
                    relative = Path("cases") / case_id / track_name / variant
                    try:
                        future.result()
                    except Exception as error:  # noqa: BLE001 - preserve batch and stop dispatch.
                        failures.append(
                            {
                                "case_id": case_id,
                                "track": track_name,
                                "variant": variant,
                                "error": str(error),
                            }
                        )
                        if (output_root / relative).exists():
                            sync_remote_relative(
                                args.remote,
                                args.remote_root,
                                output_root,
                                run_id,
                                relative,
                            )
                        continue
                    completed_count += 1
                    print(
                        f"[solver {completed_count}/{len(jobs)}] {track_name} {case_id} {variant}",
                        flush=True,
                    )
                    sync_remote_relative(
                        args.remote,
                        args.remote_root,
                        output_root,
                        run_id,
                        relative,
                    )
            if failures:
                state.update(
                    status="SOLVERS_INCOMPLETE",
                    updated_at=now_iso(),
                    failures=failures,
                )
                atomic_write_json(output_root / "state.json", state)
                sync_remote_relative(
                    args.remote, args.remote_root, output_root, run_id, Path("state.json")
                )
                raise RuntimeError(
                    "solver batch incomplete; resume with the same run-id: "
                    + json.dumps(failures, ensure_ascii=False)
                )
        state.update(status="SOLVERS_COMPLETE", updated_at=now_iso())
        atomic_write_json(output_root / "state.json", state)
        sync_remote_relative(
            args.remote, args.remote_root, output_root, run_id, Path("state.json")
        )
        invalid = []
        for track in tracks:
            for case in scenarios:
                if track.daily_only and not case["high_risk_daily_model"]:
                    continue
                for variant in ("a", "b"):
                    checks = load_json(
                        output_root
                        / "cases"
                        / case["id"]
                        / track.name
                        / variant
                        / "checks.json"
                    )
                    invalid.extend(
                        {
                            "case_id": case["id"],
                            "track": track.name,
                            "variant": variant,
                            **item,
                        }
                        for item in checks
                        if item.get("status") == "harness_invalid"
                    )
        if invalid:
            state.update(status="HARNESS_INVALID", updated_at=now_iso(), invalid=invalid)
            atomic_write_json(output_root / "state.json", state)
            sync_remote_relative(
                args.remote, args.remote_root, output_root, run_id, Path("state.json")
            )
            raise RuntimeError(
                "one or more Solver samples are harness-invalid; no Judge was started: "
                + json.dumps(invalid, ensure_ascii=False)
            )

        for track in tracks:
            for case in scenarios:
                if track.daily_only and not case["high_risk_daily_model"]:
                    continue
                for number in (1, 2):
                    try:
                        run_judge(
                            config=config,
                            case=case,
                            track=track,
                            run_id=run_id,
                            output_root=output_root,
                            temp_root=temp_root,
                            schema_path=output_root / "schemas/judge.schema.json",
                            judge_number=number,
                        )
                    except Exception as error:  # noqa: BLE001 - persist resumable Judge state.
                        state.update(
                            status="JUDGES_INCOMPLETE",
                            updated_at=now_iso(),
                            failure={
                                "case_id": case["id"],
                                "track": track.name,
                                "judge_number": number,
                                "error": str(error),
                            },
                        )
                        atomic_write_json(output_root / "state.json", state)
                        sync_remote_relative(
                            args.remote,
                            args.remote_root,
                            output_root,
                            run_id,
                            Path("judges") / case["id"] / track.name,
                        )
                        sync_remote_relative(
                            args.remote,
                            args.remote_root,
                            output_root,
                            run_id,
                            Path("state.json"),
                        )
                        raise
                    print(f"[judge {number}] {track.name} {case['id']}", flush=True)
                    sync_remote_relative(
                        args.remote,
                        args.remote_root,
                        output_root,
                        run_id,
                        Path("judges") / case["id"] / track.name,
                    )
                if judge3_required(output_root, case, track):
                    try:
                        run_judge(
                            config=config,
                            case=case,
                            track=track,
                            run_id=run_id,
                            output_root=output_root,
                            temp_root=temp_root,
                            schema_path=output_root / "schemas/judge.schema.json",
                            judge_number=3,
                        )
                    except Exception as error:  # noqa: BLE001 - persist resumable Judge state.
                        state.update(
                            status="JUDGES_INCOMPLETE",
                            updated_at=now_iso(),
                            failure={
                                "case_id": case["id"],
                                "track": track.name,
                                "judge_number": 3,
                                "error": str(error),
                            },
                        )
                        atomic_write_json(output_root / "state.json", state)
                        sync_remote_relative(
                            args.remote,
                            args.remote_root,
                            output_root,
                            run_id,
                            Path("judges") / case["id"] / track.name,
                        )
                        sync_remote_relative(
                            args.remote,
                            args.remote_root,
                            output_root,
                            run_id,
                            Path("state.json"),
                        )
                        raise
                    print(f"[judge 3] {track.name} {case['id']}", flush=True)
                    sync_remote_relative(
                        args.remote,
                        args.remote_root,
                        output_root,
                        run_id,
                        Path("judges") / case["id"] / track.name,
                    )
        state.update(status="JUDGES_COMPLETE", updated_at=now_iso())
        atomic_write_json(output_root / "state.json", state)
        sync_remote_relative(
            args.remote, args.remote_root, output_root, run_id, Path("state.json")
        )

    report = build_report(
        output_root=output_root,
        scenarios=scenarios,
        tracks=tracks,
        source_map=source_map,
    )
    atomic_write_json(output_root / "report.json", report)
    atomic_write_text(output_root / "report.md", render_report(report))
    atomic_write_json(
        output_root / "sealed/judgment_seal.json",
        {
            "report_sha256": sha256_file(output_root / "report.json"),
            "sealed_at": now_iso(),
        },
    )
    atomic_write_json(output_root / "sealed/variant_map.json", source_map)
    state.update(status="REPORTED", updated_at=now_iso(), decision="awaiting_user_review")
    atomic_write_json(output_root / "state.json", state)
    remote_output = f"{args.remote}:{args.remote_root}/runtime/tmp/skill-evals/{run_id}"
    atomic_write_text(output_root / "remote-output.txt", remote_output + "\n")
    sync_remote_output(args.remote, args.remote_root, output_root, run_id)
    print(f"[report] {remote_output}", flush=True)
    return output_root


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    sub = result.add_subparsers(dest="command", required=True)

    def common(selected: argparse.ArgumentParser) -> None:
        selected.add_argument("--remote", default="Suzhou2")
        selected.add_argument("--remote-root", default="/data/Easydesign")
        selected.add_argument("--suite", required=True)
        selected.add_argument("--codex")
        selected.add_argument("--solver-model", default="gpt-5.6-sol")
        selected.add_argument("--solver-reasoning", default="high")
        selected.add_argument("--daily-model", default="gpt-5.6-terra")
        selected.add_argument("--daily-reasoning", default="medium")
        selected.add_argument("--judge-model", default="gpt-5.6-sol")
        selected.add_argument("--judge-reasoning", default="high")

    preflight_parser = sub.add_parser(
        "preflight", help="validate harness inputs without model calls"
    )
    common(preflight_parser)

    run_parser = sub.add_parser("run", help="run or resume the complete anonymous A/B")
    common(run_parser)
    run_parser.add_argument("--live", default=".agents/skills/easydesign-research")
    run_parser.add_argument(
        "--draft", default="docs/skill-system/drafts/easydesign-research-v0.3"
    )
    run_parser.add_argument("--output", required=True)
    run_parser.add_argument("--run-id")
    run_parser.add_argument("--case", action="append")
    run_parser.add_argument("--strong-only", action="store_true")
    run_parser.add_argument("--max-workers", type=int, default=2, choices=(1, 2))
    run_parser.add_argument("--solver-timeout-minutes", type=int, default=30)
    run_parser.add_argument("--judge-timeout-minutes", type=int, default=15)
    return result


def main() -> int:
    args = parser().parse_args()
    if args.command == "preflight":
        print(json.dumps(preflight(args), ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if args.command == "run":
        output = execute(args)
        print(output)
        return 0
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
