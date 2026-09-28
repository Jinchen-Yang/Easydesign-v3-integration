"""The capacity harness measures real HTTP, never real model/GPU execution."""

import hashlib
import os
import subprocess
import sys
import threading
import time

import httpx

from scripts import capacity_smoke


def test_resource_sample_counts_child_spawned_by_a_live_http_worker_thread():
    baseline = capacity_smoke.process_sample(os.getpid())["direct_child_processes"]
    ready, release = threading.Event(), threading.Event()

    def http_worker():
        child = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(10)"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            ready.set()
            release.wait(5)
        finally:
            child.terminate()
            child.wait(timeout=3)

    thread = threading.Thread(target=http_worker)
    thread.start()
    try:
        assert ready.wait(3)
        assert capacity_smoke.process_sample(os.getpid())["direct_child_processes"] >= baseline + 1
    finally:
        release.set()
        thread.join(timeout=5)
        assert not thread.is_alive()


def test_refusals_remain_flow_failures_and_latency_does_not_hide_them():
    report = capacity_smoke.summarize(
        [
            {"operation": "login", "seconds": 2.0, "status": 200, "ok": True, "code": None},
            {
                "operation": "login",
                "seconds": 0.01,
                "status": 503,
                "ok": False,
                "code": "login_busy",
            },
            {
                "operation": "gpu_submit",
                "seconds": 0.02,
                "status": 429,
                "ok": False,
                "code": "global_queue_full",
            },
            {"operation": "ai", "seconds": 0.03, "status": 429, "ok": False, "code": "queue_full"},
        ],
        [{"ok": True}, {"ok": False}],
    )
    assert report["full_flow_success_rate"] == 0.5
    assert report["recognized_refusals"] == 3
    assert report["unexpected_failures"] == 0
    assert report["operations"]["login"]["successful_p95_seconds"] == 2.0
    assert report["operations"]["gpu_submit"]["rejected"] == 1
    assert report["operations"]["ai"]["rejected"] == 1
    assert report["goal_pass"] is False


def test_persisted_gpu_request_admission_must_meet_the_one_second_p95_target():
    report = capacity_smoke.summarize(
        [{"operation": "gpu_submit", "seconds": 1.1, "status": 202, "ok": True, "code": None}],
        [{"ok": True}],
    )
    assert report["full_flow_success_rate"] == 1
    assert report["unexpected_failures"] == 0
    assert report["latency_targets_pass"] is False
    assert report["goal_pass"] is False


def test_acceptance_fails_closed_if_any_scientific_spawn_was_attempted():
    report = {
        "summary": {"goal_pass": True},
        "slow_ai": {"passed": True},
        "flows": [{"pre_ai_ok": True}],
        "forbidden_scientific_spawns": 0,
    }
    for slow in (False, True):
        assert capacity_smoke.acceptance_passed(report, slow=slow) is True
        assert (
            capacity_smoke.acceptance_passed(
                {**report, "forbidden_scientific_spawns": 1},
                slow=slow,
            )
            is False
        )


def test_two_users_complete_real_http_with_gpu_waiting_and_ai_stub():
    report = capacity_smoke.run_stage(
        users=2,
        profile="stub-throughput",
        login_window_seconds=0.05,
        soak_seconds=0,
    )
    assert report["summary"]["full_flow_completed"] == 2
    assert report["gpu"]["queued"] == 2
    assert report["gpu"]["scientific_completed"] == 0
    assert report["provider"]["dispatched_requests"] == 2
    assert report["forbidden_scientific_spawns"] == 0
    assert report["summary"]["operations"]["snapshot"]["succeeded"] == 2
    assert report["password_iterations"] == 600000
    assert report["production_ai_defaults"]["requests_per_minute"] == 20
    assert report["test_ai_limits"]["requests_per_minute"] > 20
    assert report["scope"] == "isolated_local_engineering_stub"
    assert report["uploads"]["integrity_verified"] == 2
    assert report["uploads"]["input_bound"] == 2


def test_short_soak_repeats_real_snapshot_reads_and_reports_resource_peaks():
    report = capacity_smoke.run_stage(
        users=2,
        profile="stub-throughput",
        login_window_seconds=0.05,
        soak_seconds=0.7,
        poll_seconds=0.2,
    )
    assert report["summary"]["operations"]["snapshot"]["succeeded"] > 2
    assert report["measured_soak_seconds"] >= 0.7
    assert report["resources"]["server_peak_threads"] > 0
    assert report["resources"]["server_peak_rss_kib"] > 0
    assert report["resources"]["gpu_queue_peak"] == 2


def test_owned_restart_preserves_gpu_queue_and_does_not_replay_paid_dispatch():
    report = capacity_smoke.run_stage(
        users=2,
        profile="stub-throughput",
        login_window_seconds=0.05,
        fault_checks=True,
    )
    assert report["faults"]["gpu_cancelled"] is True
    assert report["faults"]["gpu_queue_survived_restart"] is True
    assert report["faults"]["session_survived_restart"] is True
    assert report["faults"]["unknown_ai_not_replayed"] is True
    assert report["faults"]["new_ai_quota_recovered"] is True
    assert report["faults"]["original_outcome"] == "outcome_unknown"
    assert report["summary"]["full_flow_completed"] == 2
    assert report["fault_summary"]["operations"]["ai"]["succeeded"] == 0
    assert len(report["owned_process_groups"]) == 2
    assert all(row["pid"] == row["pgid"] for row in report["owned_process_groups"])


def test_slow_ai_keeps_real_mixed_requests_observable_and_cancels_owned_requests():
    report = capacity_smoke.run_stage(
        users=3,
        profile="conservative",
        login_window_seconds=0.05,
        hold_seconds=0.5,
    )
    assert report["slow_ai"]["registered"] == 3
    assert report["slow_ai"]["initial_queued"] >= 1
    assert report["slow_ai"]["cancelled"] == 3
    assert report["slow_ai"]["mixed"]["operations"]["login"]["succeeded"] == 3
    assert report["slow_ai"]["mixed"]["operations"]["upload"]["succeeded"] == 3
    assert report["slow_ai"]["mixed"]["unexpected_failures"] == 0
    assert report["slow_ai"]["mixed"]["recognized_refusals"] == 0
    assert report["slow_ai"]["completed_model_responses"] == 0
    assert report["summary"]["full_flow_completed"] == 0


def test_slow_ai_rejects_mixed_latency_failure_even_when_every_http_request_succeeds(monkeypatch):
    class SlowSnapshotClient(httpx.Client):
        def request(self, method, url, **kwargs):
            if method == "GET" and str(url).endswith("/workbench"):
                time.sleep(1.05)  # Inject delay at the external HTTP transport boundary.
            return super().request(method, url, **kwargs)

    monkeypatch.setattr(httpx, "Client", SlowSnapshotClient)
    report = capacity_smoke.run_stage(
        users=1,
        profile="conservative",
        login_window_seconds=0,
        hold_seconds=0.1,
    )
    assert report["slow_ai"]["mixed"]["unexpected_failures"] == 0
    assert report["slow_ai"]["mixed"]["recognized_refusals"] == 0
    assert report["slow_ai"]["mixed"]["latency_targets_pass"] is False
    assert report["slow_ai"]["passed"] is False


def test_one_maximum_pdb_upload_and_declared_oversize_rejection_are_separate():
    report = capacity_smoke.run_stage(
        users=1,
        profile="stub-throughput",
        login_window_seconds=0,
        boundary_uploads=True,
    )
    assert report["upload_bytes_per_user"] == 65536
    assert report["upload_boundaries"]["maximum_accepted_bytes"] == 32 * 1024**2
    assert report["upload_boundaries"]["oversize_status"] == 413
    assert report["upload_boundaries"]["oversize_code"] == "payload_too_large"
    assert report["upload_boundaries"]["maximum_integrity_verified"] is True
    assert report["summary"]["full_flow_completed"] == 1


def test_cli_runs_increasing_isolated_stages_without_an_external_target():
    result = subprocess.run(
        [
            sys.executable,
            str(capacity_smoke.ROOT / "scripts/capacity_smoke.py"),
            "--stages",
            "1,2",
            "--profile",
            "stub-throughput",
            "--login-window-seconds",
            "0",
        ],
        cwd=capacity_smoke.ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        env={"PATH": os.defpath, "PYTHONPATH": str(capacity_smoke.ROOT / "src")},
    )
    assert result.returncode == 0, result.stderr[-2000:]
    import json

    reports = [json.loads(line) for line in result.stdout.splitlines()]
    assert [row["users"] for row in reports] == [1, 2]
    assert reports[0]["evidence_path"] != reports[1]["evidence_path"]
    assert all(row["summary"]["goal_pass"] for row in reports)


def test_upload_integrity_rejects_bad_hash_and_wrong_length():
    content = b"synthetic input"
    receipt = {
        "id": "synthetic",
        "sha256": hashlib.sha256(content).hexdigest(),
        "size_bytes": len(content),
    }
    assert capacity_smoke.upload_matches(receipt, content) is True
    assert capacity_smoke.upload_matches({**receipt, "sha256": "0" * 64}, content) is False
    assert capacity_smoke.upload_matches({**receipt, "size_bytes": 1}, content) is False
