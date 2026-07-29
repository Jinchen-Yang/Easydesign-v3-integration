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
        "show cartoon, all\ncolor marine, chain A\nzoom chain A"
    )
    assert canonical == (
        "show cartoon, all\ncolor marine, chain A\nzoom chain A\n"
    )

    for command in (
        "remove solvent",
        "delete all",
        "load /tmp/secret.cif",
        "run unsafe.py",
        "python print('unsafe')",
        "set internal_gui, 1",
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
