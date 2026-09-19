"""Agent history and a minimal command/response ledger, never a compute scheduler."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from uuid import uuid4

from .contracts import AgentBoundaryError, DecisionCard, DecisionOutcome, EvidenceAssessment

TOOL_REPAIR_LIMIT = 4


def compact(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def identity(value: Any) -> str:
    return hashlib.sha256(compact(value).encode()).hexdigest()


def confined(root: Path, path: Path) -> Path:
    """Reject links even when their current destination is inside the root."""
    root = root.absolute()
    path = path.absolute()
    if not path.is_relative_to(root) or ".." in path.parts:
        raise AgentBoundaryError("Path escapes its bound root")
    for parent in (path, *path.parents):
        if parent.is_symlink():
            raise AgentBoundaryError("Symlinks are not accepted at the agent boundary")
        if parent == root:
            break
    if not path.resolve().is_relative_to(root.resolve()):
        raise AgentBoundaryError("Resolved path escapes its bound root")
    return path


class SessionStore:
    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self.root = confined(project_root, project_root / "metadata")
        self.root.mkdir(mode=0o700, exist_ok=True)
        self.path = confined(self.root, self.root / "agent.sqlite")
        # Check SQLite's adjacent mutable files before opening an existing session.
        for suffix in ("-wal", "-shm", "-journal"):
            confined(self.root, Path(str(self.path) + suffix))
        self.db = sqlite3.connect(self.path, timeout=5)
        os.chmod(self.path, 0o600)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS threads (
                id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, goal TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS events (
                seq INTEGER PRIMARY KEY AUTOINCREMENT, thread TEXT NOT NULL,
                kind TEXT NOT NULL, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS commands (
                id TEXT PRIMARY KEY, thread TEXT NOT NULL, operation TEXT NOT NULL,
                binding TEXT NOT NULL, state TEXT NOT NULL, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS assessments (
                id TEXT PRIMARY KEY, thread TEXT NOT NULL, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS cards (
                id TEXT PRIMARY KEY, thread TEXT NOT NULL, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS responses (
                card TEXT PRIMARY KEY, thread TEXT NOT NULL, response TEXT NOT NULL,
                user TEXT NOT NULL, delivered INTEGER NOT NULL DEFAULT 0);
        """)
        self.db.commit()

    def close(self) -> None:
        self.db.close()

    @contextmanager
    def writer(self) -> Iterator[None]:
        path = confined(self.root, self.root / "agent-writer.lock")
        with path.open("a") as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise AgentBoundaryError("Another agent writer owns this project") from error
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)

    def thread(self, thread_id: str, fingerprint: str, goal: str | None = None) -> str:
        row = self.db.execute("SELECT * FROM threads WHERE id=?", (thread_id,)).fetchone()
        if row is not None:
            if row["fingerprint"] != fingerprint:
                raise AgentBoundaryError("Incompatible harness/model/skills; create a new thread")
            if goal is not None and goal != row["goal"]:
                raise AgentBoundaryError("Thread goal is immutable; use a new thread")
            return str(row["goal"])
        if not goal:
            raise AgentBoundaryError("Unknown thread; start it with an explicit user goal")
        with self.db:
            self.db.execute("INSERT INTO threads VALUES(?,?,?)", (thread_id, fingerprint, goal))
        self.event(thread_id, "user", {"text": goal})
        return goal

    def event(self, thread: str, kind: str, payload: Any) -> None:
        with self.db:
            self.db.execute(
                "INSERT INTO events(thread,kind,payload) VALUES(?,?,?)",
                (thread, kind, compact(payload)),
            )

    def events(self, thread: str) -> list[dict[str, Any]]:
        return [
            {"seq": row["seq"], "kind": row["kind"], "payload": json.loads(row["payload"])}
            for row in self.db.execute(
                "SELECT * FROM events WHERE thread=? ORDER BY seq", (thread,)
            )
        ]

    def latest_execution(self, thread: str) -> dict[str, Any] | None:
        row = self.db.execute(
            "SELECT payload FROM events WHERE thread=? AND kind='agent-execution' "
            "ORDER BY seq DESC LIMIT 1",
            (thread,),
        ).fetchone()
        return None if row is None else json.loads(row[0])

    def begin_execution(
        self,
        thread: str,
        message: str,
        *,
        followup: bool = False,
        revision: DecisionOutcome | None = None,
        steering_resume: bool = False,
        steering_card_id: str | None = None,
    ) -> dict[str, Any]:
        execution: dict[str, Any] = {
            "execution_id": f"turn-{uuid4().hex}",
            "current_user_message": message,
            "input_kind": "steering-resume" if steering_resume else "message",
        }
        if steering_card_id is not None:
            execution["steering_card_id"] = steering_card_id
        if revision is not None:
            execution["revision"] = revision.model_dump(mode="json")
        with self.db:
            self.db.execute(
                "INSERT INTO events(thread,kind,payload) VALUES(?,?,?)",
                (thread, "agent-execution", compact(execution)),
            )
            if followup:
                self.db.execute(
                    "INSERT INTO events(thread,kind,payload) VALUES(?,?,?)",
                    (thread, "user-followup", compact({"text": message})),
                )
        return execution

    def begin_revision(self, thread: str, card_id: str, goal: str) -> dict[str, Any]:
        intent = self.response(thread, card_id)
        if intent is None or intent["response"] != "revise":
            raise AgentBoundaryError("Revision requires a persisted human REVISE outcome")
        current = self.latest_execution(thread)
        if current and current.get("revision", {}).get("card_id") == card_id:
            return current
        return self.begin_execution(
            thread,
            current["current_user_message"] if current else goal,
            revision=DecisionOutcome.model_validate(intent["outcome"]),
            steering_resume=True,
        )

    def begin_gate_execution(self, thread: str, card_id: str, goal: str) -> dict[str, Any]:
        """A verified Phase 2 human acceptance starts the next bounded execution once."""
        intent = self.response(thread, card_id)
        if intent is None or intent["response"] not in {"approve", "override"}:
            raise AgentBoundaryError("Gate continuation requires a persisted human acceptance")
        current = self.latest_execution(thread)
        prior = self.db.execute(
            "SELECT payload FROM events WHERE thread=? AND kind='agent-execution' "
            "AND json_extract(payload, '$.steering_card_id')=? ORDER BY seq DESC LIMIT 1",
            (thread, card_id),
        ).fetchone()
        if prior:
            execution: dict[str, Any] = json.loads(prior[0])
            if current is None or current["execution_id"] != execution["execution_id"]:
                raise AgentBoundaryError("An old gate cannot renew a later execution budget")
            return execution
        return self.begin_execution(
            thread,
            current["current_user_message"] if current else goal,
            steering_resume=True,
            steering_card_id=card_id,
        )

    def revision_for(self, thread: str, request_identity: str) -> dict[str, Any] | None:
        for event in reversed(self.events(thread)):
            if event["kind"] == "human-response" and event["payload"]["response"] == "revise":
                card = self.card(thread, event["payload"]["card"])
                if card.request_identity == request_identity:
                    return event
        return None

    def reserve_model_call(self, thread: str, role: str, maximum: int, execution_id: str) -> None:
        """Reserve one scientific provider call under scientific and total safeguards."""
        execution = self.latest_execution(thread)
        if execution is None or execution["execution_id"] != execution_id:
            raise AgentBoundaryError("Model call is not bound to the current agent execution")
        with self.db:
            count = self.db.execute(
                "SELECT count(*) FROM events WHERE thread=? AND kind='model-call' "
                "AND json_extract(payload, '$.execution_id')=?",
                (thread, execution_id),
            ).fetchone()[0]
            if count >= maximum:
                raise AgentBoundaryError(
                    "Current turn model-call budget exhausted; worker remains detached"
                )
            provider_count = self.db.execute(
                "SELECT count(*) FROM events WHERE thread=? "
                "AND kind IN ('model-call','auxiliary-model-call') "
                "AND json_extract(payload, '$.execution_id')=?",
                (thread, execution_id),
            ).fetchone()[0]
            if provider_count >= maximum:
                raise AgentBoundaryError(
                    "Current turn total provider-call safeguard exhausted; worker remains detached"
                )
            lifetime = self.db.execute(
                "SELECT count(*) FROM events WHERE thread=? "
                "AND kind IN ('model-call','auxiliary-model-call')",
                (thread,),
            ).fetchone()[0]
            self.db.execute(
                "INSERT INTO events(thread,kind,payload) VALUES(?, 'model-call', ?)",
                (
                    thread,
                    compact(
                        {
                            "role": role,
                            "call": count + 1,
                            "provider_call": provider_count + 1,
                            "execution_id": execution_id,
                            "lifetime_call": lifetime + 1,
                            "call_category": "scientific",
                        }
                    ),
                ),
            )

    def reserve_auxiliary_model_call(
        self, thread: str, role: str, maximum: int, execution_id: str
    ) -> None:
        """Reserve framework maintenance without consuming the scientific allowance."""
        execution = self.latest_execution(thread)
        if execution is None or execution["execution_id"] != execution_id:
            raise AgentBoundaryError("Auxiliary call is not bound to the current execution")
        with self.db:
            provider_count = self.db.execute(
                "SELECT count(*) FROM events WHERE thread=? "
                "AND kind IN ('model-call','auxiliary-model-call') "
                "AND json_extract(payload, '$.execution_id')=?",
                (thread, execution_id),
            ).fetchone()[0]
            if provider_count >= maximum:
                raise AgentBoundaryError(
                    "Current turn total provider-call safeguard exhausted; worker remains detached"
                )
            auxiliary_count = self.db.execute(
                "SELECT count(*) FROM events WHERE thread=? AND kind='auxiliary-model-call' "
                "AND json_extract(payload, '$.execution_id')=?",
                (thread, execution_id),
            ).fetchone()[0]
            lifetime = self.db.execute(
                "SELECT count(*) FROM events WHERE thread=? "
                "AND kind IN ('model-call','auxiliary-model-call')",
                (thread,),
            ).fetchone()[0]
            self.db.execute(
                "INSERT INTO events(thread,kind,payload) VALUES(?, 'auxiliary-model-call', ?)",
                (
                    thread,
                    compact(
                        {
                            "role": role,
                            "call": auxiliary_count + 1,
                            "provider_call": provider_count + 1,
                            "execution_id": execution_id,
                            "lifetime_call": lifetime + 1,
                            "call_category": "auxiliary-summary",
                        }
                    ),
                ),
            )

    def reserve_prerequisite_repair(
        self,
        thread: str,
        role: str,
        execution_id: str,
        source_id: str,
        *,
        round_id: str | None = None,
        scope: str | None = None,
    ) -> int:
        """Reserve a bounded correction for one tool operation."""
        return self._reserve_repair(
            thread,
            role,
            execution_id,
            "prerequisite-repair",
            "SOURCE_NOT_SELECTED",
            source_id=source_id,
            **({"round_id": round_id} if round_id else {}),
            **({"scope": scope} if scope else {}),
        )

    def reserve_tool_argument_repair(
        self,
        thread: str,
        role: str,
        execution_id: str,
        *,
        round_id: str | None = None,
        scope: str | None = None,
    ) -> int:
        return self._reserve_repair(
            thread,
            role,
            execution_id,
            "tool-argument-repair",
            "INVALID_FIELD_PROJECTION",
            **({"round_id": round_id} if round_id else {}),
            **({"scope": scope} if scope else {}),
        )

    def mark_tool_repair_success(
        self,
        thread: str,
        role: str,
        execution_id: str,
        scope: str,
        *,
        round_id: str | None = None,
    ) -> None:
        """End a tool's correction streak after a successful invocation.

        A marker is written only when this role/tool scope has an outstanding
        repair. The durable marker keeps restart behavior bounded without making
        unrelated errors in a long research turn consume one global allowance.
        """
        execution = self.latest_execution(thread)
        if execution is None or execution["execution_id"] != execution_id:
            raise AgentBoundaryError("Tool success is outside the current execution")
        rows = self.db.execute(
            "SELECT kind,payload FROM events WHERE thread=? "
            "AND kind IN ('prerequisite-repair', 'tool-argument-repair', "
            "'tool-repair-success') "
            "AND json_extract(payload, '$.execution_id')=? ORDER BY seq DESC",
            (thread, execution_id),
        ).fetchall()
        outstanding = False
        for kind, raw in rows:
            prior = json.loads(raw)
            if kind == "tool-repair-success":
                if prior.get("role") == role and prior.get("scope") == scope:
                    break
                continue
            prior_scope = prior.get("scope")
            if prior_scope is None or (
                prior.get("role") == role and prior_scope == scope
            ):
                outstanding = True
                break
        if not outstanding:
            return
        with self.db:
            self.db.execute(
                "INSERT INTO events(thread,kind,payload) "
                "VALUES(?, 'tool-repair-success', ?)",
                (
                    thread,
                    compact(
                        {
                            "role": role,
                            "execution_id": execution_id,
                            "scope": scope,
                            **({"round_id": round_id} if round_id else {}),
                        }
                    ),
                ),
            )

    def reserve_contract_repair(
        self,
        thread: str,
        role: str,
        execution_id: str,
        diagnostic: str,
        *,
        contract: str | None = None,
    ) -> int:
        """Two corrections per typed contract/execution, durable across delegation/replay.

        Legacy unscoped records count against every contract. All calls still consume
        the independent execution-wide model-call budget.
        """
        execution = self.latest_execution(thread)
        if execution is None or execution["execution_id"] != execution_id:
            raise AgentBoundaryError("Contract repair is outside the current execution")
        with self.db:
            count = self.db.execute(
                "SELECT count(*) FROM events WHERE thread=? AND kind='contract-repair' "
                "AND json_extract(payload,'$.execution_id')=? "
                "AND (? IS NULL OR json_extract(payload,'$.contract') IS NULL "
                "OR json_extract(payload,'$.contract')=?)",
                (thread, execution_id, contract, contract),
            ).fetchone()[0]
            if count >= 2:
                raise AgentBoundaryError(
                    "Structured contract repair budget exhausted (2 per contract per execution)"
                )
            self.db.execute(
                "INSERT INTO events(thread,kind,payload) VALUES(?, 'contract-repair', ?)",
                (
                    thread,
                    compact(
                        {
                            "role": role,
                            "execution_id": execution_id,
                            "contract": contract,
                            "attempt": count + 1,
                            "diagnostic": diagnostic[:6000],
                        }
                    ),
                ),
            )
        return int(count) + 1

    def _reserve_repair(
        self,
        thread: str,
        role: str,
        execution_id: str,
        kind: str,
        error_code: str,
        **details: str,
    ) -> int:
        """Reserve one of four consecutive correction rounds.

        Native harness calls are isolated by role and tool scope. A successful
        invocation of that tool resets its streak, while replaying one native
        model batch retains the same attempt. Legacy unscoped callers preserve
        the original execution-wide accounting.
        """
        execution = self.latest_execution(thread)
        if execution is None or execution["execution_id"] != execution_id:
            raise AgentBoundaryError("Repair is not bound to the current execution")
        with self.db:
            scope = details.get("scope")
            if scope:
                rows = self.db.execute(
                    "SELECT seq,kind,payload FROM events WHERE thread=? "
                    "AND kind IN ('prerequisite-repair', 'tool-argument-repair', "
                    "'tool-repair-success') "
                    "AND json_extract(payload, '$.execution_id')=? ORDER BY seq",
                    (thread, execution_id),
                ).fetchall()
                rounds: dict[tuple[str, str], int] = {}
                current_round = details.get("round_id")
                for seq, event_kind, raw in rows:
                    prior = json.loads(raw)
                    if event_kind == "tool-repair-success":
                        if (
                            prior.get("role") == role
                            and prior.get("scope") == scope
                            and (
                                current_round is None
                                or prior.get("round_id") != current_round
                            )
                        ):
                            rounds = {}
                        continue
                    prior_scope = prior.get("scope")
                    if prior_scope is not None and (
                        prior.get("role") != role or prior_scope != scope
                    ):
                        continue
                    key = (
                        (prior.get("role", "legacy"), prior["round_id"])
                        if prior.get("round_id")
                        else ("legacy-event", str(seq))
                    )
                    rounds.setdefault(key, len(rounds) + 1)
                current_key = (
                    (role, current_round) if current_round is not None else None
                )
                attempt = rounds.get(current_key) if current_key is not None else None
                limit_label = f"{TOOL_REPAIR_LIMIT} consecutive rounds for {scope}"
            else:
                rows = self.db.execute(
                    "SELECT seq,payload FROM events WHERE thread=? "
                    "AND kind IN ('prerequisite-repair', 'tool-argument-repair') "
                    "AND json_extract(payload, '$.execution_id')=? ORDER BY seq",
                    (thread, execution_id),
                ).fetchall()
                rounds = {}
                for seq, raw in rows:
                    prior = json.loads(raw)
                    key = (
                        (prior["role"], prior["round_id"])
                        if prior.get("round_id")
                        else ("legacy-event", str(seq))
                    )
                    rounds.setdefault(key, int(prior["attempt"]))
                current_key = (
                    (role, details["round_id"]) if details.get("round_id") else None
                )
                attempt = rounds.get(current_key) if current_key is not None else None
                limit_label = f"{TOOL_REPAIR_LIMIT} shared correction rounds per execution"
            if attempt is None:
                if len(rounds) >= TOOL_REPAIR_LIMIT:
                    label = "prerequisite" if kind == "prerequisite-repair" else "tool argument"
                    raise AgentBoundaryError(
                        f"{error_code}: {label} repair budget exhausted "
                        f"({limit_label}); inspect the tool arguments and prerequisites."
                    )
                attempt = len(rounds) + 1
            self.db.execute(
                "INSERT INTO events(thread,kind,payload) VALUES(?, ?, ?)",
                (
                    thread,
                    kind,
                    compact(
                        {
                            "role": role,
                            "execution_id": execution_id,
                            "attempt": attempt,
                            "error_code": error_code,
                            **details,
                        }
                    ),
                ),
            )
        return attempt

    def command(self, command_id: str) -> dict[str, Any] | None:
        row = self.db.execute("SELECT * FROM commands WHERE id=?", (command_id,)).fetchone()
        if row is None:
            return None
        return {
            **dict(row),
            "binding": json.loads(row["binding"]),
            "payload": json.loads(row["payload"]),
        }

    def prepare(
        self, thread: str, operation: str, binding: dict[str, Any], **payload: Any
    ) -> dict[str, Any]:
        command_id = identity(
            {"project": str(self.project_root), "operation": operation, **binding}
        )
        with self.db:
            self.db.execute(
                "INSERT OR IGNORE INTO commands VALUES(?,?,?,?,?,?)",
                (command_id, thread, operation, compact(binding), "prepared", compact(payload)),
            )
        result = self.command(command_id)
        assert result is not None
        return result

    def update(self, command_id: str, state: str, **values: Any) -> dict[str, Any]:
        current = self.command(command_id)
        if current is None:
            raise AgentBoundaryError("Unknown command")
        payload = {**current["payload"], **values}
        with self.db:
            self.db.execute(
                "UPDATE commands SET state=?, payload=? WHERE id=?",
                (state, compact(payload), command_id),
            )
        return {**current, "state": state, "payload": payload}

    def save_assessment(self, thread: str, assessment: EvidenceAssessment) -> None:
        with self.db:
            self.db.execute(
                "INSERT INTO assessments VALUES(?,?,?)",
                (assessment.assessment_id, thread, assessment.model_dump_json()),
            )
        self.event(thread, "judge-assessment", assessment.model_dump(mode="json"))

    def assessment(self, thread: str, assessment_id: str) -> EvidenceAssessment:
        row = self.db.execute(
            "SELECT payload FROM assessments WHERE id=? AND thread=?", (assessment_id, thread)
        ).fetchone()
        if row is None:
            raise AgentBoundaryError("No trusted Evidence Judge result for this thread")
        return EvidenceAssessment.model_validate_json(row[0])

    def save_card(self, thread: str, card: DecisionCard) -> None:
        with self.db:
            self.db.execute(
                "INSERT OR IGNORE INTO cards VALUES(?,?,?)",
                (card.card_id, thread, card.model_dump_json()),
            )

    def card(self, thread: str, card_id: str) -> DecisionCard:
        row = self.db.execute(
            "SELECT payload FROM cards WHERE id=? AND thread=?", (card_id, thread)
        ).fetchone()
        if row is None:
            raise AgentBoundaryError("Card does not belong to this thread")
        return DecisionCard.model_validate_json(row[0])

    def response(self, thread: str, card: str) -> dict[str, Any] | None:
        row = self.db.execute(
            "SELECT * FROM responses WHERE card=? AND thread=?", (card, thread)
        ).fetchone()
        if row is None:
            return None
        event = self.db.execute(
            "SELECT payload FROM events WHERE thread=? AND kind='human-response' "
            "AND json_extract(payload, '$.card')=? ORDER BY seq DESC LIMIT 1",
            (thread, card),
        ).fetchone()
        if event is None:
            raise AgentBoundaryError("Human response lacks its trusted steering provenance")
        return {**dict(row), "outcome": json.loads(event[0])["outcome"]}

    def respond(
        self,
        thread: str,
        card: str,
        response: str,
        user: str,
        *,
        human_instruction: str | None = None,
        revision_gate: Any = None,
        optional_reason: str | None = None,
        explicit_acknowledgement: str | None = None,
        selected_option_id: str | None = None,
    ) -> dict[str, Any]:
        proposal = self.card(thread, card)
        downstream = proposal.gate_type in {"pilot-promotion", "wet-lab-handoff"}
        if proposal.gate_type not in {
            "target-structure",
            "site-hotspot",
            "design-specification",
            "pilot-promotion",
            "wet-lab-handoff",
        }:
            raise AgentBoundaryError("Decision card has an unsupported scientific Gate")
        if response not in {"approve", "revise", "reject", "override"} or not user.strip():
            raise AgentBoundaryError("A recognized, identified human action is required")
        if response == "revise" and (not human_instruction or not human_instruction.strip()):
            raise AgentBoundaryError("REVISE requires a non-empty human instruction")
        if revision_gate is not None and (
            response != "revise"
            or not (
                revision_gate == proposal.gate_type
                or (
                    proposal.gate_type == "design-specification" and revision_gate == "site-hotspot"
                )
                or (
                    proposal.gate_type == "pilot-promotion"
                    and revision_gate in {"design-specification", "site-hotspot"}
                )
            )
        ):
            raise AgentBoundaryError("Revision target is outside this Gate's authorized scope")
        if response == "override" and (
            not explicit_acknowledgement
            or not explicit_acknowledgement.strip()
            or not optional_reason
            or not optional_reason.strip()
        ):
            raise AgentBoundaryError(
                "OVERRIDE requires explicit acknowledgement and a human rationale"
            )
        from .site_portfolio import is_portfolio_card

        ranked = is_portfolio_card(proposal)
        if ranked and response == "override":
            raise AgentBoundaryError(
                "Choose a selectable candidate with APPROVE; no override is required"
            )
        candidate_warnings: list[str] = []
        effective_judge_status = proposal.judge_status
        if ranked and response == "approve":
            # Explicit APPROVE selects the displayed default; merely displaying A never acts.
            selected_option_id = selected_option_id or proposal.option_id
            option = next(
                (
                    option
                    for option in proposal.options
                    if option["option_id"] == selected_option_id
                ),
                None,
            )
            if option is None or not option["eligible"]:
                raise AgentBoundaryError("Choose one selectable candidate from the displayed card")
            risks = option.get("major_risks", [])
            assert isinstance(risks, list)
            candidate_warnings = [str(risk) for risk in risks]
        elif downstream and response in {"approve", "override"}:
            selected_option_id = selected_option_id or proposal.option_id
            option = next(
                (o for o in proposal.options if o.get("option_id") == selected_option_id), None
            )
            if option is None or option.get("eligible") is not True:
                raise AgentBoundaryError("Selected scientific Gate option is not eligible")
            selected_status = option.get("judge_status")
            if selected_status in {"SUPPORTED", "DISCOURAGED", "BLOCKED"}:
                effective_judge_status = selected_status
        elif selected_option_id is not None:
            raise AgentBoundaryError("Candidate selection requires a ranked Site card and APPROVE")
        if response in {"approve", "override"}:
            if effective_judge_status == "BLOCKED":
                raise AgentBoundaryError(
                    "BLOCKED: revise the input or hard constraint; no override"
                )
            if (
                response == "approve"
                and effective_judge_status in {"DISCOURAGED", None}
                and not ranked
                and not (downstream and effective_judge_status is None)
            ):
                raise AgentBoundaryError("Review the warning and use explicit OVERRIDE or REVISE")
            if response == "override" and effective_judge_status not in {"DISCOURAGED", None}:
                raise AgentBoundaryError("OVERRIDE is only for a warned, discouraged proposal")
        outcome = DecisionOutcome.model_validate(
            {
                "card_id": card,
                "action": response.upper(),
                "human_actor": user,
                "human_instruction": human_instruction,
                "revision_gate": revision_gate,
                "optional_reason": optional_reason,
                "explicit_acknowledgement": explicit_acknowledgement,
                "selected_option_id": selected_option_id,
                "recorded_warnings": list(
                    dict.fromkeys(
                        [
                            *proposal.warnings,
                            *candidate_warnings,
                        ]
                    )
                ),
            }
        )
        previous = self.response(thread, card)
        if previous is not None:
            if DecisionOutcome.model_validate(previous["outcome"]) != outcome:
                raise AgentBoundaryError("Conflicting duplicate response")
            return previous
        with self.db:
            self.db.execute(
                "INSERT INTO responses(card,thread,response,user) VALUES(?,?,?,?)",
                (card, thread, response, user),
            )
            self.db.execute(
                "INSERT INTO events(thread,kind,payload) VALUES(?, 'human-response', ?)",
                (
                    thread,
                    compact(
                        {
                            "card": card,
                            "response": response,
                            "user": user,
                            "outcome": outcome.model_dump(mode="json"),
                        }
                    ),
                ),
            )
        result = self.response(thread, card)
        assert result is not None
        return result

    def delivered(self, thread: str, card: str) -> None:
        with self.db:
            self.db.execute(
                "UPDATE responses SET delivered=1 WHERE card=? AND thread=?", (card, thread)
            )

    def offload(self, thread: str, value: Any, limit: int = 8192) -> str:
        encoded = compact(value)
        if len(encoded.encode()) <= limit:
            return encoded
        # Only bounded summaries/interpretations, never scientific structure bytes.
        if len(encoded.encode()) > 256000:
            raise AgentBoundaryError("Output too large; narrow or paginate the evidence query")
        directory = confined(self.root, self.root / "agent-work" / thread)
        directory.mkdir(parents=True, exist_ok=True)
        name = f"result-{uuid4().hex}.json"
        path = directory / name
        with path.open("x", encoding="utf-8") as handle:
            # The existing read_file tool pages by line. A compact single-line source
            # document can be truncated before its scientific fields become readable.
            json.dump(value, handle, ensure_ascii=False, indent=2)
        return compact({"status": "offloaded", "ref": f"/{name}", "bytes": len(encoded.encode())})
