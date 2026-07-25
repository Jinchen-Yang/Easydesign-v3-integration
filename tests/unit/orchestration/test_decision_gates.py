from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import yaml

from easydesign.core import DecisionOption, DecisionRequest, load_model
from easydesign.orchestration.decisions import (
    approve_decision,
    export_decision,
    publish_decision_request,
)


def test_decision_export_and_approval_pin_request_hash(tmp_path: Path) -> None:
    run = tmp_path / "run"
    request = DecisionRequest(
        decision_id="stage01-chain-selection",
        stage_id="01-target-preparation",
        gate="chain-selection",
        created_at=datetime(2026, 7, 25, tzinfo=UTC),
        message="Choose a chain.",
        options=(
            DecisionOption(
                option_id="chain-a",
                label="A",
                description="Protein chain A.",
            ),
        ),
    )
    publish_decision_request(run, request)
    review = export_decision(run, output=tmp_path / "decision.yaml")
    payload = yaml.safe_load(review.read_text(encoding="utf-8"))
    payload["selected_option_ids"] = ["chain-a"]
    payload["approved_by"] = "tester"
    review.write_text(
        yaml.safe_dump(payload, sort_keys=False),
        encoding="utf-8",
    )

    record_path = approve_decision(
        run,
        input_path=review,
        approved_at=datetime(2026, 7, 25, 1, tzinfo=UTC),
    )

    from easydesign.core import DecisionRecord

    record = load_model(record_path, DecisionRecord)
    assert record.selected_option_ids == ("chain-a",)
    assert record.authority == "human"
