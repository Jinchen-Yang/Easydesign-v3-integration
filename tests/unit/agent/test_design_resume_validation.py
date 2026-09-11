"""Validation runner recovery must preserve the already applied scientific authority."""

import hashlib
import importlib
import json
from copy import deepcopy
from typing import Any

import pytest


def test_reviewed_site_resume_checks_exact_preapproval_content_and_applied_gate(
    site_bridge: Any, monkeypatch: Any, tmp_path: Any
) -> None:
    monkeypatch.setenv("EASYDESIGN_GOLDEN_SOURCE_ROOT", str(tmp_path))
    from scripts.validate_phase2_design_resume import reviewed_site
    from tests.unit.agent.test_site_runtime import propose, reviewed_card

    golden = importlib.import_module("scripts.validate_phase2_goldens")
    bridge = site_bridge
    propose(bridge)
    card = reviewed_card(bridge)
    request = {
        "evidence": {
            "card": card.model_dump(mode="json"),
            "site": bridge.site_snapshot(bridge.current_site()),
            "judge": golden.judge_record(bridge, card.model_dump(mode="json")),
        },
        "required_review_sections": [
            "Hard Facts",
            "Scientific Interpretation",
            "Evidence",
            "Uncertainty",
            "Alternatives",
            "Decision",
        ],
    }
    request["snapshot_sha256"] = hashlib.sha256(
        json.dumps(request["evidence"], sort_keys=True, default=str).encode()
    ).hexdigest()
    review = {
        key: "SYNTHETIC receipt fixture; mechanics only"
        for key in request["required_review_sections"]
    } | {
        "Decision": "PASS",
        "reviewer": "development-scientific-content-review",
        "snapshot_sha256": request["snapshot_sha256"],
    }
    with pytest.raises(AssertionError):
        reviewed_site(bridge, request, review)
    bridge.store.respond(bridge.thread, card.card_id, "approve", golden.ACTOR)
    bridge.apply_decision(card)
    # The same trusted delivery event used by the runtime must have been completed.
    response = bridge.store.response(bridge.thread, card.card_id)
    assert response
    if not response["delivered"]:
        bridge.store.delivered(bridge.thread, card.card_id)
    jobs_before = [job.job_id for job in bridge.controller.list(project_id=bridge.project_id)]
    approved = reviewed_site(bridge, request, review)
    assert approved["proposal"]["intent"] == request["evidence"]["site"]["proposal"]
    assert approved["outcome"]["card_id"] == card.card_id
    assert jobs_before == [
        job.job_id for job in bridge.controller.list(project_id=bridge.project_id)
    ]
    for bad_review in (review | {"Decision": "FAIL"}, review | {"snapshot_sha256": "wrong"}):
        with pytest.raises(AssertionError):
            reviewed_site(bridge, request, bad_review)
    changed = deepcopy(request)
    changed["evidence"]["site"]["proposal"]["mechanistic_rationale"] = "Changed after review"
    with pytest.raises(AssertionError):
        reviewed_site(bridge, changed, review)
