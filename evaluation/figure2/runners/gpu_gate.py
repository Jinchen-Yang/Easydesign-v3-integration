"""Validate a fully bound GPU queue. Never launches commands itself."""
import argparse
import hashlib
import json
from pathlib import Path


def validate_queue(queue, protocol, profile_sha):
    errors = []
    if not queue:
        errors.append("Empty queue cannot establish launch readiness")
    ids = [row.get("run_id") for row in queue]
    if len(ids) != len(set(ids)):
        errors.append("Duplicate run IDs")
    groups = {}
    required_hashes = ("target_sha256", "site_sha256", "condition_sha256", "plan_sha256", "prompt_sha256", "backend_receipt_sha256")
    for row in queue:
        key = (row["target_id"], row["replicate_id"])
        groups.setdefault(key, []).append(row)
        if type(row["x_conditions"]) is not int or row["x_conditions"] < 1 or type(row["candidate_budget"]) is not int or row["candidate_budget"] != 7 * 40 * row["x_conditions"]:
            errors.append(f"{row['run_id']}: 7x40xX violation")
        for field in required_hashes:
            value = row.get(field, "")
            if len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
                errors.append(f"{row['run_id']}: missing valid {field}")
        if row.get("evaluator_profile_sha256") != profile_sha:
            errors.append(f"{row['run_id']}: evaluator mismatch")
        if row.get("model_id") != protocol["model_id"] or row.get("reasoning_effort") != protocol["reasoning_effort"]:
            if row["method"] != "fixed_pipeline":
                errors.append(f"{row['run_id']}: model/effort mismatch")
        for field in ("site_approved", "runtime_validated", "baseline_isolation_verified", "independent_evaluator_smoke_passed", "resource_cost_measured", "explicit_gpu_authorization"):
            if row.get(field) is not True:
                errors.append(f"{row['run_id']}: {field} is not true")
    for key, group in groups.items():
        if sorted(row["method"] for row in group) != sorted(protocol["methods"]):
            errors.append(f"{key}: missing or duplicate method")
        for field in ("target_sha256", "site_sha256", "condition_sha256", "candidate_budget", "x_conditions", "generation_backend", "evaluator_profile_sha256", "seed_policy"):
            if len({str(row.get(field)) for row in group}) != 1:
                errors.append(f"{key}: unfair {field}")
    if not protocol["gpu_gate"]["allow_real_gpu_runs"]:
        errors.append("Global GPU gate is closed in the frozen protocol")
    return errors


def verify_bound_files(queue, root):
    """A syntactically correct digest is not evidence that an artifact exists."""
    errors = []
    required = ("target_sha256", "site_sha256", "condition_sha256", "plan_sha256", "prompt_sha256", "backend_receipt_sha256")
    for row in queue:
        bindings = row.get("artifact_bindings", {})
        for field in required:
            relative = bindings.get(field)
            if not relative:
                errors.append(f"{row['run_id']}: no file binding for {field}")
                continue
            path = (root / relative).resolve()
            if not path.is_relative_to(root.resolve()) or not path.is_file():
                errors.append(f"{row['run_id']}: missing/out-of-root artifact for {field}")
            elif hashlib.sha256(path.read_bytes()).hexdigest() != row.get(field):
                errors.append(f"{row['run_id']}: checksum mismatch for {field}")
    return errors


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    protocol = json.loads((root / "configs/protocol.json").read_text())
    profile_sha = hashlib.sha256((root / "configs/evaluator_profile.json").read_bytes()).hexdigest()
    queue = json.loads(args.queue.read_text())
    errors = validate_queue(queue, protocol, profile_sha) + verify_bound_files(queue, root)
    print(json.dumps({"status": "blocked" if errors else "metadata-and-artifacts-validated-pending-human-launch-review", "launch_performed": False, "errors": errors}, indent=2))
    raise SystemExit(2 if errors else 0)
