"""Continue Phase2 Design goldens from independently reviewed, actually approved Site.

The caller must stop the failed source Agent before invoking this validation-only runner.
No old checkpoint, approval, proposal ownership or scientific job is rewritten.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import traceback
from datetime import UTC, datetime
from pathlib import Path

import yaml

from scripts import validate_phase2_goldens as golden


def reviewed_site(bridge, request, review):
    binding = hashlib.sha256(
        json.dumps(request["evidence"], sort_keys=True, default=str).encode()
    ).hexdigest()
    assert request["snapshot_sha256"] == review["snapshot_sha256"] == binding
    assert review["reviewer"] == "development-scientific-content-review"
    assert review["Decision"] == "PASS"
    assert request["required_review_sections"] == [
        "Hard Facts",
        "Scientific Interpretation",
        "Evidence",
        "Uncertainty",
        "Alternatives",
        "Decision",
    ]
    assert all(review.get(section) for section in request["required_review_sections"])
    evidence = request["evidence"]
    card = bridge.store.card(bridge.thread, evidence["card"]["card_id"])
    assert card.model_dump(mode="json") == evidence["card"]
    assert golden.judge_record(bridge, evidence["card"]) == evidence["judge"]
    assert card.evidence_id == evidence["site"]["evidence_id"]
    assert card.request_identity == evidence["site"]["request_identity"]
    response = bridge.store.response(bridge.thread, card.card_id)
    assert response and response["delivered"] and response["user"] == golden.ACTOR
    assert response["response"] in {"approve", "override"}
    approved = bridge.approved_site()
    assert approved and approved["outcome"]["card_id"] == card.card_id
    assert approved["run_id"] == card.run_id
    current = bridge.site_snapshot(approved["proposal"])
    # Approval changes the Stage02 manifest/evidence binding. Compare scientific content,
    # preserving the separately reviewed pending snapshot and the verified applied state.
    for key in current.keys() - {"evidence_id", "evidence_refs"}:
        assert current[key] == evidence["site"][key], key
    assert bridge.pending_site() is None
    return approved


async def main():
    origin = Path(os.environ["EASYDESIGN_GOLDEN_APPROVED_SITE"]).resolve()
    assert origin.name == "soluble"
    assert origin.is_relative_to(golden.ROOT / "runtime/tmp/autonomous-v3-20260912")
    source_report = json.loads((origin.parent / "report.json").read_text())
    assert source_report["formal_acceptance"] == "VALIDATION_ATTEMPT_FAILED"
    passed = {item["case"] for item in source_report["cases"] if item["status"] == "PASS"}
    assert {"case-1-soluble", "case-3-identity-trap"} <= passed
    for name, key in (
        ("docs/PHASE2_GOLDEN_CASE_SPEC.md", "spec_sha256"),
        ("tests/fixtures/agent/phase2_golden_truth.json", "oracle_sha256"),
    ):
        assert hashlib.sha256((golden.ROOT / name).read_bytes()).hexdigest() == source_report[key]
    info = json.loads((origin / "inherited-target.json").read_text())
    project = Path(info["project"]).resolve()
    assert project.is_relative_to(golden.ROOT / "runtime/tmp/autonomous-v3-20260912")
    workspace = Path(info["origin"]).resolve() / "workspace-root"
    os.environ["EASYDESIGN_WORKSPACE"] = str(workspace)
    assert golden.WorkspaceContext.from_root(workspace).projects_root / "soluble" == project
    config = golden.ModelConfig.model_validate(
        yaml.safe_load((golden.ROOT / "config/llm.yaml").read_text())
    )
    assert config.max_input_chars == 60000 and config.max_model_calls == 32
    secrets = [os.environ.get(c.secret_env, "") for c in [config.default, *config.roles.values()]]
    golden.OUT.mkdir(exist_ok=False)
    case = golden.OUT / "soluble"
    case.mkdir()
    print("Evidence directory:", golden.OUT, flush=True)
    report = {
        "type": "REAL MODEL / VERIFIED APPROVED SITE / REAL BACKEND YAML CHECK",
        "model": config.default.model,
        "model_configuration": config.model_dump(mode="json"),
        "case_scope": "soluble-design-resume",
        "generation_started": False,
        "gate_response_actor": golden.ACTOR,
        "cases": [],
        "formal_acceptance": "PENDING",
        "source_case": str(origin),
        "spec_sha256": source_report["spec_sha256"],
        "oracle_sha256": source_report["oracle_sha256"],
    }
    store = golden.SessionStore(project)
    active_case = "source-site-verification"
    try:
        bridge = golden.Phase2Bridge(project, info["continuation_thread"], store)
        request = json.loads((origin / "gate2-review-request.json").read_text())
        review = json.loads((origin / "gate2-independent-review.json").read_text())
        approved = reviewed_site(bridge, request, review)
        identity = golden.approved_identity(bridge, golden.golden_truth()["soluble"])
        golden.check_binding_roundtrip(
            golden.Phase2Bridge(project, "live-target-site", store), "P00698"
        )
        jobs_before = [job.job_id for job in bridge.controller.list(project_id="soluble")]
        assert all(job.step <= 2 for job in bridge.controller.list(project_id="soluble"))
        golden.save(case / "approved-identity-oracle.json", identity, secrets)
        golden.save(
            case / "inherited-approved-site.json",
            {
                "origin": str(origin),
                "project": str(project),
                "source_thread": bridge.thread,
                "review_snapshot_sha256": review["snapshot_sha256"],
                "source_card_id": approved["outcome"]["card_id"],
                "proposal_id": approved["proposal"]["proposal_id"],
                "job_id": approved["proposal"]["job_id"],
                "run_id": approved["run_id"],
                "hotspots_sha256": approved["hotspots_sha256"],
                "source_model_configuration": source_report["model_configuration"],
                "authority": "Existing applied Site approval, independently reviewed before "
                "approval. Only fresh Design reasoning/Judge/Gate3 are run; "
                "no science is restarted.",
            },
            secrets,
        )
        for label in ("gate1", "gate2", "identity-trap"):
            for suffix in ("review-request", "independent-review"):
                name = f"{label}-{suffix}.json"
                golden.save(case / name, json.loads((origin / name).read_text()), secrets)
        report["cases"] = [
            {
                "case": key,
                "status": "PASS",
                "acceptance": "inherited exact reviewed snapshot",
                "source_case": str(origin),
            }
            for key in ("case-1-soluble", "case-3-identity-trap")
        ]
        golden.save(golden.OUT / "report.json", report, secrets)
        if os.environ.get("EASYDESIGN_GOLDEN_VERIFY_ONLY") == "1":
            report["formal_acceptance"] = "APPROVED_SITE_VERIFICATION_ONLY"
            print("VERIFIED APPROVED SITE; no model calls or new jobs", flush=True)
            return 0

        def observe_request(metadata):
            with (golden.OUT / "model-wire-metadata.jsonl").open("a") as handle:
                handle.write(json.dumps({"at": datetime.now(UTC).isoformat(), **metadata}) + "\n")

        def emit(event):
            if event["kind"] in {
                "model-call",
                "model-context",
                "tool",
                "agent-terminal",
                "contract-repair",
                "tool-argument-repair",
            }:
                with (case / "progress.jsonl").open("a") as handle:
                    handle.write(json.dumps(event, ensure_ascii=False) + "\n")

        active_case = "design-validator-initialization"
        models = golden.create_models(config, request_observer=observe_request)
        golden.save(case / "backend-validation.json", golden.configure_live_validation(), secrets)
        for kind in ("standard", "expert-native"):
            active_case = "case-4-standard" if kind == "standard" else "case-5-native"
            thread = "live-design-" + kind + "-" + golden.STAMP.lower()
            if kind == "standard":
                golden.save(
                    case / "inherited-target.json",
                    {
                        **info,
                        "continuation_thread": thread,
                        "approved_site_origin": str(origin),
                    },
                    secrets,
                )
            await golden.run_design_case(
                project,
                store,
                case,
                kind,
                config,
                models,
                secrets,
                emit,
                thread=thread,
            )
            assert jobs_before == [j.job_id for j in bridge.controller.list(project_id="soluble")]
            report["cases"].append({"case": active_case, "status": "PASS", "thread": thread})
            golden.save(golden.OUT / "report.json", report, secrets)
        report["formal_acceptance"] = "PARTIAL_CASE_SCIENTIFIC_ACCEPTANCE_PASS"
    except Exception:
        report["formal_acceptance"] = "VALIDATION_ATTEMPT_FAILED"
        report["error"] = traceback.format_exc()
        report["cases"].append({"case": active_case, "status": "FAIL"})
    finally:
        jobs = bridge.controller.list(project_id="soluble") if "bridge" in locals() else []
        golden.save(
            case / "final-jobs.json",
            [{"job_id": j.job_id, "step": j.step, "status": str(j.status)} for j in jobs],
            secrets,
        )
        store.close()
        golden.save(golden.OUT / "report.json", report, secrets)
    print(report["formal_acceptance"], golden.OUT, flush=True)
    return 0 if report["formal_acceptance"].endswith("ACCEPTANCE_PASS") else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
