"""Append-only Scale batch receipts using the existing runtime snapshot journal."""

from __future__ import annotations

import fcntl
from collections import Counter
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, model_validator

from easydesign.core import canonical_model_sha256, load_model
from easydesign.core.artifacts import ID_PATTERN, SHA256_PATTERN
from easydesign.orchestration.task_tracking import (
    atomic_dump_runtime_model,
    load_latest_runtime_model,
)

from .contracts import AgentBoundaryError
from .phase4 import build_global_candidate_pool
from .phase34_contracts import (
    FrozenContract,
    GlobalCandidatePool,
    ScaleCampaignSpecification,
    ScaleCandidateObservation,
)
from .session_store import confined, identity


class ScaleBatchPlan(FrozenContract):
    batch_id: str = Field(pattern=ID_PATTERN)
    strategy_allocations: dict[str, int] = Field(min_length=1)

    @model_validator(mode="after")
    def positive(self) -> Self:
        if any(n < 1 for n in self.strategy_allocations.values()):
            raise ValueError("Batch allocations must be positive")
        return self


class ScaleBatchManifest(FrozenContract):
    project_id: str = Field(pattern=ID_PATTERN)
    campaign: ScaleCampaignSpecification
    batches: tuple[ScaleBatchPlan, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def exact_allocation(self) -> Self:
        if len({b.batch_id for b in self.batches}) != len(self.batches):
            raise ValueError("Batch identities must be unique")
        actual: Counter[str] = Counter()
        for batch in self.batches:
            actual.update(batch.strategy_allocations)
        if dict(actual) != self.campaign.strategy_allocations:
            raise ValueError("Batches must partition the exact campaign allocation")
        return self


class ScaleBatchReceipt(FrozenContract):
    manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    batch_id: str = Field(pattern=ID_PATTERN)
    state: Literal["completed", "failed", "resumable"]
    source_run_id: str | None = Field(default=None, pattern=ID_PATTERN)
    candidates: tuple[ScaleCandidateObservation, ...] = ()
    source_refs: tuple[str, ...] = ()
    operational_failures: tuple[str, ...] = ()


def partition_campaign(
    project_id: str, campaign: ScaleCampaignSpecification, *, batch_size: int = 100
) -> ScaleBatchManifest:
    if batch_size < 1:
        raise AgentBoundaryError("Scale batch size must be positive")
    batches = []
    # Single-strategy batches preserve arm/scaffold YAML identity even when two
    # strategies have unequal approved counts. Every result still competes globally.
    for strategy, count in sorted(campaign.strategy_allocations.items()):
        for offset in range(0, count, batch_size):
            allocation = {strategy: min(count - offset, batch_size)}
            batches.append(
                ScaleBatchPlan(
                    batch_id="batch-"
                    + identity(
                        {"campaign": campaign.campaign_id, "strategy": strategy, "offset": offset}
                    )[:24],
                    strategy_allocations=allocation,
                )
            )
    return ScaleBatchManifest(project_id=project_id, campaign=campaign, batches=tuple(batches))


class ScaleBatchStore:
    """Project-confined receipts; completed evidence cannot be replaced by a retry."""

    def __init__(self, root: Path, manifest: ScaleBatchManifest):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.manifest = manifest
        self.digest = canonical_model_sha256(manifest)
        self.plans = {b.batch_id: b for b in manifest.batches}
        path = self.root / "manifest.json"
        with (self.root / "journal.lock").open("a") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            if path.exists():
                if load_model(path, ScaleBatchManifest) != manifest:
                    raise AgentBoundaryError("Scale journal belongs to another project or plan")
            else:
                atomic_dump_runtime_model(manifest, path)

    def _path(self, batch_id: str) -> Path:
        if batch_id not in self.plans:
            raise AgentBoundaryError("Unplanned Scale batch")
        return confined(self.root, self.root / "batches" / batch_id / "receipt.json")

    def read(self, batch_id: str) -> ScaleBatchReceipt | None:
        path = self._path(batch_id)
        if not path.exists():
            return None
        receipt = load_latest_runtime_model(path, ScaleBatchReceipt)
        self._validate(receipt)
        return receipt

    def _validate(self, receipt: ScaleBatchReceipt) -> None:
        if receipt.manifest_sha256 != self.digest or receipt.batch_id not in self.plans:
            raise AgentBoundaryError("Scale receipt has stale or foreign authority")
        allocation = self.plans[receipt.batch_id].strategy_allocations
        counts: Counter[str] = Counter()
        ids: set[str] = set()
        for c in receipt.candidates:
            line = c.lineage
            if (
                line.campaign_id != self.manifest.campaign.campaign_id
                or line.batch_id != receipt.batch_id
                or line.candidate_id in ids
                or c.global_development_rank is not None
            ):
                raise AgentBoundaryError("Scale batch lineage is inconsistent or already ranked")
            ids.add(line.candidate_id)
            counts[line.strategy_id] += 1
        if any(s not in allocation or n > allocation[s] for s, n in counts.items()):
            raise AgentBoundaryError("Scale batch exceeds its approved allocation")
        if receipt.state == "completed" and dict(counts) != allocation:
            raise AgentBoundaryError("Completed Scale batch must retain its entire population")

    def append(self, receipt: ScaleBatchReceipt) -> bool:
        self._validate(receipt)
        with (self.root / "journal.lock").open("a") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            previous = self.read(receipt.batch_id)
            if previous == receipt:
                return False
            if previous and previous.state == "completed":
                raise AgentBoundaryError("Completed Scale evidence cannot change on replay")
            if previous:
                new = {c.lineage.candidate_id: c for c in receipt.candidates}
                if any(new.get(c.lineage.candidate_id) != c for c in previous.candidates):
                    raise AgentBoundaryError("Retry cannot erase or rewrite retained candidates")
            atomic_dump_runtime_model(receipt, self._path(receipt.batch_id))
        return True

    def pool(self) -> GlobalCandidatePool:
        receipts = [self.read(i) for i in sorted(self.plans)]
        groups: dict[str, list[str]] = {s: [] for s in ("completed", "failed", "resumable")}
        candidates: dict[str, ScaleCandidateObservation] = {}
        refs = []
        for batch_id, receipt in zip(sorted(self.plans), receipts, strict=True):
            groups[receipt.state if receipt else "resumable"].append(batch_id)
            if receipt is None:
                continue
            refs.append(canonical_model_sha256(receipt))
            for candidate in receipt.candidates:
                cid = candidate.lineage.candidate_id
                if cid in candidates:
                    raise AgentBoundaryError("Candidate identity is reused across Scale batches")
                candidates[cid] = candidate
        digest = identity(refs)
        return build_global_candidate_pool(
            campaign=self.manifest.campaign,
            source_candidate_index_sha256=digest,
            source_metric_report_sha256=digest,
            planned_batches=len(self.plans),
            completed_batch_ids=tuple(groups["completed"]),
            failed_batch_ids=tuple(groups["failed"]),
            resumable_batch_ids=tuple(groups["resumable"]),
            candidates=tuple(candidates[i] for i in sorted(candidates)),
        )
