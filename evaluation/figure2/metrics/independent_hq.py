"""Frozen, method-blind acceptance and target-level paired estimation.

Consumes measured independent-evaluator metrics. It does not perform or simulate
structure prediction. Missing rows cannot be converted into passing designs.
"""
import json
import math
import random
from collections import defaultdict
from pathlib import Path

PROFILE = Path(__file__).resolve().parents[1] / "configs/evaluator_profile.json"


def evaluate_candidate(seed_rows, profile=None):
    profile = profile or json.loads(PROFILE.read_text())
    expected = profile["seeds"]
    if len(seed_rows) != len(expected) or sorted(row.get("seed", -1) for row in seed_rows) != sorted(expected):
        return {"status": "unevaluable", "accepted": None, "reason": "missing-or-duplicate-seed"}
    passing = []
    for row in seed_rows:
        passed = True
        for metric, gate in profile["per_seed_gates"].items():
            value = row.get(metric)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                return {"status": "unevaluable", "accepted": None, "reason": "missing-or-invalid-" + metric}
            if metric in {"independent_iptm", "hotspot_coverage"} and value > 1:
                return {"status": "unevaluable", "accepted": None, "reason": "invalid-fraction-scale"}
            if metric == "severe_clash_count" and value != int(value):
                return {"status": "unevaluable", "accepted": None, "reason": "nonintegral-clash-count"}
            passed &= value >= gate["threshold"] if gate["operator"] == ">=" else value <= gate["threshold"]
        passing.append(passed)
    return {"status": "evaluated", "accepted": sum(passing) >= profile["multi_seed_gate"]["passing_seeds_at_least"], "passing_seed_count": sum(passing)}


def campaign_yield(generated_ids, evaluated_rows):
    if len(generated_ids) != len(set(generated_ids)):
        raise ValueError("Duplicate generated candidate IDs; preserve attempt identities and resolve denominator")
    unexpected = set(evaluated_rows) - set(generated_ids)
    if unexpected:
        raise ValueError("Evaluator returned candidates outside the generated manifest")
    if not generated_ids:
        return {"status": "zero-generated", "hq_yield": None, "generated": 0, "accepted": 0, "unevaluable": 0}
    decisions = [evaluate_candidate(evaluated_rows.get(identifier, [])) for identifier in generated_ids]
    accepted = sum(item["accepted"] is True for item in decisions)
    missing = sum(item["status"] == "unevaluable" for item in decisions)
    return {"status": "incomplete-evaluation" if missing else "evaluated", "hq_yield": None if missing else accepted / len(generated_ids), "generated": len(generated_ids), "accepted": accepted, "unevaluable": missing, "accepted_lower_bound": accepted / len(generated_ids)}


def quantile(values, probability):
    values = sorted(values)
    index = (len(values) - 1) * probability
    low = int(index)
    high = min(low + 1, len(values) - 1)
    return values[low] * (high - index) + values[high] * (index - low) if high != low else values[low]


def paired_target_bootstrap(rows, draws=10000, seed=20260906):
    """Rows: one complete matched campaign pair with target_id, full, plain.

    Targets resampled first, matched campaigns within each sampled target second.
    Equal target weight; candidate records never enter this sampler.
    """
    if isinstance(draws, bool) or not isinstance(draws, int) or draws < 1:
        raise ValueError("Bootstrap draws must be a positive integer")
    groups = defaultdict(list)
    seen = set()
    for row in rows:
        for method in ("full", "plain"):
            value = row.get(method)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError("Only complete finite campaign yields in [0, 1] can be paired")
        key = (row["target_id"], row["replicate_id"])
        if key in seen:
            raise ValueError("Duplicate target/campaign pair")
        seen.add(key)
        groups[row["target_id"]].append(float(row["full"]) - float(row["plain"]))
    targets = sorted(groups)
    if not targets:
        return {"status": "not-available", "estimate": None, "ci_low": None, "ci_high": None, "n_targets": 0, "n_pairs": 0}
    effects = {key: sum(values) / len(values) for key, values in groups.items()}
    estimate = sum(effects.values()) / len(targets)
    output = {"status": "estimated", "estimate": estimate, "per_target_effect": effects, "n_targets": len(targets), "n_pairs": len(rows), "ci_low": None, "ci_high": None}
    if len(targets) < 2:
        output["status"] = "descriptive-one-target"
        return output
    rng = random.Random(seed)
    boot = []
    for _ in range(draws):
        sampled = rng.choices(targets, k=len(targets))
        means = [sum(rng.choices(groups[target], k=len(groups[target]))) / len(groups[target]) for target in sampled]
        boot.append(sum(means) / len(means))
    output.update(ci_low=quantile(boot, 0.025), ci_high=quantile(boot, 0.975), bootstrap_draws=draws, bootstrap_seed=seed)
    return output
