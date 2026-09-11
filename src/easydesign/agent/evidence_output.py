"""Bounded tool-owned views and exact on-demand reading of existing offloads."""

from __future__ import annotations

import json
from typing import Any

from pydantic import Field

from easydesign.core import ArtifactRef

from .contracts import AgentBoundaryError, StrictDTO
from .session_store import compact, confined


class ReadEvidenceResult(StrictDTO):
    ref: str = Field(pattern=r"^/result-[a-f0-9]+\.json$")
    field: list[str] = Field(default_factory=list, max_length=10)
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=4, ge=1, le=8)


def preview(value: Any, *, depth: int = 0) -> Any:
    if isinstance(value, dict):
        return {
            k: preview(v, depth=depth + 1)
            for k, v in value.items()
            if k not in {"evidence_refs", "source_refs", "request_identity", "evidence_id"}
        }
    if isinstance(value, list):
        count = 3 if depth < 2 else 2
        return [preview(v, depth=depth + 1) for v in value[:count]]
    if isinstance(value, str) and len(value) > 650:
        return value[:650] + " [partial; read the scoped field for more]"
    return value


def scientific_projection(value: Any) -> Any:
    """Keep all scoped opinions, limitations and counterevidence; strip only mechanics."""
    if isinstance(value, dict):
        return {
            k: scientific_projection(v)
            for k, v in value.items()
            if k
            not in {
                "evidence_refs",
                "source_refs",
                "input_refs",
                "request_identity",
                "evidence_id",
                "sha256",
                "sequence_sha256",
                "context_ref",
                "corpus_ref",
            }
        }
    if isinstance(value, list):
        return [scientific_projection(v) for v in value]
    return value


def output_message(bridge: Any, role: str, execution_id: str, message: Any) -> Any:
    from langchain_core.messages import ToolMessage

    if (
        not isinstance(message, ToolMessage)
        or not isinstance(message.content, str)
        or message.name == "read_file"
    ):
        return message
    try:
        value = json.loads(message.content)
    except (ValueError, TypeError):
        value = message.content
    if isinstance(value, dict) and value.get("status") == "offloaded":
        path = confined(
            bridge.store.root,
            bridge.store.root / "agent-work" / bridge.thread / value["ref"].lstrip("/"),
        )
        value = json.loads(path.read_text())
    if len(compact(value)) <= 1600:
        return message.model_copy(
            update={"content": compact(value) if not isinstance(value, str) else value}
        )
    receipt = json.loads(bridge.store.offload(bridge.thread, value, limit=0))
    path = confined(
        bridge.store.root,
        bridge.store.root / "agent-work" / bridge.thread / receipt["ref"].lstrip("/"),
    )
    ref = ArtifactRef.from_file(
        run_root=bridge.project,
        relative_path=path.relative_to(bridge.project).as_posix(),
        artifact_id="agent-output",
        role="scientific-evidence",
        file_format="json",
    )
    from .tools import JUDGE_EVIDENCE

    judge_binding = JUDGE_EVIDENCE.get() if role == "judge" else None
    bridge.store.event(
        bridge.thread,
        "tool-view",
        {
            "role": role,
            "execution_id": execution_id,
            "ref": receipt["ref"],
            "artifact": ref.model_dump(mode="json"),
            "tool_call_id": message.tool_call_id,
            "judge_binding": judge_binding.model_dump(mode="json") if judge_binding else None,
        },
    )
    exact_page = message.name in {"retrieve_evidence", "read_evidence_result"}
    projected = scientific_projection(value) if role == "judge" or exact_page else preview(value)
    view_limit = 32000 if role == "judge" else 6000
    if role == "judge" and len(compact(projected)) > view_limit:
        raise AgentBoundaryError(
            "Judge snapshot exceeds the scoped review limit. Narrow the proposal/evidence "
            "question; supporting or contradictory evidence must not be silently truncated."
        )
    if exact_page and len(compact(projected)) > view_limit:
        projected = {
            "fields": list(value) if isinstance(value, dict) else [],
            "instruction": "Full page retained; read a narrower field before continuing.",
        }
    if len(compact(projected)) > view_limit:
        projected = (
            {k: preview(v, depth=4) for k, v in value.items()}
            if isinstance(value, dict)
            else str(projected)[:4000]
        )
    if len(compact(projected)) > view_limit:
        # Explicit field index, never silently discard the full result.
        projected = (
            {"fields": list(value), "instruction": "Read the relevant named field."}
            if isinstance(value, dict)
            else str(projected)[:4000]
        )
    return message.model_copy(
        update={
            "content": compact(
                {
                    **(projected if isinstance(projected, dict) else {"view": projected}),
                    "full_result": receipt["ref"],
                    "partial": True,
                    "read": (
                        "read_evidence_result(ref, field=[key,...], offset, limit); full resu"
                        "lt retained"
                    ),
                }
            )
        }
    )


def result_tool(bridge: Any, role: str) -> Any:
    from langchain_core.tools import StructuredTool

    async def read(**arguments: Any) -> str:
        query = ReadEvidenceResult.model_validate(arguments)
        execution = bridge.store.latest_execution(bridge.thread)
        row = bridge.store.db.execute(
            "SELECT payload FROM events WHERE thread=? AND kind='tool-view' "
            "AND json_extract(payload,'$.role')=? AND json_extract(payload,'$.ref')=? "
            "AND json_extract(payload,'$.execution_id')=? ORDER BY seq DESC LIMIT 1",
            (bridge.thread, role, query.ref, execution["execution_id"] if execution else None),
        ).fetchone()
        if row is None:
            raise AgentBoundaryError("Result was not supplied to this role/execution")
        stored = json.loads(row[0])
        if role == "judge":
            from .tools import JUDGE_EVIDENCE

            binding = JUDGE_EVIDENCE.get()
            if binding is None or stored.get("judge_binding") != binding.model_dump(mode="json"):
                raise AgentBoundaryError("Result belongs to another delegated Judge snapshot")
        path = confined(
            bridge.project, ArtifactRef.model_validate(stored["artifact"]).verify(bridge.project)
        )
        value = json.loads(path.read_text())
        try:
            for field in query.field:
                value = value[int(field)] if isinstance(value, list) else value[field]
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise AgentBoundaryError("Unknown scoped result field") from exc
        page: Any
        if isinstance(value, list):
            page = []
            for item in value[query.offset : query.offset + query.limit]:
                if len(compact([*page, item])) > 4400:
                    break
                page.append(item)
            if not page and query.offset < len(value):
                item = value[query.offset]
                return compact(
                    {
                        "status": "narrower-scope-required",
                        "field": [*query.field, str(query.offset)],
                        "fields": list(item)[:30] if isinstance(item, dict) else [],
                        "instruction": "Read an item field; no array entries were consumed.",
                        "next_offset": query.offset,
                    }
                )
            next_offset = (
                query.offset + len(page) if query.offset + len(page) < len(value) else None
            )
        elif isinstance(value, str):
            page = value[query.offset : query.offset + 3000]
            while len(compact(page)) > 4400:
                page = page[: len(page) // 2]
            next_offset = (
                query.offset + len(page) if query.offset + len(page) < len(value) else None
            )
        else:
            page, next_offset = value, None
            if len(compact(page)) > 4400:
                return compact(
                    {
                        "status": "narrower-scope-required",
                        "field": query.field,
                        "fields": list(value)[:30] if isinstance(value, dict) else [],
                        "instruction": "Read a child field; the full object was not supplied.",
                    }
                )
        return compact({"value": page, "next_offset": next_offset, "field": query.field})

    return StructuredTool.from_function(
        name="read_evidence_result",
        coroutine=read,
        args_schema=ReadEvidenceResult,
        description=(
            "Read a named JSON field or a short list/text page from a full_result"
            " reference supplied to this role in this execution. For example fiel"
            "d=['candidate_patches'] then offset. Use focused scientific fields; "
            "do not read the whole artifact sequentially."
        ),
    )
