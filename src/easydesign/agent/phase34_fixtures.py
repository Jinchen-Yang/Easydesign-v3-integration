"""Read-only verification of accepted pending Gate 3 development fixtures."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from .contracts import AgentBoundaryError
from .phase34_contracts import AcceptedGate3Fixture


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AgentBoundaryError(message)


def verify_accepted_gate3_fixtures(
    *,
    fixture_path: Path,
    acceptance_index_path: Path,
    source_repository: Path | None = None,
) -> dict[str, Any]:
    """Verify fixture projections against exact immutable acceptance source files."""

    fixture_payload = json.loads(fixture_path.read_text())
    fixtures = tuple(
        AcceptedGate3Fixture.model_validate(item) for item in fixture_payload["fixtures"]
    )
    acceptance_index = json.loads(acceptance_index_path.read_text())
    indexed = {item["case"]: item for item in acceptance_index["cases"]}
    results: list[dict[str, Any]] = []
    for fixture in fixtures:
        _require(fixture.case_id in indexed, f"fixture case missing: {fixture.case_id}")
        source = indexed[fixture.case_id]
        request_path = Path(source["request"])
        receipt_path = Path(source["receipt"])
        _require(request_path.is_file(), f"accepted request missing: {request_path}")
        _require(receipt_path.is_file(), f"accepted receipt missing: {receipt_path}")
        _require(
            _file_sha256(request_path) == fixture.review_request_sha256,
            f"accepted request hash changed: {fixture.case_id}",
        )
        _require(
            _file_sha256(receipt_path) == fixture.review_receipt_sha256,
            f"accepted receipt hash changed: {fixture.case_id}",
        )
        for fixture_field, source_field in (
            ("source_commit", "source_commit"),
            ("milestone_tag", "milestone_tag"),
            ("gate3_snapshot_sha256", "snapshot_sha256"),
            ("review_request_sha256", "request_file_sha256"),
            ("review_receipt_sha256", "receipt_file_sha256"),
        ):
            _require(
                getattr(fixture, fixture_field) == source[source_field],
                f"acceptance index mismatch for {fixture.case_id}:{fixture_field}",
            )
        request = json.loads(request_path.read_text())
        receipt = json.loads(receipt_path.read_text())
        card = request["evidence"]["card"]
        snapshot = request["evidence"]["snapshot"]
        _require(card["gate_type"] == "design-specification", "fixture is not Gate 3")
        _require(card["card_id"] == fixture.gate3_card_id, "Gate 3 card identity changed")
        _require(
            card["request_identity"] == fixture.gate3_request_identity,
            "Gate 3 request identity changed",
        )
        _require(
            request["snapshot_sha256"] == fixture.gate3_snapshot_sha256,
            "request snapshot identity changed",
        )
        _require(
            receipt["snapshot_sha256"] == fixture.gate3_snapshot_sha256,
            "receipt snapshot identity changed",
        )
        _require(receipt["Decision"] == fixture.review_decision, "review is not accepted")
        _require(
            receipt["acceptance_scope"] == fixture.acceptance_scope,
            "acceptance scope changed",
        )
        _require(
            snapshot["proposal"]["strategy_source"] == fixture.strategy_source,
            "strategy source changed",
        )
        evaluation = snapshot["evaluation"]
        _require(
            evaluation["planned_candidates"] == fixture.planned_candidates,
            "planned candidate count changed",
        )
        _require(
            evaluation["generation_started"] is fixture.generation_started,
            "generation authority state changed",
        )
        evidence_text = json.dumps(request["evidence"], sort_keys=True)
        for artifact_hash in (
            fixture.target_bundle_sha256,
            fixture.site_intent_sha256,
            fixture.strategy_sha256,
            fixture.compiled_manifest_sha256,
            fixture.execution_plan_sha256,
        ):
            _require(
                artifact_hash in evidence_text,
                f"accepted Gate 3 evidence lost artifact {artifact_hash}",
            )
        _require(
            fixture.target_identity.split(":", 1)[-1] in evidence_text,
            "accepted Gate 3 evidence lost target identity",
        )
        tag_commit = None
        if source_repository is not None:
            resolved = subprocess.run(
                ["git", "rev-list", "-n", "1", fixture.milestone_tag],
                cwd=source_repository,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            _require(resolved == source["tag_commit"], "accepted milestone tag moved")
            tag_commit = resolved
        results.append(
            {
                "fixture_id": fixture.fixture_id,
                "case_id": fixture.case_id,
                "status": "VERIFIED_ACCEPTED_PENDING_GATE3",
                "request_path": str(request_path),
                "request_sha256": fixture.review_request_sha256,
                "receipt_path": str(receipt_path),
                "receipt_sha256": fixture.review_receipt_sha256,
                "snapshot_sha256": fixture.gate3_snapshot_sha256,
                "milestone_tag": fixture.milestone_tag,
                "tag_commit": tag_commit,
                "generation_started": False,
                "scientific_authority": "pending-human-gate3",
            }
        )
    return {
        "schema_version": "0.1",
        "status": "PASS",
        "source_index": str(acceptance_index_path),
        "source_index_sha256": _file_sha256(acceptance_index_path),
        "fixtures": results,
        "scope": (
            "Read-only verification of accepted Design evidence. No Gate 3 approval, "
            "scientific Pilot authority, generation, or prediction is created."
        ),
    }
