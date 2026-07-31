from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from easydesign.core import ConfigurationError
from easydesign.ui.structure_interactions import (
    AssistantProposal,
    AssistantProviderSecret,
    AssistantProviderStore,
    ReferenceStructure,
    SceneVersionConflictError,
    StructureInteractionStore,
    ViewerAction,
    compile_viewer_actions,
    request_assistant_proposal,
    validate_safe_pml,
    validate_scene_pml,
)

_MANAGED_TARGET_LINE = (
    "# @easydesign target object=target sha256=" + "a" * 64 + "\n"
)


def test_safe_pml_accepts_display_commands_and_rejects_mutation() -> None:
    canonical = validate_safe_pml(
        'show cartoon, all\ncolor marine, chain A\n'
        'label (chain A and name CA), "%s%s" % (resn, resi)\n'
        "zoom chain A"
    )
    assert canonical == (
        "show cartoon, all\ncolor marine, chain A\n"
        'label (chain A and name CA), "%s%s" % (resn, resi)\n'
        "zoom chain A\n"
    )

    for command in (
        "remove solvent",
        "delete all",
        "load /tmp/secret.cif",
        "run unsafe.py",
        "python print('unsafe')",
        "set internal_gui, 1",
        'label all, __import__("os").system("id")',
    ):
        with pytest.raises(ConfigurationError):
            validate_safe_pml(command)


def test_viewer_actions_compile_to_allow_listed_pml() -> None:
    actions = (
        ViewerAction(
            action="representation",
            target="chain A",
            value="cartoon",
        ),
        ViewerAction(action="color", target="chain A", value="#3366FF"),
        ViewerAction(action="focus", target="chain A and resi 32+36"),
    )
    result = compile_viewer_actions(actions)
    assert "hide everything, chain A" in result
    assert "show cartoon, chain A" in result
    assert "color #3366FF, chain A" in result
    assert "zoom chain A and resi 32+36" in result


def test_provider_store_masks_key_and_keeps_revisions(tmp_path: Path) -> None:
    store = AssistantProviderStore(tmp_path / "secrets")
    status = store.configure(
        provider="deepseek",
        model="deepseek-chat",
        base_url="https://api.deepseek.example/v1",
        api_key="secret-first",
    )
    assert status.configured is True
    assert status.api_key_masked == "••••irst"
    assert "secret" not in status.model_dump_json()

    store.configure(
        provider="deepseek",
        model="deepseek-chat-v2",
        base_url="https://api.deepseek.example/v1",
        api_key="secret-second",
    )
    assert store.load("deepseek").api_key == "secret-second"
    revisions = tuple(
        (tmp_path / "secrets" / "deepseek" / "provider.json.revisions").glob(
            "revision-*.json"
        )
    )
    assert len(revisions) == 1


def test_platform_assistant_config_is_owner_managed_and_public_status_is_generic(
    tmp_path: Path,
) -> None:
    store = AssistantProviderStore(tmp_path / "secrets")
    store.platform_path.write_text(
        "\n".join(
            (
                'schema_version: "0.1"',
                "provider: deepseek",
                "model: deepseek-chat",
                "base_url: https://api.deepseek.com",
                "api_key: owner-secret",
                "",
            )
        ),
        encoding="utf-8",
    )
    store.platform_path.chmod(0o600)

    secret = store.load_platform()
    assert secret.provider == "deepseek"
    assert secret.model == "deepseek-chat"
    assert secret.api_key == "owner-secret"

    status = store.platform_status()
    assert status.available is True
    assert status.service_name == "EasyDesign 结构助手"
    public_payload = status.model_dump_json()
    assert "deepseek" not in public_payload
    assert "owner-secret" not in public_payload
    assert "api.deepseek.com" not in public_payload


def test_platform_assistant_rejects_missing_or_overbroad_secret(
    tmp_path: Path,
) -> None:
    store = AssistantProviderStore(tmp_path / "secrets")
    assert store.platform_status().available is False

    store.platform_path.write_text(
        "\n".join(
            (
                'schema_version: "0.1"',
                "provider: zhipu-glm",
                "model: glm-4-plus",
                "base_url: https://open.bigmodel.cn/api/paas/v4",
                "api_key: owner-secret",
                "",
            )
        ),
        encoding="utf-8",
    )
    store.platform_path.chmod(0o644)
    if store.platform_path.stat().st_mode & 0o077:
        with pytest.raises(ConfigurationError, match="权限过宽"):
            store.load_platform()
        assert store.platform_status().available is False


def test_structure_session_publishes_revision_only_snapshots(
    tmp_path: Path,
) -> None:
    store = StructureInteractionStore(tmp_path / "projects")
    session = store.create(
        project_id="demo",
        run_key="demo/run-001",
        stage_number=2,
        target_structure_sha256="a" * 64,
        residue_mapping_sha256="b" * 64,
        current_regions={"A": (3, 1), "B": (4,)},
        created_at=datetime(2026, 7, 29, tzinfo=UTC),
    )
    assert session.current_regions == {"A": (1, 3), "B": (4,)}

    updated = store.append_pml(
        session.session_id,
        pml="show surface, all",
        source="expert-console",
        updated_at=datetime(2026, 7, 29, 1, tzinfo=UTC),
    )
    assert len(updated.pml_revisions) == 1
    assert store.load(session.session_id).pml_revisions[0].revision == 1
    revision_root = (
        tmp_path
        / "projects"
        / "demo"
        / "interactive-sessions"
        / session.session_id
        / "session.json.revisions"
    )
    assert len(tuple(revision_root.glob("revision-*.json"))) == 1


def test_viewer_pml_append_extends_active_scene_without_managed_line_conflict(
    tmp_path: Path,
) -> None:
    store = StructureInteractionStore(tmp_path / "projects")
    session = store.create(
        project_id="demo",
        run_key="demo/run-001",
        stage_number=2,
        target_structure_sha256="a" * 64,
        residue_mapping_sha256="b" * 64,
        created_at=datetime(2026, 7, 29, tzinfo=UTC),
    )
    initial_pml = (
        f"# @easydesign target object=target sha256={'a' * 64}\n"
        "hide everything, all\n"
        "show cartoon, target\n"
    )
    store.save_scene_version(
        session.session_id,
        pml=initial_pml,
        actor="system",
        source="initial-scene",
        summary="初始场景",
        updated_at=datetime(2026, 7, 29, 1, tzinfo=UTC),
    )

    updated = store.append_pml(
        session.session_id,
        pml="center target\nzoom target, 5\n",
        source="viewer",
        updated_at=datetime(2026, 7, 29, 2, tzinfo=UTC),
    )

    active = next(
        item
        for item in updated.scene_versions
        if item.version_id == updated.active_scene_version_id
    )
    assert len(updated.scene_versions) == 2
    assert "# @chatpymol native-pymol source=viewer" in active.pml
    assert "# @easydesign native-pymol" not in active.pml



def test_structure_session_reuses_only_matching_latest_snapshot(
    tmp_path: Path,
) -> None:
    store = StructureInteractionStore(tmp_path / "projects")
    first = store.create(
        project_id="demo",
        run_key="demo/run-001",
        stage_number=1,
        target_structure_sha256="a" * 64,
        residue_mapping_sha256="b" * 64,
        created_at=datetime(2026, 7, 29, tzinfo=UTC),
    )
    store.create(
        project_id="demo",
        run_key="demo/run-002",
        stage_number=1,
        target_structure_sha256="c" * 64,
        residue_mapping_sha256="d" * 64,
        created_at=datetime(2026, 7, 29, 1, tzinfo=UTC),
    )

    matched = store.latest_for(
        project_id="demo",
        run_key="demo/run-001",
        stage_number=1,
        target_structure_sha256="a" * 64,
        residue_mapping_sha256="b" * 64,
    )
    assert matched is not None
    assert matched.session_id == first.session_id
    assert (
        store.latest_for(
            project_id="demo",
            run_key="demo/run-001",
            stage_number=2,
            target_structure_sha256="a" * 64,
            residue_mapping_sha256="b" * 64,
        )
        is None
    )


def test_get_or_create_is_idempotent_and_view_state_is_viewer_neutral(
    tmp_path: Path,
) -> None:
    store = StructureInteractionStore(tmp_path / "projects")
    first = store.get_or_create(
        project_id="demo",
        run_key="demo/run-001",
        stage_number=1,
        target_structure_sha256="a" * 64,
        residue_mapping_sha256="b" * 64,
    )
    second = store.get_or_create(
        project_id="demo",
        run_key="demo/run-001",
        stage_number=1,
        target_structure_sha256="a" * 64,
        residue_mapping_sha256="b" * 64,
    )
    assert first.session_id == second.session_id

    proposal = AssistantProposal(
        kind="viewer-actions",
        explanation="以表面显示并居中。",
        viewer_actions=(
            ViewerAction(action="representation", target="all", value="surface"),
            ViewerAction(action="center", target="all"),
        ),
    )
    exchanged = store.append_exchange(
        first.session_id,
        user_text="显示表面",
        proposal=proposal,
        provider="deepseek",
        model="fixture-model",
        request_id="request-001",
    )
    updated = store.apply_proposal(
        first.session_id,
        proposal_id=exchanged.messages[-1].proposal.proposal_id,
        viewer_actions=proposal.viewer_actions,
    )

    assert updated.schema_version == "0.3"
    assert updated.pml_revisions == ()
    assert updated.view_state_revisions[0].actions == proposal.viewer_actions


def test_assistant_request_uses_minimal_context_and_validates_json() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        captured.update(payload)
        proposal = AssistantProposal(
            kind="region-edit",
            explanation="把明确给出的两个 label 编号加入 A 区。",
            region_operations=(
                {
                    "operation": "add",
                    "region_id": "A",
                    "numbering": "label",
                    "residues": ["32", "36"],
                },
            ),
        )
        return httpx.Response(
            200,
            headers={"x-request-id": "request-001"},
            json={
                "choices": [
                    {"message": {"content": proposal.model_dump_json()}}
                ]
            },
        )

    secret = AssistantProviderSecret(
        provider="deepseek",
        model="deepseek-chat",
        base_url="https://api.deepseek.example/v1",
        api_key="secret",
        configured_at=datetime(2026, 7, 29, tzinfo=UTC),
    )
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        proposal, request_id = request_assistant_proposal(
            secret=secret,
            user_text="把32、36加入A区",
            context={
                "stage_number": 2,
                "object_id": "target",
                "label_chain_id": "A",
                "current_region_counts": {"A": 0, "B": 0, "C": 0},
                "allowed_analysis_methods": ["sasa", "scannet"],
            },
            client=client,
        )
    assert proposal.kind == "region-edit"
    assert request_id == "request-001"
    request_text = json.dumps(captured, ensure_ascii=False)
    assert "target.cif" not in request_text
    assert "coordinates" not in request_text
    assert "msa" not in request_text.lower()


def test_assistant_http_error_is_not_silently_fallback() -> None:
    secret = AssistantProviderSecret(
        provider="zhipu-glm",
        model="glm-example",
        base_url="https://glm.example/v4",
        api_key="secret",
        configured_at=datetime(2026, 7, 29, tzinfo=UTC),
    )
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(429, json={"error": "limited"})
        )
    ) as client:
        with pytest.raises(ConfigurationError, match="HTTP 429"):
            request_assistant_proposal(
                secret=secret,
                user_text="请解释当前结构",
                context={"stage_number": 1},
                client=client,
            )


@pytest.mark.parametrize(
    "response",
    (
        httpx.Response(200, json={"choices": []}),
        httpx.Response(
            200,
            json={"choices": [{"message": {"content": "{not-json"}}]},
        ),
        httpx.Response(500, json={"error": "upstream failure"}),
    ),
)
def test_assistant_unrecoverable_invalid_responses_fail_after_retry(
    response: httpx.Response,
) -> None:
    secret = AssistantProviderSecret(
        provider="deepseek",
        model="deepseek-chat",
        base_url="https://api.deepseek.example/v1",
        api_key="secret",
        configured_at=datetime(2026, 7, 29, tzinfo=UTC),
    )

    def handler(_request: httpx.Request) -> httpx.Response:
        return response

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ConfigurationError):
            request_assistant_proposal(
                secret=secret,
                user_text="请解释当前结构",
                context={"stage_number": 1},
                client=client,
            )


def test_assistant_retries_once_and_repairs_common_json_shape() -> None:
    calls: list[dict[str, object]] = []
    malformed_payload = {
        "kind": "viewer-actions",
        "explanation": "把背景改成白色。",
        "viewer_actions": {
            "action": "background",
            "target": "all",
            "value": "white",
        },
    }

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(json.loads(request.content))
        return httpx.Response(
            200,
            headers={"x-request-id": f"request-{len(calls):03d}"},
            json={
                "choices": [
                    {"message": {"content": json.dumps(malformed_payload)}}
                ]
            },
        )

    secret = AssistantProviderSecret(
        provider="deepseek",
        model="deepseek-chat",
        base_url="https://api.deepseek.example/v1",
        api_key="secret",
        configured_at=datetime(2026, 7, 29, tzinfo=UTC),
    )
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        proposal, request_id = request_assistant_proposal(
            secret=secret,
            user_text="把背景改成白色",
            context={"stage_number": 1},
            client=client,
        )

    assert len(calls) == 2
    assert "repair_instruction" in json.dumps(calls[1], ensure_ascii=False)
    assert request_id == "request-002"
    assert proposal.kind == "viewer-actions"
    assert proposal.viewer_actions[0].action == "background"


def test_assistant_retries_semantically_invalid_viewer_action() -> None:
    calls: list[dict[str, object]] = []
    responses = [
        {
            "kind": "viewer-actions",
            "explanation": "把背景改成白色。",
            "viewer_actions": [
                {"action": "background", "target": "all", "value": None}
            ],
        },
        {
            "kind": "viewer-actions",
            "explanation": "把背景改成白色。",
            "viewer_actions": [
                {"background": "white", "target": "all"}
            ],
        },
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(json.loads(request.content))
        payload = responses[min(len(calls) - 1, len(responses) - 1)]
        return httpx.Response(
            200,
            headers={"x-request-id": f"request-{len(calls):03d}"},
            json={
                "choices": [
                    {"message": {"content": json.dumps(payload)}}
                ]
            },
        )

    secret = AssistantProviderSecret(
        provider="deepseek",
        model="deepseek-chat",
        base_url="https://api.deepseek.example/v1",
        api_key="secret",
        configured_at=datetime(2026, 7, 29, tzinfo=UTC),
    )
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        proposal, request_id = request_assistant_proposal(
            secret=secret,
            user_text="把背景改成白色",
            context={"stage_number": 1},
            client=client,
        )

    assert len(calls) == 2
    assert request_id == "request-002"
    assert proposal.viewer_actions[0].value == "white"



def test_assistant_repairs_common_viewer_action_aliases() -> None:
    calls: list[dict[str, object]] = []
    response_payload = {
        "kind": "viewer-actions",
        "explanation": "把结构显示为表面。",
        "viewer_actions": [
            {"action": "set_representation", "target": "all", "value": "surface"}
        ],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(json.loads(request.content))
        return httpx.Response(
            200,
            headers={"x-request-id": f"request-{len(calls):03d}"},
            json={
                "choices": [
                    {"message": {"content": json.dumps(response_payload)}}
                ]
            },
        )

    secret = AssistantProviderSecret(
        provider="deepseek",
        model="deepseek-chat",
        base_url="https://api.deepseek.example/v1",
        api_key="secret",
        configured_at=datetime(2026, 7, 29, tzinfo=UTC),
    )
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        proposal, request_id = request_assistant_proposal(
            secret=secret,
            user_text="把结构显示为表面",
            context={"stage_number": 1},
            client=client,
        )

    assert len(calls) == 2
    assert request_id == "request-002"
    assert proposal.viewer_actions[0].action == "representation"
    assert proposal.viewer_actions[0].value == "surface"



def test_assistant_timeout_fails_without_fallback() -> None:
    secret = AssistantProviderSecret(
        provider="zhipu-glm",
        model="glm-example",
        base_url="https://glm.example/v4",
        api_key="secret",
        configured_at=datetime(2026, 7, 29, tzinfo=UTC),
    )

    def timeout_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout", request=request)

    with httpx.Client(transport=httpx.MockTransport(timeout_handler)) as client:
        with pytest.raises(ConfigurationError, match="响应无法验证"):
            request_assistant_proposal(
                secret=secret,
                user_text="请解释当前结构",
                context={"stage_number": 1},
                client=client,
            )


def test_chatpymol_style_top_level_pml_response_creates_pml_edit_after_repair() -> None:
    calls: list[dict[str, object]] = []
    previous_pml = _MANAGED_TARGET_LINE + (
        "hide everything, all\n"
        "show cartoon, target\n"
        "color gray70, target\n"
        "orient target\n"
    )
    response_payload = {
        "assistantMessage": "已把整个结构切换为 sticks 并居中。",
        "summary": "显示为 sticks 并居中",
        "conversationTitle": "Sticks view",
        "pml": _MANAGED_TARGET_LINE
        + (
            "hide everything, all\n"
            "show sticks, target\n"
            "color gray70, target\n"
            "center target\n"
            "orient target\n"
        ),
    }

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(json.loads(request.content))
        return httpx.Response(
            200,
            headers={"x-request-id": f"request-{len(calls):03d}"},
            json={"choices": [{"message": {"content": json.dumps(response_payload)}}]},
        )

    secret = AssistantProviderSecret(
        provider="deepseek",
        model="deepseek-chat",
        base_url="https://api.deepseek.example/v1",
        api_key="secret",
        configured_at=datetime(2026, 7, 29, tzinfo=UTC),
    )
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        proposal, request_id = request_assistant_proposal(
            secret=secret,
            user_text="把整个结构显示为 sticks 并居中",
            context={"stage_number": 2, "currentPml": previous_pml},
            previous_pml=previous_pml,
            known_object_names=("target",),
            known_chain_ids=("A",),
            client=client,
        )

    assert len(calls) == 2
    assert request_id == "request-002"
    assert proposal.kind == "pml-edit"
    assert proposal.pml_edit is not None
    assert "show sticks, target" in proposal.pml_edit.pml


def test_scene_pml_validator_protects_managed_lines_and_blocks_unsafe_commands() -> None:
    previous_pml = _MANAGED_TARGET_LINE + (
        "hide everything, all\n"
        "show cartoon, target\n"
    )
    valid = validate_scene_pml(
        previous_pml + "center target\n",
        previous_pml=previous_pml,
        known_object_names=("target",),
        known_chain_ids=("A",),
    )
    assert valid.endswith("center target\n")

    with pytest.raises(ConfigurationError, match="受保护"):
        validate_scene_pml(
            "hide everything, all\nshow cartoon, target\n",
            previous_pml=previous_pml,
            known_object_names=("target",),
            known_chain_ids=("A",),
        )

    with pytest.raises(ConfigurationError, match="安全列表"):
        validate_scene_pml(
            previous_pml + "fetch 1ubq\n",
            previous_pml=previous_pml,
            known_object_names=("target",),
            known_chain_ids=("A",),
        )

    with pytest.raises(ConfigurationError, match="不存在的对象"):
        validate_scene_pml(
            previous_pml + "align reference_1ubq, target\n",
            previous_pml=previous_pml,
            known_object_names=("target",),
            known_chain_ids=("A",),
        )


def test_scene_versions_restore_as_new_version_instead_of_overwriting(tmp_path: Path) -> None:
    store = StructureInteractionStore(tmp_path / "projects")
    session = store.create(
        project_id="demo",
        run_key="demo/run-001",
        stage_number=2,
        target_structure_sha256="a" * 64,
        residue_mapping_sha256="b" * 64,
        created_at=datetime(2026, 7, 29, tzinfo=UTC),
    )
    target = ReferenceStructure(
        object_id="target",
        role="target",
        object_name="target",
        filename="target.cif",
        file_format="cif",
        sha256="a" * 64,
        source="stage1-target-bundle",
        created_at=datetime(2026, 7, 29, tzinfo=UTC),
    )
    initial = store.ensure_scene(
        session.session_id,
        pml=_MANAGED_TARGET_LINE
        + (
            "hide everything, all\n"
            "show cartoon, target\n"
            "color gray70, target\n"
            "orient target\n"
        ),
        target_object=target,
        updated_at=datetime(2026, 7, 29, tzinfo=UTC),
    )
    updated, second = store.save_scene_version(
        session.session_id,
        pml=_MANAGED_TARGET_LINE
        + (
            "hide everything, all\n"
            "show sticks, target\n"
            "color gray70, target\n"
            "center target\n"
            "orient target\n"
        ),
        actor="ai",
        source="assistant-message",
        summary="显示为 sticks",
        base_version_id=initial.active_scene_version_id,
        known_object_names=("target",),
        known_chain_ids=("A",),
        updated_at=datetime(2026, 7, 29, 1, tzinfo=UTC),
    )
    restored, third = store.restore_scene_version(
        session.session_id,
        version_id=initial.active_scene_version_id or "",
        base_version_id=updated.active_scene_version_id,
        updated_at=datetime(2026, 7, 29, 2, tzinfo=UTC),
    )

    assert second.revision == 2
    assert third.revision == 3
    assert restored.active_scene_version_id == third.version_id
    assert third.parent_version_id == initial.active_scene_version_id
    assert restored.scene_versions[0].pml == restored.scene_versions[-1].pml


def test_region_operation_supports_clear_without_residues() -> None:
    proposal = AssistantProposal(
        kind="region-edit",
        explanation="清空 C 区，A 和 B 保持不变。",
        region_operations=(
            {
                "operation": "clear",
                "region_id": "C",
                "numbering": "label",
                "residues": [],
            },
        ),
    )
    assert proposal.region_operations[0].operation == "clear"
    assert proposal.region_operations[0].residues == ()

    with pytest.raises(ValueError):
        AssistantProposal(
            kind="region-edit",
            explanation="错误的 clear。",
            region_operations=(
                {
                    "operation": "clear",
                    "region_id": "C",
                    "numbering": "label",
                    "residues": ["75"],
                },
            ),
        )


def test_scene_version_can_add_server_managed_reference_line_only_when_allowed(
    tmp_path: Path,
) -> None:
    store = StructureInteractionStore(tmp_path / "projects")
    session = store.create(
        project_id="demo",
        run_key="demo/run-001",
        stage_number=2,
        target_structure_sha256="a" * 64,
        residue_mapping_sha256="b" * 64,
        created_at=datetime(2026, 7, 29, tzinfo=UTC),
    )
    target = ReferenceStructure(
        object_id="target",
        role="target",
        object_name="target",
        filename="target.cif",
        file_format="cif",
        sha256="a" * 64,
        source="stage1-target-bundle",
        created_at=datetime(2026, 7, 29, tzinfo=UTC),
    )
    initialized = store.ensure_scene(
        session.session_id,
        pml=_MANAGED_TARGET_LINE
        + (
            "hide everything, all\n"
            "show cartoon, target\n"
            "color gray70, target\n"
            "orient target\n"
        ),
        target_object=target,
        updated_at=datetime(2026, 7, 29, tzinfo=UTC),
    )
    reference = ReferenceStructure(
        object_id="reference-000001",
        role="reference",
        object_name="ref_1ubq",
        filename="1UBQ.cif",
        file_format="mmcif",
        sha256="c" * 64,
        source="rcsb:1UBQ",
        created_at=datetime(2026, 7, 29, 1, tzinfo=UTC),
    )
    managed = (
        "# @easydesign reference object=ref_1ubq "
        "object_id=reference-000001 sha256=" + "c" * 64
    )
    next_pml = (
        initialized.scene_versions[-1].pml
        + managed
        + "\nshow cartoon, ref_1ubq\ncolor marine, ref_1ubq\n"
    )

    with pytest.raises(ConfigurationError, match="伪造"):
        store.save_scene_version(
            session.session_id,
            pml=next_pml,
            actor="ai",
            source="assistant-message",
            summary="模型试图新增 reference 管理行",
            base_version_id=initialized.active_scene_version_id,
            known_object_names=("target", "ref_1ubq"),
        )

    updated, version = store.save_scene_version(
        session.session_id,
        pml=next_pml,
        actor="system",
        source="reference-rcsb",
        summary="添加参考结构 ref_1ubq",
        base_version_id=initialized.active_scene_version_id,
        known_object_names=("target", "ref_1ubq"),
        allowed_new_managed_lines=(managed,),
        reference_structures=initialized.reference_structures + (reference,),
    )
    assert version.revision == 2
    assert updated.reference_structures[-1].object_name == "ref_1ubq"
    assert managed in updated.scene_versions[-1].pml




def test_scene_version_stale_base_raises_conflict(tmp_path: Path) -> None:
    store = StructureInteractionStore(tmp_path / "projects")
    session = store.create(
        project_id="demo",
        run_key="demo/run-001",
        stage_number=2,
        target_structure_sha256="a" * 64,
        residue_mapping_sha256="b" * 64,
        created_at=datetime(2026, 7, 29, tzinfo=UTC),
    )
    target = ReferenceStructure(
        object_id="target",
        role="target",
        object_name="target",
        filename="target.cif",
        file_format="cif",
        sha256="a" * 64,
        source="stage1-target-bundle",
        created_at=datetime(2026, 7, 29, tzinfo=UTC),
    )
    initialized = store.ensure_scene(
        session.session_id,
        pml=_MANAGED_TARGET_LINE
        + (
            "hide everything, all\n"
            "show cartoon, target\n"
            "orient target\n"
        ),
        target_object=target,
    )
    updated, _ = store.save_scene_version(
        session.session_id,
        pml=initialized.scene_versions[-1].pml + "center target\n",
        actor="human",
        source="pml-editor",
        summary="center target",
        base_version_id=initialized.active_scene_version_id,
        known_object_names=("target",),
    )
    with pytest.raises(SceneVersionConflictError):
        store.save_scene_version(
            session.session_id,
            pml=updated.scene_versions[-1].pml + "zoom target\n",
            actor="human",
            source="pml-editor",
            summary="stale edit",
            base_version_id=initialized.active_scene_version_id,
            known_object_names=("target",),
        )
