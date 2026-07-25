from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from easydesign.core import (
    DecisionAuthority,
    DecisionOption,
    DecisionRecord,
    DecisionRequest,
)


def test_decision_request_has_unique_versioned_options() -> None:
    request = DecisionRequest(
        decision_id="stage01-structure-selection",
        stage_id="01-target-preparation",
        gate="structure-selection",
        created_at=datetime(2026, 7, 25, tzinfo=UTC),
        message="Select one structure or prediction.",
        options=(
            DecisionOption(
                option_id="pdb-1ubq",
                label="1UBQ",
                description="Eligible X-ray structure.",
            ),
            DecisionOption(
                option_id="predict-protenix-v2",
                label="Predict",
                description="Use required-MSA Protenix-v2.",
            ),
        ),
    )

    assert request.revision == 1
    assert request.status == "pending"


def test_deterministic_record_requires_policy_identity() -> None:
    with pytest.raises(ValidationError, match="policy_id"):
        DecisionRecord(
            decision_id="stage02-hotspot-selection",
            request_revision=1,
            request_sha256="a" * 64,
            authority=DecisionAuthority.DETERMINISTIC_POLICY,
            selected_option_ids=("sasa-region-1",),
            approved_at=datetime(2026, 7, 25, tzinfo=UTC),
            approved_by="easydesign",
        )
