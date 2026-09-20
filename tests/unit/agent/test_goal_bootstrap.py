from __future__ import annotations

import asyncio
import json
from pathlib import Path

from langchain_core.messages import AIMessage

from easydesign.agent.bootstrap import GoalTargetIntent, resolve_goal_target
from easydesign.agent.harness import fingerprint
from easydesign.agent.session_store import SessionStore
from easydesign.workspace_context import WorkspaceContext
from tests.agent_support import scripted_config, structure


def test_goal_bootstrap_intent_is_non_authoritative_and_replayed(tmp_path: Path) -> None:
    class IntentModel:
        calls = 0

        def bind_tools(self, tools, **kwargs):
            return self

        async def ainvoke(self, messages):
            self.calls += 1
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "id": "intent-call",
                        "name": "GoalTargetIntent",
                        "args": {
                            "target_label": "NK2R",
                            "uniprot_query": "TACR2",
                            "organism": "Homo sapiens",
                            "taxon_id": 9606,
                            "interpretation": (
                                "NK2R is provisionally interpreted as tachykinin receptor 2."
                            ),
                            "limitations": [
                                "Identity and structure remain subject to native Stage 01 review."
                            ],
                        },
                    }
                ],
            )

    config = scripted_config()
    project_root = tmp_path / "bootstrap-project"
    project_root.mkdir()
    store = SessionStore(project_root)
    model = IntentModel()
    try:
        thread = "goal-first-thread"
        goal = "Please design an inhibitory nanobody against human NK2R."
        store.thread(thread, fingerprint(config), goal)
        first = asyncio.run(
            resolve_goal_target(
                store=store,
                thread=thread,
                goal=goal,
                model=model,
                config=config,
            )
        )
        second = asyncio.run(
            resolve_goal_target(
                store=store,
                thread=thread,
                goal=goal,
                model=model,
                config=config,
            )
        )
        assert first == second
        assert first.uniprot_query == "TACR2" and first.taxon_id == 9606
        assert model.calls == 1
        event = next(e for e in store.events(thread) if e["kind"] == "goal-target-intent")
        assert event["payload"]["authority"] == "discovery-input-only"
    finally:
        store.close()


def test_cli_start_accepts_goal_only_and_preserves_optional_structure_path(
    tmp_path: Path, monkeypatch
) -> None:
    from easydesign.agent import bootstrap, cli
    from easydesign.orchestration.config import (
        LocalFileSourceConfig,
        UniProtSearchSourceConfig,
        load_run_config,
    )
    from easydesign.orchestration.local_project import project_config_path

    (tmp_path / "easydesign-workspace.yaml").write_text(
        'schema_version: "0.1"\nworkspace_id: goal-first-cli-test\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("EASYDESIGN_WORKSPACE", str(tmp_path))
    context = WorkspaceContext.from_root(tmp_path)
    context.ensure_layout()
    models = tmp_path / "models.json"
    models.write_text(json.dumps(scripted_config().model_dump(mode="json")), encoding="utf-8")

    goal_only_loops: list[int] = []

    async def resolve(**_kwargs):
        goal_only_loops.append(id(asyncio.get_running_loop()))
        return GoalTargetIntent(
            target_label="NK2R",
            uniprot_query="TACR2",
            organism="Homo sapiens",
            taxon_id=9606,
            interpretation="Provisional discovery input for NK2R.",
            limitations=["Identity remains subject to native Stage 01 review."],
        )

    created_models: list[dict[str, object]] = []

    async def drive(_args, bridge, _config, _goal, *, models=None):
        bridge.validate_project()
        if models is not None:
            assert models is created_models[-1]
            goal_only_loops.append(id(asyncio.get_running_loop()))
        return 0

    monkeypatch.setattr(bootstrap, "resolve_goal_target", resolve)
    monkeypatch.setattr(cli, "_drive", drive)

    def create_models(*_args, **_kwargs):
        value = {"target": object()}
        created_models.append(value)
        return value

    monkeypatch.setattr("easydesign.agent.models.create_models", create_models)
    goal = "Please design an inhibitory nanobody against human NK2R."
    assert (
        cli.main(
            [
                "start",
                "goal-only",
                "--through",
                "target",
                "--models",
                str(models),
                "--goal",
                goal,
            ]
        )
        == 0
    )
    assert len(goal_only_loops) == 2
    assert goal_only_loops[0] == goal_only_loops[1]
    goal_source = load_run_config(
        project_config_path(context.projects_root / "goal-only")
    ).config.target.source
    assert isinstance(goal_source, UniProtSearchSourceConfig)
    assert goal_source.query == "TACR2" and goal_source.organism_taxon_id == 9606
    assert len(created_models) == 1

    target = context.runtime_root / "tmp/optional-seed.pdb"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(structure("A"), encoding="utf-8")
    assert (
        cli.main(
            [
                "start",
                "optional-seed",
                "--through",
                "target",
                "--models",
                str(models),
                "--goal",
                goal,
                "--target",
                str(target),
            ]
        )
        == 0
    )
    local_source = load_run_config(
        project_config_path(context.projects_root / "optional-seed")
    ).config.target.source
    assert isinstance(local_source, LocalFileSourceConfig)
    assert len(created_models) == 1


def test_remote_target_source_enters_existing_downstream_runtime(
    tmp_path: Path, monkeypatch
) -> None:
    from easydesign.agent.phase34_runtime import Phase34Runtime
    from easydesign.agent.target_identity import CanonicalProposal, propose_canonical
    from easydesign.orchestration.research import initialize_research_project

    (tmp_path / "easydesign-workspace.yaml").write_text(
        'schema_version: "0.1"\nworkspace_id: remote-source-test\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("EASYDESIGN_WORKSPACE", str(tmp_path))
    context = WorkspaceContext.from_root(tmp_path)
    context.ensure_layout()
    root = context.projects_root / "goal-first-remote"
    initialize_research_project(
        project_root=root,
        uniprot_query="TACR2",
        taxon_id=9606,
    )
    store = SessionStore(root)
    try:
        config = scripted_config()
        thread = "remote-target-thread"
        store.thread(thread, fingerprint(config), "Design an inhibitory NK2R nanobody")
        runtime = Phase34Runtime(root, thread, store, through="handoff")
        loaded = runtime.validate_project()
        assert loaded.source_path is None
        assert runtime.binding()["source_identity"]
        assert runtime.target_submission_evidence()["status"] == "not-prepared"
        before = runtime.binding()
        proposal = propose_canonical(
            runtime,
            CanonicalProposal(
                uniprot_card_id="native-source",
                reason="Use native Stage 01 identity and structure selection.",
            ),
        )
        assert proposal["status"] == "native-source-configured"
        assert proposal["authority"].startswith("Discovery configuration only")
        assert runtime.binding() == before
        assert not runtime._jobs()
    finally:
        store.close()
