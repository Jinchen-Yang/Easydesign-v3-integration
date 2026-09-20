#!/usr/bin/env python3
"""Read-only Figure 2A metric derivation for EasyDesign experimental runs."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import sqlite3
from collections import Counter
from datetime import datetime
from pathlib import Path

NA = "not_available"
STAGES = ("target", "structure", "site", "design", "compiler", "backend-validation", "pilot-ready")
RANK = {x: i for i, x in enumerate(STAGES)}


def jsonl(path: Path):
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]


def sha(path: Path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def runtime(path: Path):
    if not path.is_file():
        return []
    db = sqlite3.connect(path)
    try:
        rows = db.execute("select seq,kind,payload from events order by seq").fetchall()
    finally:
        db.close()
    out = []
    for seq, kind, raw in rows:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {"unparsed": raw}
        out.append({"seq": seq, "kind": kind, "payload": payload})
    return out


def one(events, **wanted):
    return next((e for e in events if all(e.get(k) == v for k, v in wanted.items())), None)


def elapsed(a, b):
    if a is None or b is None:
        return NA
    if isinstance(a.get("monotonic_ns"), int) and isinstance(b.get("monotonic_ns"), int):
        return round((b["monotonic_ns"] - a["monotonic_ns"]) / 1e9, 6)
    try:
        return round(
            (
                datetime.fromisoformat(b["timestamp_utc"])
                - datetime.fromisoformat(a["timestamp_utc"])
            ).total_seconds(),
            6,
        )
    except (KeyError, TypeError, ValueError):
        return NA


def runtime_summary(rows):
    contexts = [e["payload"] for e in rows if e["kind"] == "model-context"]
    responses = [e["payload"] for e in rows if e["kind"] == "model-response"]
    data = Counter()
    stops = Counter()
    latency = 0.0
    for row in responses:
        latency += float(row.get("latency_seconds") or 0)
        data["transport_retries"] += int(bool(row.get("transport_failure")))
        for response in row.get("responses") or []:
            data["invalid_tools"] += len(response.get("invalid_tool_names") or [])
            stops[str(response.get("stop_reason"))] += 1
            usage = response.get("usage") or {}
            data["input_tokens"] += int(usage.get("input_tokens") or 0)
            data["output_tokens"] += int(usage.get("output_tokens") or 0)
            detail = usage.get("input_token_details") or {}
            data["cache_read"] += int(detail.get("cache_read") or 0)
            data["cache_create"] += int(detail.get("cache_creation") or 0)
    repairs = {
        (str(x.get("execution_id")), int(x.get("repair_attempt") or 0))
        for x in contexts
        if int(x.get("repair_attempt") or 0) > 0
    }
    repair_ids = {x[0] for x in repairs}
    repair_seconds = sum(
        float(x.get("latency_seconds") or 0)
        for x in responses
        if str(x.get("execution_id")) in repair_ids
    )
    sources = {
        json.dumps(e["payload"].get("ref"), sort_keys=True)
        for e in rows
        if e["kind"] == "evidence-research" and e["payload"].get("ref")
    }
    return {
        "model_calls": sum(e["kind"] in {"model-call", "auxiliary-model-call"} for e in rows),
        "tool_calls": sum(e["kind"] == "tool" for e in rows),
        "submissions": sum(e["kind"] == "submission-preflight-passed" for e in rows),
        "summaries": sum(e["kind"] == "framework-summary-call" for e in rows),
        "input_tokens": data["input_tokens"],
        "output_tokens": data["output_tokens"],
        "invalid_tools": data["invalid_tools"],
        "cache_read": data["cache_read"],
        "cache_create": data["cache_create"],
        "transport_retries": data["transport_retries"],
        "repair_count": len(repairs),
        "repair_seconds": round(repair_seconds, 6),
        "budget_exhaustions": stops["max_tokens"],
        "sources": len(sources),
        "peak_chars": max(
            (int(x.get("input_chars_with_schemas") or 0) for x in contexts), default=0
        ),
        "claimed": any(
            e["kind"] == "agent-terminal" and e["payload"].get("status") == "finished" for e in rows
        ),
        "checkpoint_resumes": sum(
            e["kind"] == "agent-execution" and e["payload"].get("input_kind") == "checkpoint-resume"
            for e in rows
        ),
        "model_latency_seconds": round(latency, 6),
    }


def derive(repo: Path, spec, defs):
    ledger_path = repo / spec["ledger"]
    project = repo / spec["project_root"]
    db_path = project / "metadata/agent.sqlite"
    events, rt = jsonl(ledger_path), runtime(db_path)
    usage = runtime_summary(rt)
    for field, expected in (
        ("run_id", spec["run_id"]),
        ("case_id", spec["case_id"]),
        ("method_id", "easydesign_v3_full"),
    ):
        got = {e.get(field) for e in events}
        if got != {expected}:
            raise ValueError(f"{ledger_path}: {field}={got}, expected={expected}")
    goal = one(events, event_type="goal_released")
    endpoint = next(
        (e for e in events if e.get("stage") == "pilot-ready" and e.get("status") == "passed"), None
    )
    design_submit = one(events, stage="design", event_type="decision_card_created")
    handoff = next(
        (
            e
            for e in events
            if e.get("event_type") == "awaiting_operator_repair"
            or e.get("status") == "awaiting_operator_repair"
        ),
        None,
    )
    ep = endpoint.get("payload", {}) if endpoint else {}
    valid = endpoint is not None
    repairs = [
        e
        for e in events
        if e.get("actor") == "operator"
        and e.get("operator_episode_id")
        and e.get("payload", {}).get("operator_repair") is True
        and not e.get("payload", {}).get("excluded_from_method_scientific_failures", False)
    ]
    excluded = [
        e
        for e in events
        if e.get("actor") == "operator"
        and e.get("operator_episode_id")
        and e.get("payload", {}).get("excluded_from_method_scientific_failures", False)
    ]
    repair_ids = {e["operator_episode_id"] for e in repairs}
    self_ids = {e["self_recovery_episode_id"] for e in events if e.get("self_recovery_episode_id")}
    if self_ids:
        self_count = len(self_ids)
    elif ep.get("zero_framework_self_repair") is True:
        self_count = 0
    elif usage["repair_count"]:
        self_count = usage["repair_count"]
    else:
        self_count = NA
    first_valid = ep.get("first_submission_valid", NA)
    vals = {d["metric_id"]: NA for d in defs}
    notes = {}

    def put(name, value, note=""):
        if name not in vals:
            raise KeyError(name)
        vals[name] = value
        if note:
            notes[name] = note

    compiler = next(
        (e for e in events if e.get("stage") == "compiler" and e.get("status") == "passed"), None
    )
    backend = next(
        (
            e
            for e in events
            if e.get("stage") == "backend-validation" and e.get("status") == "passed"
        ),
        None,
    )
    target_card = one(events, stage="target", event_type="decision_card_created")
    target_ok = one(events, stage="target", event_type="routine_gate_approval")
    site_card = one(events, stage="site", event_type="decision_card_created")
    site_ok = one(events, stage="site", event_type="routine_gate_approval")
    design_ok = next(
        (
            e
            for e in events
            if e.get("stage") == "design"
            and e.get("actor") == "operator"
            and e.get("event_type", "").startswith("routine_gate")
        ),
        None,
    )

    put("time_to_first_submission_seconds", elapsed(goal, design_submit))
    put("time_to_valid_seconds", elapsed(goal, endpoint))
    put("time_to_first_operator_handoff_seconds", elapsed(goal, handoff))
    put(
        "autonomous_elapsed_seconds",
        elapsed(goal, endpoint) if valid and not repair_ids else NA,
        "Includes immediate routine gate approvals.",
    )
    put("self_recovery_seconds", usage["repair_seconds"] if isinstance(self_count, int) else NA)
    put("active_operator_seconds", 0.0 if not repair_ids else NA)
    put("operator_queue_seconds", 0.0 if handoff is None else NA)
    put("transport_wait_seconds", 0.0 if usage["transport_retries"] == 0 else NA)
    put("backend_wait_seconds", elapsed(compiler, backend))
    put(
        "stage_duration_seconds",
        {
            "target": elapsed(goal, target_card),
            "site": elapsed(target_ok, site_card),
            "design": elapsed(site_ok, design_submit),
            "compiler": elapsed(design_ok, compiler),
            "backend-validation": elapsed(compiler, backend),
            "pilot-ready": elapsed(backend, endpoint),
        },
    )

    put("first_submission_valid", first_valid)
    put(
        "zero_self_recovery_valid", valid and self_count == 0 if isinstance(self_count, int) else NA
    )
    put("zero_operator_valid", valid and not repair_ids)
    put(
        "self_recovered_valid",
        valid
        and first_valid is False
        and isinstance(self_count, int)
        and self_count > 0
        and not repair_ids
        if isinstance(first_valid, bool)
        else NA,
    )
    put("operator_assisted_valid", valid and bool(repair_ids))
    put("eventual_mechanical_valid", valid)
    put("agent_claimed_success", usage["claimed"])
    put("validator_confirmed_success", valid)
    put("false_success_claim_rate", int(usage["claimed"] and not valid))
    facts = [
        ep.get(k)
        for k in (
            "target_verified",
            "site_ranked_and_approved",
            "design_approved",
            "compiler_valid",
            "backend_valid",
        )
    ]
    put("hard_fact_integrity", all(facts) if all(isinstance(x, bool) for x in facts) else NA)
    put("silent_failure_rate", NA, "Requires independent read-only audit.")

    put("self_recovery_count", self_count)
    if isinstance(self_count, int) and self_count > 0:
        recovered = {
            e["self_recovery_episode_id"]
            for e in events
            if e.get("self_recovery_episode_id") and e.get("status") in {"recovered", "passed"}
        }
        put("self_recovery_success_rate", round(len(recovered) / self_count, 6))
    put(
        "same_blocker_repeat_count",
        0
        if self_count == 0
        else sum(e.get("event_type") == "same_blocker_repeated" for e in events)
        if self_ids
        else NA,
    )
    put(
        "no_progress_recovery_count",
        0
        if self_count == 0
        else sum(e.get("event_type") == "no_progress_recovery" for e in events)
        if self_ids
        else NA,
    )
    put("context_compaction_count", usage["summaries"])
    put("checkpoint_resume_count", usage["checkpoint_resumes"])
    put("budget_exhaustion_count", usage["budget_exhaustions"])

    put("operator_intervention_count", len(repair_ids))
    put("operator_intervention_incidence", bool(repair_ids))
    engcats = {
        "schema",
        "required_field",
        "artifact_reference",
        "path_or_handle",
        "provenance",
        "structure_mapping",
        "residue_numbering",
        "stage_handoff",
        "compiler",
        "backend_input",
    }
    put(
        "operator_engineering_intervention_count",
        len(
            {
                e["operator_episode_id"]
                for e in repairs
                if e.get("blocker_category") in engcats
                or e.get("payload", {}).get("correction_type") == "engineering"
            }
        ),
    )
    put(
        "operator_scientific_intervention_count",
        len(
            {
                e["operator_episode_id"]
                for e in repairs
                if e.get("payload", {}).get("correction_type") in {"scientific-minimal", "mixed"}
            }
        ),
    )
    fields = {f for e in repairs for f in e.get("payload", {}).get("changed_fields", [])}
    arts = {p for e in repairs for p in (e.get("input_artifact"), e.get("output_artifact")) if p}
    put("operator_corrected_field_count", len(fields) if fields or not repair_ids else NA)
    put("operator_corrected_artifact_count", len(arts) if arts or not repair_ids else NA)
    put(
        "operator_repair_success_count",
        len(
            {
                e["operator_episode_id"]
                for e in repairs
                if e.get("status") in {"recovered", "passed", "approved"}
            }
        ),
    )
    put(
        "same_blocker_recurrence_after_handoff",
        sum(e.get("event_type") == "same_blocker_recurred_after_handoff" for e in events),
    )

    if not repair_ids:
        reach = (
            "pilot-ready"
            if valid
            else max(
                (e.get("stage") for e in events if e.get("stage") in RANK),
                key=lambda x: RANK[x],
                default=NA,
            )
        )
    else:
        cut = min(events.index(e) for e in repairs)
        reach = max(
            (e.get("stage") for e in events[:cut] if e.get("stage") in RANK),
            key=lambda x: RANK[x],
            default=NA,
        )
    put("autonomous_stage_reach", reach)
    stage_map = {}
    for stage in STAGES:
        subset = [e for e in events if e.get("stage") == stage]
        if any(e.get("status") == "passed" for e in subset):
            state = "validator-confirmed"
        elif any(e.get("status") in {"approved", "override-approved"} for e in subset):
            state = "approved"
        elif any(e.get("status") == "awaiting-human-approval" for e in subset):
            state = "submitted"
        else:
            state = "not-reached"
        stage_map[stage] = state
    put("stage_wise_completion", stage_map)

    failures = sum(
        e.get("actor") == "validator" and e.get("status") not in {"passed", "approved"}
        for e in events
    )
    put("submission_count", usage["submissions"])
    put("validation_failure_count", failures if failures or first_valid is not False else NA)
    put("model_call_count", usage["model_calls"])
    put("tool_call_count", usage["tool_calls"])
    put("invalid_tool_call_count", usage["invalid_tools"])
    put("repeated_tool_call_count", NA, "Canonicalized arguments unavailable for every call.")
    put("input_tokens", usage["input_tokens"])
    put("output_tokens", usage["output_tokens"])
    put("peak_input_chars", usage["peak_chars"])
    put("provider_api_cost", NA, "Provider monetary receipt unavailable.")
    put("acquired_source_count", usage["sources"])
    put(
        "cache_hit_miss",
        {"cache_read_tokens": usage["cache_read"], "cache_creation_tokens": usage["cache_create"]},
    )
    put("transport_retry_count", usage["transport_retries"])
    incidents = [
        e
        for e in events
        if e.get("blocker_category") == "infrastructure"
        or e.get("payload", {}).get("excluded_from_method_scientific_failures", False)
    ]
    put("infrastructure_incident_count", len(incidents))
    composition = Counter(
        str(e["blocker_category"])
        for e in events
        if e.get("blocker_category")
        and not e.get("payload", {}).get("excluded_from_method_scientific_failures", False)
    )
    put("blocker_category_composition", dict(sorted(composition.items())))
    outcome = (
        "first-submission-valid"
        if first_valid is True
        else "self-recovered-valid"
        if valid and not repair_ids
        else "operator-assisted-valid"
        if valid
        else "invalid"
    )
    put("final_outcome_category", outcome)

    sources = {d["metric_id"]: d["raw_source"] for d in defs}
    records = {
        k: {"value": v, "available": v != NA, "source": sources[k], "note": notes.get(k, "")}
        for k, v in vals.items()
    }
    result = {
        "schema_version": "figure2a-easydesign-metrics-v1",
        "run_id": spec["run_id"],
        "case_id": spec["case_id"],
        "target_id": spec["target_id"],
        "method_id": "easydesign_v3_full",
        "replicate": spec["replicate"],
        "formal": bool(spec["formal"]),
        "eligible_for_formal_analysis": bool(spec["formal"]),
        "agent_baseline_commit": spec["agent_baseline_commit"],
        "goal": spec["goal"],
        "metrics": records,
        "coverage": {
            "available": sum(x["available"] for x in records.values()),
            "total": len(records),
        },
        "excluded_operator_event_count": len(excluded),
    }

    blockers = [
        {
            "run_id": spec["run_id"],
            "case_id": spec["case_id"],
            "timestamp_utc": e.get("timestamp_utc", ""),
            "stage": e.get("stage", ""),
            "actor": e.get("actor", ""),
            "event_type": e.get("event_type", ""),
            "blocker_category": e.get("blocker_category") or "",
            "error_type": e.get("error_type") or "",
            "status": e.get("status", ""),
            "excluded_from_method_metrics": bool(
                e.get("payload", {}).get("excluded_from_method_scientific_failures", False)
            ),
        }
        for e in events
        if e.get("blocker_category") or e.get("error_type")
    ]
    operators = [
        {
            "run_id": spec["run_id"],
            "case_id": spec["case_id"],
            "timestamp_utc": e.get("timestamp_utc", ""),
            "stage": e.get("stage", ""),
            "event_type": e.get("event_type", ""),
            "operator_episode_id": e.get("operator_episode_id") or "",
            "routine_gate_action": e.get("event_type", "").startswith("routine_gate"),
            "operator_repair": bool(e.get("payload", {}).get("operator_repair")),
            "excluded_from_method_metrics": bool(
                e.get("payload", {}).get("excluded_from_method_scientific_failures", False)
            ),
            "status": e.get("status", ""),
        }
        for e in events
        if e.get("actor") == "operator"
    ]

    paths = {ledger_path}
    paths.add(db_path) if db_path.is_file() else None
    for e in events:
        for key in ("input_artifact", "output_artifact"):
            if e.get(key) and (repo / e[key]).is_file():
                paths.add(repo / e[key])
    for rel in (
        "PROJECT.yaml",
        "SITE_CURRENT",
        "STRATEGY_CURRENT",
        "strategies/strategy-r000001.yaml",
    ):
        if (project / rel).is_file():
            paths.add(project / rel)
    artifacts = {
        str(p.relative_to(repo)): {"sha256": sha(p), "size_bytes": p.stat().st_size}
        for p in sorted(paths)
    }
    manifest = {
        "schema_version": "figure2a-easydesign-run-manifest-v1",
        **spec,
        "method_id": "easydesign_v3_full",
        "ledger_sha256": sha(ledger_path),
        "runtime_db_sha256": sha(db_path) if db_path.is_file() else NA,
        "artifacts": artifacts,
        "development_fixture_only": not bool(spec["formal"]),
    }
    return result, blockers, operators, manifest


def write_csv(path, rows, fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow(
                {
                    k: json.dumps(row.get(k), sort_keys=True, separators=(",", ":"))
                    if isinstance(row.get(k), (dict, list))
                    else row.get(k, "")
                    for k in fields
                }
            )


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--repo", type=Path, default=Path.cwd())
    p.add_argument(
        "--registry", default="evaluation/figure2_benchbb/configs/easydesign_experimental_runs.json"
    )
    p.add_argument(
        "--dictionary", default="evaluation/figure2_benchbb/configs/metric_dictionary.csv"
    )
    p.add_argument("--output", default="evaluation/figure2_benchbb/results")
    a = p.parse_args()
    repo, out = a.repo.resolve(), a.repo.resolve() / a.output
    registry = json.loads((repo / a.registry).read_text())
    with (repo / a.dictionary).open(newline="") as f:
        defs = list(csv.DictReader(f))
    results, blockers, operators = [], [], []
    out.mkdir(parents=True, exist_ok=True)
    for spec in registry["runs"]:
        result, br, op, manifest = derive(repo, spec, defs)
        results.append(result)
        blockers += br
        operators += op
        raw = out / "raw_events" / spec["run_id"]
        raw.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(repo / spec["ledger"], raw / "events.jsonl")
        for folder, data in (("run_manifests", manifest), ("artifacts", manifest["artifacts"])):
            path = out / folder / f"{spec['run_id']}.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    (out / "per_run_metrics.json").write_text(json.dumps(results, indent=2, sort_keys=True) + "\n")
    meta = [
        "run_id",
        "case_id",
        "target_id",
        "method_id",
        "replicate",
        "formal",
        "eligible_for_formal_analysis",
        "agent_baseline_commit",
    ]
    mids = [x["metric_id"] for x in defs]
    rows = []
    for r in results:
        row = {k: r[k] for k in meta}
        row.update({m: r["metrics"][m]["value"] for m in mids})
        rows.append(row)
    write_csv(out / "figure2a_source_data.csv", rows, meta + mids)
    write_csv(
        out / "blocker_events.csv",
        blockers,
        [
            "run_id",
            "case_id",
            "timestamp_utc",
            "stage",
            "actor",
            "event_type",
            "blocker_category",
            "error_type",
            "status",
            "excluded_from_method_metrics",
        ],
    )
    write_csv(
        out / "operator_interventions.csv",
        operators,
        [
            "run_id",
            "case_id",
            "timestamp_utc",
            "stage",
            "event_type",
            "operator_episode_id",
            "routine_gate_action",
            "operator_repair",
            "excluded_from_method_metrics",
            "status",
        ],
    )
    md = [
        "# Figure 2A EasyDesign measurement dictionary",
        "",
        "Missing values are not_available and are never imputed as zero.",
        "",
        "| Metric | Layer | Definition | Direction | Source | Use |",
        "| --- | --- | --- | --- | --- | --- |",
    ] + [
        "| {metric_id} | {layer} | {definition} | {direction} | {source} | {use} |".format(
            metric_id=x["metric_id"],
            layer=x["layer"],
            definition=x["definition"],
            direction=x["direction"],
            source=x["raw_source"],
            use=x["main_or_supporting"],
        )
        for x in defs
    ]
    (out / "measurement_dictionary.md").write_text("\n".join(md) + "\n")
    audit = [
        "# Figure 2A EasyDesign audit report",
        "",
        f"- Runs: {len(results)}",
        f"- Formal: {sum(x['formal'] for x in results)}",
        f"- Development fixtures: {sum(not x['formal'] for x in results)}",
        "- Agent/Harness mutation: none; read-only derivation.",
        "",
        "| Run | Formal | Available | Total | Missing |",
        "| --- | --- | ---: | ---: | ---: |",
    ]
    audit += [
        "| {run} | {formal} | {available} | {total} | {missing} |".format(
            run=x["run_id"],
            formal=str(x["formal"]).lower(),
            available=x["coverage"]["available"],
            total=x["coverage"]["total"],
            missing=x["coverage"]["total"] - x["coverage"]["available"],
        )
        for x in results
    ]
    audit += [
        "",
        "Development fixtures are excluded from formal analysis.",
        "Unavailable observations remain explicit.",
    ]
    (out / "audit_report.md").write_text("\n".join(audit) + "\n")


if __name__ == "__main__":
    main()
