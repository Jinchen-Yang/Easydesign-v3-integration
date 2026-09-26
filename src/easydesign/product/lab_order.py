"""Server-owned, simulation-only lab order workflow after an exact Gate 5 handoff.

This module deliberately has no HTTP client, vendor credential or production provider.
It proves the product boundary without turning a validation handoff into an experiment.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, model_validator

from easydesign.agent.phase34_contracts import WetLabHandoffPackage
from easydesign.core import canonical_model_sha256

from .artifacts import digest, immutable_json
from .contracts import ProductError, Value


class LabOrderRequirements(Value):
    format: Literal["VHH", "VHH-Fc"]
    amount: str = Field(min_length=1, max_length=160)
    host: str = Field(default="", max_length=160)
    buffer: str = Field(default="", max_length=160)
    profile: Literal["simulation-lab"]
    preferred_date: str = Field(default="", pattern=r"^$|^\d{4}-\d{2}-\d{2}$")
    purchase_order: str = Field(default="", max_length=160)
    sds_purity: str = Field(default="", max_length=160)
    sec_purity: str = Field(default="", max_length=160)
    endotoxin: str = Field(default="", max_length=160)
    concentration: str = Field(default="", max_length=160)
    notes: str = Field(default="", max_length=2000)


class LabOrderDraft(Value):
    schema_version: Literal["1"] = "1"
    candidate_ids: tuple[str, ...] = Field(min_length=1)
    requirements: LabOrderRequirements
    reviewed: Literal[True]

    @model_validator(mode="after")
    def unique_candidates(self) -> LabOrderDraft:
        if len(self.candidate_ids) != len(set(self.candidate_ids)):
            raise ValueError("Lab order candidates must be unique")
        return self


class LabOrderCommand(Value):
    request_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{16,96}$")
    revision: str = Field(pattern=r"^[0-9a-f]{64}$")
    action: Literal["save", "quote", "submit"]
    draft: LabOrderDraft | None = None
    acknowledgement: Literal["SIMULATED_ORDER_ONLY"] | None = None

    @model_validator(mode="after")
    def action_payload(self) -> LabOrderCommand:
        if self.action == "save" and self.draft is None:
            raise ValueError("Saving a lab order requires a draft")
        if self.action != "save" and self.draft is not None:
            raise ValueError("Only the save action accepts a lab order draft")
        if self.action == "submit" and self.acknowledgement != "SIMULATED_ORDER_ONLY":
            raise ValueError("Simulated submission requires its exact acknowledgement")
        if self.action != "submit" and self.acknowledgement is not None:
            raise ValueError("Only submit accepts an acknowledgement")
        return self


class MockQuote(Value):
    quote_id: str
    provider: Literal["mock-lab-v1"] = "mock-lab-v1"
    environment: Literal["simulation"] = "simulation"
    draft_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    sample_count: int = Field(ge=1)
    illustrative_total: int = Field(ge=0)
    currency: Literal["USD"] = "USD"
    turnaround: Literal["simulation-only"] = "simulation-only"
    non_binding: Literal[True] = True
    external_request_sent: Literal[False] = False


class MockOrderReceipt(Value):
    receipt_id: str
    order_id: str
    provider: Literal["mock-lab-v1"] = "mock-lab-v1"
    environment: Literal["simulation"] = "simulation"
    status: Literal["simulated-accepted"] = "simulated-accepted"
    project_id: str
    handoff_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    quote_id: str
    candidate_ids: tuple[str, ...] = Field(min_length=1)
    candidate_sequence_sha256: dict[str, str]
    submitted_at: str
    financial_commitment: Literal[False] = False
    external_request_sent: Literal[False] = False
    experiment_authorized: Literal[False] = False
    ordering_status: Literal["simulation-only-not-ordered"] = "simulation-only-not-ordered"
    receipt_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class MockLabProvider:
    """Deterministic local provider. It cannot perform external I/O by construction."""

    provider_id = "mock-lab-v1"

    def quote(self, draft: LabOrderDraft) -> MockQuote:
        draft_sha = canonical_model_sha256(draft)
        return MockQuote(
            quote_id="mock-quote-" + draft_sha[:20],
            draft_sha256=draft_sha,
            sample_count=len(draft.candidate_ids),
            illustrative_total=250 * len(draft.candidate_ids),
        )

    def submit(
        self,
        *,
        project: str,
        handoff: WetLabHandoffPackage,
        draft: LabOrderDraft,
        quote: MockQuote,
    ) -> MockOrderReceipt:
        handoff_sha = canonical_model_sha256(handoff)
        sequences = {item.candidate_id: item.sequence for item in handoff.candidates}
        sequence_sha = {
            candidate_id: hashlib.sha256(sequences[candidate_id].encode()).hexdigest()
            for candidate_id in draft.candidate_ids
        }
        identity = digest(
            {
                "project": project,
                "handoff": handoff_sha,
                "quote": quote.quote_id,
                "candidates": draft.candidate_ids,
                "sequences": sequence_sha,
            }
        )
        return MockOrderReceipt(
            receipt_id="mock-receipt-" + identity[:20],
            order_id="SIM-" + identity[:16].upper(),
            project_id=project,
            handoff_sha256=handoff_sha,
            quote_id=quote.quote_id,
            candidate_ids=draft.candidate_ids,
            candidate_sequence_sha256=sequence_sha,
            submitted_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        )


class LabOrderStore:
    """Durable optimistic state and command idempotency for simulated orders."""

    def __init__(self, path: Path, receipts: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        receipts.mkdir(parents=True, exist_ok=True)
        self.receipts = receipts
        self.db = sqlite3.connect(path, timeout=15)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS lab_orders ("
            "project TEXT NOT NULL,handoff TEXT NOT NULL,state TEXT NOT NULL,updated REAL NOT NULL,"
            "PRIMARY KEY(project,handoff))"
        )
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS lab_order_commands ("
            "id TEXT PRIMARY KEY,project TEXT NOT NULL,hash TEXT NOT NULL,response TEXT NOT NULL,"
            "created REAL NOT NULL)"
        )
        self.db.commit()

    def close(self) -> None:
        self.db.close()

    @staticmethod
    def _empty() -> dict[str, Any]:
        return {"draft": None, "quote": None, "receipt": None}

    def _state(self, project: str, handoff_sha: str) -> dict[str, Any]:
        row = self.db.execute(
            "SELECT state FROM lab_orders WHERE project=? AND handoff=?",
            (project, handoff_sha),
        ).fetchone()
        return json.loads(row[0]) if row else self._empty()

    @staticmethod
    def _revision(project: str, handoff_sha: str, state: dict[str, Any]) -> str:
        return digest({"project": project, "handoff": handoff_sha, "state": state})

    @staticmethod
    def _candidates(handoff: WetLabHandoffPackage) -> list[dict[str, Any]]:
        return [
            {
                "id": item.candidate_id,
                "selection_class": item.selection_class,
                "selection_rank": item.selection_rank,
                "sequence_length": len(item.sequence),
                "sequence_sha256": hashlib.sha256(item.sequence.encode()).hexdigest(),
                "sequence_ready": True,
            }
            for item in handoff.candidates
        ]

    def view(self, project: str, handoff: WetLabHandoffPackage) -> dict[str, Any]:
        handoff_sha = canonical_model_sha256(handoff)
        state = self._state(project, handoff_sha)
        return {
            "schema_version": "1",
            "mode": "simulation",
            "provider": "mock-lab-v1",
            "project_id": project,
            "handoff_sha256": handoff_sha,
            "handoff_status": handoff.handoff_status,
            "ordering_status": handoff.ordering_status,
            "revision": self._revision(project, handoff_sha, state),
            "candidates": self._candidates(handoff),
            **state,
            "capabilities": {
                "save": state["receipt"] is None,
                "quote": state["draft"] is not None and state["receipt"] is None,
                "submit": state["quote"] is not None and state["receipt"] is None,
                "real_order": False,
            },
            "disclaimer": (
                "Simulation only. No vendor request, experiment, payment or financial "
                "commitment is created."
            ),
        }

    @staticmethod
    def _validate_draft(
        draft: LabOrderDraft, handoff: WetLabHandoffPackage
    ) -> None:
        available = {item.candidate_id: item for item in handoff.candidates}
        unknown = [
            candidate_id
            for candidate_id in draft.candidate_ids
            if candidate_id not in available
        ]
        if unknown:
            raise ProductError(
                "candidate_outside_gate5",
                "A simulated order can only contain the exact Gate 5 panel",
                409,
            )
        for candidate_id in draft.candidate_ids:
            sequence = available[candidate_id].sequence
            if not sequence or any(residue not in "ACDEFGHIKLMNPQRSTVWY" for residue in sequence):
                raise ProductError(
                    "sequence_not_ready",
                    "Every simulated sample requires its complete authoritative sequence",
                    409,
                )

    def apply(
        self,
        *,
        project: str,
        handoff: WetLabHandoffPackage,
        command: LabOrderCommand,
        provider: MockLabProvider,
    ) -> dict[str, Any]:
        handoff_sha = canonical_model_sha256(handoff)
        command_value = command.model_dump(mode="json")
        command_hash = digest(
            {"project": project, "handoff": handoff_sha, "command": command_value}
        )
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            previous = self.db.execute(
                "SELECT hash,response FROM lab_order_commands WHERE id=?",
                (command.request_id,),
            ).fetchone()
            if previous:
                if previous["hash"] != command_hash:
                    raise ProductError(
                        "idempotency_conflict",
                        "This simulated order request identity has a different payload",
                        409,
                    )
                return json.loads(previous["response"])
            state = self._state(project, handoff_sha)
            if command.revision != self._revision(project, handoff_sha, state):
                raise ProductError(
                    "stale_state", "Refresh the current simulated order before changing it", 409
                )
            if state["receipt"] is not None:
                raise ProductError(
                    "order_finalized", "The simulated order receipt is already final", 409
                )
            if command.action == "save":
                assert command.draft is not None
                self._validate_draft(command.draft, handoff)
                state = {
                    "draft": command.draft.model_dump(mode="json"),
                    "quote": None,
                    "receipt": None,
                }
            elif command.action == "quote":
                if state["draft"] is None:
                    raise ProductError(
                        "draft_required", "Save a complete simulated order first", 409
                    )
                draft = LabOrderDraft.model_validate(state["draft"])
                self._validate_draft(draft, handoff)
                state["quote"] = provider.quote(draft).model_dump(mode="json")
            else:
                if state["draft"] is None or state["quote"] is None:
                    raise ProductError(
                        "quote_required", "A current simulated quote is required before submit", 409
                    )
                draft = LabOrderDraft.model_validate(state["draft"])
                quote = MockQuote.model_validate(state["quote"])
                if quote.draft_sha256 != canonical_model_sha256(draft):
                    raise ProductError("stale_quote", "The simulated quote no longer matches", 409)
                self._validate_draft(draft, handoff)
                receipt = provider.submit(
                    project=project, handoff=handoff, draft=draft, quote=quote
                )
                receipt_value = receipt.model_dump(mode="json", exclude={"receipt_sha256"})
                receipt_sha = digest(receipt_value)
                receipt = receipt.model_copy(update={"receipt_sha256": receipt_sha})
                immutable_json(
                    self.receipts / (receipt.receipt_id + ".json"),
                    receipt.model_dump(mode="json"),
                )
                state["receipt"] = receipt.model_dump(mode="json")
            now = time.time()
            self.db.execute(
                "INSERT INTO lab_orders VALUES(?,?,?,?) "
                "ON CONFLICT(project,handoff) DO UPDATE SET "
                "state=excluded.state,updated=excluded.updated",
                (project, handoff_sha, json.dumps(state, sort_keys=True), now),
            )
            response = {
                "schema_version": "1",
                "request_id": command.request_id,
                "action": command.action,
                "state": "succeeded",
                "order": self.view(project, handoff),
            }
            self.db.execute(
                "INSERT INTO lab_order_commands VALUES(?,?,?,?,?)",
                (command.request_id, project, command_hash, json.dumps(response), now),
            )
        return response
