"""Synthetic checks of evaluation math only; values never exported as results."""
from independent_hq import evaluate_candidate, campaign_yield, paired_target_bootstrap
import pytest


def good(seed):
    return dict(seed=seed, independent_iptm=0.70, interface_pae_angstrom=10.0, hotspot_coverage=0.5, severe_clash_count=0, target_site_ca_rmsd_angstrom=2.0)


def test_exact_boundary_and_multiseed():
    assert evaluate_candidate([good(11), good(29), good(47)])["accepted"] is True
    assert evaluate_candidate([good(11), good(29)])["accepted"] is None
    assert evaluate_candidate([good(11), good(11), good(47)])["accepted"] is None
    items = [good(11), good(29), good(47)]
    items[0]["hotspot_coverage"] = 0.49
    items[1]["severe_clash_count"] = 1
    assert evaluate_candidate(items)["accepted"] is False


def test_missing_invalid_and_denominator():
    items = [good(11), good(29), good(47)]
    items[0]["interface_pae_angstrom"] = float("nan")
    assert evaluate_candidate(items)["accepted"] is None
    assert campaign_yield([], {})["hq_yield"] is None
    assert campaign_yield(["a", "b"], {"a": [good(11), good(29), good(47)]})["hq_yield"] is None
    assert campaign_yield(["a"], {"a": [good(11), good(29), good(47)]})["hq_yield"] == 1


def test_pairs_and_no_mock_bootstrap():
    assert paired_target_bootstrap([])["estimate"] is None
    one = [{"target_id": "t", "replicate_id": 1, "full": 0.5, "plain": 0.2}]
    assert paired_target_bootstrap(one)["ci_low"] is None
    pairs = one + [{"target_id": "s", "replicate_id": 1, "full": 0.2, "plain": 0.5}]
    assert abs(paired_target_bootstrap(pairs, draws=100)["estimate"]) < 1e-12


def test_reject_unknown_candidates_and_invalid_pairs():
    with pytest.raises(ValueError):
        campaign_yield([], {"unknown": []})
    for value in (None, float("nan"), float("inf"), -1, 1.1, True):
        with pytest.raises(ValueError):
            paired_target_bootstrap([dict(target_id="t", replicate_id=1, full=value, plain=0.2)])
    with pytest.raises(ValueError):
        paired_target_bootstrap([], draws=0)


def test_gpu_gate_closed_and_artifacts_required():
    import importlib.util
    from pathlib import Path
    import json
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("gpu_gate", root / "runners/gpu_gate.py")
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    protocol = json.loads((root / "configs/protocol.json").read_text())
    assert gate.validate_queue([], protocol, "x")
    assert gate.verify_bound_files([dict(run_id="unbound")], root)
