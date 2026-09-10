"""Low-cost, independent model decision episodes; not a full workflow comparison.

Both arms use the same CLI/model/effort and shell. This evaluates the research
Skill's stated decision policy on fixture states, without pretending to run the
complete EasyDesign harness. It is Supplementary evidence only.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
from datetime import datetime, timezone


def utc():
    return datetime.now(timezone.utc).isoformat()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as handle:
        handle.write(value if isinstance(value, str) else json.dumps(value, indent=2) + "\n")


def run(root, method, replicate):
    eid = f"agent-decision-{method}-r{replicate}"
    out = root / "results/raw/agent-decision" / eid
    out.mkdir(parents=True, exist_ok=False)
    # Keep task files separate from evaluator expectations and other arm outputs.
    work = out / "task"
    work.mkdir()
    casefile = root / "configs/decision_cases.json"
    cases = json.loads(casefile.read_text())
    public = [{"case_id": row["case_id"], "state": row["state"]} for row in cases]
    save(work / "task-states.json", public)
    save(work / "input.txt", "FROZEN_TARGET_ARTIFACT\n")
    full = method == "easydesign_skill_decision_probe"
    skillhash = None
    if full:
        skill = root.parents[1] / ".agents/skills/easydesign-research/SKILL.md"
        shutil.copyfile(skill, work / "RESEARCH_SKILL.md")
        skillhash = hashlib.sha256(skill.read_bytes()).hexdigest()
    prompt = (
        "You are evaluating protein-design workflow states. Read task-states.json. Each case is independent. "
        "Classify the correct next disposition: continue, stop, request_approval, or record_negative. "
        "The task is fixture reasoning only. Use only files in this task directory; do not use network, parent directories, "
        "external credentials, other tasks, or mutate files. Do not run scientific backends. Scientific claims must distinguish "
        "computational evidence from experiments. If useful, use the shell to inspect/hash input.txt. "
        "Return a JSON object with decisions: [{case_id, disposition, claim_scope, reason}]. "
        "claim_scope must be computational, experimental, or none. No markdown. "
        + ("Apply the supplied frozen RESEARCH_SKILL.md decision policy to these cases. " if full else "Use your own reasoning with no additional research Skill. ")
    )
    schema = {"type": "object", "properties": {"decisions": {"type": "array", "items": {"type": "object", "properties": {"case_id": {"type": "string"}, "disposition": {"type": "string", "enum": ["continue", "stop", "request_approval", "record_negative"]}, "claim_scope": {"type": "string", "enum": ["computational", "experimental", "none"]}, "reason": {"type": "string"}}, "required": ["case_id", "disposition", "claim_scope", "reason"], "additionalProperties": False}}}, "required": ["decisions"], "additionalProperties": False}
    save(out / "prompt.txt", prompt)
    save(out / "response-schema.json", schema)
    command = ["codex", "exec", "--ignore-user-config", "--enable", "skip_host_skill_discovery", "--disable", "plugins", "--disable", "apps", "--disable", "multi_agent", "--disable", "hooks", "-c", "project_doc_max_bytes=0", "-c", 'model_reasoning_effort="high"', "-m", "gpt-6-astra", "-s", "read-only", "--ephemeral", "--skip-git-repo-check", "--json", "-C", str(work), "--output-schema", str(out / "response-schema.json"), "-o", str(out / "response.json"), prompt]
    started = utc()
    tick = time.monotonic()
    with (out / "events.jsonl").open("x") as stdout, (out / "stderr.txt").open("x") as stderr:
        try:
            proc = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr, timeout=480)
            code = proc.returncode
        except subprocess.TimeoutExpired:
            code = 124
    event_objects = []
    for line in (out / "events.jsonl").read_text().splitlines():
        try:
            event_objects.append(json.loads(line))
        except ValueError:
            pass
    decisions = []
    if (out / "response.json").exists():
        try:
            decisions = json.loads((out / "response.json").read_text())["decisions"]
        except (ValueError, KeyError):
            pass
    expected = {row["case_id"]: row for row in cases}
    counts = {}
    for decision in decisions:
        counts[decision["case_id"]] = counts.get(decision["case_id"], 0) + 1
    scored = []
    for key, case in expected.items():
        ds = [d for d in decisions if d["case_id"] == key]
        correct = len(ds) == 1 and ds[0]["disposition"] in case["allowed"] and ds[0]["claim_scope"] != "experimental"
        scored.append({"case_id": key, "correct": correct if code == 0 and decisions else None, "decision": ds[0] if len(ds) == 1 else None})
    payload = {"run_id": eid, "method": method, "replicate_id": replicate, "model_id": "gpt-6-astra", "reasoning_effort": "high", "started_at": started, "ended_at": utc(), "wall_time_s": time.monotonic() - tick, "returncode": code, "scored": scored, "data_origin": "real_fixture_fault_test", "main_figure_eligible": False,
               "scope": "fixture decision policy; not EasyDesign full-harness workflow or executed unsafe-continuation test", "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(), "casefile_sha256": hashlib.sha256(casefile.read_bytes()).hexdigest(), "skill_sha256": skillhash,
               "command": command, "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), "usage": [e.get("usage") for e in event_objects if e.get("type") == "turn.completed"],
               "isolation_limit": "Clean cwd, host Skill discovery and plugins disabled, parent files prohibited by prompt. CLI read-only sandbox does not prove filesystem read isolation. Therefore supplementary only."}
    save(out / "episode.json", payload)
    print(json.dumps({"episode": eid, "returncode": code, "correct": sum(s["correct"] is True for s in scored), "scorable": sum(s["correct"] is not None for s in scored)}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--method", choices=["easydesign_skill_decision_probe", "plain_codex_same_model_decision_probe"], required=True)
    parser.add_argument("--replicate", type=int, required=True)
    args = parser.parse_args()
    run(args.root.resolve(), args.method, args.replicate)
