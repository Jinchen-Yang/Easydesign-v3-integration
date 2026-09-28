#!/usr/bin/env python3
"""Isolated local HTTP capacity evidence; never a production load generator."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import secrets
import signal
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import UTC, datetime
from http.client import HTTPConnection
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MARKER = "easydesign-synthetic-capacity-only-v1"

RECOGNIZED_REFUSALS = {
    "login_busy",
    "http_busy",
    "upload_busy",
    "queue_full",
    "global_queue_full",
    "user_limit",
    "rate_limited",
    "budget_exhausted",
    "queue_timeout",
    "quota_exceeded",
}
LIGHT_OPERATIONS = {"me", "projects", "snapshot", "gpu_status", "gpu_submit", "health"}


def percentile(values: list[float], fraction: float) -> float | None:
    """Nearest rank; absent observations are not zero latency."""
    return sorted(values)[max(0, math.ceil(len(values) * fraction) - 1)] if values else None


def summarize(samples: list[dict[str, Any]], flows: list[dict[str, Any]]) -> dict[str, Any]:
    operations: dict[str, Any] = {}
    for operation in sorted({row["operation"] for row in samples}):
        rows = [row for row in samples if row["operation"] == operation]
        successful = [row["seconds"] for row in rows if row["ok"]]
        operations[operation] = {
            "count": len(rows),
            "succeeded": len(successful),
            "rejected": sum(row.get("code") in RECOGNIZED_REFUSALS for row in rows),
            "p95_seconds": percentile([row["seconds"] for row in rows], 0.95),
            "p99_seconds": percentile([row["seconds"] for row in rows], 0.99),
            "successful_p95_seconds": percentile(successful, 0.95),
            "successful_p99_seconds": percentile(successful, 0.99),
            "outcomes": dict(
                Counter(
                    "ok" if row["ok"] else str(row.get("code") or row["status"]) for row in rows
                )
            ),
        }
    failures = [row for row in samples if not row["ok"]]
    refused = sum(row.get("code") in RECOGNIZED_REFUSALS for row in failures)
    unexpected = len(failures) - refused
    completed = sum(bool(row["ok"]) for row in flows)
    flow_rate = completed / len(flows) if flows else 0.0
    latency_pass = all(
        (values["successful_p95_seconds"] is not None)
        and values["successful_p95_seconds"] <= (3.0 if op == "login" else 1.0)
        for op, values in operations.items()
        if op == "login" or op in LIGHT_OPERATIONS
    )
    return {
        "operations": operations,
        "full_flow_count": len(flows),
        "full_flow_completed": completed,
        "full_flow_success_rate": flow_rate,
        "recognized_refusals": refused,
        "unexpected_failures": unexpected,
        "refusal_rate": refused / len(samples) if samples else 0.0,
        "unexpected_failure_rate": unexpected / len(samples) if samples else 0.0,
        "latency_targets_pass": latency_pass,
        "goal_pass": bool(samples) and flow_rate == 1.0 and not failures and latency_pass,
        "goal_definition": "all web flows complete; GPU queued, not scientific completion",
    }


def write_json(path: Path, value: Any) -> None:
    pending = path.with_suffix(path.suffix + ".tmp")
    pending.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    pending.replace(path)


def fixture_path(value: str | Path) -> Path:
    """Never accept an external target URL, existing workspace, or symlink fixture."""
    path = Path(value).absolute()
    base = ROOT / "runtime/tmp"
    if path != path.resolve() or not path.is_relative_to(base.resolve()):
        raise ValueError("Capacity fixtures must be inside this clone's runtime/tmp")
    if json.loads((path / "spec.json").read_text()).get("marker") != MARKER:
        raise ValueError("Not an explicitly synthetic capacity fixture")
    return path


def child_environment(path: Path) -> dict[str, str]:
    # Do not forward any provider credentials, proxy configuration, or user HOME.
    for name in ("tmp", "cache"):
        (path / name).mkdir(exist_ok=True)
    return {
        "PATH": os.defpath,
        "TMPDIR": str(path / "tmp"),
        "XDG_CACHE_HOME": str(path / "cache"),
        "PYTHONPATH": str(ROOT / "src"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "LANG": "C.UTF-8",
    }


def serve_fixture(path: Path) -> None:
    """Owned child process, bound ONLY to loopback with no executable GPU slots."""
    from easydesign.product.account_server import MultiUserServer
    from easydesign.product.accounts import AccountStore
    from easydesign.product.capacity_config import CapacityConfig
    from easydesign.product.domain import NativeGateway
    from easydesign.product.rabbit_capacity import RabbitCapacityLimits
    from easydesign.product.rabbit_chat import RabbitChatService, SubprocessChatProvider
    from easydesign.product.resource_supervisor import ResourceSupervisor
    from easydesign.product.tenancy import MultiUserRuntime
    from easydesign.workspace_context import WorkspaceContext

    path = fixture_path(path)
    spec = json.loads((path / "spec.json").read_text())
    config = CapacityConfig.model_validate(spec["capacity"])
    config.validate_limits()
    context = WorkspaceContext.from_root(path / "workspace")
    accounts = AccountStore(
        context.runtime_root / "state/accounts/accounts.sqlite",
        login_max_concurrency=config.login.max_concurrency,
        login_max_pending=config.login.max_pending,
        login_wait_timeout=config.login.wait_timeout,
    )

    def no_models(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("Scientific model execution is forbidden in capacity fixtures")

    runtime = MultiUserRuntime(
        context,
        accounts,
        lambda c: NativeGateway(c, context.root / "models.yaml", model_factory=no_models),
        max_active_admissions=config.queue.max_active_admissions,
    )

    class BusyProbe:
        def snapshots(self) -> tuple[Any, ...]:
            return ()

    class NoSpawnSupervisor(ResourceSupervisor):
        forbidden_spawns = 0

        def _spawn(self, admission: Any) -> Any:
            self.forbidden_spawns += 1
            raise RuntimeError("Scientific process creation is forbidden in capacity fixtures")

    supervisor = NoSpawnSupervisor(runtime, probe=BusyProbe())
    # Reuse the real bounded subprocess transport, with an explicit local stub.
    provider = SubprocessChatProvider(
        Path(__file__),
        Path("--provider-stub"),
        environment=lambda: child_environment(path),
    )
    rabbit = RabbitChatService(
        provider,
        limits=RabbitCapacityLimits(**config.ai),
        ledger_path=context.runtime_root / "state/accounts/rabbit-chat.sqlite",
    )
    server = MultiUserServer(
        runtime,
        port=int(spec.get("port", 0)),
        web_root=context.root / "web",
        rabbit_chat=rabbit,
        transport_policy=config.http.policy(),
    )
    stopping = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stopping.set())
    supervisor.start()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    write_json(path / "ready.json", {"pid": os.getpid(), "port": server.server_port})
    try:
        with (path / "server-metrics.jsonl").open("a") as evidence:
            while not stopping.wait(0.5):
                active = runtime.resources.active()
                row = {
                    "at": time.time(),
                    "provider": rabbit.capacity_status(),
                    "gpu": dict(
                        Counter(
                            item.state
                            for item in active
                            if item.dispatch_channel == "scoped_worker"
                        )
                    ),
                    "forbidden_scientific_spawns": supervisor.forbidden_spawns,
                }
                evidence.write(json.dumps(row) + "\n")
                evidence.flush()
                write_json(path / "server-state.json", row)
    finally:
        rabbit.close()
        supervisor.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def provider_stub() -> None:
    """Only a subprocess fixture: no networking or vendor library is imported."""
    value = json.load(sys.stdin)
    content = value["messages"][-1]["content"]
    print(json.dumps({"type": "delta", "text": "Synthetic fixture response"}), flush=True)
    time.sleep(60 if content == "capacity hold" else 0.05)
    print(json.dumps({"type": "done"}), flush=True)


class FixtureProcess:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.process: subprocess.Popen[bytes] | None = None
        self.output: Any = None
        self.origin = ""
        self.port = 0
        self.generation = 0
        self.owned_process_groups: list[dict[str, int]] = []

    def start(self) -> None:
        self.generation += 1
        ready = self.path / "ready.json"
        if ready.exists():
            ready.rename(self.path / f"ready-{self.generation - 1}.json")
        self.output = (self.path / f"server-{self.generation}.log").open("wb")
        self.process = subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), "--serve", str(self.path)],
            cwd=ROOT,
            env=child_environment(self.path),
            stdout=self.output,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        self.owned_process_groups.append(
            {"pid": self.process.pid, "pgid": os.getpgid(self.process.pid)}
        )
        write_json(self.path / "owned-process-groups.json", self.owned_process_groups)
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError(f"Fixture server exited; inspect {self.output.name}")
            if ready.exists():
                try:
                    value = json.loads(ready.read_text())
                except json.JSONDecodeError:
                    time.sleep(0.02)
                    continue
                if value["pid"] == self.process.pid:
                    self.port = int(value["port"])
                    self.origin = f"http://127.0.0.1:{self.port}"
                    return
            time.sleep(0.02)
        raise TimeoutError("Fixture server failed to become ready")

    def stop(self, *, abrupt: bool = False) -> None:
        if self.process is not None and self.process.poll() is None:
            if abrupt:
                # This private session contains only this fixture and its local stubs.
                assert os.getpgid(self.process.pid) == self.process.pid
                os.killpg(self.process.pid, signal.SIGKILL)
            else:
                self.process.terminate()
            try:
                self.process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                assert os.getpgid(self.process.pid) == self.process.pid
                os.killpg(self.process.pid, signal.SIGKILL)
                self.process.wait(timeout=10)
        if self.output is not None:
            self.output.close()


class Measurements:
    def __init__(self, path: Path) -> None:
        self.rows: list[dict[str, Any]] = []
        self.lock = threading.Lock()
        self.evidence = (path / "requests.jsonl").open("a")
        self.phase = "normal"

    def request(self, client: Any, operation: str, method: str, path: str, **kwargs: Any) -> Any:
        phase = kwargs.pop("measurement_phase", self.phase)
        started_at = time.time()
        started = time.monotonic()
        response = None
        status, code, ok = 0, None, False
        try:
            response = client.request(method, path, **kwargs)
            status = response.status_code
            ok = 200 <= status < 300
            if operation == "ai" and ok:
                events = [json.loads(line) for line in response.text.splitlines() if line]
                ok = bool(events) and events[-1].get("type") == "done"
                code = None if ok else (events[-1].get("code") if events else "missing_terminal")
            elif not ok:
                try:
                    code = response.json().get("error", {}).get("code")
                except (ValueError, AttributeError):
                    code = "invalid_response"
        except Exception as error:
            # Type only: exception messages can include cookies/URLs or payload content.
            code = type(error).__name__
            ok = False
        row = {
            "operation": operation,
            "seconds": time.monotonic() - started,
            "status": status,
            "ok": ok,
            "code": code,
            "at": time.time(),
            "phase": phase,
            "started_at": started_at,
        }
        with self.lock:
            self.rows.append(row)
            self.evidence.write(json.dumps(row) + "\n")
            self.evidence.flush()
        return response if ok else None

    def close(self) -> None:
        self.evidence.close()


def process_sample(pid: int) -> dict[str, Any]:
    try:
        text = Path(f"/proc/{pid}/status").read_text()
        values = {
            line.split(":", 1)[0]: line.split(":", 1)[1].strip()
            for line in text.splitlines()
            if ":" in line
        }
        stats = Path(f"/proc/{pid}/stat").read_text().rpartition(") ")[2].split()
        children: set[str] = set()
        # Linux attributes a child to the particular thread which created it.
        # Sampling only the thread-group leader misses live HTTP-worker providers.
        for entry in Path(f"/proc/{pid}/task").glob("*/children"):
            try:
                children.update(entry.read_text().split())
            except (FileNotFoundError, ProcessLookupError):
                continue  # A thread can exit between listing and reading its entry.
        return {
            "at": time.time(),
            "pid": pid,
            "threads": int(values["Threads"]),
            "rss_kib": int(values.get("VmRSS", "0 kB").split()[0]),
            "peak_rss_kib": int(values.get("VmHWM", "0 kB").split()[0]),
            "cpu_seconds": (int(stats[11]) + int(stats[12])) / os.sysconf("SC_CLK_TCK"),
            "direct_child_processes": len(children),
        }
    except (OSError, KeyError, IndexError, ValueError):
        return {"at": time.time(), "pid": pid, "unavailable": True}


def chat_payload(content: str = "fixture") -> dict[str, Any]:
    return {
        "locale": "en",
        "messages": [{"role": "user", "content": content}],
        "context": {"stage": "Idle", "status": "idle", "goal": ""},
    }


def light_reads(flow: dict[str, Any], client: Any, metrics: Measurements) -> None:
    prefix = f"/api/v1/scopes/{flow['scope']}"
    metrics.request(client, "me", "GET", "/api/v1/accounts/me")
    if flow.get("project"):
        metrics.request(
            client, "snapshot", "GET", prefix + f"/projects/{flow['project']}/workbench"
        )
        metrics.request(client, "gpu_status", "GET", prefix + "/requests/" + flow["request_id"])


def soak(
    flows: list[dict[str, Any]],
    clients: list[Any],
    metrics: Measurements,
    duration: float,
    interval: float,
) -> float:
    began = time.monotonic()
    until = began + duration
    valid = [flow for flow in flows if flow.get("logged_in")]
    if not valid or not duration:
        return 0.0
    pending: dict[int, tuple[Any, str]] = {}
    next_ai = began + 60
    with (
        ThreadPoolExecutor(max_workers=len(valid)) as reads,
        ThreadPoolExecutor(max_workers=len(valid)) as ai,
    ):
        while time.monotonic() < until:
            tick = time.monotonic()
            list(reads.map(lambda flow: light_reads(flow, clients[flow["index"]], metrics), valid))
            if tick >= next_ai:
                for flow in valid:
                    index = flow["index"]
                    if index in pending and not pending[index][0].done():
                        continue
                    request_id = uuid.uuid4().hex
                    pending[index] = (
                        ai.submit(
                            metrics.request,
                            clients[index],
                            "ai",
                            "POST",
                            f"/api/v1/scopes/{flow['scope']}/rabbit/chat",
                            headers={"X-Request-ID": request_id},
                            json=chat_payload(),
                        ),
                        request_id,
                    )
                next_ai = tick + 60
            time.sleep(max(0, min(until, tick + interval) - time.monotonic()))
        for flow in valid:
            index = flow["index"]
            if index in pending and not pending[index][0].done():
                # Explicit final-drain cancellations remain failed AI attempts in the summary.
                metrics.request(
                    clients[index],
                    "soak_cancel",
                    "POST",
                    f"/api/v1/scopes/{flow['scope']}/rabbit/requests/{pending[index][1]}/cancel",
                    json={},
                )
    return time.monotonic() - began


def resource_summary(path: Path, samples: list[dict[str, Any]]) -> dict[str, Any]:
    states = [json.loads(line) for line in (path / "server-metrics.jsonl").read_text().splitlines()]
    return {
        "server_peak_threads": max((row["server"].get("threads", 0) for row in samples), default=0),
        "server_peak_rss_kib": max(
            (row["server"].get("peak_rss_kib", 0) for row in samples), default=0
        ),
        "server_peak_children": max(
            (row["server"].get("direct_child_processes", 0) for row in samples), default=0
        ),
        "server_cpu_seconds": max(
            (row["server"].get("cpu_seconds", 0) for row in samples), default=0
        ),
        "gpu_queue_peak": max((row["gpu"].get("queued", 0) for row in states), default=0),
        "ai_active_peak": max((row["provider"]["active"] for row in states), default=0),
        "ai_queue_peak": max((row["provider"]["queued"] for row in states), default=0),
        "sampling_interval_seconds": 0.5,
        "peak_semantics": "observed at 0.5-second intervals, not absolute maxima",
    }


def wait_dispatched(client: Any, route: str) -> dict[str, Any]:
    until = time.monotonic() + 10
    while time.monotonic() < until:
        response = client.get(route)
        if response.status_code == 200 and response.json().get("dispatched"):
            return response.json()
        time.sleep(0.05)
    raise TimeoutError("Synthetic AI did not dispatch before restart injection")


def exercise_faults(
    server: FixtureProcess,
    client: Any,
    flow: dict[str, Any],
    metrics: Measurements,
) -> dict[str, Any]:
    metrics.phase = "fault"
    prefix = f"/api/v1/scopes/{flow['scope']}"
    request_route = prefix + "/requests/" + flow["request_id"]
    cancelled = metrics.request(client, "gpu_cancel", "POST", request_route + "/cancel", json={})
    resumed = metrics.request(client, "gpu_resume", "POST", request_route + "/resume", json={})
    key = uuid.uuid4().hex
    ai_route = prefix + "/rabbit/requests/" + key
    with ThreadPoolExecutor(max_workers=1) as pool:
        stream = pool.submit(
            metrics.request,
            client,
            "ai",
            "POST",
            prefix + "/rabbit/chat",
            headers={"X-Request-ID": key},
            json=chat_payload("capacity hold"),
        )
        wait_dispatched(client, ai_route)
        spec = json.loads((server.path / "spec.json").read_text())
        spec["port"] = server.port
        write_json(server.path / "spec.json", spec)
        server.stop(abrupt=True)
        stream.result(timeout=10)
    server.start()
    session = metrics.request(client, "me", "GET", "/api/v1/accounts/me")
    gpu = metrics.request(client, "gpu_status", "GET", request_route)
    old = metrics.request(client, "ai_status", "GET", ai_route)
    duplicate = metrics.request(
        client,
        "ai_duplicate",
        "POST",
        prefix + "/rabbit/chat",
        headers={"X-Request-ID": key},
        json=chat_payload("capacity hold"),
    )
    duplicate_row = metrics.rows[-1]
    replacement = metrics.request(
        client,
        "ai_replacement",
        "POST",
        prefix + "/rabbit/chat",
        headers={"X-Request-ID": uuid.uuid4().hex},
        json=chat_payload(),
    )
    result = {
        "gpu_cancelled": cancelled is not None and cancelled.json()["state"] == "failed",
        "gpu_resumed": resumed is not None,
        "gpu_queue_survived_restart": gpu is not None
        and gpu.json().get("result", {}).get("queue", {}).get("state") == "queued",
        "session_survived_restart": session is not None,
        "original_outcome": old.json().get("code") if old is not None else None,
        "unknown_ai_not_replayed": duplicate is None
        and duplicate_row["status"] == 409
        and duplicate_row["code"] == "request_already_processed",
        "new_ai_quota_recovered": replacement is not None
        and any(json.loads(line).get("type") == "done" for line in replacement.text.splitlines()),
    }
    result["passed"] = all(
        value is True for key, value in result.items() if key != "original_outcome"
    )
    result["passed"] &= result["original_outcome"] == "outcome_unknown"
    metrics.phase = "normal"
    return result


def slow_ai(
    flows: list[dict[str, Any]],
    clients: list[Any],
    identities: list[Any],
    metrics: Measurements,
    seconds: float,
    upload: bytes,
) -> dict[str, Any]:
    valid = [flow for flow in flows if flow.get("logged_in")]
    if not valid:
        return {"passed": False, "registered": 0, "cancelled": 0}
    keys = {flow["index"]: uuid.uuid4().hex for flow in valid}
    initial: list[dict[str, Any]] = []
    terminal: list[dict[str, Any]] = []
    began = time.monotonic()
    with ThreadPoolExecutor(max_workers=len(valid)) as streams:
        pending = {
            flow["index"]: streams.submit(
                metrics.request,
                clients[flow["index"]],
                "ai",
                "POST",
                f"/api/v1/scopes/{flow['scope']}/rabbit/chat",
                headers={"X-Request-ID": keys[flow["index"]]},
                json=chat_payload("capacity hold"),
                measurement_phase="slow_stream",
            )
            for flow in valid
        }
        until = time.monotonic() + 15
        for flow in valid:
            route = f"/api/v1/scopes/{flow['scope']}/rabbit/requests/{keys[flow['index']]}"
            while time.monotonic() < until:
                status = clients[flow["index"]].get(route)
                if status.status_code == 200:
                    initial.append(status.json())
                    break
                if pending[flow["index"]].done():
                    break
                time.sleep(0.05)

        def mixed(flow: dict[str, Any]) -> None:
            import httpx

            index = flow["index"]
            user, password = identities[index]
            client = clients[index]
            # A fresh browser session must not log out the session owning the waiting stream.
            with httpx.Client(
                base_url=str(client.base_url),
                trust_env=False,
                timeout=30,
                headers={"Origin": client.headers["Origin"]},
            ) as login_client:
                metrics.request(
                    login_client,
                    "login",
                    "POST",
                    "/api/v1/accounts/login",
                    json={"username": user.username, "password": password},
                )
            light_reads(flow, client, metrics)
            uploaded = metrics.request(
                client,
                "upload",
                "POST",
                f"/api/v1/scopes/{flow['scope']}/inputs?filename=synthetic.pdb",
                content=upload,
            )
            flow["slow_upload_integrity"] = uploaded is not None and upload_matches(
                uploaded.json(), upload
            )

        metrics.phase = "slow_mixed"
        try:
            with ThreadPoolExecutor(max_workers=len(valid)) as readers:
                list(readers.map(mixed, valid))
            time.sleep(max(0.0, began + seconds - time.monotonic()))
        finally:
            metrics.phase = "slow_cancel"

            def cancel(flow: dict[str, Any]) -> None:
                metrics.request(
                    clients[flow["index"]],
                    "ai_cancel",
                    "POST",
                    f"/api/v1/scopes/{flow['scope']}/rabbit/requests/{keys[flow['index']]}/cancel",
                    json={},
                )

            # Control cleanup has its own bounded fan-out, not a disguised retry of rejected work.
            with ThreadPoolExecutor(max_workers=min(32, len(valid))) as cancellers:
                list(cancellers.map(cancel, valid))
            for future in pending.values():
                future.result(timeout=95)
            for flow in valid:
                response = clients[flow["index"]].get(
                    f"/api/v1/scopes/{flow['scope']}/rabbit/requests/{keys[flow['index']]}"
                )
                if response.status_code == 200:
                    terminal.append(response.json())
            metrics.phase = "normal"
    mixed_result = summarize([row for row in metrics.rows if row["phase"] == "slow_mixed"], [])
    cancelled = sum(row["state"] == "cancelled" for row in terminal)
    return {
        "requested_hold_seconds": seconds,
        "measured_seconds": time.monotonic() - began,
        "registered": len(initial),
        "initial_queued": sum(row["state"] == "queued" for row in initial),
        "initial_running": sum(row["state"] == "running" for row in initial),
        "cancelled": cancelled,
        "mixed_upload_integrity_verified": sum(
            bool(flow.get("slow_upload_integrity")) for flow in valid
        ),
        "mixed": mixed_result,
        "completed_model_responses": sum(row["state"] == "completed" for row in terminal),
        "stream_outcomes": dict(Counter(row.get("code") or row["state"] for row in terminal)),
        "passed": len(initial) == len(flows) == cancelled
        and mixed_result["recognized_refusals"] == mixed_result["unexpected_failures"] == 0
        and mixed_result["latency_targets_pass"]
        and all(flow.get("slow_upload_integrity") for flow in valid),
    }


def synthetic_pdb(size: int) -> bytes:
    atom = b"ATOM      1  CA  ALA A   1      11.000  12.000  13.000  1.00 20.00           C\nEND\n"
    if not 128 <= size <= 32 * 1024**2:
        raise ValueError("Synthetic PDB size must be 128 bytes..32 MiB")
    padding = size - len(atom) - 1
    line = b"REMARK synthetic capacity padding\n"
    return (line * math.ceil(padding / len(line)))[:padding] + b"\n" + atom


def upload_matches(receipt: dict[str, Any], content: bytes) -> bool:
    return (
        bool(receipt.get("id"))
        and receipt.get("sha256") == hashlib.sha256(content).hexdigest()
        and receipt.get("size_bytes") == len(content)
    )


def upload_boundary(client: Any, flow: dict[str, Any], metrics: Measurements) -> dict[str, Any]:
    metrics.phase = "boundary"
    route = f"/api/v1/scopes/{flow['scope']}/inputs?filename=maximum.pdb"
    content = synthetic_pdb(32 * 1024**2)
    accepted = metrics.request(client, "upload_boundary", "POST", route, content=content)
    integrity = accepted is not None and upload_matches(accepted.json(), content)
    assert client.base_url.host == "127.0.0.1"
    # Send an oversized declared length without flooding a connection the server rejects early.
    # This tests the bounded-body contract, not a 32-MiB+1 throughput measurement.
    request = client.build_request("POST", route, content=b"")
    headers = dict(request.headers)
    headers["content-length"] = str(32 * 1024**2 + 1)
    connection = HTTPConnection("127.0.0.1", client.base_url.port, timeout=10)
    started = time.monotonic()
    try:
        connection.request("POST", route, headers=headers)
        response = connection.getresponse()
        status, data = response.status, json.loads(response.read())
    finally:
        connection.close()
        metrics.phase = "normal"
    return {
        "maximum_accepted_bytes": 32 * 1024**2 if accepted is not None else 0,
        "maximum_integrity_verified": integrity,
        "oversize_declared_bytes": 32 * 1024**2 + 1,
        "oversize_status": status,
        "oversize_code": data.get("error", {}).get("code"),
        "oversize_seconds": time.monotonic() - started,
        "passed": integrity
        and status == 413
        and data.get("error", {}).get("code") == "payload_too_large",
    }


def run_stage(
    *,
    users: int,
    profile: str = "conservative",
    login_window_seconds: float = 5.0,
    soak_seconds: float = 0,
    poll_seconds: float = 5.0,
    fault_checks: bool = False,
    hold_seconds: float = 0,
    upload_bytes: int = 65536,
    boundary_uploads: bool = False,
) -> dict[str, Any]:
    import httpx

    from easydesign.product.accounts import AccountStore
    from easydesign.product.capacity_config import CapacityConfig
    from easydesign.product.rabbit_capacity import RabbitCapacityLimits
    from easydesign.workspace_context import WorkspaceContext

    if not 1 <= users <= 300 or profile not in {"conservative", "stub-throughput"}:
        raise ValueError("Use 1..300 synthetic users and an explicit supported profile")
    if not 0 <= soak_seconds <= 1800 or not 0 <= login_window_seconds <= 30:
        raise ValueError("Invalid bounded test duration")
    if not 0.1 <= poll_seconds <= 60:
        raise ValueError("Polling interval must be 0.1..60 seconds")
    if not 0 <= hold_seconds <= 30 or (hold_seconds and (fault_checks or soak_seconds)):
        raise ValueError("Slow AI is a separate 0..30-second scenario, not a soak/restart phase")
    upload = synthetic_pdb(upload_bytes)
    base = ROOT / "runtime/tmp"
    base.mkdir(parents=True, exist_ok=True)
    path = Path(tempfile.mkdtemp(prefix="capacity-smoke-", dir=base))
    os.chmod(path, 0o700)
    config = CapacityConfig()
    defaults = asdict(RabbitCapacityLimits())
    if profile == "stub-throughput":
        config.ai = {
            "max_active": 16,
            "requests_per_minute": 60000,
            "requests_per_minute_per_user": 600,
            "queue_timeout_seconds": 120.0,
        }
    limits = asdict(RabbitCapacityLimits(**config.ai))
    write_json(path / "spec.json", {"marker": MARKER, "capacity": config.model_dump()})
    workspace = path / "workspace"
    workspace.mkdir()
    (workspace / "easydesign-workspace.yaml").write_text('schema_version: "0.1"\n')
    (workspace / "models.yaml").write_text(
        "default:\n  provider: openai\n  model: synthetic-forbidden\n"
        "  secret_env: EASYDESIGN_CAPACITY_STUB_NO_CREDENTIAL\n"
    )
    (workspace / "web/assets").mkdir(parents=True)
    (workspace / "web/index.html").write_text(
        "<html><body>Capacity fixture, not product UI</body></html>"
    )
    (workspace / "web/assets/fixture-BAsZliUl.js").write_text(
        "/* synthetic static content */\n" * 4096
    )
    context = WorkspaceContext.from_root(workspace)
    context.ensure_layout()
    accounts = AccountStore(context.runtime_root / "state/accounts/accounts.sqlite")
    admin = accounts.bootstrap_admin("fixture-admin", secrets.token_urlsafe(24), "Fixture admin")
    identities = []
    for index in range(users):
        password = secrets.token_urlsafe(24)
        user = accounts.register(
            f"fixture-{index}", password, "Synthetic user", peer=f"seed-{index}"
        )
        accounts.update_user(admin, user.id, status="active")
        if fault_checks and index == 0:
            accounts.set_limits(
                admin,
                user.id,
                accounts.limits(admin, user.id).model_copy(update={"max_active_chats": 1}),
            )
        identities.append((user, password))
    # The report records strength without persisting passwords or full hash material.
    with accounts.db() as database:
        iterations = {
            int(row[0].split("$")[1]) for row in database.execute("SELECT password_hash FROM users")
        }
    if iterations != {600000}:
        raise RuntimeError("Capacity fixture password strength differs from the required baseline")
    server = FixtureProcess(path)
    metrics = Measurements(path)
    clients: list[Any] = []
    samples: list[dict[str, Any]] = []
    sampler_stop = threading.Event()

    def sample_resources() -> None:
        with (path / "process-metrics.jsonl").open("a") as evidence:
            while not sampler_stop.wait(0.5):
                if server.process is not None:
                    row = {
                        "server": process_sample(server.process.pid),
                        "load_generator": process_sample(os.getpid()),
                    }
                    samples.append(row)
                    evidence.write(json.dumps(row) + "\n")
                    evidence.flush()

    thread = threading.Thread(target=sample_resources, daemon=True)
    flows: list[dict[str, Any]] = []
    try:
        server.start()
        thread.start()
        clients = [
            httpx.Client(
                base_url=server.origin,
                headers={"Origin": server.origin},
                trust_env=False,
                timeout=150,
            )
            for _ in identities
        ]
        start = time.monotonic() + 1.0

        def initial(index: int) -> dict[str, Any]:
            user, password = identities[index]
            client = clients[index]
            scheduled = start + login_window_seconds * index / max(1, users - 1)
            time.sleep(max(0.0, scheduled - time.monotonic()))
            flow: dict[str, Any] = {
                "ok": True,
                "index": index,
                "scope": user.id,
                "request_id": uuid.uuid4().hex,
            }
            login = metrics.request(
                client,
                "login",
                "POST",
                "/api/v1/accounts/login",
                json={"username": user.username, "password": password},
            )
            if login is None:
                flow["ok"] = False
                return flow
            client.headers["X-CSRF-Token"] = login.json()["csrf_token"]
            flow["logged_in"] = True
            prefix = f"/api/v1/scopes/{user.id}"
            for operation, route in (
                ("static", "/assets/fixture-BAsZliUl.js"),
                ("me", "/api/v1/accounts/me"),
                ("projects", prefix + "/projects"),
            ):
                flow["ok"] &= metrics.request(client, operation, "GET", route) is not None
            uploaded = metrics.request(
                client,
                "upload",
                "POST",
                prefix + "/inputs?filename=synthetic.pdb",
                content=upload,
            )
            flow["upload_integrity"] = uploaded is not None and upload_matches(
                uploaded.json(), upload
            )
            flow["ok"] &= flow["upload_integrity"]
            if not flow["upload_integrity"]:
                return flow
            input_id = uploaded.json()["id"]
            queued = metrics.request(
                client,
                "gpu_submit",
                "POST",
                prefix + "/projects",
                json={
                    "request_id": flow["request_id"],
                    "title": "Synthetic fixture",
                    "goal": "Synthetic target",
                    "input_id": input_id,
                },
            )
            flow["ok"] &= queued is not None
            flow["input_bound"] = queued is not None
            if queued is not None:
                flow["project"] = queued.json()["project"]
            return flow

        with ThreadPoolExecutor(max_workers=users) as pool:
            flows = list(pool.map(initial, range(users)))

            def complete(flow: dict[str, Any]) -> None:
                if not flow.get("logged_in"):
                    return
                client = clients[flow["index"]]
                prefix = f"/api/v1/scopes/{flow['scope']}"
                if flow.get("project"):
                    status = metrics.request(
                        client, "gpu_status", "GET", prefix + "/requests/" + flow["request_id"]
                    )
                    flow["gpu_queued"] = (
                        status is not None
                        and status.json().get("result", {}).get("queue", {}).get("state")
                        == "queued"
                    )
                    flow["ok"] &= flow["gpu_queued"]
                    flow["ok"] &= (
                        metrics.request(
                            client,
                            "snapshot",
                            "GET",
                            prefix + f"/projects/{flow['project']}/workbench",
                        )
                        is not None
                    )
                if hold_seconds:
                    flow["pre_ai_ok"] = flow["ok"]
                    # Cancellation is not a completed model response/full flow.
                    flow["ok"] = False
                    return
                flow["ai_completed"] = (
                    metrics.request(
                        client,
                        "ai",
                        "POST",
                        prefix + "/rabbit/chat",
                        headers={"X-Request-ID": uuid.uuid4().hex},
                        json={
                            "locale": "en",
                            "messages": [{"role": "user", "content": "fixture"}],
                            "context": {"stage": "Idle", "status": "idle", "goal": ""},
                        },
                    )
                    is not None
                )
                flow["ok"] &= flow["ai_completed"]

            list(pool.map(complete, flows))
        measured_soak = soak(flows, clients, metrics, soak_seconds, poll_seconds)
        slow = (
            slow_ai(
                flows,
                clients,
                identities,
                metrics,
                hold_seconds,
                upload,
            )
            if hold_seconds
            else None
        )
        faults = None
        if fault_checks:
            selected = next((flow for flow in flows if flow.get("project")), None)
            if selected is not None:
                faults = exercise_faults(server, clients[selected["index"]], selected, metrics)
        boundaries = None
        if boundary_uploads:
            selected = next((flow for flow in flows if flow.get("logged_in")), None)
            if selected is not None:
                boundaries = upload_boundary(clients[selected["index"]], selected, metrics)
        # Allow one observation after final completion; excluded from request timings.
        time.sleep(0.6)
        state = json.loads((path / "server-state.json").read_text())
        login_starts = [
            row["started_at"]
            for row in metrics.rows
            if row["operation"] == "login" and row["phase"] == "normal"
        ]
        result = {
            "scope": "isolated_local_engineering_stub",
            "tenant_shape": "independent personal scopes, not a shared team workload",
            "profile": profile,
            "evidence_path": str(path),
            "users": users,
            "soak_seconds": soak_seconds,
            "measured_soak_seconds": measured_soak,
            "poll_seconds": poll_seconds,
            "login_window_seconds": login_window_seconds,
            "observed_login_start_span_seconds": max(login_starts) - min(login_starts)
            if login_starts
            else None,
            "password_iterations": 600000,
            "upload_bytes_per_user": upload_bytes,
            "upload_format": "synthetic_PDB_with_remark_padding",
            "upload_boundaries": boundaries,
            "uploads": {
                "integrity_verified": sum(bool(flow.get("upload_integrity")) for flow in flows),
                "input_bound": sum(bool(flow.get("input_bound")) for flow in flows),
            },
            "production_ai_defaults": defaults,
            "test_ai_limits": limits,
            "capacity_config": config.model_dump(),
            "summary": summarize([row for row in metrics.rows if row["phase"] == "normal"], flows),
            "faults": faults,
            "fault_fixture_chat_quota": 1 if fault_checks else None,
            "owned_process_groups": server.owned_process_groups,
            "slow_ai": slow,
            "fault_summary": summarize(
                [row for row in metrics.rows if row["phase"] == "fault"], []
            ),
            "boundary_summary": summarize(
                [row for row in metrics.rows if row["phase"] == "boundary"], []
            ),
            "gpu": {
                "queued": sum(bool(flow.get("gpu_queued")) for flow in flows),
                "scientific_completed": 0,
            },
            "provider": state["provider"],
            "forbidden_scientific_spawns": state["forbidden_scientific_spawns"],
            "host": {
                "logical_cpus": os.cpu_count(),
                "machine": os.uname().machine,
                "mem_total": next(
                    line
                    for line in Path("/proc/meminfo").read_text().splitlines()
                    if line.startswith("MemTotal:")
                ),
            },
            "resource_samples": len(samples),
            "resources": resource_summary(path, samples),
            "flows": flows,
            "limitations": [
                "No production network/CDN or browser rendering measurement",
                "No paid provider/GPU throughput or scientific validation",
                "300 queue slots do not promise completion under default 20 RPM/120s",
            ],
            "finished_at": datetime.now(UTC).isoformat(),
        }
        write_json(path / "report.json", result)
        return result
    finally:
        for client in clients:
            client.close()
        server.stop()
        sampler_stop.set()
        if thread.is_alive():
            thread.join(timeout=3)
        metrics.close()


def stage_counts(value: str) -> tuple[int, ...]:
    try:
        counts = tuple(int(part) for part in value.split(","))
    except ValueError as error:
        raise argparse.ArgumentTypeError("Use increasing user counts, e.g. 30,100,300") from error
    if (
        not counts
        or len(counts) > 3
        or tuple(sorted(set(counts))) != counts
        or not (1 <= counts[0] <= counts[-1] <= 300)
    ):
        raise argparse.ArgumentTypeError("Use 1..3 strictly increasing counts within 1..300")
    return counts


def acceptance_passed(
    report: dict[str, Any],
    *,
    slow: bool = False,
    faults: bool = False,
    boundaries: bool = False,
) -> bool:
    passed = (
        (report["slow_ai"]["passed"] and all(flow.get("pre_ai_ok") for flow in report["flows"]))
        if slow
        else report["summary"]["goal_pass"]
    )
    return bool(
        passed
        and report.get("forbidden_scientific_spawns") == 0
        and (not faults or (report["faults"] and report["faults"]["passed"]))
        and (
            not boundaries
            or (report["upload_boundaries"] and report["upload_boundaries"]["passed"])
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serve", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--provider-stub", action="store_true", help=argparse.SUPPRESS)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--users", type=int)
    group.add_argument("--stages", type=stage_counts, help="e.g. 30,100,300; final stage gets soak")
    parser.add_argument(
        "--profile", choices=("conservative", "stub-throughput"), default="conservative"
    )
    parser.add_argument("--login-window-seconds", type=float, default=5.0)
    parser.add_argument("--soak-seconds", type=float, default=0)
    parser.add_argument("--poll-seconds", type=float, default=5.0)
    parser.add_argument(
        "--hold-seconds",
        type=float,
        default=0,
        help="separate slow-AI scenario; submitted streams are cancelled, not completed",
    )
    parser.add_argument("--upload-bytes", type=int, default=65536)
    parser.add_argument(
        "--fault-checks", action="store_true", help="final-stage owned-process restart"
    )
    parser.add_argument(
        "--boundary-uploads", action="store_true", help="one final-stage 32MiB sample"
    )
    args = parser.parse_args()
    if args.provider_stub:
        provider_stub()
        return 0
    if args.serve:
        serve_fixture(args.serve)
        return 0
    counts = args.stages or (args.users or 2,)
    for index, users in enumerate(counts):
        final = index == len(counts) - 1
        report = run_stage(
            users=users,
            profile=args.profile,
            login_window_seconds=args.login_window_seconds,
            soak_seconds=args.soak_seconds if final else 0,
            poll_seconds=args.poll_seconds,
            hold_seconds=args.hold_seconds,
            upload_bytes=args.upload_bytes,
            fault_checks=args.fault_checks and final,
            boundary_uploads=args.boundary_uploads and final,
        )
        print(
            json.dumps(
                {
                    key: report[key]
                    for key in (
                        "users",
                        "evidence_path",
                        "summary",
                        "faults",
                        "slow_ai",
                        "upload_boundaries",
                        "forbidden_scientific_spawns",
                    )
                }
            ),
            flush=True,
        )
        passed = acceptance_passed(
            report,
            slow=bool(args.hold_seconds),
            faults=args.fault_checks and final,
            boundaries=args.boundary_uploads and final,
        )
        if not passed:
            # Do not silently escalate a failed smaller workload to a larger one.
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
