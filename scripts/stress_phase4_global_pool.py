#!/usr/bin/env python3
"""Exercise production-size Phase 4 aggregation without scientific backends."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

from easydesign.agent.phase4 import build_global_candidate_pool, build_review_shortlist
from easydesign.agent.phase34_batches import (
    ScaleBatchManifest,
    ScaleBatchPlan,
    ScaleBatchReceipt,
    ScaleBatchStore,
)
from easydesign.agent.phase34_contracts import (
    DiversityContext,
    ExecutionProjection,
    Gate4PromotionAuthority,
    MetricObservation,
    ScaleCampaignSpecification,
    ScaleCandidateLineageV3,
    ScaleCandidateObservation,
    ScaleCandidateValidity,
)
from easydesign.core import ArtifactRef, canonical_model_sha256


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _candidate(
    index: int,
    candidates_per_batch: int,
    campaign_id: str,
) -> ScaleCandidateObservation:
    candidate_id = f"candidate-{index:06d}"
    batch_id = f"batch-{index // candidates_per_batch + 1:04d}"
    strategy_id = "arm-a" if index % 2 == 0 else "arm-b"
    valid = index % 997 != 0
    score = ((index * 7919) % 10000) / 10000 if valid else None
    metrics = (
        MetricObservation(
            metric_id="synthetic-development-score",
            value=score,
            available=valid,
            missing_reason=None if valid else "synthetic prediction failure",
            source="deterministic-stress-fixture",
            definition_version="phase4-stress-v1",
        ),
    )
    return ScaleCandidateObservation(
        lineage=ScaleCandidateLineageV3(
            campaign_id=campaign_id,
            batch_id=batch_id,
            shard_id=f"shard-{batch_id}",
            candidate_id=candidate_id,
            strategy_id=strategy_id,
            strategy_ordinal=index // 2 + 1,
            generation_task_id=f"generation-{batch_id}",
            generation_attempt=1,
            backend_candidate_id=f"synthetic-backend-{candidate_id}",
            prediction_id=f"prediction-{candidate_id}" if valid else None,
            prediction_seed=101 if valid else None,
            prediction_ids=(f"prediction-{candidate_id}",) if valid else (),
            prediction_seeds=(101,) if valid else (),
            sequence_sha256=_sha(f"sequence-{candidate_id}"),
            artifact_refs=(
                ArtifactRef(
                    artifact_id=f"structure-{candidate_id}",
                    role="synthetic-stress-evidence",
                    relative_path=f"synthetic/{batch_id}/{candidate_id}.cif",
                    file_format="cif",
                    sha256=_sha(f"artifact-{candidate_id}"),
                    size_bytes=1,
                    producer_stage="07-final-filtering-and-selection",
                    producer_attempt="attempt-0001",
                ),
            ),
        ),
        validity=(
            ScaleCandidateValidity.VALID_EVALUATED if valid else ScaleCandidateValidity.UNEVALUABLE
        ),
        metrics=metrics,
        development_score=score,
        failure_reason=None if valid else "synthetic prediction failure",
        diversity=DiversityContext(
            sequence_cluster_id=f"cluster-{index % 4096:04d}",
            method="deterministic synthetic partition",
        ),
    )


def run_stress(
    *, candidate_count: int, batch_count: int, checkpoint_dir: Path | None = None
) -> dict[str, object]:
    if candidate_count < batch_count or candidate_count % batch_count:
        raise ValueError("candidate count must be a positive multiple of batch count")
    candidates_per_batch = candidate_count // batch_count
    if candidate_count % 2:
        raise ValueError("candidate count must split equally across two strategies")
    campaign_id = f"scale-synthetic-stress-{candidate_count}"
    campaign = ScaleCampaignSpecification(
        campaign_id=campaign_id,
        promotion_authority=Gate4PromotionAuthority(
            authority_id="synthetic-gate4-control-authority",
            gate4_card_id="a" * 64,
            pilot_dossier_sha256="b" * 64,
            selected_strategy_ids=("arm-a", "arm-b"),
            requested_scale_candidates=candidate_count,
            production_strategy_allocations={
                "arm-a": candidate_count // 2,
                "arm-b": candidate_count // 2,
            },
            authority_scope="test-only-control-flow",
            human_actor="synthetic-stress-runner",
            authorizes_scientific_scale=False,
            authorizes_production_compute=False,
        ),
        execution=ExecutionProjection(
            mode="synthetic-stress",
            requested_production_candidates=candidate_count,
            execution_candidates=candidate_count,
            uses_real_generation_backend=False,
            uses_real_prediction_backend=False,
            purpose="Stress global aggregation and recovery semantics without compute.",
        ),
        strategy_allocations={
            "arm-a": candidate_count // 2,
            "arm-b": candidate_count // 2,
        },
        generation_backend="synthetic-none",
        prediction_backend="synthetic-none",
        allocation_policy="equal-across-promoted-validation",
    )
    started = time.monotonic()
    candidates = tuple(
        _candidate(index, candidates_per_batch, campaign_id) for index in range(candidate_count)
    )
    generated_seconds = time.monotonic() - started
    batch_ids = tuple(f"batch-{index + 1:04d}" for index in range(batch_count))
    partial_candidates = candidates[: -2 * candidates_per_batch]
    partial_pool = build_global_candidate_pool(
        campaign=campaign,
        source_candidate_index_sha256=_sha(f"synthetic-candidate-index-{len(partial_candidates)}"),
        source_metric_report_sha256=_sha(f"synthetic-metric-report-{len(partial_candidates)}"),
        planned_batches=batch_count,
        completed_batch_ids=batch_ids[:-2],
        failed_batch_ids=(batch_ids[-2],),
        resumable_batch_ids=(batch_ids[-1],),
        candidates=partial_candidates,
    )
    partial_sha256 = canonical_model_sha256(partial_pool)
    partial_retained_candidates = len(partial_pool.candidates)
    del partial_pool
    resumed_at = time.monotonic()
    final_pool = build_global_candidate_pool(
        campaign=campaign,
        source_candidate_index_sha256=_sha(f"synthetic-candidate-index-{len(candidates)}"),
        source_metric_report_sha256=_sha(f"synthetic-metric-report-{len(candidates)}"),
        planned_batches=batch_count,
        completed_batch_ids=batch_ids,
        failed_batch_ids=(),
        resumable_batch_ids=(),
        candidates=candidates,
    )
    final_sha256 = canonical_model_sha256(final_pool)
    replay = build_global_candidate_pool(
        campaign=campaign,
        source_candidate_index_sha256=_sha(f"synthetic-candidate-index-{len(candidates)}"),
        source_metric_report_sha256=_sha(f"synthetic-metric-report-{len(candidates)}"),
        planned_batches=batch_count,
        completed_batch_ids=batch_ids,
        failed_batch_ids=(),
        resumable_batch_ids=(),
        candidates=candidates,
    )
    replay_sha256 = canonical_model_sha256(replay)
    valid_count = len(final_pool.global_ranking_candidate_ids)
    report = {
        "schema_version": "0.1",
        "status": "PASS" if final_sha256 == replay_sha256 else "FAIL",
        "mode": "synthetic-stress",
        "scientific_claims_authorized": False,
        "production_compute_used": False,
        "requested_production_candidates": candidate_count,
        "synthetic_candidates": candidate_count,
        "planned_batches": batch_count,
        "partial_checkpoint": {
            "completed_batches": batch_count - 2,
            "failed_batches": 1,
            "resumable_batches": 1,
            "retained_candidates": partial_retained_candidates,
            "pool_sha256": partial_sha256,
        },
        "resume": {
            "completed_batches": batch_count,
            "retained_candidates": len(final_pool.candidates),
            "valid_evaluated_candidates": valid_count,
            "unevaluable_candidates": candidate_count - valid_count,
            "global_ranked_candidates": valid_count,
            "global_pool_sha256": final_sha256,
            "idempotent_replay_sha256": replay_sha256,
        },
        "timing_seconds": {
            "candidate_construction": round(generated_seconds, 3),
            "partial_and_resume_aggregation": round(time.monotonic() - resumed_at, 3),
            "total": round(time.monotonic() - started, 3),
        },
        "scope": (
            "Aggregation/checkpoint stress only. Scores, failures, clusters, and artifacts "
            "are deterministic synthetic fixtures and carry no biological meaning."
        ),
    }
    if checkpoint_dir is not None:
        persisted = persistent_stress(checkpoint_dir, campaign, candidates, batch_ids)
        report["persistence_and_process_restart"] = persisted
        if not persisted["pass"]:
            report["status"] = "FAIL"
    return report


def persistent_stress(root, campaign, candidates, batch_ids):
    from easydesign.orchestration.task_tracking import atomic_dump_runtime_model

    groups = {bid: tuple(c for c in candidates if c.lineage.batch_id == bid) for bid in batch_ids}
    manifest = ScaleBatchManifest(
        project_id="synthetic-stress-project",
        campaign=campaign,
        batches=tuple(
            ScaleBatchPlan(
                batch_id=bid,
                strategy_allocations=dict(Counter(c.lineage.strategy_id for c in groups[bid])),
            )
            for bid in batch_ids
        ),
    )
    journal = ScaleBatchStore(root, manifest)
    for bid in batch_ids[:-2]:
        journal.append(
            ScaleBatchReceipt(
                manifest_sha256=journal.digest,
                batch_id=bid,
                state="completed",
                candidates=groups[bid],
            )
        )
    for bid, state in zip(batch_ids[-2:], ("failed", "resumable"), strict=True):
        if journal.read(bid) is None:
            journal.append(
                ScaleBatchReceipt(
                    manifest_sha256=journal.digest,
                    batch_id=bid,
                    state=state,
                    operational_failures=("Synthetic interrupted batch",),
                )
            )
    partial = journal.pool()
    atomic_dump_runtime_model(partial, root / "partial-pool.json")
    # Recovery reopens receipts; replaying every completed batch must be a no-op.
    journal = ScaleBatchStore(root, manifest)
    duplicate_count = 0
    for bid in batch_ids:
        receipt = ScaleBatchReceipt(
            manifest_sha256=journal.digest, batch_id=bid, state="completed", candidates=groups[bid]
        )
        journal.append(receipt)
        duplicate_count += not journal.append(receipt)
    pool = journal.pool()
    shortlist = build_review_shortlist(pool=pool, requested_count=30, sequence_cluster_cap=2)
    atomic_dump_runtime_model(pool, root / "global-pool.json")
    atomic_dump_runtime_model(shortlist, root / "shortlist.json")
    # A fresh interpreter has no access to the parent's in-memory candidates.
    child = r"""
import json, sys
from pathlib import Path
from easydesign.agent.phase34_batches import ScaleBatchManifest, ScaleBatchStore
from easydesign.agent.phase34_contracts import GlobalCandidatePool
from easydesign.agent.phase4 import build_review_shortlist
from easydesign.core import canonical_model_sha256, load_model
from easydesign.orchestration.task_tracking import load_latest_runtime_model
root=Path(sys.argv[1])
manifest=load_model(root/'manifest.json', ScaleBatchManifest)
pool=ScaleBatchStore(root, manifest).pool()
saved=load_latest_runtime_model(root/'global-pool.json', GlobalCandidatePool)
short=build_review_shortlist(pool=pool, requested_count=30, sequence_cluster_cap=2)
print(json.dumps({'pool':canonical_model_sha256(pool),'persisted':canonical_model_sha256(saved),
                 'shortlist':canonical_model_sha256(short),'count':len(pool.candidates)}))
"""
    restart = json.loads(
        subprocess.check_output([sys.executable, "-c", child, str(root)], text=True)
    )
    digest, short_digest = canonical_model_sha256(pool), canonical_model_sha256(shortlist)
    by_id = {c.lineage.candidate_id: c for c in pool.candidates}
    cluster_counts = Counter(
        by_id[e.candidate_id].diversity.sequence_cluster_id for e in shortlist.entries
    )
    passed = (
        restart["pool"] == restart["persisted"] == digest
        and restart["shortlist"] == short_digest
        and restart["count"] == len(candidates)
        and duplicate_count == len(batch_ids)
        and max(cluster_counts.values(), default=0) <= 2
    )
    return {
        "pass": passed,
        "checkpoint_directory": str(root),
        "deduplicated_batch_replays": duplicate_count,
        "initial_failed_batches": len(partial.failed_batch_ids),
        "initial_resumable_batches": len(partial.resumable_batch_ids),
        "all_batches_recovered": not pool.failed_batch_ids and not pool.resumable_batch_ids,
        "pool_sha256": digest,
        "shortlist_sha256": short_digest,
        "shortlist_count": len(shortlist.entries),
        "process_restart": restart,
        "diversity_cluster_cap": 2,
        "diversity_note": "Synthetic advisory clusters; no biological or pose-quality inference.",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidates", type=int, default=50_000)
    parser.add_argument("--batches", type=int, default=50)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--checkpoint-dir", type=Path)
    args = parser.parse_args()
    report = run_stress(
        candidate_count=args.candidates,
        batch_count=args.batches,
        checkpoint_dir=args.checkpoint_dir,
    )
    encoded = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded)
    print(encoded, end="")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
