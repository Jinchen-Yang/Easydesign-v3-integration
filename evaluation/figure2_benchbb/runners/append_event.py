#!/usr/bin/env python3
"""Append one immutable external Figure 2 event to a JSONL ledger."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path


def sha256_or_none(path: str | None) -> str | None:
    if path is None:
        return None
    resolved = Path(path).resolve(strict=True)
    digest = hashlib.sha256()
    with resolved.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--method-id", required=True, choices=("base_llm_tools", "generic_agent", "easydesign_v3_full", "expert_curated_reference"))
    parser.add_argument("--replicate", type=int, required=True)
    parser.add_argument("--actor", required=True, choices=("model", "method_framework", "easydesign", "operator", "transport", "validator", "backend"))
    parser.add_argument("--stage", required=True, choices=("discovery", "target", "structure", "site", "design", "compiler", "backend-validation", "pilot-ready", "run"))
    parser.add_argument("--event-type", required=True)
    parser.add_argument("--status", required=True)
    parser.add_argument("--attempt-id")
    parser.add_argument("--self-recovery-episode-id")
    parser.add_argument("--operator-episode-id")
    parser.add_argument("--input-artifact")
    parser.add_argument("--output-artifact")
    parser.add_argument("--error-type")
    parser.add_argument("--blocker-category")
    parser.add_argument("--payload-json", default="{}")
    args = parser.parse_args()
    if args.replicate < 1:
        raise ValueError("replicate must be >= 1")
    payload = json.loads(args.payload_json)
    if not isinstance(payload, dict):
        raise ValueError("payload-json must decode to an object")
    ledger = args.ledger.resolve(strict=False)
    ledger.parent.mkdir(parents=True, exist_ok=True)
    event = {
        "schema_version": "figure2-benchbb-run-event-v1",
        "event_id": str(uuid.uuid4()),
        "run_id": args.run_id,
        "case_id": args.case_id,
        "method_id": args.method_id,
        "replicate": args.replicate,
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "monotonic_ns": time.monotonic_ns(),
        "actor": args.actor,
        "stage": args.stage,
        "event_type": args.event_type,
        "status": args.status,
        "attempt_id": args.attempt_id,
        "self_recovery_episode_id": args.self_recovery_episode_id,
        "operator_episode_id": args.operator_episode_id,
        "input_artifact": args.input_artifact,
        "input_sha256": sha256_or_none(args.input_artifact),
        "output_artifact": args.output_artifact,
        "output_sha256": sha256_or_none(args.output_artifact),
        "error_type": args.error_type,
        "blocker_category": args.blocker_category,
        "payload": payload,
    }
    descriptor = os.open(ledger, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(descriptor, "a", encoding="utf-8") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        handle.write(json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    print(json.dumps({"event_id": event["event_id"], "ledger": str(ledger)}))


if __name__ == "__main__":
    main()
