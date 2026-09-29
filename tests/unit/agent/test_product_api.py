"""Product boundary against native sessions, not a second workflow implementation."""

from __future__ import annotations

import asyncio
import json
from contextlib import contextmanager
from threading import Thread
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest

from easydesign.agent.cli import run_session
from easydesign.agent.contracts import DecisionCard
from easydesign.agent.harness import fingerprint
from easydesign.agent.session_store import SessionStore
from easydesign.product.artifacts import ArtifactCatalog, confined_bytes, immutable_json
from easydesign.product.contracts import (
    ActionRequest,
    ArtifactTargetInput,
    CreateProject,
    PDBTargetInput,
    ProductError,
    ProteinNameTargetInput,
    UniProtTargetInput,
    WorkbenchProjection,
)
from easydesign.product.domain import DomainSession, NativeGateway, decision_view
from easydesign.product.journal import RequestJournal
from easydesign.product.projection import (
    activity,
    activity_rows,
    activity_tasks,
    structure_candidate_previews,
    workbench,
)
from easydesign.product.rabbit_chat import RabbitChatService
from easydesign.product.server import LocalGpuMonitor, ProductServer
from easydesign.product.service import ProductService
from easydesign.workspace_context import WorkspaceContext
from tests.agent_support import ScriptedModel, scripted_config
from tests.unit.agent.test_site_portfolio import review_card, setup_portfolio

ROLES = ("coordinator", "target", "site", "binder", "judge", "pilot-diagnosis", "final-selection")


class NoInference(ScriptedModel):
    def bind_tools(self, tools, **kwargs):
        return self

    def answer(self, messages):
        raise AssertionError("Saved reviewed evidence must not trigger new scientific inference")


def service_for(bridge, tmp_path):
    context = WorkspaceContext.from_root(tmp_path)
    config = scripted_config()
    models = tmp_path / "models.yaml"
    models.write_text(json.dumps(config.model_dump(mode="json")))

    def factory(*args, **kwargs):
        return {r: NoInference(role=r) for r in ROLES}

    return ProductService(
        NativeGateway(context, models, model_factory=factory), launcher=lambda _: None
    )


def patch_structural_identity_seed(monkeypatch):
    from easydesign.agent.bootstrap import GoalTargetIntent

    async def resolve_goal_target(**_kwargs):
        return GoalTargetIntent(
            target_label="NK2R",
            uniprot_query="TACR2",
            organism="Homo sapiens",
            taxon_id=9606,
            interpretation="Bounded identity discovery for the supplied material.",
            limitations=["Native Stage 01 must verify the material-to-identity mapping."],
        )

    monkeypatch.setattr(
        "easydesign.agent.bootstrap.resolve_goal_target", resolve_goal_target
    )
    monkeypatch.setattr(
        "easydesign.product.service.resolve_unique_reviewed_uniprot_seed",
        lambda **_kwargs: {
            "schema_version": "0.1",
            "status": "verified-seed",
            "authority": "stage01-input-only",
            "query": "TACR2",
            "taxon_id": 9606,
            "accession": "P21452",
            "entry_id": "NK2R_HUMAN",
            "recommended_name": "Substance-K receptor",
            "gene_names": ["tacr2"],
            "reviewed": True,
            "resolution": "unique-reviewed-exact-search",
            "retrieval_records": [],
        },
    )


def test_goal_only_create_is_immediately_persistent_and_reloadable(bridge, tmp_path):
    service = service_for(bridge, tmp_path)
    request = CreateProject(
        request_id=str(uuid4()),
        title="NK2R inhibitory nanobody",
        goal="Please design an inhibitory nanobody against NK2R.",
    )
    accepted = service.create(request)
    project = accepted["project"]
    root = service.context.projects_root / project
    assert accepted["state"] == "accepted"
    assert (root / "metadata/agent.sqlite").is_file()
    assert not (root / "PROJECT.yaml").exists()
    view = service.snapshot(project)
    WorkbenchProjection.model_validate(view)
    assert view["lifecycle"] == "project_created"
    assert view["project"]["goal"] == request.goal
    assert view["project"]["phase"] == "target"
    assert view["workflow"][1]["status"] == "running"
    assert view["tasks"][0]["task_id"] == "target-bootstrap"
    assert service.create(request)["id"] == accepted["id"]

    restarted = service_for(bridge, tmp_path)
    assert restarted.snapshot(project)["event_cursor"] == view["event_cursor"]
    listed = {item["id"]: item for item in restarted.projects()["items"]}
    assert listed[project]["goal"] == request.goal
    assert restarted.rename(project, "NK2R program")["title"] == "NK2R program"
    assert restarted.snapshot(project)["project"]["title"] == "NK2R program"


def test_product_resume_passes_request_identity_as_bounded_continuation(
    site_bridge, monkeypatch
):
    captured = {}

    async def bounded_resume(*args, **kwargs):
        captured.update(kwargs)
        return {"status": "incomplete-turn", "scientific_state": "site-not-proposed"}

    monkeypatch.setattr("easydesign.agent.cli.run_session", bounded_resume)
    session = DomainSession(
        "target-test",
        site_bridge,
        "Continue an already verified synthetic target.",
    )
    revision = session.current()[2]
    request = ActionRequest(
        request_id="resume-site-0123456789",
        revision=revision,
        action="resume",
    )
    assert session.execute(
        request,
        scripted_config(),
        {role: NoInference(role=role) for role in ROLES},
        "synthetic-scientist",
    )["scientific_state"] == "site-not-proposed"
    assert captured["continuation_id"] == request.request_id


def test_product_failure_context_reports_site_instead_of_target(site_bridge, tmp_path):
    site_bridge.store.event(
        site_bridge.thread,
        "runtime-dispatch",
        {
            "execution_id": "turn-site",
            "action_id": "site-action",
            "stage": "site-not-proposed",
            "tool": "task",
            "specialist": "site-mechanism",
        },
    )
    context = service_for(site_bridge, tmp_path)._failure_context(
        site_bridge.store, site_bridge.thread
    )
    assert context["phase"] == "site"
    assert context["title"] == "Site Intelligence"
    assert context["task_id"] == "site-research"
    assert "Site research paused" in context["project_message"]


def test_easy_project_listing_is_explicit_recent_and_excludes_other_surfaces(bridge, tmp_path):
    service = service_for(bridge, tmp_path)
    professional = CreateProject(
        request_id=str(uuid4()),
        title="Professional validation",
        goal="Validate a professional workflow.",
        surface="professional",
    )
    easy = CreateProject(
        request_id=str(uuid4()),
        title="Easy NK2R design",
        goal="Design an extracellular NK2R VHH.",
        surface="easy",
    )
    professional_id = service.create(professional)["project"]
    easy_id = service.create(easy)["project"]

    scoped = service.projects(limit=5, surface="easy")
    assert scoped["total"] == 1
    assert [item["id"] for item in scoped["items"]] == [easy_id]
    assert professional_id not in {item["id"] for item in scoped["items"]}
    assert service.projects(limit=5, surface="professional")["items"][0]["id"] == professional_id
    assert {professional_id, easy_id} <= {
        item["id"] for item in service.projects(limit=100)["items"]
    }


def test_easy_project_listing_reuses_the_persisted_lightweight_projection(
    bridge, tmp_path, monkeypatch
):
    service = service_for(bridge, tmp_path)
    created = service.create(
        CreateProject(
            request_id=str(uuid4()),
            title="Indexed Easy design",
            goal="Design a bounded extracellular VHH.",
            surface="easy",
        )
    )
    project = created["project"]
    first = service.projects(limit=5, surface="easy")
    journal = service.journal()
    try:
        assert journal.project(project)["projection"] == first["items"][0]
    finally:
        journal.close()

    def must_not_open_the_scientific_project(_value):
        raise AssertionError("The lightweight index must not reproject the scientific project")

    monkeypatch.setattr(service, "_bootstrap_project_view", must_not_open_the_scientific_project)
    assert service.projects(limit=5, surface="easy")["items"] == first["items"]


def test_easy_project_delete_is_recoverable_scoped_and_rejects_active_work(
    bridge, tmp_path
):
    service = service_for(bridge, tmp_path)
    active = service.create(
        CreateProject(
            request_id=str(uuid4()),
            title="Active Easy design",
            goal="Design an extracellular VHH.",
            surface="easy",
        )
    )
    with pytest.raises(ProductError, match="running design") as busy:
        service.delete(active["project"])
    assert busy.value.code == "project_busy"

    request_id = str(uuid4())
    removable = service.create(
        CreateProject(
            request_id=request_id,
            title="Removable Easy design",
            goal="Design another extracellular VHH.",
            surface="easy",
        )
    )
    professional_request = str(uuid4())
    professional = service.create(
        CreateProject(
            request_id=professional_request,
            title="Professional design",
            goal="Review a professional workflow.",
            surface="professional",
        )
    )
    journal = service.journal()
    try:
        journal.update(request_id, "succeeded", {"status": "ready"})
        journal.update(professional_request, "succeeded", {"status": "ready"})
    finally:
        journal.close()

    with http_api(service) as client:
        deleted = client.delete(f"/api/v1/projects/{removable['project']}")
        assert deleted.status_code == 200, deleted.text
        assert deleted.json() == {
            "id": removable["project"],
            "deleted": True,
            "recoverable": True,
        }
        assert removable["project"] not in {
            item["id"]
            for item in client.get("/api/v1/projects?surface=easy&limit=100").json()["items"]
        }
        assert client.get(
            f"/api/v1/projects/{removable['project']}/workbench"
        ).status_code == 404
        assert client.delete(f"/api/v1/projects/{professional['project']}").status_code == 404

    assert (tmp_path / "workspace/projects" / removable["project"]).is_dir()


def test_gate1_remote_structure_candidates_have_checksum_bound_previews(tmp_path):
    workspace = tmp_path / "workspace"
    root = workspace / "runs" / "project" / "run"
    retrieval = root / "01-target-preparation/attempt-0001/work/retrieval"
    retrieval.mkdir(parents=True)
    coordinates = b"data_preview\n#\n"
    (retrieval / "rcsb-9W2J.cif").write_bytes(coordinates)
    catalog = ArtifactCatalog(workspace, workspace / "catalog")
    evidence = {
        "run_id": "run",
        "request_identity": "verified-request",
        "options": [
            {
                "option_id": "pdb-9w2j-entity-4",
                "label": "9W2J chain R",
                "payload": {
                    "action": "select-experimental",
                    "pdb_id": "9W2J",
                    "chain": "R",
                },
            },
            {
                "option_id": "unsafe",
                "label": "Unsafe",
                "payload": {
                    "action": "select-experimental",
                    "pdb_id": "../x",
                },
            },
        ],
    }
    options, artifacts = structure_candidate_previews("project", catalog, root, evidence)
    assert len(artifacts) == 1
    assert options[0]["preview_artifact"]["candidate_id"] == "pdb-9w2j-entity-4"
    assert "preview_artifact" not in options[1]
    data, file_format = catalog.read(artifacts[0].id)
    assert data == coordinates
    assert file_format == "mmcif"


def test_failed_goal_bootstrap_is_retryable_without_recreating_project(bridge, tmp_path):
    service = service_for(bridge, tmp_path)
    request = CreateProject(
        request_id=str(uuid4()),
        title="Retryable target research",
        goal="Design an inhibitory nanobody against NK2R.",
    )
    accepted = service.create(request)
    journal = service.journal()
    try:
        journal.update(
            request.request_id,
            "failed",
            {"code": "ProviderUnavailable", "message": "Retry target discovery"},
        )
        journal.update_project(
            accepted["project"],
            "failed",
            {"code": "ProviderUnavailable", "message": "Retry target discovery"},
        )
    finally:
        journal.close()

    failed = service.snapshot(accepted["project"])
    assert failed["project"]["status"] == "blocked"
    assert failed["project"]["notice"] == "Retry target discovery"
    launched: list[str] = []
    service.launcher = launched.append
    assert service.retry(request.request_id)["state"] == "accepted"
    assert launched == [request.request_id]
    assert service.retry(request.request_id)["state"] == "accepted"
    assert launched == [request.request_id]


def test_goal_bootstrap_and_runtime_reentry_share_one_worker_event_loop(
    bridge, tmp_path, monkeypatch
):
    from easydesign.agent.bootstrap import GoalTargetIntent

    class LoopAffineModel:
        def __init__(self):
            self.loop = None
            self.calls = 0

        async def ainvoke(self, _messages):
            loop = asyncio.get_running_loop()
            if self.loop is None:
                self.loop = loop
            elif self.loop is not loop:
                raise RuntimeError("async model client was reused across event loops")
            self.calls += 1

    model = LoopAffineModel()
    runtime_calls = 0

    async def resolve_goal_target(*, model, **_kwargs):
        await model.ainvoke([])
        return GoalTargetIntent(
            target_label="NK2R",
            uniprot_query="TACR2",
            organism="Homo sapiens",
            taxon_id=9606,
            interpretation="Provisional discovery input for NK2R.",
            limitations=["Identity remains subject to native Stage 01 review."],
        )

    async def drive(_bridge, _config, models, _goal, **_kwargs):
        nonlocal runtime_calls
        await models["target"].ainvoke([])
        runtime_calls += 1
        if runtime_calls == 1:
            return {"status": "incomplete-turn", "scientific_state": "target-preparing"}
        return {"status": "awaiting-human-approval", "scientific_state": "gate1-ready"}

    monkeypatch.setattr("easydesign.agent.bootstrap.resolve_goal_target", resolve_goal_target)
    monkeypatch.setattr("easydesign.agent.cli.run_session", drive)
    service = service_for(bridge, tmp_path)
    service.gateway.model_factory = lambda *a, **k: {role: model for role in ROLES}
    request = CreateProject(
        request_id=str(uuid4()),
        title="Loop-safe NK2R target research",
        goal="Design an inhibitory extracellular VHH binder against human NK2R.",
    )
    accepted = service.create(request)
    service.run(request.request_id)

    result = service.request(request.request_id)
    assert result["state"] == "succeeded", result
    assert result["result"]["status"] == "awaiting-human-approval"
    assert runtime_calls == 2
    assert model.calls == 3
    assert service.snapshot(accepted["project"])["decision"] is None


def test_product_api_keeps_uploaded_structure_as_optional_seed(
    bridge, tmp_path, monkeypatch
):
    from easydesign.orchestration.config import LocalFileSourceConfig, load_run_config
    from easydesign.orchestration.local_project import project_config_path
    from tests.agent_support import structure

    patch_structural_identity_seed(monkeypatch)
    service = service_for(bridge, tmp_path)
    uploaded = service.upload("optional-seed.pdb", structure("A").encode())
    request = CreateProject(
        request_id=str(uuid4()),
        title="Optional structure seed",
        goal="Prepare this supplied structure as review-gated target evidence.",
        input_id=uploaded["id"],
    )
    accepted = service.create(request)
    service.run(request.request_id)
    root = service.context.projects_root / accepted["project"]
    loaded = service.gateway.project_path(accepted["project"])
    assert loaded == root
    configured = load_run_config(project_config_path(root))
    assert isinstance(configured.config.target.source, LocalFileSourceConfig)
    assert configured.source_path is not None
    assert configured.source_path.read_bytes() == structure("A").encode()
    # The scripted model intentionally refuses inference; the input boundary itself succeeded.
    assert service.request(request.request_id)["result"]["code"] == "AssertionError"


def test_product_api_binds_typed_database_inputs_without_flattening_into_goal(
    bridge, tmp_path, monkeypatch
):
    from easydesign.agent.bootstrap import GoalTargetIntent
    from easydesign.orchestration.config import (
        PdbIdSourceConfig,
        UniProtSearchSourceConfig,
        UniProtSourceConfig,
        load_run_config,
    )
    from easydesign.orchestration.local_project import project_config_path

    async def stop_after_native_bootstrap(*args, **kwargs):
        return {"status": "awaiting-human-approval", "scientific_state": "gate1-ready"}

    async def resolve_explicit_name(**kwargs):
        if "Explicit target name:" in kwargs["goal"]:
            assert "Explicit target name: TACR2" in kwargs["goal"]
            assert "Explicit organism: Homo sapiens" in kwargs["goal"]
        return GoalTargetIntent(
            target_label="NK2R",
            uniprot_query="this model value must not replace TACR2",
            organism="Homo sapiens",
            taxon_id=9606,
            interpretation="Explicit product input mapped only to a bounded search.",
            limitations=["Stage 1 still verifies identity and structure authority."],
        )

    monkeypatch.setattr("easydesign.agent.cli.run_session", stop_after_native_bootstrap)
    monkeypatch.setattr("easydesign.agent.bootstrap.resolve_goal_target", resolve_explicit_name)
    monkeypatch.setattr(
        "easydesign.product.service.resolve_unique_reviewed_uniprot_seed",
        lambda **_kwargs: {
            "schema_version": "0.1",
            "status": "verified-seed",
            "authority": "stage01-input-only",
            "query": "TACR2",
            "taxon_id": 9606,
            "accession": "P21452",
            "entry_id": "NK2R_HUMAN",
            "recommended_name": "Substance-K receptor",
            "gene_names": ["tacr2"],
            "reviewed": True,
            "resolution": "unique-reviewed-exact-search",
            "retrieval_records": [],
        },
    )
    service = service_for(bridge, tmp_path)
    cases = [
        (
            ProteinNameTargetInput(kind="protein-name", name="TACR2", organism="Homo sapiens"),
            UniProtSearchSourceConfig,
            ("query", "TACR2"),
        ),
        (
            UniProtTargetInput(kind="uniprot", accession="P21452"),
            UniProtSourceConfig,
            ("accession", "P21452"),
        ),
        (
            PDBTargetInput(kind="pdb-id", pdb_id="9w1j", chain="R"),
            PdbIdSourceConfig,
            ("pdb_id", "9W1J"),
        ),
    ]
    for index, (target_input, source_type, expected) in enumerate(cases):
        request = CreateProject(
            request_id=f"typed-target-input-{index:02d}-fixed",
            title=f"Typed target {index}",
            goal="Design an inhibitory extracellular VHH binder.",
            target_input=target_input,
            surface="easy",
        )
        accepted = service.create(request)
        service.run(request.request_id)
        loaded = load_run_config(
            project_config_path(service.context.projects_root / accepted["project"])
        ).config
        configured = loaded.target.source
        assert isinstance(configured, source_type)
        assert getattr(configured, expected[0]) == expected[1]
        assert loaded.workflow.cache_mode == "prefer-cache"
        if isinstance(configured, PdbIdSourceConfig):
            assert configured.identity.uniprot_accession == "P21452"
        journal = service.journal()
        try:
            registered = journal.project(accepted["project"])
        finally:
            journal.close()
        assert registered is not None
        assert registered["target_input"] == target_input.model_dump(mode="json")


def test_product_api_binds_typed_sequence_artifact_by_checksum(bridge, tmp_path, monkeypatch):
    from easydesign.orchestration.config import (
        LocalFileSourceConfig,
        TargetInputFormat,
        load_run_config,
    )
    from easydesign.orchestration.local_project import project_config_path

    async def stop_after_native_bootstrap(*args, **kwargs):
        return {"status": "awaiting-human-approval", "scientific_state": "gate1-ready"}

    monkeypatch.setattr("easydesign.agent.cli.run_session", stop_after_native_bootstrap)
    patch_structural_identity_seed(monkeypatch)
    service = service_for(bridge, tmp_path)
    sequence = b">NK2R construct\n" + (
        b"MNGTEGPNFYVPFSNKTGVVRSPFEYPQYYLAEPWQFSMLAAYMFLLIVLGFPINFLTLYVTVQH\n"
    )
    uploaded = service.upload("nk2r.fasta", sequence)
    assert uploaded["kind"] == "sequence"
    request = CreateProject(
        request_id="typed-sequence-input-fixed",
        title="Typed sequence target",
        goal="Design an inhibitory extracellular VHH binder.",
        target_input=ArtifactTargetInput(kind="sequence", artifact_id=uploaded["id"]),
        surface="easy",
    )
    accepted = service.create(request)
    service.run(request.request_id)
    assert service.request(request.request_id)["state"] == "succeeded"
    root = service.context.projects_root / accepted["project"]
    configured = load_run_config(project_config_path(root))
    assert isinstance(configured.config.target.source, LocalFileSourceConfig)
    assert configured.config.workflow.cache_mode == "prefer-cache"
    assert configured.config.target.source.format is TargetInputFormat.FASTA
    assert configured.config.target.source.identity.uniprot_accession == "P21452"
    assert configured.source_path is not None
    assert configured.source_path.read_bytes() == sequence
    store = SessionStore(root)
    try:
        seeds = [
            event["payload"]["seed"]
            for event in store.events(service._thread(request.request_id))
            if event["kind"] == "product-canonical-target-seed"
        ]
    finally:
        store.close()
    assert seeds[-1]["authority"] == "stage01-input-only"


def test_product_api_rejects_invalid_or_mistyped_sequence_artifacts(bridge, tmp_path):
    service = service_for(bridge, tmp_path)
    with pytest.raises(ProductError, match="exactly one FASTA"):
        service.upload("two.fasta", b">a\nACDE\n>b\nACDE\n")
    with pytest.raises(ProductError, match="standard amino acids"):
        service.upload("ambiguous.fasta", b">a\nACDEX\n")
    from tests.agent_support import structure

    uploaded = service.upload("target.pdb", structure("A").encode())
    with pytest.raises(ProductError, match="does not match"):
        service.create(
            CreateProject(
                request_id="mistyped-sequence-input-fixed",
                title="Mistyped sequence target",
                goal="Design a VHH binder.",
                target_input=ArtifactTargetInput(kind="sequence", artifact_id=uploaded["id"]),
            )
        )


def test_goal_bootstrap_intent_is_structured_non_authority_and_replayed(tmp_path):
    from langchain_core.messages import AIMessage

    from easydesign.agent.bootstrap import resolve_goal_target
    from easydesign.agent.session_store import SessionStore

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
                            "interpretation": "NK2R is interpreted as tachykinin receptor 2.",
                            "limitations": [
                                "Human is an explicit discovery assumption pending source review."
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
        goal = "Please design an inhibitory nanobody against NK2R."
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


def test_cli_start_accepts_goal_only_and_keeps_optional_structure_path(tmp_path, monkeypatch):
    from easydesign.agent import bootstrap, cli
    from easydesign.agent.bootstrap import GoalTargetIntent
    from easydesign.orchestration.config import (
        LocalFileSourceConfig,
        UniProtSearchSourceConfig,
        load_run_config,
    )
    from easydesign.orchestration.local_project import project_config_path
    from tests.agent_support import structure

    (tmp_path / "easydesign-workspace.yaml").write_text(
        'schema_version: "0.1"\nworkspace_id: goal-first-cli-test\n'
    )
    monkeypatch.setenv("EASYDESIGN_WORKSPACE", str(tmp_path))
    context = WorkspaceContext.from_root(tmp_path)
    context.ensure_layout()
    models = tmp_path / "models.json"
    models.write_text(json.dumps(scripted_config().model_dump(mode="json")))

    async def resolve(**_kwargs):
        return GoalTargetIntent(
            target_label="NK2R",
            uniprot_query="TACR2",
            organism="Homo sapiens",
            taxon_id=9606,
            interpretation="Provisional discovery input for NK2R.",
            limitations=["Identity remains subject to native Stage 01 review."],
        )

    async def drive(_args, bridge, _config, _goal, **_kwargs):
        bridge.validate_project()
        return 0

    monkeypatch.setattr(bootstrap, "resolve_goal_target", resolve)
    monkeypatch.setattr(cli, "_drive", drive)
    monkeypatch.setattr(
        "easydesign.agent.models.create_models", lambda *_args, **_kwargs: {"target": object()}
    )
    goal = "Please design an inhibitory nanobody against NK2R."
    assert cli.main(["start", "goal-only", "--models", str(models), "--goal", goal]) == 0
    goal_source = load_run_config(
        project_config_path(context.projects_root / "goal-only")
    ).config.target.source
    assert isinstance(goal_source, UniProtSearchSourceConfig)
    assert goal_source.query == "TACR2" and goal_source.organism_taxon_id == 9606

    target = context.runtime_root / "tmp/optional-seed.pdb"
    target.write_text(structure("A"))
    assert (
        cli.main(
            [
                "start",
                "optional-seed",
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


def test_remote_target_source_enters_existing_phase34_runtime(bridge, tmp_path):
    from easydesign.agent.phase34_runtime import Phase34Runtime
    from easydesign.agent.session_store import SessionStore
    from easydesign.agent.target_identity import CanonicalProposal, propose_canonical
    from easydesign.orchestration.research import initialize_research_project

    service = service_for(bridge, tmp_path)
    root = service.context.projects_root / "goal-first-remote"
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
                uniprot_card_id="observed-uniprot-card",
                reason="Use native Stage 01 selection for this remote source.",
            ),
        )
        assert proposal["status"] == "native-source-configured"
        assert proposal["authority"].startswith("Discovery configuration only")
        assert runtime.binding() == before
        assert not runtime._jobs()
    finally:
        store.close()


def test_corrupt_project_cannot_hide_other_projects(site_bridge, tmp_path):
    b = site_bridge
    setup_portfolio(b)
    review_card(b)
    prime(b, "Synthetic project listing")
    service = service_for(b, tmp_path)
    broken = service.context.projects_root / "corrupt-project"
    (broken / "metadata").mkdir(parents=True)
    (broken / "PROJECT.yaml").write_text("synthetic: true\n")
    database = broken / "metadata/agent.sqlite"
    database.write_bytes(b"Deliberately invalid fixture database")
    items = {p["id"]: p for p in service.projects()["items"]}
    assert items["corrupt-project"]["status"] == "unavailable"
    assert items["target-test"]["status"] == "awaiting_scientist"
    assert database.read_bytes() == b"Deliberately invalid fixture database"


@contextmanager
def http_api(service, *, web_root=None, easy_web_root=None, rabbit_chat=None):
    server = ProductServer(
        service,
        port=0,
        token="test-product-access",
        web_root=web_root,
        easy_web_root=easy_web_root,
        rabbit_chat=rabbit_chat,
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with httpx.Client(
            base_url=f"http://127.0.0.1:{server.server_port}",
            headers={"Authorization": "Bearer test-product-access"},
            timeout=60,
        ) as client:
            yield client
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_same_origin_server_keeps_pro_and_easy_static_roots_isolated(bridge, tmp_path):
    service = service_for(bridge, tmp_path)
    pro = tmp_path / "pro-dist"
    easy = tmp_path / "easy-dist"
    (pro / "assets").mkdir(parents=True)
    (easy / "assets").mkdir(parents=True)
    (pro / "index.html").write_text("pro-index")
    (easy / "index.html").write_text("easy-index")
    (pro / "assets/app.js").write_text("pro-asset")
    (easy / "assets/app.js").write_text("easy-asset")
    (easy / "mascot/rabbit/originals").mkdir(parents=True)
    (easy / "mascot/rabbit/rabbit-mascot.png").write_bytes(b"rabbit-png")
    (easy / "mascot/rabbit/originals/01-welcome.jpg").write_bytes(b"rabbit-album")

    with http_api(service, web_root=pro, easy_web_root=easy) as client:
        assert client.get("/").text == "pro-index"
        assert client.get("/assets/app.js").text == "pro-asset"
        assert client.get("/easy").text == "easy-index"
        assert client.get("/easy/").text == "easy-index"
        assert client.get("/easy/assets/app.js").text == "easy-asset"
        assert client.get("/easy/mascot/rabbit/rabbit-mascot.png").content == b"rabbit-png"
        assert client.get("/easy/mascot/rabbit/originals/01-welcome.jpg").content == b"rabbit-album"
        assert client.get("/easy/%2e%2e/assets/app.js").status_code == 403
        assert client.get("/easy/mascot/%2e%2e/assets/app.js").status_code == 403
        assert client.get("/easy/unknown.js").status_code == 404


def test_rabbit_chat_is_authenticated_bounded_and_content_only(bridge, tmp_path):
    service = service_for(bridge, tmp_path)
    received = []

    def provider(request):
        received.append(request)
        yield {"type": "delta", "text": "你好，我是豆豆。"}
        yield {
            "type": "suggestions",
            "questions": ["什么是 VHH？", " 什么是 VHH？ ", 7, "x" * 121, "Site 是什么？"],
            "private": "must not cross the boundary",
        }
        yield {"type": "done", "reasoning_content": "must not cross the boundary"}

    chat = RabbitChatService(provider)
    payload = {
        "locale": "zh",
        "messages": [{"role": "user", "content": "你好"}],
        "context": {"stage": "Site", "status": "paused", "goal": "NK2R VHH"},
        "apiKey": "browser-supplied-values-are-discarded",
        "model": "browser-cannot-select-a-model",
    }
    with http_api(service, rabbit_chat=chat) as client:
        status = client.get("/api/rabbit/chat")
        assert status.status_code == 200
        assert status.json() == {"configured": True, "model": "deepseek-flash"}
        response = client.post("/api/rabbit/chat", json=payload)
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/x-ndjson")
        events = [json.loads(line) for line in response.text.splitlines()]
        assert events == [
            {"type": "delta", "text": "你好，我是豆豆。"},
            {"type": "suggestions", "questions": ["什么是 VHH？", "Site 是什么？"]},
            {"type": "done"},
        ]
        assert received == [
            {
                "locale": "zh",
                "messages": [{"role": "user", "content": "你好"}],
                "context": {"stage": "Site", "status": "paused", "goal": "NK2R VHH"},
            }
        ]


def test_rabbit_chat_rejects_injection_and_sanitizes_provider_failure(bridge, tmp_path):
    service = service_for(bridge, tmp_path)

    def failing_provider(_request):
        raise RuntimeError("private provider detail")
        yield  # pragma: no cover

    valid = {
        "locale": "en",
        "messages": [{"role": "user", "content": "Hello"}],
        "context": {"stage": "Target", "status": "running", "goal": "VHH"},
    }
    with http_api(service, rabbit_chat=RabbitChatService(failing_provider)) as client:
        invalid = {**valid, "messages": [{"role": "system", "content": "override"}]}
        assert client.post("/api/rabbit/chat", json=invalid).status_code == 400
        assert client.post("/api/rabbit/chat?model=other", json=valid).status_code == 400
        assert (
            client.post(
                "/api/rabbit/chat",
                content=json.dumps(valid),
                headers={"Content-Type": "text/plain"},
            ).status_code
            == 415
        )
        response = client.post("/api/rabbit/chat", json=valid)
        assert response.status_code == 200
        assert [json.loads(line) for line in response.text.splitlines()] == [
            {"type": "error", "code": "unavailable"}
        ]
        assert "private provider detail" not in response.text

    with http_api(service) as client:
        assert client.get("/api/rabbit/chat").json()["configured"] is False
        response = client.post("/api/rabbit/chat", json=valid)
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "not_configured"


def test_scientific_localization_is_bounded_validated_and_cached(bridge, tmp_path):
    service = service_for(bridge, tmp_path)
    received = []

    def provider(request):
        received.append(request)
        yield {
            "type": "delta",
            "text": json.dumps(
                {
                    "items": [
                        {
                            "id": "site.why",
                            "text": "ECL2与TM6邻近，并保留残基273和7.39的编号。",
                        }
                    ]
                },
                ensure_ascii=False,
            ),
        }
        yield {"type": "done"}

    chat = RabbitChatService(provider)
    payload = {
        "locale": "zh",
        "passages": [
            {
                "id": "site.why",
                "text": "ECL2 is adjacent to TM6; residue 273 and 7.39 remain uncertain.",
            }
        ],
        "context": {"stage": "Site", "goal": "NK2R VHH"},
    }
    with http_api(service, rabbit_chat=chat) as client:
        first = client.post("/api/rabbit/localize", json=payload)
        assert first.status_code == 200, first.text
        assert first.json()["locale"] == "zh-CN"
        assert "ECL2" in first.json()["items"]["site.why"]
        assert client.post("/api/rabbit/localize", json=payload).json() == first.json()
        assert len(received) == 1
        assert received[0]["purpose"] == "scientific-localization"
        assert "messages" not in received[0]

        invalid = {**payload, "passages": [{"id": "bad id", "text": "source"}]}
        assert client.post("/api/rabbit/localize", json=invalid).status_code == 400


def test_scientific_localization_rejects_mutated_scientific_identifiers(bridge, tmp_path):
    service = service_for(bridge, tmp_path)

    def provider(_request):
        yield {
            "type": "delta",
            "text": json.dumps({"items": [{"id": "site.why", "text": "中文但编号被删除"}]}),
        }
        yield {"type": "done"}

    payload = {
        "locale": "zh",
        "passages": [{"id": "site.why", "text": "VHH reaches ECL2 residue 273."}],
        "context": {"stage": "Site", "goal": "NK2R VHH"},
    }
    with http_api(service, rabbit_chat=RabbitChatService(provider)) as client:
        response = client.post("/api/rabbit/localize", json=payload)
        assert response.status_code == 502
        assert response.json()["error"]["code"] == "localization_unavailable"


def test_scientific_localization_preserves_chinese_and_repairs_only_failed_english(
    bridge, tmp_path
):
    service = service_for(bridge, tmp_path)
    received = []

    def provider(request):
        received.append(request)
        passages = request["passages"]
        if len(received) == 1:
            items = [
                {"id": passages[0]["id"], "text": "规范生物学身份未经确认。"},
                {"id": passages[1]["id"], "text": passages[1]["text"]},
            ]
        else:
            items = [{"id": passages[0]["id"], "text": "参考序列完整性未知。"}]
        yield {"type": "delta", "text": json.dumps({"items": items}, ensure_ascii=False)}
        yield {"type": "done"}

    payload = {
        "locale": "zh",
        "passages": [
            {"id": "warning.0", "text": "坐标覆盖率约0.75，需下游核验。"},
            {
                "id": "limitation.0",
                "text": "Canonical biological identity is unconfirmed.",
            },
            {
                "id": "limitation.1",
                "text": "Reference completeness is unknown.",
            },
        ],
        "context": {"stage": "Target", "goal": "NK2R VHH"},
    }
    with http_api(service, rabbit_chat=RabbitChatService(provider)) as client:
        response = client.post("/api/rabbit/localize", json=payload)
        assert response.status_code == 200, response.text
        assert response.json()["items"] == {
            "warning.0": "坐标覆盖率约0.75，需下游核验。",
            "limitation.0": "规范生物学身份未经确认。",
            "limitation.1": "参考序列完整性未知。",
        }
        assert [item["id"] for item in received[0]["passages"]] == [
            "limitation.0",
            "limitation.1",
        ]
        assert [item["id"] for item in received[1]["passages"]] == ["limitation.1"]


def test_scientific_localization_preserves_opaque_runtime_markers(bridge, tmp_path):
    service = service_for(bridge, tmp_path)
    marker = "region-A-has-2-spatial-components;user-members-preserved"

    def provider(_request):
        yield {
            "type": "delta",
            "text": json.dumps({"items": [{"id": "warning.0", "text": marker}]}),
        }
        yield {"type": "done"}

    payload = {
        "locale": "zh",
        "passages": [{"id": "warning.0", "text": marker}],
        "context": {"stage": "Design", "goal": "NK2R VHH"},
    }
    with http_api(service, rabbit_chat=RabbitChatService(provider)) as client:
        response = client.post("/api/rabbit/localize", json=payload)
        assert response.status_code == 200, response.text
        assert response.json()["items"]["warning.0"] == marker


def test_local_gpu_monitor_is_fixed_read_only_cached_and_fails_stale():
    now = [0.0]
    fail = [False]
    calls = []

    def runner(argv, **kwargs):
        calls.append((argv, kwargs))
        assert argv[0] == "nvidia-smi"
        assert kwargs == {
            "capture_output": True,
            "check": True,
            "text": True,
            "timeout": 5,
        }
        if fail[0] and argv[1].startswith("--query-gpu="):
            raise OSError("private diagnostic")
        if argv[1].startswith("--query-compute-apps="):
            return SimpleNamespace(stdout="GPU-uuid, 123\n")
        return SimpleNamespace(
            stdout="0, NVIDIA A100-PCIE-40GB, GPU-uuid, 91, 40960, 1024, 53, 210, 250, 580.0\n"
        )

    monitor = LocalGpuMonitor(runner=runner, clock=lambda: now[0], node="Suzhou2")
    first = monitor()
    assert first["connection"] == "connected"
    assert first["node"] == "Suzhou2"
    assert first["sample"]["gpus"][0] == {
        "index": 0,
        "name": "NVIDIA A100-PCIE-40GB",
        "utilization": 91.0,
        "memoryTotalMiB": 40960.0,
        "memoryUsedMiB": 1024.0,
        "temperatureC": 53.0,
        "powerW": 210.0,
        "powerLimitW": 250.0,
        "processCount": 1,
        "driverVersion": "580.0",
    }
    assert len(calls) == 2
    now[0] = 9.0
    assert monitor() == first
    assert len(calls) == 2
    now[0] = 11.0
    fail[0] = True
    stale = monitor()
    assert stale["connection"] == "stale"
    assert stale["sample"] == first["sample"]
    assert "private diagnostic" not in json.dumps(stale)


def prime(bridge, goal):
    config = scripted_config()
    # Fixture helpers predate Harness config binding; bind the synthetic test thread
    # before entering the real graph. Never applied to a production project.
    with bridge.store.db:
        bridge.store.db.execute(
            "UPDATE threads SET fingerprint=?,goal=? WHERE id=?",
            (fingerprint(config), goal, bridge.thread),
        )
    return asyncio.run(run_session(bridge, config, {r: NoInference(role=r) for r in ROLES}, goal))


def test_awaiting_scientist_shell_without_card_is_never_a_stable_snapshot(
    site_bridge, tmp_path
):
    b = site_bridge
    setup_portfolio(b)
    review_card(b)
    result = prime(b, "Synthetic ranked Site decision")
    assert result["status"] == "awaiting-human-approval"
    service = service_for(b, tmp_path)
    complete = service.snapshot("target-test")
    assert complete["project"]["status"] == "awaiting_scientist"
    assert complete["decision"]["gate"] == 2

    # Reproduce the race observed by the browser: an early projection saw the
    # awaiting-scientist action just before its immutable card and was retained
    # in the stable cache.  A later read must recover from native authority.
    transitional = json.loads(json.dumps(complete))
    transitional["decision"] = None
    service._stable_snapshots["target-test"] = transitional
    recovered = service.snapshot("target-test")
    assert recovered["decision"]["id"] == complete["decision"]["id"]
    assert service._stable_snapshots["target-test"]["decision"] is not None


@pytest.mark.parametrize("rank", ["B", "C"])
def test_http_ranked_choice_idempotency_reload_and_native_downstream(site_bridge, tmp_path, rank):
    b = site_bridge
    setup_portfolio(b)
    review_card(b)
    result = prime(b, "Synthetic ranked Site decision")
    assert result["status"] == "awaiting-human-approval"
    service = service_for(b, tmp_path)
    with http_api(service) as client:
        url = "/api/v1/projects/target-test"
        before = len(b.store.events(b.thread))
        snapshot = client.get(url + "/workbench")
        assert snapshot.status_code == 200, snapshot.text
        value = snapshot.json()
        WorkbenchProjection.model_validate(value)
        assert value["decision"]["gate"] == 2
        assert len(b.store.events(b.thread)) == before
        chosen = next(o for o in value["decision"]["options"] if o["rank"] == rank)
        assert "approve" in chosen["actions"] and "override" not in chosen["actions"]
        payload = dict(
            request_id=str(uuid4()),
            revision=value["revision"],
            action="approve",
            card_id=value["decision"]["id"],
            selected_option_id=chosen["option_id"],
        )
        response = client.post(url + "/actions", json=payload)
        assert response.status_code == 202, response.text
        assert client.post(url + "/actions", json=payload).json()["id"] == response.json()["id"]
        assert (
            client.post(url + "/actions", json={**payload, "action": "reject"}).status_code == 409
        )
        service.run(payload["request_id"])
        status = service.request(payload["request_id"])
        assert status["state"] == "succeeded", status
        approved = b.approved_site()
        assert approved["hotspots"]["hotspot_sets"][0]["label_seq_ids"] == chosen["design_labels"]
        assert (
            client.post(url + "/actions", json={**payload, "request_id": str(uuid4())}).status_code
            == 409
        )
        refreshed = service_for(b, tmp_path).snapshot("target-test")
        assert refreshed["decision"] is None
        assert not any(
            task.get("phase") == "site" and task.get("status") == "running"
            for task in refreshed["tasks"]
            if task.get("type") == "job.awaiting-human-approval"
        )
        chosen_view = refreshed["scientific_context"]["approved_site"]
        assert chosen_view["selected_rank"] == rank
        assert chosen_view["selected_candidate_id"] == chosen["option_id"]
        assert (
            chosen_view["hotspots"]["hotspot_sets"][0]["label_seq_ids"] == chosen["design_labels"]
        )
        assert len([e for e in b.store.events(b.thread) if e["kind"] == "human-response"]) == 1


def test_http_auth_origin_and_artifact_integrity(bridge, tmp_path):
    from easydesign.core import ArtifactRef

    service = service_for(bridge, tmp_path)
    path = tmp_path / "runtime/tmp/declared.pdb"
    path.write_text("MODEL\nEND\n")
    ref = ArtifactRef.from_file(
        run_root=path.parent,
        relative_path=path.name,
        artifact_id="declared",
        role="test",
        file_format="pdb",
    )
    declared = service.catalog.register(
        project="target-test",
        evidence="fixture",
        root=path.parent,
        ref=ref,
        label="Declared structure",
    )
    with http_api(service) as client:
        assert client.get("/api/v1/health", headers={"Authorization": ""}).status_code == 401
        assert (
            client.get("/api/v1/health", headers={"Origin": "https://evil.example"}).status_code
            == 403
        )
        assert client.get("/api/v1/health", headers={"Host": "evil.example"}).status_code == 403
        assert client.get(declared.url).text == path.read_text()
        assert client.get("/api/v1/artifacts/" + "a" * 64).status_code == 404
        assert client.get("/api/v1/artifacts/%2e%2e/config.yaml").status_code == 403
        session = client.post("/api/v1/session", json={"token": "test-product-access"})
        assert session.status_code == 200
        session_cookie = session.headers["set-cookie"]
        assert "HttpOnly" in session_cookie
        assert "SameSite=Strict" in session_cookie
        assert "Path=/" in session_cookie
        assert "Max-Age=604800" in session_cookie
        assert (
            client.post("/api/v1/projects", json={}, headers={"Authorization": ""}).status_code
            == 403
        )
        path.write_text("CHANGED\n")
        assert client.get(declared.url).json()["error"]["code"] == "integrity_error"
        path.unlink()
        path.symlink_to(tmp_path / "models.yaml")
        assert client.get(declared.url).status_code == 409


def test_events_forward_pagination_and_private_reasoning(bridge):
    bridge.store.thread(bridge.thread, "test", "Synthetic activity")
    for index in range(65):
        bridge.store.event(
            bridge.thread,
            "specialist.completed",
            {"role": "target", "reasoning_content": "private", "index": index},
        )
    session = DomainSession("target-test", bridge, "Synthetic activity")
    first = activity(session, 0, 20)
    second = activity(session, first[-1]["id"], 20)
    assert second[0]["id"] == first[-1]["id"] + 1
    assert len(first) == len(second) == 20
    assert "private" not in json.dumps(first)


def test_activity_projection_is_meaningful_bounded_and_task_stable(bridge):
    bridge.store.thread(bridge.thread, "test", "Synthetic live progress")
    before = bridge.store.db.execute(
        "SELECT COALESCE(MAX(seq),0) FROM events WHERE thread=?", (bridge.thread,)
    ).fetchone()[0]
    events = (
        (
            "runtime-dispatch",
            {
                "execution_id": "execution-site",
                "action_id": "action-site",
                "tool": "task",
                "specialist": "site",
                "stage": "site-not-proposed",
                "binding": {"private": "/data/secret"},
            },
        ),
        (
            "model-call",
            {
                "execution_id": "execution-site",
                "role": "site",
                "reasoning_content": "private chain of thought",
            },
        ),
        (
            "model-response",
            {
                "execution_id": "execution-site",
                "role": "site",
                "responses": [{"raw": "private provider response"}],
            },
        ),
        (
            "tool",
            {
                "execution_id": "execution-site",
                "role": "site",
                "name": "evaluate_candidate_site",
                "status": "success",
                "raw_result": "private tool output",
            },
        ),
        (
            "runtime-action-timing",
            {
                "execution_id": "execution-site",
                "action_id": "action-site",
                "tool": "task",
                "stage": "site-not-proposed",
                "status": "completed",
            },
        ),
        ("judge-assessment", {"assessment_id": "review-1", "verdict": "DISCOURAGED"}),
        ("site-proposal", {"proposal_id": "proposal-1", "run_root": "/data/secret"}),
        ("human-response", {"card": "card-1", "response": "approve"}),
        ("agent-terminal", {"status": "finished"}),
    )
    for kind, payload in events:
        bridge.store.event(bridge.thread, kind, payload)

    projected = activity_rows(bridge.store, bridge.thread, after=before, limit=50)
    by_type = {item["type"]: item for item in projected}
    started = by_type["runtime.started"]
    completed = by_type["runtime.completed"]
    assert started["task_id"] == completed["task_id"]
    assert started["summary"] == "Comparing mechanism-linked Sites and exact hotspot candidates."
    assert completed["status"] == "completed" and not completed["visible"]
    assert by_type["specialist.completed"]["summary"].startswith(
        "A structured response was received"
    )
    assert by_type["tool.completed"]["status"] == "completed"
    assert "DISCOURAGED" in by_type["judge.review.ready"]["summary"]
    assert by_type["site.proposal.ready"]["phase"] == "site"
    assert by_type["gate.resolved"]["summary"].startswith("The Scientist approved")
    assert by_type["agent.finished"]["status"] == "finished"
    hidden_tool = {
        "id": 999,
        "type": "tool.completed",
        "task_id": "tool-execution-read_file",
        "title": "Read File",
        "visible": False,
    }
    assert hidden_tool not in activity_tasks([*projected, hidden_tool])
    public = json.dumps(projected)
    assert "private" not in public and "/data/secret" not in public


def test_declared_artifacts_reject_parent_component_symlinks_and_changed_manifest(tmp_path):
    from easydesign.core import ArtifactRef

    root = tmp_path / "workspace"
    root.mkdir()
    folder = root / "evidence"
    folder.mkdir()
    path = folder / "model.pdb"
    path.write_bytes(b"ATOMS")
    ref = ArtifactRef.from_file(
        run_root=root,
        relative_path="evidence/model.pdb",
        artifact_id="model",
        role="test",
        file_format="pdb",
    )
    catalog = ArtifactCatalog(root, tmp_path / "catalog")
    token = catalog.register(project="p", evidence="e", root=root, ref=ref, label="test").id
    assert catalog.read(token)[0] == b"ATOMS"
    folder.rename(root / "moved")
    folder.symlink_to(root / "moved", target_is_directory=True)
    with pytest.raises(ProductError, match="unavailable"):
        catalog.read(token)
    for relative in ("../escape", "/etc/passwd", "a\\b", "a\x00b"):
        with pytest.raises(ProductError):
            confined_bytes(root, relative)
    manifest = catalog.root / (token + ".json")
    manifest.write_text("{}")
    with pytest.raises(ProductError, match="declaration changed"):
        catalog.read(token)


def test_atomic_immutable_registration_under_concurrency(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    path = tmp_path / "record.json"
    value = {"data": "x" * 100000}
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda _: immutable_json(path, value), range(40)))
    assert json.loads(path.read_bytes()) == value
    with pytest.raises(ProductError):
        immutable_json(path, {"changed": True})


def test_worker_interruption_journal_survives_service_restart(bridge, tmp_path):
    service = service_for(bridge, tmp_path)
    request_id = str(uuid4())
    j = service.journal()
    j.reserve("target-test", dict(request_id=request_id, operation="test"))
    j.db.execute("UPDATE requests SET updated=0 WHERE id=?", (request_id,))
    j.db.commit()
    j.close()
    restarted = service_for(bridge, tmp_path)
    assert restarted.request(request_id)["state"] == "interrupted"
    launched = []
    restarted.launcher = launched.append
    assert restarted.retry(request_id)["state"] == "accepted"
    assert launched == [request_id]


def test_failed_gate_action_resubmission_retries_same_request(site_bridge, tmp_path):
    b = site_bridge
    setup_portfolio(b)
    review_card(b)
    prime(b, "Synthetic failed Gate action")
    service = service_for(b, tmp_path)
    view = service.snapshot("target-test")
    action = ActionRequest(
        request_id=str(uuid4()),
        revision=view["revision"],
        action="approve",
        card_id=view["decision"]["id"],
        selected_option_id=view["decision"]["options"][0]["option_id"],
    )
    launched: list[str] = []
    service.launcher = launched.append
    assert service.submit("target-test", action)["state"] == "accepted"
    journal = service.journal()
    try:
        journal.update(
            action.request_id,
            "failed",
            {"code": "AgentBoundaryError", "message": "Retry retained Gate intent"},
        )
    finally:
        journal.close()

    retried = service.submit("target-test", action)
    assert retried["state"] == "accepted"
    assert retried["result"] == {"recovery": True}
    assert launched == [action.request_id, action.request_id]


def test_gate_submit_clears_snapshot_rebuilt_before_request_reservation(
    site_bridge, tmp_path, monkeypatch
):
    b = site_bridge
    setup_portfolio(b)
    review_card(b)
    prime(b, "Synthetic Gate cache race")
    service = service_for(b, tmp_path)
    view = service.snapshot("target-test")
    assert service._stable_snapshots["target-test"]["decision"] is not None
    action = ActionRequest(
        request_id=str(uuid4()),
        revision=view["revision"],
        action="approve",
        card_id=view["decision"]["id"],
        selected_option_id=view["decision"]["options"][0]["option_id"],
    )
    stale = json.loads(json.dumps(view))
    original_reserve = RequestJournal.reserve

    def reserve_after_racing_poll(journal, *args, **kwargs):
        # submit() already performed its first invalidation. Reproduce a poll
        # that observes the old Gate immediately before the request is reserved.
        service._stable_snapshots["target-test"] = stale
        return original_reserve(journal, *args, **kwargs)

    monkeypatch.setattr(RequestJournal, "reserve", reserve_after_racing_poll)
    service.submit("target-test", action)
    assert "target-test" not in service._stable_snapshots


def test_frozen_pilot_query_is_read_only(design_bridge, tmp_path):
    from easydesign.agent.phase34_runtime import Phase34Runtime
    from tests.unit.agent.test_design_runtime import design_card, propose_design

    b = design_bridge
    propose_design(b)
    card = design_card(b)
    b.store.respond(b.thread, card.card_id, "approve", "synthetic-scientist")
    b.apply_decision(card)
    b = Phase34Runtime(b.project, b.thread, b.store)
    before = len(b.store.events(b.thread))
    before_cards = b.store.db.execute("SELECT count(*) FROM cards").fetchone()[0]
    service = service_for(b, tmp_path)
    b.store.thread(b.thread, fingerprint(scripted_config()), "Synthetic plan review")
    before = len(b.store.events(b.thread))
    with service.gateway.session("target-test") as session:
        view = workbench(session, service.catalog)
    assert view.decision["gate"] == 3
    assert view.decision["summary"]["pilot_scope"]["planned_candidates"] == 280
    assert len(b.store.events(b.thread)) == before
    assert b.store.db.execute("SELECT count(*) FROM cards").fetchone()[0] == before_cards
    WorkbenchProjection.model_validate_json(view.model_dump_json())


@pytest.mark.parametrize("action_name", ["approve", "reject"])
def test_interrupted_gate_request_recovers_native_response_exactly_once(
    site_bridge, tmp_path, monkeypatch, action_name
):
    b = site_bridge
    setup_portfolio(b)
    review_card(b)
    prime(b, "Synthetic recovery")
    service = service_for(b, tmp_path)
    view = service.snapshot("target-test")
    chosen = view["decision"]["options"][1]
    action = ActionRequest(
        request_id=str(uuid4()),
        revision=view["revision"],
        action=action_name,
        card_id=view["decision"]["id"],
        selected_option_id=chosen["option_id"],
    )
    service.submit("target-test", action)
    original = NativeGateway.session

    @contextmanager
    def crashing_session(self, *args, **kwargs):
        with original(self, *args, **kwargs) as session:

            def crash(name):
                if name == "after_response_intent":
                    raise SystemExit("Synthetic process death")

            session.bridge.failpoint = crash
            yield session

    monkeypatch.setattr(NativeGateway, "session", crashing_session)
    with pytest.raises(SystemExit):
        service.run(action.request_id)
    assert b.store.response(b.thread, action.card_id) is not None
    assert b.approved_site() is None
    monkeypatch.setattr(NativeGateway, "session", original)
    j = service.journal()
    j.db.execute("UPDATE requests SET updated=0 WHERE id=?", (action.request_id,))
    j.db.commit()
    j.close()
    restarted = service_for(b, tmp_path)
    assert restarted.request(action.request_id)["state"] == "interrupted"
    restarted.retry(action.request_id)
    restarted.run(action.request_id)
    assert restarted.request(action.request_id)["state"] == "succeeded"
    if action_name == "approve":
        assert (
            b.approved_site()["hotspots"]["hotspot_sets"][0]["label_seq_ids"]
            == chosen["design_labels"]
        )
    else:
        assert b.approved_site() is None
    assert len([e for e in b.store.events(b.thread) if e["kind"] == "human-response"]) == 1


def test_gate1_real_http_approval_and_reload(bridge, tmp_path):
    config = scripted_config()
    models = {r: ScriptedModel(role=r) for r in ROLES}
    result = asyncio.run(run_session(bridge, config, models, "Synthetic target approval"))
    assert result["card"]["gate_type"] == "target-structure"
    service = service_for(bridge, tmp_path)
    service.gateway.model_factory = lambda *a, **k: models
    with http_api(service) as client:
        snapshot = client.get("/api/v1/projects/target-test/workbench")
        assert snapshot.status_code == 200, snapshot.text
        value = snapshot.json()
        assert value["decision"]["gate"] == 1
        assert "approve" in value["decision"]["options"][0]["actions"]
        payload = dict(
            request_id=str(uuid4()),
            revision=value["revision"],
            action="approve",
            card_id=value["decision"]["id"],
        )
        response = client.post("/api/v1/projects/target-test/actions", json=payload)
        assert response.status_code == 202, response.text
        service.run(payload["request_id"])
        status = service.request(payload["request_id"])
        assert status["state"] == "succeeded", status
        assert bridge.read_evidence()["request_identity"] is None


def test_native_candidate_product_projection_preserves_fail_and_missing(tmp_path):
    from types import SimpleNamespace

    from easydesign.product.projection import candidate_view
    from tests.unit.agent.test_phase4_native import native_fixture, observations, pool_for

    measured, campaign, _, _ = native_fixture(tmp_path)
    rows = observations(tmp_path, measured, campaign)
    pool = pool_for(campaign, rows)
    session = SimpleNamespace(
        project="synthetic", bridge=SimpleNamespace(run=lambda _: (tmp_path, None))
    )
    catalog = ArtifactCatalog(tmp_path, tmp_path / "catalog")
    values = [candidate_view(session, c, pool, {}, catalog) for c in rows]
    assert len([v for v in values if v.native_status == "pass"]) == 3
    failed = next(v for v in values if v.native_status == "fail")
    assert failed.evaluable and not failed.competition_eligible
    assert failed.independent_prediction == "not-requested"
    assert all(m.value is not None for m in failed.metrics if m.status == "available")
    incomplete = rows[0].model_copy(
        update={
            "validity": "operational-failed",
            "native_evidence": None,
            "competition_eligible": False,
            "failure_reason": "Missing native outputs",
        }
    )
    value = candidate_view(session, incomplete, pool, {}, catalog)
    assert not value.evaluable and not value.competition_eligible
    assert value.native_status == "not-available"
    compact = candidate_view(session, rows[0], pool, {}, catalog, compact=True)
    assert compact.metrics == []
    assert compact.id == values[0].id
    assert compact.scaffold == rows[0].lineage.strategy_id.rsplit("-scaffold-", 1)[1]
    assert compact.sequence_sha256 == values[0].sequence_sha256
    assert compact.artifacts == values[0].artifacts


def test_http_compact_candidate_view_is_explicit(bridge, tmp_path, monkeypatch):
    service = service_for(bridge, tmp_path)
    observed = []

    def candidates(project, offset, limit, candidate=None, *, compact=False, phase=None):
        observed.append((project, offset, limit, candidate, compact, phase))
        return {"items": [], "total": 0, "offset": offset, "limit": limit}

    monkeypatch.setattr(service, "candidates", candidates)
    with http_api(service) as client:
        response = client.get("/api/v1/projects/example/candidates?offset=0&limit=20&view=summary")
        assert response.status_code == 200
        assert observed == [("example", 0, 20, None, True, None)]
        assert client.get("/api/v1/projects/example/candidates?view=unknown").status_code == 400
        assert client.get("/api/v1/projects/example/candidates?phase=design").status_code == 400
        response = client.get(
            "/api/v1/projects/example/candidates?offset=0&limit=20&view=summary&phase=pilot"
        )
        assert response.status_code == 200
        assert observed[-1] == ("example", 0, 20, None, True, "pilot")


def test_compact_candidate_cache_is_project_scoped_and_invalidated(bridge, tmp_path, monkeypatch):
    service = service_for(bridge, tmp_path)
    cached = {"items": [], "total": 0, "offset": 0, "limit": 20}
    service._compact_candidate_pages[("project", 0, 20, None, None)] = cached

    def must_not_open(_project):
        raise AssertionError("A stable compact candidate page must not reopen the project")

    monkeypatch.setattr(service.gateway, "session", must_not_open)
    assert service.candidates("project", 0, 20, compact=True) == cached
    service._invalidate_projection_cache("project")
    assert service._compact_candidate_pages == {}


def test_gate3_decision_is_bound_to_current_pilot_plan(design_bridge, tmp_path):
    from easydesign.agent.phase34_runtime import Phase34Runtime
    from tests.unit.agent.test_phase34_authority import prepared

    original, _, _ = prepared(design_bridge)
    b = Phase34Runtime(original.project, original.thread, original.store, through="handoff")
    config = scripted_config()
    goal = "Synthetic Gate3 rejection; no generation"
    b.store.thread(b.thread, fingerprint(config), goal)
    result = prime(b, goal)
    assert result["card"]["gate_type"] == "design-specification"
    card = DecisionCard.model_validate(result["card"])
    discouraged = decision_view(card.model_copy(update={"judge_status": "DISCOURAGED"}))
    assert "approve" in discouraged["options"][0]["actions"]
    assert "override" not in discouraged["options"][0]["actions"]
    blocked = decision_view(card.model_copy(update={"judge_status": "BLOCKED"}))
    assert "approve" not in blocked["options"][0]["actions"]
    assert "override" not in blocked["options"][0]["actions"]
    service = service_for(b, tmp_path)
    with http_api(service) as client:
        snapshot = client.get("/api/v1/projects/target-test/workbench").json()
        assert snapshot["decision"]["gate"] == 3
        assert "approve" in snapshot["decision"]["options"][0]["actions"]
        assert snapshot["decision"]["summary"]["pilot_scope"]["planned_candidates"] == 280
        req = dict(
            request_id=str(uuid4()),
            revision=snapshot["revision"],
            action="reject",
            card_id=snapshot["decision"]["id"],
        )
        assert client.post("/api/v1/projects/target-test/actions", json=req).status_code == 202
        service.run(req["request_id"])
        assert service.request(req["request_id"])["state"] == "succeeded"
        assert b.pilot_authority() is None
        assert not any(j.step >= 4 for j in b.controller.list(project_id=b.project_id))


def test_review_capacity_keeps_full_evidence_and_bounded_display(tmp_path):
    from easydesign.product.preview import excerpt

    raw = {
        "pilot_scope": {"planned_candidates": 6000},
        "candidate_rankings": [
            {"id": f"candidate-{i}", "rationale": "Synthetic evidence " * 100} for i in range(200)
        ],
    }
    display = excerpt(raw)
    assert len(json.dumps(display)) < 16000
    assert display["pilot_scope"]["planned_candidates"] == 6000
    catalog = ArtifactCatalog(tmp_path, tmp_path / "product/artifacts")
    view = catalog.document("project", "gate-identity", raw, "Full review")
    assert json.loads(catalog.read(view.id)[0]) == raw


def test_questions_at_gate_persist_without_approving_or_resuming(site_bridge, tmp_path):
    from langchain_core.messages import AIMessage

    b = site_bridge
    setup_portfolio(b)
    review_card(b)
    prime(b, "Synthetic conversational review")
    service = service_for(b, tmp_path)
    calls = []

    class Explainer:
        async def ainvoke(self, inputs):
            calls.append(inputs)
            return AIMessage(
                content=(
                    "Site B is an alternative. Its risks remain uncertain; "
                    "your Gate decision is still pending."
                )
            )

    service.gateway.model_factory = lambda *a, **k: {"coordinator": Explainer()}
    before = b.store.events(b.thread)
    with http_api(service) as client:
        base = "/api/v1/projects/target-test"
        view = client.get(base + "/workbench").json()
        assert view["capabilities"]["message"] and view["capabilities"]["decide"]
        question = dict(
            request_id=str(uuid4()),
            revision=view["revision"],
            action="message",
            instruction="Why choose Site B? Do not approve yet.",
            viewed_phase="site",
        )
        first = client.post(base + "/actions", json=question)
        assert first.status_code == 202, first.text
        assert client.post(base + "/actions", json=question).json()["id"] == first.json()["id"]
        running = client.get(base + "/workbench").json()
        assert running["capabilities"]["decide"]  # asking does not lock the Scientist Gate
        assert not running["capabilities"]["message"]
        service.run(question["request_id"])
        result = client.get("/api/v1/requests/" + question["request_id"]).json()
        assert result["state"] == "succeeded", result
        after = client.get(base + "/workbench").json()
        assert after["revision"] == view["revision"]
        assert after["decision"] == view["decision"]
        assert b.store.events(b.thread) == before
        assert len(calls) == 1
        assert "tool" not in json.dumps(calls[0][-1])
        assert after["conversation"][-2]["text"] == question["instruction"]
        assert "Site B" in after["conversation"][-1]["text"]
        restarted = service_for(b, tmp_path)
        assert restarted.snapshot("target-test")["conversation"] == after["conversation"]


def test_failed_question_keeps_draft_and_retry_without_scientific_execution(site_bridge, tmp_path):
    from langchain_core.messages import AIMessage

    b = site_bridge
    setup_portfolio(b)
    review_card(b)
    prime(b, "Synthetic failed answer")
    service = service_for(b, tmp_path)
    before = b.store.events(b.thread)
    view = service.snapshot("target-test")
    request = ActionRequest(
        request_id=str(uuid4()),
        revision=view["revision"],
        action="message",
        instruction="Explain the remaining uncertainties.",
        viewed_phase="site",
    )
    service.submit("target-test", request)
    service.run(request.request_id)  # NoInference raises, rather than silently fabricating a reply.
    assert service.request(request.request_id)["state"] == "failed"
    assert (
        service.snapshot("target-test")["conversation"][-1]["retry_request_id"]
        == request.request_id
    )

    class Explainer:
        async def ainvoke(self, inputs):
            return AIMessage(content="The evidence is incomplete; this is a relative ranking.")

    service.gateway.model_factory = lambda *a, **k: {"coordinator": Explainer()}
    service.retry(request.request_id)
    service.run(request.request_id)
    assert service.request(request.request_id)["state"] == "succeeded"
    assert b.store.events(b.thread) == before
    assert (
        len(
            [
                m
                for m in service.snapshot("target-test")["conversation"]
                if m["kind"] == "user" and m["text"] == request.instruction
            ]
        )
        == 1
    )


def test_conversation_retry_respects_active_lane_and_does_not_lock_gate(tmp_path):
    from easydesign.product.journal import RequestJournal

    journal = RequestJournal(tmp_path / "requests.sqlite")
    try:
        failed = {"request_id": "failed-question", "operation": "conversation"}
        journal.reserve("project", failed)
        journal.update("failed-question", "failed", {"message": "Provider unavailable"})
        journal.reserve("project", {"request_id": "other-question", "operation": "conversation"})
        # Native actions and observational questions have separate concurrency lanes.
        journal.reserve("project", {"request_id": "gate-decision", "operation": "action"})
        with pytest.raises(ProductError, match="active"):
            journal.retry("failed-question")
        journal.update("other-question", "succeeded", {"answer": "Saved explanation"})
        assert journal.retry("failed-question")
        assert not journal.retry("failed-question")
        assert journal.get("gate-decision")["state"] == "accepted"
    finally:
        journal.close()


def test_product_journal_adds_surface_column_to_existing_database(tmp_path):
    import sqlite3

    path = tmp_path / "legacy-requests.sqlite"
    db = sqlite3.connect(path)
    db.execute(
        "CREATE TABLE product_projects ("
        "id TEXT PRIMARY KEY, request_id TEXT UNIQUE NOT NULL, title TEXT NOT NULL, "
        "goal TEXT NOT NULL, thread TEXT NOT NULL, input_id TEXT, state TEXT NOT NULL, "
        "detail TEXT NOT NULL, created REAL NOT NULL, updated REAL NOT NULL)"
    )
    db.commit()
    db.close()

    from easydesign.product.journal import RequestJournal

    journal = RequestJournal(path)
    try:
        columns = {
            str(row["name"]) for row in journal.db.execute("PRAGMA table_info(product_projects)")
        }
        assert "surface" in columns
    finally:
        journal.close()


def test_project_rename_persists_without_changing_scientific_authority(site_bridge, tmp_path):
    b = site_bridge
    setup_portfolio(b)
    review_card(b)
    prime(b, "Synthetic project rename")
    service = service_for(b, tmp_path)
    before = service.snapshot("target-test")
    events = b.store.events(b.thread)
    with http_api(service) as client:
        url = "/api/v1/projects/target-test/title"
        assert client.post(url, json={"title": "   "}).status_code == 400
        assert client.post(url, json={"title": "Case B", "approve": True}).status_code == 400
        for _ in range(2):
            response = client.post(url, json={"title": "  NK2R — Site B  "})
            assert response.status_code == 200, response.text
            assert response.json()["title"] == "NK2R — Site B"
    after = service_for(b, tmp_path).snapshot("target-test")
    assert after["project"]["title"] == "NK2R — Site B"
    assert after["revision"] == before["revision"]
    assert after["decision"] == before["decision"]
    assert b.store.events(b.thread) == events
