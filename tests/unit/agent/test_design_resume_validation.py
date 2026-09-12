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


def test_failed_design_review_can_only_steer_the_exact_unanswered_pending_card(
    design_bridge: Any, monkeypatch: Any, tmp_path: Any
) -> None:
    monkeypatch.setenv("EASYDESIGN_GOLDEN_SOURCE_ROOT", str(tmp_path))
    from scripts.validate_phase2_design_resume import reviewed_design_revision
    from tests.unit.agent.test_design_runtime import binder_intent, design_card, propose_design

    golden = importlib.import_module("scripts.validate_phase2_goldens")
    bridge = design_bridge
    propose_design(bridge, binder_intent())
    card = design_card(bridge)
    request = {
        "evidence": {
            "card": card.model_dump(mode="json"),
            "snapshot": bridge.design_snapshot(bridge.current_design()),
            "judge": golden.judge_record(bridge, card.model_dump(mode="json")),
            "approved_site": bridge.approved_site(),
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
        k: "SYNTHETIC review fixture; no biological judgment"
        for k in request["required_review_sections"]
    } | {
        "Decision": "FAIL",
        "reviewer": "development-scientific-content-review",
        "snapshot_sha256": request["snapshot_sha256"],
        "revision_instruction": "Clarify the existing scientific explanation; retain all bounds.",
    }
    jobs_before = [j.job_id for j in bridge.controller.list(project_id=bridge.project_id)]
    steering = reviewed_design_revision(bridge, request, review)
    assert steering == {
        "decision": "revise",
        "card_id": card.card_id,
        "user": golden.ACTOR,
        "human_instruction": review["revision_instruction"],
    }
    assert bridge.store.response(bridge.thread, card.card_id) is None
    assert jobs_before == [j.job_id for j in bridge.controller.list(project_id=bridge.project_id)]
    for invalid in (review | {"Decision": "PASS"}, review | {"revision_instruction": ""}):
        with pytest.raises(AssertionError):
            reviewed_design_revision(bridge, request, invalid)
    changed = deepcopy(request)
    changed["evidence"]["snapshot"]["proposal"]["objective"] = "Changed after actual review"
    changed["snapshot_sha256"] = hashlib.sha256(
        json.dumps(changed["evidence"], sort_keys=True, default=str).encode()
    ).hexdigest()
    with pytest.raises(AssertionError):
        reviewed_design_revision(
            bridge, changed, review | {"snapshot_sha256": changed["snapshot_sha256"]}
        )
    bridge.store.respond(bridge.thread, card.card_id, "approve", "synthetic-scientist")
    with pytest.raises(AssertionError):
        reviewed_design_revision(bridge, request, review)
