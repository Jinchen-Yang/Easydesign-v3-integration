from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from easydesign.agent.contracts import AgentBoundaryError
from easydesign.agent.phase34_fixtures import verify_accepted_gate3_fixtures


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_gate3_fixture_verifier_rejects_changed_source(tmp_path: Path) -> None:
    source_request = tmp_path / "request.json"
    source_receipt = tmp_path / "receipt.json"
    fixture_source = json.loads(
        Path("tests/fixtures/agent/phase34_gate3_fixtures.json").read_text()
    )["fixtures"][0]
    request = {
        "snapshot_sha256": fixture_source["gate3_snapshot_sha256"],
        "evidence": {
            "card": {
                "gate_type": "design-specification",
                "card_id": fixture_source["gate3_card_id"],
                "request_identity": fixture_source["gate3_request_identity"],
            },
            "snapshot": {
                "proposal": {"strategy_source": fixture_source["strategy_source"]},
                "evaluation": {
                    "planned_candidates": fixture_source["planned_candidates"],
                    "generation_started": False,
                },
            },
            "artifact_hashes": [
                fixture_source["target_bundle_sha256"],
                fixture_source["site_intent_sha256"],
                fixture_source["strategy_sha256"],
                fixture_source["compiled_manifest_sha256"],
                fixture_source["execution_plan_sha256"],
            ],
            "target_identity": fixture_source["target_identity"],
        },
    }
    receipt = {
        "snapshot_sha256": fixture_source["gate3_snapshot_sha256"],
        "Decision": "PASS",
        "acceptance_scope": fixture_source["acceptance_scope"],
    }
    source_request.write_text(json.dumps(request))
    source_receipt.write_text(json.dumps(receipt))
    fixture_source.update(
        {
            "review_request_sha256": _sha(source_request),
            "review_receipt_sha256": _sha(source_receipt),
        }
    )
    fixture_path = tmp_path / "fixtures.json"
    fixture_path.write_text(json.dumps({"fixtures": [fixture_source]}))
    index_path = tmp_path / "index.json"
    index_path.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "case": fixture_source["case_id"],
                        "source_commit": fixture_source["source_commit"],
                        "milestone_tag": fixture_source["milestone_tag"],
                        "snapshot_sha256": fixture_source["gate3_snapshot_sha256"],
                        "request": str(source_request),
                        "receipt": str(source_receipt),
                        "request_file_sha256": fixture_source["review_request_sha256"],
                        "receipt_file_sha256": fixture_source["review_receipt_sha256"],
                    }
                ]
            }
        )
    )
    report = verify_accepted_gate3_fixtures(
        fixture_path=fixture_path,
        acceptance_index_path=index_path,
    )
    assert report["status"] == "PASS"
    source_receipt.write_text(source_receipt.read_text() + "\n")
    with pytest.raises(AgentBoundaryError, match="hash changed"):
        verify_accepted_gate3_fixtures(
            fixture_path=fixture_path,
            acceptance_index_path=index_path,
        )
