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
    StructureInteractionStore,
    ViewerAction,
    compile_viewer_actions,
    request_assistant_proposal,
    validate_safe_pml,
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

    assert updated.schema_version == "0.2"
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
def test_assistant_invalid_responses_fail_without_fallback(
    response: httpx.Response,
) -> None:
    secret = AssistantProviderSecret(
        provider="deepseek",
        model="deepseek-chat",
        base_url="https://api.deepseek.example/v1",
        api_key="secret",
        configured_at=datetime(2026, 7, 29, tzinfo=UTC),
    )
    with httpx.Client(
        transport=httpx.MockTransport(lambda _request: response)
    ) as client:
        with pytest.raises(ConfigurationError):
            request_assistant_proposal(
                secret=secret,
                user_text="请解释当前结构",
                context={"stage_number": 1},
                client=client,
            )


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
