"""Bounded tool-owned views and exact on-demand reading of existing offloads."""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import Field, ValidationError

from easydesign.core import ArtifactRef

from .contracts import AgentBoundaryError, InvalidFieldProjection, StrictDTO
from .session_store import compact, confined


class ReadEvidenceResult(StrictDTO):
    ref: str = Field(pattern=r"^/result-[a-f0-9]+\.json$")
    field: str | list[str] | None = Field(
        default=None,
        description="One top-level key. Deprecated list form retains nested-path semantics.",
    )
    fields: list[str] | None = Field(
        default=None,
        min_length=1,
        max_length=10,
        description="Multiple top-level sibling keys; never a nested path.",
    )
    path: list[str] | None = Field(
        default=None,
        max_length=10,
        description="Nested keys or nonnegative list indices in traversal order.",
    )
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


def site_page_projection(value: dict[str, Any]) -> dict[str, Any]:
    """Losslessly encode a bounded residue page without repeating every column name."""
    projected: dict[str, Any] = scientific_projection(value)
    rows = projected.get("facts", [])
    if not rows:
        return projected
    mapping_columns = list(dict.fromkeys(k for row in rows for k in row["mapping"]))
    metric_columns = list(dict.fromkeys(k for row in rows for k in row if k != "mapping"))
    # Missing keys remain distinct from a present null. Runtime rows normally have
    # one uniform schema; otherwise keep the original representation.
    if any(
        set(row["mapping"]) != set(mapping_columns) or set(row) != {"mapping", *metric_columns}
        for row in rows
    ):
        return projected
    table: dict[str, Any] = {
        "mapping_columns": mapping_columns,
        "metric_columns": metric_columns,
        "rows": [
            [*[row["mapping"][k] for k in mapping_columns], *[row[k] for k in metric_columns]]
            for row in rows
        ],
        "row_count": len(rows),
        "encoding": "Values follow mapping_columns then metric_columns; nulls retained.",
    }
    result = {k: v for k, v in projected.items() if k != "facts"} | {"facts_table": table}
    # Unlike a generic preview, a shortened page must advance only over rows that
    # were actually delivered. Source offsets are supplied by the read-only adapter.
    if "offset" in projected:
        while len(compact(result)) > 5500 and len(table["rows"]) > 1:
            table["rows"].pop()
            table["row_count"] = len(table["rows"])
            result["next_offset"] = projected["offset"] + table["row_count"]
    return result


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
    if (
        message.name == "read_evidence_result"
        and isinstance(value, dict)
        and value.get("full_result")
    ):
        # The reader's source is already registered and immutable. Re-offloading its
        # wrapper would change the navigation root from scientific data to {value,...}.
        verified_result(bridge, role, value["full_result"], execution_id=execution_id)
        projected = scientific_projection(value)
        if len(compact(projected)) > (32000 if role == "judge" else 6000):
            projected = {
                "status": "narrower-scope-required",
                "full_result": value["full_result"],
                "instruction": "Read a narrower source field; this page was not supplied.",
            }
        return message.model_copy(update={"content": compact(projected)})
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
    if message.name == "read_target_evidence":
        complete_facts = scientific_projection(value)
        if len(compact(complete_facts)) <= view_limit:
            projected = complete_facts
    if message.name == "read_site_evidence" and isinstance(value, dict):
        table_page = site_page_projection(value)
        if len(compact(table_page)) <= view_limit:
            projected = table_page
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
                    "partial": projected != scientific_projection(value),
                    "scientific_content_complete": projected == scientific_projection(value),
                    "read": (
                        "Use supplied scientific content directly when complete. "
                        "read_evidence_result(ref, field='key') for one top-level field; "
                        "fields=['a','b'] for siblings; path=['a','b'] for nested traversal. "
                        "Use offset/limit for list pages. Full result retained."
                    ),
                }
            )
        }
    )


def verified_result(bridge: Any, role: str, ref: Any, *, execution_id: str | None = None) -> Any:
    """Authorization and integrity precede all recoverable argument diagnostics."""
    if not isinstance(ref, str) or not re.fullmatch(r"/result-[a-f0-9]+\.json", ref):
        raise AgentBoundaryError("Invalid scoped result reference")
    execution = bridge.store.latest_execution(bridge.thread)
    if execution_id is not None and (
        execution is None or execution["execution_id"] != execution_id
    ):
        raise AgentBoundaryError("Result read is not bound to the current execution")
    row = bridge.store.db.execute(
        "SELECT payload FROM events WHERE thread=? AND kind='tool-view' "
        "AND json_extract(payload,'$.role')=? AND json_extract(payload,'$.ref')=? "
        "AND json_extract(payload,'$.execution_id')=? ORDER BY seq DESC LIMIT 1",
        (bridge.thread, role, ref, execution["execution_id"] if execution else None),
    ).fetchone()
    if row is None:
        raise AgentBoundaryError("Result was not supplied to this role/execution")
    stored = json.loads(row[0])
    if role == "judge":
        from .tools import JUDGE_EVIDENCE

        binding = JUDGE_EVIDENCE.get()
        if binding is None or stored.get("judge_binding") != binding.model_dump(mode="json"):
            raise AgentBoundaryError("Result belongs to another delegated Judge snapshot")
    artifact_path = confined(
        bridge.project, ArtifactRef.model_validate(stored["artifact"]).verify(bridge.project)
    )
    return json.loads(artifact_path.read_text())


def read_query(arguments: dict[str, Any]) -> ReadEvidenceResult:
    try:
        query = ReadEvidenceResult.model_validate(arguments)
    except ValidationError as exc:
        # Called only AFTER verified_result by the harness and read callback.
        if all(
            e["loc"] and e["loc"][0] in {"field", "fields", "path", "offset", "limit"}
            for e in exc.errors()
        ):
            raise InvalidFieldProjection("Invalid selector or pagination syntax.") from exc
        raise
    if sum(item is not None for item in (query.field, query.fields, query.path)) > 1:
        raise InvalidFieldProjection("Selectors field, fields and path are mutually exclusive.")
    if isinstance(query.field, list) and len(query.field) > 10:
        raise InvalidFieldProjection("A nested path may contain at most ten components.")
    return query


def navigation_hint(value: Any) -> str:
    if isinstance(value, dict):
        return "Available object keys: " + compact(list(value)[:30])[:2000]
    if isinstance(value, list):
        return f"This is a list of {len(value)} items; use a nonnegative index within its length."
    return "This is a scalar; read this value without an additional child selector."


def scoped_value(value: Any, query: ReadEvidenceResult) -> tuple[Any, list[str]]:
    if query.fields is not None:
        if (
            not isinstance(value, dict)
            or len(set(query.fields)) != len(query.fields)
            or any(key not in value for key in query.fields)
        ):
            raise InvalidFieldProjection(
                "Sibling projection requires distinct existing object keys. "
                + navigation_hint(value)
            )
        return {key: value[key] for key in query.fields}, []
    path = ([query.field] if isinstance(query.field, str) else query.field) or query.path or []
    try:
        for key in path:
            if isinstance(value, list):
                if not re.fullmatch(r"[0-9]+", key):
                    raise ValueError("List indices must be nonnegative integers")
                value = value[int(key)]
            else:
                value = value[key]
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise InvalidFieldProjection(
            "Unknown scoped result field or list index. " + navigation_hint(value)
        ) from exc
    return value, path


def result_tool(bridge: Any, role: str) -> Any:
    from langchain_core.tools import StructuredTool

    async def read(**arguments: Any) -> str:
        full = verified_result(bridge, role, arguments.get("ref"))
        query = read_query(arguments)
        value, selected_path = scoped_value(full, query)
        source = {"full_result": query.ref}
        selector = {"path": selected_path}
        if query.fields is not None:
            selector = {"fields": query.fields}
        if isinstance(query.field, list):
            # Preserve meaning and the old response key for existing callers.
            selector.update(field=query.field)
        deprecation = (
            {"deprecation": "field=[...] retains nested traversal; use path=[...] instead."}
            if isinstance(query.field, list)
            else {}
        )
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
                        "path": [*selected_path, str(query.offset)],
                        "available_fields": list(item)[:30] if isinstance(item, dict) else [],
                        "instruction": "Read an item field; no array entries were consumed.",
                        "next_offset": query.offset,
                        **source,
                        **deprecation,
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
                        **selector,
                        "available_fields": list(value)[:30] if isinstance(value, dict) else [],
                        "instruction": "Read a child field; the full object was not supplied.",
                        **source,
                        **deprecation,
                    }
                )
        return compact(
            {"value": page, "next_offset": next_offset, **selector, **deprecation, **source}
        )

    return StructuredTool.from_function(
        name="read_evidence_result",
        coroutine=read,
        args_schema=ReadEvidenceResult,
        description=(
            "Read a verified full_result supplied to this role/execution. Choose keys from "
            "that actual result, not from another gate's schema. Use exactly one of field "
            "(one top-level key), fields (sibling keys), or path (nested traversal). "
            "Legacy field=[...] is deprecated and retains nested-path semantics. "
            "Use offset/limit for list pages, offset for text pages. Use focused fields; "
            "do not read the whole artifact sequentially."
        ),
    )
