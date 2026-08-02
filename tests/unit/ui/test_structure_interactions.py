from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from easydesign.core import ConfigurationError
from easydesign.ui.pml_skills import select_pml_skills
from easydesign.ui.structure_interactions import (
    AssistantProposal,
    AssistantProviderSecret,
    AssistantProviderStore,
    ChatPyMolEdit,
    InteractionMessage,
    ReferenceStructure,
    SceneVersionConflictError,
    StructureInteractionStore,
    ViewerAction,
    _assistant_http_timeout,
    compile_viewer_actions,
    request_assistant_pml_edit,
    validate_safe_pml,
    validate_scene_pml,
)

_MANAGED_TARGET_LINE = "# @easydesign target object=target sha256=" + "a" * 64 + "\n"


def test_assistant_http_timeout_contract_is_sixty_seconds() -> None:
    timeout = _assistant_http_timeout()

    assert timeout.connect == 10.0
    assert timeout.read == 60.0


def test_safe_pml_accepts_display_commands_and_rejects_mutation() -> None:
    canonical = validate_safe_pml(
        "show cartoon, all\ncolor marine, chain A\n"
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
        (tmp_path / "secrets" / "deepseek" / "provider.json.revisions").glob("revision-*.json")
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


def test_viewer_transient_or_duplicate_commands_do_not_create_scene_versions(
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
    initialized, _ = store.save_scene_version(
        session.session_id,
        pml=_MANAGED_TARGET_LINE + "show cartoon, target\ndeselect\n",
        actor="system",
        source="initial-scene",
        summary="初始场景",
    )

    deselected = store.append_pml(
        session.session_id,
        pml="deselect\n",
        source="viewer",
    )
    duplicated = store.append_pml(
        session.session_id,
        pml="show cartoon, target\n",
        source="viewer",
    )

    assert deselected.active_scene_version_id == initialized.active_scene_version_id
    assert duplicated.active_scene_version_id == initialized.active_scene_version_id
    assert len(duplicated.scene_versions) == 1
    assert duplicated.pml_revisions == ()


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

    assert updated.schema_version == "0.4"
    assert updated.pml_revisions == ()
    assert updated.view_state_revisions[0].actions == proposal.viewer_actions


def _assistant_secret(
    *,
    provider: str = "deepseek",
    model: str = "deepseek-chat",
    base_url: str = "https://api.deepseek.example/v1",
) -> AssistantProviderSecret:
    return AssistantProviderSecret(
        provider=provider,
        model=model,
        base_url=base_url,
        api_key="secret",
        configured_at=datetime(2026, 7, 29, tzinfo=UTC),
    )


def _chatpymol_response(
    pml: str,
    *,
    assistant_message: str = "已更新结构显示。",
    summary: str = "更新结构显示",
    title: str = "结构显示",
) -> dict[str, object]:
    return {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "assistantMessage": assistant_message,
                            "summary": summary,
                            "conversationTitle": title,
                            "pml": pml,
                        },
                        ensure_ascii=False,
                    )
                }
            }
        ]
    }


def _message(index: int) -> InteractionMessage:
    return InteractionMessage(
        message_id=f"message-{index:02d}",
        role="user" if index % 2 == 0 else "assistant",
        content=f"历史消息 {index}",
        created_at=datetime(2026, 7, 29, index % 24, tzinfo=UTC),
    )


def test_chatpymol_request_contains_complete_context_history_and_skills() -> None:
    captured: dict[str, object] = {}
    previous_pml = _MANAGED_TARGET_LINE + (
        "hide everything, all\nshow cartoon, target\ncolor gray70, target\norient target\n"
    )
    next_pml = previous_pml + (
        "select ligand_nearby, target within 5 of resn LIG\n"
        "show sticks, ligand_nearby\n"
        "bg_color white\n"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        captured.update(payload)
        return httpx.Response(
            200,
            headers={"x-request-id": "request-001"},
            json=_chatpymol_response(next_pml),
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        edit, request_id, skill_ids = request_assistant_pml_edit(
            secret=_assistant_secret(),
            user_text="分析配体口袋并生成适合论文的白底图",
            context={
                "stage_number": 2,
                "currentPml": previous_pml,
                "scene": {"objects": [{"name": "target"}]},
                "structures": [
                    {
                        "objectName": "target",
                        "format": "cif",
                        "sha256": "a" * 64,
                        "chains": ["A"],
                    }
                ],
                "currentRegionCounts": {"A": 0, "B": 0, "C": 0},
            },
            history=tuple(_message(index) for index in range(12)),
            previous_pml=previous_pml,
            known_object_names=("target",),
            known_chain_ids=("A",),
            client=client,
        )
    assert isinstance(edit, ChatPyMolEdit)
    assert edit.pml == next_pml
    assert request_id == "request-001"
    assert skill_ids == ("safe-pml", "ligand-pocket", "publication-figure")

    messages = captured["messages"]
    assert isinstance(messages, list)
    assert len(messages) == 12
    assert messages[1]["content"] == "历史消息 2"
    assert messages[10]["content"] == "历史消息 11"
    assert "当前完整 PML" in messages[0]["content"]
    assert "一个或多个区域" in messages[0]["content"]
    assert "explicit_region_edit_intent" not in messages[0]["content"]
    assert "### 技能：安全 PML（safe-pml）" in messages[0]["content"]
    assert "### 技能：配体与口袋（ligand-pocket）" in messages[0]["content"]
    assert "### 技能：视觉设计与论文构图（publication-figure）" in messages[0]["content"]
    context_text = messages[-1]["content"].split("当前工作区：\n", 1)[1]
    context_payload = json.loads(context_text.split("\n\n用户要求：", 1)[0])
    assert context_payload["currentPml"] == previous_pml

    request_text = json.dumps(captured, ensure_ascii=False)
    assert "coordinates" not in request_text
    assert "msa" not in request_text.lower()
    assert "/root/" not in request_text
    assert "secret" not in request_text


def test_chatpymol_semantic_validator_gets_one_repair_attempt() -> None:
    previous_pml = _MANAGED_TARGET_LINE + "show cartoon, target\n"
    invalid_pml = previous_pml + "select ed_region_A, chain A and resi 32\n"
    repaired_pml = previous_pml + "select ed_region_A, chain A and resi 54\n"
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            200,
            json=_chatpymol_response(invalid_pml if calls == 1 else repaired_pml),
        )

    def validate(edit: ChatPyMolEdit) -> ChatPyMolEdit:
        if "resi 54" not in edit.pml:
            raise ConfigurationError("必须使用已经映射的 author selector")
        return edit

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        edit, _, _ = request_assistant_pml_edit(
            secret=_assistant_secret(),
            user_text="将规范编号32加入A区",
            context={
                "numbering": {
                    "rows": [{"label_seq_id": 32, "auth_residue_id": "54"}]
                }
            },
            history=(),
            previous_pml=previous_pml,
            known_object_names=("target",),
            known_chain_ids=("A",),
            edit_validator=validate,
            client=client,
        )

    assert calls == 2
    assert "resi 54" in edit.pml


def test_chatpymol_final_semantic_failure_reports_specific_reason() -> None:
    previous_pml = _MANAGED_TARGET_LINE + "show cartoon, target\n"
    invalid_pml = previous_pml + "select ed_region_A, chain A and resi 999\n"
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=_chatpymol_response(invalid_pml))

    def validate(_edit: ChatPyMolEdit) -> ChatPyMolEdit:
        raise ConfigurationError(
            "ed_region_A 残基 A:999 不能唯一映射到 Target Bundle"
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ConfigurationError) as captured:
            request_assistant_pml_edit(
                secret=_assistant_secret(),
                user_text="把不存在的残基加入 A 区",
                context={"stage_number": 2, "currentPml": previous_pml},
                history=(),
                previous_pml=previous_pml,
                known_object_names=("target",),
                known_chain_ids=("A",),
                edit_validator=validate,
                client=client,
            )

    assert calls == 2
    assert "原场景未被修改" in str(captured.value)
    assert "具体原因：ed_region_A 残基 A:999 不能唯一映射" in str(captured.value)


def test_chatpymol_skill_router_keeps_safe_skill_and_at_most_two_matches() -> None:
    skills = select_pml_skills("请给链上色、分析界面、查看配体口袋、做论文图并结构比对")
    assert tuple(skill.skill_id for skill in skills) == (
        "safe-pml",
        "ligand-pocket",
        "publication-figure",
    )


def test_assistant_http_error_is_not_silently_fallback() -> None:
    previous_pml = _MANAGED_TARGET_LINE + "show cartoon, target\n"
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(429, json={"error": "limited"})
        )
    ) as client:
        with pytest.raises(ConfigurationError, match="HTTP 429"):
            request_assistant_pml_edit(
                secret=_assistant_secret(
                    provider="zhipu-glm",
                    model="glm-example",
                    base_url="https://glm.example/v4",
                ),
                user_text="请解释当前结构",
                context={"stage_number": 1, "currentPml": previous_pml},
                history=(),
                previous_pml=previous_pml,
                known_object_names=("target",),
                known_chain_ids=("A",),
                client=client,
            )


@pytest.mark.parametrize(
    "response_payload",
    (
        {"choices": []},
        {"choices": [{"message": {"content": "{not-json"}}]},
        _chatpymol_response(
            _MANAGED_TARGET_LINE + "show cartoon, target\n",
            assistant_message="",
        ),
        {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "assistantMessage": "完成",
                                "summary": "完成",
                                "conversationTitle": "完成",
                                "pml": _MANAGED_TARGET_LINE + "show cartoon, target\n",
                                "unexpected": True,
                            }
                        )
                    }
                }
            ]
        },
    ),
)
def test_assistant_unrecoverable_invalid_responses_fail_after_retry(
    response_payload: dict[str, object],
) -> None:
    previous_pml = _MANAGED_TARGET_LINE + "show cartoon, target\n"

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=response_payload)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ConfigurationError):
            request_assistant_pml_edit(
                secret=_assistant_secret(),
                user_text="请解释当前结构",
                context={"stage_number": 1, "currentPml": previous_pml},
                history=(),
                previous_pml=previous_pml,
                known_object_names=("target",),
                known_chain_ids=("A",),
                client=client,
            )


def test_assistant_retries_once_then_accepts_repaired_complete_pml() -> None:
    calls: list[dict[str, object]] = []
    previous_pml = _MANAGED_TARGET_LINE + "show cartoon, target\n"
    repaired_pml = previous_pml + "bg_color white\n"

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(json.loads(request.content))
        if len(calls) == 1:
            return httpx.Response(
                200,
                headers={"x-request-id": "request-001"},
                json={"choices": [{"message": {"content": "{not-json"}}]},
            )
        return httpx.Response(
            200,
            headers={"x-request-id": f"request-{len(calls):03d}"},
            json=_chatpymol_response(repaired_pml),
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        edit, request_id, _ = request_assistant_pml_edit(
            secret=_assistant_secret(),
            user_text="把背景改成白色",
            context={"stage_number": 1, "currentPml": previous_pml},
            history=(),
            previous_pml=previous_pml,
            known_object_names=("target",),
            known_chain_ids=("A",),
            client=client,
        )

    assert len(calls) == 2
    assert "上一次响应未通过" in json.dumps(calls[1], ensure_ascii=False)
    assert request_id == "request-002"
    assert edit.pml == repaired_pml


def test_assistant_retries_semantically_unsafe_pml_then_fails_closed() -> None:
    calls: list[dict[str, object]] = []
    previous_pml = _MANAGED_TARGET_LINE + "show cartoon, target\n"
    unsafe_pml = previous_pml + "fetch 1ubq\n"

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(json.loads(request.content))
        return httpx.Response(
            200,
            headers={"x-request-id": f"request-{len(calls):03d}"},
            json=_chatpymol_response(unsafe_pml),
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ConfigurationError) as captured:
            request_assistant_pml_edit(
                secret=_assistant_secret(),
                user_text="获取 1ubq",
                context={"stage_number": 1, "currentPml": previous_pml},
                history=(),
                previous_pml=previous_pml,
                known_object_names=("target",),
                known_chain_ids=("A",),
                client=client,
            )

    assert len(calls) == 2
    assert "原场景未被修改" in str(captured.value)
    assert "具体原因：PML 命令触及系统、文件或网络边界: fetch" in str(
        captured.value
    )


def test_assistant_read_timeout_reports_real_error_type_and_limit() -> None:
    previous_pml = _MANAGED_TARGET_LINE + "show cartoon, target\n"

    def timeout_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout", request=request)

    with httpx.Client(transport=httpx.MockTransport(timeout_handler)) as client:
        with pytest.raises(ConfigurationError) as captured:
            request_assistant_pml_edit(
                secret=_assistant_secret(
                    provider="zhipu-glm",
                    model="glm-example",
                    base_url="https://glm.example/v4",
                ),
                user_text="请解释当前结构",
                context={"stage_number": 1, "currentPml": previous_pml},
                history=(),
                previous_pml=previous_pml,
                known_object_names=("target",),
                known_chain_ids=("A",),
                client=client,
            )

    message = str(captured.value)
    assert "ReadTimeout" in message
    assert "60 秒" in message
    assert "当前场景未修改" in message
    assert "响应无法验证" not in message


@pytest.mark.parametrize(
    ("raised", "expected"),
    (
        (httpx.ConnectTimeout("connect timeout"), "ConnectTimeout"),
        (httpx.ConnectError("connection failed"), "ConnectError"),
        (httpx.RemoteProtocolError("truncated response"), "RemoteProtocolError"),
    ),
)
def test_assistant_transport_failures_report_real_error_type(
    raised: httpx.HTTPError,
    expected: str,
) -> None:
    previous_pml = _MANAGED_TARGET_LINE + "show cartoon, target\n"

    def handler(request: httpx.Request) -> httpx.Response:
        raised.request = request
        raise raised

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ConfigurationError) as captured:
            request_assistant_pml_edit(
                secret=_assistant_secret(),
                user_text="解释当前结构",
                context={"stage_number": 1, "currentPml": previous_pml},
                history=(),
                previous_pml=previous_pml,
                known_object_names=("target",),
                known_chain_ids=("A",),
                client=client,
            )

    assert expected in str(captured.value)
    assert "当前场景未修改" in str(captured.value)


def test_assistant_http_status_reports_status_and_reason() -> None:
    previous_pml = _MANAGED_TARGET_LINE + "show cartoon, target\n"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, request=request, json={"error": {"message": "busy"}})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ConfigurationError) as captured:
            request_assistant_pml_edit(
                secret=_assistant_secret(),
                user_text="解释当前结构",
                context={"stage_number": 1, "currentPml": previous_pml},
                history=(),
                previous_pml=previous_pml,
                known_object_names=("target",),
                known_chain_ids=("A",),
                client=client,
            )

    assert "HTTP 429" in str(captured.value)
    assert "请求频率或额度受限" in str(captured.value)


def test_assistant_non_json_and_missing_envelope_report_specific_errors() -> None:
    previous_pml = _MANAGED_TARGET_LINE + "show cartoon, target\n"
    responses = iter(
        (
            httpx.Response(200, text="temporarily unavailable"),
            httpx.Response(200, json={"id": "request-without-choices"}),
        )
    )

    def handler(request: httpx.Request) -> httpx.Response:
        response = next(responses)
        response.request = request
        return response

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ConfigurationError, match="JSONDecodeError"):
            request_assistant_pml_edit(
                secret=_assistant_secret(),
                user_text="解释当前结构",
                context={"stage_number": 1, "currentPml": previous_pml},
                history=(),
                previous_pml=previous_pml,
                known_object_names=("target",),
                known_chain_ids=("A",),
                client=client,
            )
        with pytest.raises(ConfigurationError, match="没有返回 choices"):
            request_assistant_pml_edit(
                secret=_assistant_secret(),
                user_text="解释当前结构",
                context={"stage_number": 1, "currentPml": previous_pml},
                history=(),
                previous_pml=previous_pml,
                known_object_names=("target",),
                known_chain_ids=("A",),
                client=client,
            )


def test_chatpymol_four_field_response_is_accepted_without_protocol_repair() -> None:
    calls: list[dict[str, object]] = []
    previous_pml = _MANAGED_TARGET_LINE + (
        "hide everything, all\nshow cartoon, target\ncolor gray70, target\norient target\n"
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

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        edit, request_id, skill_ids = request_assistant_pml_edit(
            secret=_assistant_secret(),
            user_text="把整个结构显示为 sticks 并居中",
            context={"stage_number": 2, "currentPml": previous_pml},
            history=(),
            previous_pml=previous_pml,
            known_object_names=("target",),
            known_chain_ids=("A",),
            client=client,
        )

    assert len(calls) == 1
    assert request_id == "request-001"
    assert skill_ids == ("safe-pml",)
    assert "show sticks, target" in edit.pml


def test_chatpymol_exchange_creates_immutable_scene_even_when_pml_is_unchanged(
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
    initial_pml = _MANAGED_TARGET_LINE + "show cartoon, target\n"
    initialized = store.ensure_scene(
        session.session_id,
        pml=initial_pml,
        target_object=ReferenceStructure(
            object_id="target",
            role="target",
            object_name="target",
            filename="target.cif",
            file_format="cif",
            sha256="a" * 64,
            source="stage1-target-bundle",
            created_at=datetime(2026, 7, 29, tzinfo=UTC),
        ),
    )
    updated = store.append_chatpymol_exchange(
        session.session_id,
        user_text="解释当前结构",
        edit=ChatPyMolEdit(
            assistantMessage="当前保持 cartoon 显示。",
            summary="保持当前场景",
            conversationTitle="场景说明",
            pml=initial_pml,
        ),
        provider="deepseek",
        model="deepseek-chat",
        request_id="request-001",
        skill_ids=("safe-pml",),
        known_object_names=("target",),
        known_chain_ids=("A",),
        updated_at=datetime(2026, 7, 29, 1, tzinfo=UTC),
    )

    assert initialized.active_scene_version_id != updated.active_scene_version_id
    assert len(updated.scene_versions) == 2
    version = updated.scene_versions[-1]
    assert version.provider == "deepseek"
    assert version.model == "deepseek-chat"
    assert version.skill_ids == ("safe-pml",)
    assert version.conversation_title == "场景说明"
    assert version.parent_version_id == initialized.active_scene_version_id
    assert updated.messages[-1].version_id == version.version_id


def test_scene_pml_validator_protects_managed_lines_and_blocks_unsafe_commands() -> None:
    previous_pml = _MANAGED_TARGET_LINE + ("hide everything, all\nshow cartoon, target\n")
    valid = validate_scene_pml(
        previous_pml + "center target\n",
        previous_pml=previous_pml,
        known_object_names=("target",),
        known_chain_ids=("A",),
    )
    assert valid.endswith("center target\n")

    legacy_overlay = "# @easydesign live region overlay\n"
    with_legacy_overlay = validate_scene_pml(
        previous_pml + legacy_overlay + "select ed_region_A, none\n",
        previous_pml=previous_pml,
        known_object_names=("target",),
        known_chain_ids=("A",),
    )
    assert legacy_overlay in with_legacy_overlay
    without_legacy_overlay = validate_scene_pml(
        previous_pml + "select ed_region_A, none\n",
        previous_pml=previous_pml + legacy_overlay,
        known_object_names=("target",),
        known_chain_ids=("A",),
    )
    assert legacy_overlay not in without_legacy_overlay

    pymol_native = validate_scene_pml(
        previous_pml
        + (
            "select interface_atoms, target within 4.0 of target\n"
            "distance interface_contacts, interface_atoms, target\n"
            "create target_display_copy, target\n"
        ),
        previous_pml=previous_pml,
        known_object_names=("target",),
        known_chain_ids=("A",),
    )
    assert "distance interface_contacts" in pymol_native
    assert "create target_display_copy" in pymol_native

    with pytest.raises(ConfigurationError, match="受保护"):
        validate_scene_pml(
            "hide everything, all\nshow cartoon, target\n",
            previous_pml=previous_pml,
            known_object_names=("target",),
            known_chain_ids=("A",),
        )

    with pytest.raises(ConfigurationError, match="系统、文件或网络边界"):
        validate_scene_pml(
            previous_pml + "fetch 1ubq\n",
            previous_pml=previous_pml,
            known_object_names=("target",),
            known_chain_ids=("A",),
        )

    for destructive in ("delete target", "remove target", "system rm -rf /tmp/example"):
        with pytest.raises(ConfigurationError, match="系统、文件或网络边界"):
            validate_scene_pml(
                previous_pml + destructive + "\n",
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

    with pytest.raises(ConfigurationError, match="不存在的对象或 selection"):
        validate_scene_pml(
            previous_pml + "show sticks, invented_object\n",
            previous_pml=previous_pml,
            known_object_names=("target",),
            known_chain_ids=("A",),
        )

    with pytest.raises(ConfigurationError, match="不能用 create 覆盖"):
        validate_scene_pml(
            previous_pml + "create target, target\n",
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
        + ("hide everything, all\nshow cartoon, target\ncolor gray70, target\norient target\n"),
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
        + ("hide everything, all\nshow cartoon, target\ncolor gray70, target\norient target\n"),
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
        "# @easydesign reference object=ref_1ubq object_id=reference-000001 sha256=" + "c" * 64
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
        pml=_MANAGED_TARGET_LINE + ("hide everything, all\nshow cartoon, target\norient target\n"),
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
