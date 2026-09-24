"""Read and execute current domain services. No workflow transition is implemented here."""

from __future__ import annotations

import asyncio
import fcntl
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Literal

import yaml  # type: ignore[import-untyped]

from easydesign.agent.contracts import DecisionCard
from easydesign.agent.control_flow import RuntimeAction, next_action
from easydesign.agent.design import DesignBridge
from easydesign.agent.models import ModelConfig
from easydesign.agent.phase2 import Phase2Bridge
from easydesign.agent.phase34_runtime import Phase34Runtime
from easydesign.agent.session_store import SessionStore, confined
from easydesign.agent.site_portfolio import is_portfolio_card
from easydesign.agent.tools import TargetBridge
from easydesign.workspace_context import WorkspaceContext

from .artifacts import digest
from .contracts import ActionRequest, ProductError

GATES = {
    "target-structure": (1, "target"),
    "site-hotspot": (2, "site"),
    "design-specification": (3, "design"),
    "pilot-promotion": (4, "pilot"),
    "wet-lab-handoff": (5, "candidates"),
}


def public_value(value: Any) -> Any:
    """Evidence summaries remain data; server paths and raw model traces stay private."""
    if isinstance(value, dict):
        return {
            k: public_value(v)
            for k, v in value.items()
            if k
            not in {
                "relative_path",
                "file_path",
                "root",
                "run_root",
                "bundle_path",
                "source_path",
                "config_path",
                "stdout",
                "stderr",
                "reasoning_content",
            }
        }
    if isinstance(value, (list, tuple)):
        return [public_value(v) for v in value]
    if isinstance(value, Path):
        return None
    if isinstance(value, str) and value.startswith(("/data/", "/home/", "/Users/", "/tmp/")):
        return "[server-local evidence]"
    return value


def option_actions(card: DecisionCard, option: dict[str, Any]) -> list[str]:
    actions = ["revise", "reject"]
    ranked = is_portfolio_card(card)
    downstream = card.gate_type in {"pilot-promotion", "wet-lab-handoff"}
    if (ranked or downstream) and option.get("eligible") is not True:
        return actions
    if option.get("eligible") is False:
        return actions
    status = option.get("judge_status", card.judge_status) if downstream else card.judge_status
    if status == "BLOCKED":
        return actions
    # Gate 3 governance is runtime-validity first: advisory criticism changes the
    # displayed warnings but cannot turn an executable compiled Design into an
    # override-only route. Only Runtime-authored BLOCKED/hard-invalid evidence
    # removes ordinary approval. Gate 2 ranked choices and optional downstream
    # reviews follow their existing non-blocking contracts as well.
    if (
        ranked
        or card.gate_type == "design-specification"
        or status == "SUPPORTED"
        or (downstream and status is None)
    ):
        return ["approve", *actions]
    if status in {"DISCOURAGED", None}:
        return ["override", *actions]
    return actions


def decision_view(card: DecisionCard) -> dict[str, Any]:
    ranked = is_portfolio_card(card)
    downstream = card.gate_type in {"pilot-promotion", "wet-lab-handoff"}
    # Gate 1 alternatives are evidence, not arbitrary chain-switch authority. Revision
    # returns through the owner/Judge. Site and downstream cards support actual choice.
    options = [
        {**public_value(o), "eligible": o.get("eligible", True), "actions": option_actions(card, o)}
        for o in card.options
        if ranked or downstream or o.get("option_id") == card.option_id
    ]
    targets = [card.gate_type]
    if card.gate_type == "design-specification":
        targets.append("site-hotspot")
    if card.gate_type == "pilot-promotion":
        targets = ["design-specification", "site-hotspot"]
    return {
        "id": card.card_id,
        "gate": GATES[card.gate_type][0],
        "type": card.gate_type,
        "question": card.question,
        "default_option_id": card.option_id,
        "selectable_options": ranked or downstream,
        "options": options,
        "warnings": card.warnings,
        "limitations": card.limitations,
        "action_summary": card.action,
        "revision_targets": targets,
        "review_status": card.judge_status,
        "required_fields": {"revise": ["instruction"], "override": ["reason", "acknowledgement"]},
        "summary": public_value(card.scientific_summary),
    }


class ProjectionStore(SessionStore):
    """Read-only native ledger; freshly derived cards exist only during this GET.

    Runtime's existing Pilot-card builder normally saves its derived card. A view
    may calculate that exact card without publishing it or changing the Harness.
    All other writes fail at SQLite's mode=ro boundary.
    """

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self.root = confined(project_root, project_root / "metadata")
        self.path = confined(self.root, self.root / "agent.sqlite")
        for suffix in ("-wal", "-shm", "-journal"):
            confined(self.root, Path(str(self.path) + suffix))
        self.db = sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True, timeout=5)
        self.db.row_factory = sqlite3.Row
        self._cards: dict[tuple[str, str], DecisionCard] = {}

    def save_card(self, thread: str, card: DecisionCard) -> None:
        self._cards[thread, card.card_id] = card

    def card(self, thread: str, card_id: str) -> DecisionCard:
        return self._cards.get((thread, card_id)) or super().card(thread, card_id)


class DomainSession:
    def __init__(self, project: str, bridge: Any, goal: str) -> None:
        self.project, self.bridge, self.goal = project, bridge, goal
        self._observation: tuple[RuntimeAction, DecisionCard | None, str] | None = None
        self._observation_revision: int | None = None

    def current(self) -> tuple[RuntimeAction, DecisionCard | None, str]:
        b = self.bridge
        observed = b.store.db.execute("SELECT COALESCE(MAX(seq),0) FROM events").fetchone()[0]
        if self._observation is not None and self._observation_revision == observed:
            return self._observation
        if isinstance(b, Phase2Bridge):
            action = next_action(b)
        else:
            evidence = b.read_evidence() if b._jobs() else None
            action = RuntimeAction(
                "target-review" if evidence and evidence.get("request_identity") else "target",
                digest(evidence or b.binding()),
                "resume",
            )
        card = None
        if action.tool == "request_downstream_decision":
            card = b.store.card(b.thread, action.arguments["card_id"])
        elif action.tool == "request_scientific_decision" or action.stage == "target-review":
            evidence = b.judge_evidence() if isinstance(b, Phase2Bridge) else b.read_evidence()
            rows = b.store.db.execute(
                "SELECT payload FROM cards WHERE thread=? ORDER BY rowid DESC", (b.thread,)
            )
            for row in rows:
                possible = DecisionCard.model_validate_json(row[0])
                if (
                    possible.request_identity == evidence["request_identity"]
                    and possible.evidence_id == evidence["evidence_id"]
                    and (
                        not action.arguments.get("assessment_id")
                        or possible.assessment_id == action.arguments["assessment_id"]
                    )
                ):
                    card = possible
                    break
        if card and b.store.response(b.thread, card.card_id):
            card = None  # A durable response awaiting execution must never ask again.
        revision = digest(
            {
                "project": self.project,
                "thread": b.thread,
                "action": action.action_id,
                "card": card.model_dump(mode="json") if card else None,
            }
        )
        self._observation = action, card, revision
        self._observation_revision = observed
        return self._observation

    def check_action(self, request: ActionRequest) -> None:
        if request.action == "message":
            if (
                request.card_id
                or request.selected_option_id
                or not (request.instruction or "").strip()
            ):
                raise ProductError("invalid_question", "Send a question without a Gate response")
            return
        action, card, revision = self.current()
        if request.revision != revision:
            raise ProductError(
                "stale_state", "Scientific state changed; refresh before deciding", 409
            )
        if request.action == "resume":
            if card is not None or request.card_id or request.selected_option_id:
                raise ProductError("gate_required", "Respond to the current Scientist Gate", 409)
            if request.action == "resume" and action.tool is None:
                raise ProductError(
                    "not_resumable", "No unfinished authorized action is available", 409
                )
            return
        if card is None or request.card_id != card.card_id:
            raise ProductError("stale_state", "This Gate card is no longer current", 409)
        view = decision_view(card)
        selected = request.selected_option_id or card.option_id
        option = next((o for o in view["options"] if o["option_id"] == selected), None)
        if option is None or request.action not in option["actions"]:
            raise ProductError("action_not_allowed", "The selected Gate action is not available")
        for field in view["required_fields"].get(request.action, []):
            if not (getattr(request, field) or "").strip():
                raise ProductError("field_required", f"{field} is required")
        if request.revision_target and request.revision_target not in view["revision_targets"]:
            raise ProductError("invalid_revision_target", "Revision target is outside this Gate")

    def execute(
        self, request: ActionRequest, config: ModelConfig, models: dict[str, Any], actor: str
    ) -> dict[str, Any]:
        from easydesign.agent.cli import run_session

        self.check_action(request)
        _, card, _ = self.current()
        # Use the native session function, including graph checkpoint, response intent,
        # reconciliation and scientific validation. The browser never applies a transition.
        return asyncio.run(
            run_session(
                self.bridge,
                config,
                models,
                self.goal,
                decision=request.action if card else None,
                card_id=card.card_id if card else None,
                user=actor,
                new_message=request.instruction if request.action == "message" else None,
                human_instruction=request.instruction if request.action == "revise" else None,
                revision_gate=request.revision_target,
                optional_reason=request.reason,
                explicit_acknowledgement=request.acknowledgement,
                selected_option_id=request.selected_option_id
                if card
                and decision_view(card)["selectable_options"]
                and request.action in {"approve", "override"}
                else None,
            )
        )


class NativeGateway:
    def __init__(
        self,
        context: WorkspaceContext,
        models_path: Path,
        *,
        prediction_backend: Literal["protenix-v2", "openfold3-af3-jax"] = "openfold3-af3-jax",
        model_factory: Callable[..., dict[str, Any]] | None = None,
    ) -> None:
        self.context, self.models_path = context, models_path
        self.prediction_backend, self.model_factory = prediction_backend, model_factory

    def project_path(self, project: str) -> Path:
        import re

        if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}", project):
            raise ProductError("invalid_project", "Invalid project identity", 404)
        root = self.context.projects_root / project
        if root.is_symlink():
            raise ProductError("invalid_project", "Project links are not supported", 403)
        confined(self.context.projects_root, root)
        if not (root / "PROJECT.yaml").is_file():
            raise ProductError("not_found", "Project is not registered in this workspace", 404)
        return root

    def projects(self) -> list[str]:
        # Enumerate project descriptors only, never discover artifacts by directory scans.
        return sorted(
            p.name
            for p in self.context.projects_root.iterdir()
            if p.is_dir() and not p.is_symlink() and (p / "PROJECT.yaml").is_file()
        )

    def config(self) -> ModelConfig:
        return ModelConfig.model_validate(yaml.safe_load(self.models_path.read_text()))

    @contextmanager
    def session(self, project: str, *, write: bool = False) -> Iterator[DomainSession]:
        root = self.project_path(project)
        if not (root / "metadata/agent.sqlite").is_file():
            raise ProductError("no_agent_session", "Project has no v3 Agent session", 409)
        store = SessionStore(root) if write else ProjectionStore(root)
        try:
            row = store.db.execute(
                "SELECT t.id,t.goal FROM threads t LEFT JOIN events e ON e.thread=t.id "
                "GROUP BY t.id ORDER BY MAX(e.seq) DESC,t.rowid DESC LIMIT 1"
            ).fetchone()
            if row is None:
                raise ProductError(
                    "no_agent_session", "Project has no initialized Agent thread", 409
                )
            thread, goal = str(row["id"]), str(row["goal"])
            events = store.events(thread)
            downstream = next(
                (e["payload"] for e in reversed(events) if e["kind"] == "phase34-scope"), None
            )
            upstream = next((e["payload"] for e in events if e["kind"] == "scientific-scope"), None)
            with (root / "metadata/agent-session.lock").open("a") as handle:
                if write:
                    try:
                        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    except BlockingIOError as error:
                        raise ProductError(
                            "project_busy", "An Agent session already owns this project", 409
                        ) from error
                if downstream:
                    bridge: Any = Phase34Runtime(root, thread, store, **downstream)
                elif upstream:
                    bridge = (
                        DesignBridge(root, thread, store)
                        if upstream["through"] == "design"
                        else Phase2Bridge(root, thread, store)
                    )
                else:
                    bridge = TargetBridge(root, thread, store)
                if not write:
                    # Native verified-read cache lives only for this synchronous GET.
                    bridge._authority_reads = {}
                try:
                    yield DomainSession(project, bridge, goal)
                finally:
                    bridge._authority_reads = None
        finally:
            store.close()

    def execute(self, project: str, request: ActionRequest, actor: str) -> dict[str, Any]:
        from easydesign.agent.models import create_models

        with self.session(project, write=True) as session:
            session.check_action(request)
            b = session.bridge
            previous = b.store.latest_execution(b.thread)
            b.store.event(
                b.thread,
                "product-command-started",
                {
                    "request_id": request.request_id,
                    "payload_hash": digest(request.model_dump(mode="json")),
                    "previous_execution_id": previous["execution_id"] if previous else None,
                },
            )
            config = self.config()
            models = (self.model_factory or create_models)(
                config, downstream=isinstance(session.bridge, Phase34Runtime)
            )
            return session.execute(request, config, models, actor)
