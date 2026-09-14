import pytest

from easydesign.agent.contracts import AgentBoundaryError
from easydesign.agent.phase34_batches import (
    ScaleBatchManifest,
    ScaleBatchPlan,
    ScaleBatchReceipt,
    ScaleBatchStore,
)
from easydesign.core import canonical_model_sha256
from tests.unit.agent.test_phase4_pool import _campaign, _candidate


def manifest():
    return ScaleBatchManifest(
        project_id="synthetic-project",
        campaign=_campaign(),
        batches=(
            ScaleBatchPlan(batch_id="batch-a", strategy_allocations={"arm-a": 2}),
            ScaleBatchPlan(batch_id="batch-b", strategy_allocations={"arm-b": 2}),
        ),
    )


def receipt(journal, batch, score):
    arm = "arm-" + batch[-1]
    return ScaleBatchReceipt(
        manifest_sha256=journal.digest,
        batch_id=batch,
        state="completed",
        candidates=tuple(_candidate(batch + str(i), arm, batch, i, score) for i in (1, 2)),
    )


def test_restart_recovery_global_order_and_duplicate_ingestion(tmp_path):
    journal = ScaleBatchStore(tmp_path, manifest())
    a = receipt(journal, "batch-a", 0.4)
    assert journal.append(a)
    journal.append(
        ScaleBatchReceipt(
            manifest_sha256=journal.digest,
            batch_id="batch-b",
            state="failed",
            operational_failures=("Synthetic interrupted worker",),
        )
    )
    assert journal.pool().failed_batch_ids == ("batch-b",)
    restored = ScaleBatchStore(tmp_path, manifest())
    assert not restored.append(a)
    b = receipt(restored, "batch-b", 0.9)
    assert restored.append(b)
    pool = restored.pool()
    assert len(pool.candidates) == 4
    assert pool.global_ranking_candidate_ids[:2] == ("batch-b1", "batch-b2")
    assert canonical_model_sha256(
        ScaleBatchStore(tmp_path, manifest()).pool()
    ) == canonical_model_sha256(pool)
    assert len(list((tmp_path / "batches/batch-b/receipt.json.revisions").glob("*.json"))) == 1
    with pytest.raises(AgentBoundaryError, match="cannot change"):
        restored.append(receipt(restored, "batch-a", 0.8))


def test_stale_authority_foreign_project_and_allocation_rejected(tmp_path):
    journal = ScaleBatchStore(tmp_path, manifest())
    with pytest.raises(AgentBoundaryError, match="foreign authority"):
        journal.append(
            receipt(journal, "batch-a", 0.5).model_copy(update={"manifest_sha256": "f" * 64})
        )
    with pytest.raises(AgentBoundaryError, match="another project"):
        ScaleBatchStore(tmp_path, manifest().model_copy(update={"project_id": "other-project"}))
    complete = receipt(journal, "batch-a", 0.5)
    with pytest.raises(AgentBoundaryError, match="entire population"):
        journal.append(complete.model_copy(update={"candidates": complete.candidates[:1]}))


def test_cross_batch_candidate_identity_is_never_silently_deduplicated(tmp_path):
    journal = ScaleBatchStore(tmp_path, manifest())
    a, b = receipt(journal, "batch-a", 0.4), receipt(journal, "batch-b", 0.6)
    journal.append(a)
    bad = b.candidates[0].model_copy(
        update={
            "lineage": b.candidates[0].lineage.model_copy(
                update={"candidate_id": a.candidates[0].lineage.candidate_id}
            )
        }
    )
    journal.append(b.model_copy(update={"candidates": (bad, b.candidates[1])}))
    with pytest.raises(AgentBoundaryError, match="reused across"):
        journal.pool()
