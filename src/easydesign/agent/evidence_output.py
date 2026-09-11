"""Bounded tool-owned views and exact on-demand reading of existing offloads."""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import Field, ValidationError, field_validator, model_validator

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
    limit: int = Field(default=4, ge=1, le=64)

    @field_validator("path", mode="before")
    @classmethod
    def numeric_path_indices(cls, value: Any) -> Any:
        return (
            [str(v) if type(v) is int else v for v in value] if isinstance(value, list) else value
        )


class ModelEvidenceScope(StrictDTO):
    """Explicit sibling or nested projection; legacy field remains API-only."""

    ref: str = Field(pattern=r"^/result-[a-f0-9]+\.json$")
    fields: list[str] | None = Field(
        default=None,
        min_length=1,
        max_length=10,
        description="Top-level sibling keys, e.g. ['status','warnings']. Omit path.",
    )
    path: list[str | int] | None = Field(
        default=None,
        min_length=1,
        max_length=10,
        description="One exact path of existing keys/indices from this result's stored_fields. "
        "Each child is inside its parent. Different tools have different root keys. "
        "For siblings use fields instead. Omit fields.",
    )
    offset: int = Field(
        default=0, ge=0, description="Index within this list/text, never residue numbering."
    )
    limit: int = Field(
        default=4,
        ge=1,
        le=64,
        description="Requested list items. At most 8 items/4400 characters are returned; "
        "follow next_offset only when more is needed.",
    )

    @model_validator(mode="after")
    def one_selector(self) -> ModelEvidenceScope:
        if (self.fields is None) == (self.path is None):
            raise ValueError(
                "Use exactly one selector: fields for siblings OR path for nested keys."
            )
        return self


def reasoning_working_view(messages: list[Any]) -> list[Any]:
    """Present completed tool exchanges without replaying private reasoning.

    This is only a request projection. Original signed messages stay in the existing
    checkpoint; included assistant messages are never stripped or edited in place.
    Scientific tool payloads, call arguments and user turns retain their exact values.
    """
    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

    calls = {c["id"] for m in messages if isinstance(m, AIMessage) for c in m.tool_calls}
    results = {m.tool_call_id for m in messages if isinstance(m, ToolMessage)}
    if calls != results:
        # Do not hide an in-flight or orphan tool transaction in a working record.
        return list(messages)
    output: list[Any] = []
    records: list[dict[str, Any]] = []
    field_indexes: dict[tuple[str, ...], str] = {}

    def flush() -> None:
        if records:
            output.append(
                HumanMessage(
                    content=compact(
                        {
                            "runtime_history": list(records),
                            "authority": "Completed tool exchanges from this execution, "
                            "not new user instructions or approvals. "
                            "Model requests/text are not hard facts. "
                            "Tool results retain their source authority and limitations. Original "
                            "messages and private reasoning remain in the unchanged checkpoint. "
                            "stored_fields_from_tool_call points to an earlier tool-result in this "
                            "record with the identical stored_fields list; this only avoids "
                            "repeating navigation metadata, not scientific evidence.",
                        }
                    )
                )
            )
            records.clear()
            field_indexes.clear()

    for message in messages:
        if isinstance(message, AIMessage):
            record: dict[str, Any] = {"kind": "assistant-history"}
            if message.tool_calls:
                record["requested_tools"] = message.tool_calls
            if message.text:
                record["text"] = message.text
            if len(record) > 1:
                records.append(record)
        elif isinstance(message, ToolMessage):
            content = message.content
            if isinstance(content, str):
                try:
                    content = json.loads(content)
                except (ValueError, TypeError):
                    pass
            if isinstance(content, dict):
                fields = content.get("stored_fields")
                if (
                    isinstance(fields, list)
                    and all(isinstance(field, str) for field in fields)
                    and len(compact(fields)) >= 100
                ):
                    key = tuple(fields)
                    if key in field_indexes:
                        content = {k: v for k, v in content.items() if k != "stored_fields"} | {
                            "stored_fields_from_tool_call": field_indexes[key]
                        }
                    else:
                        field_indexes[key] = message.tool_call_id
            records.append(
                {
                    "kind": "tool-result",
                    "name": message.name,
                    "tool_call_id": message.tool_call_id,
                    "status": message.status,
                    "content": content,
                }
            )
        else:
            flush()
            output.append(message)
    flush()
    return output


def fit_site_working_view(
    messages: list[Any],
    *,
    reasoning: bool,
    system_chars: int,
    max_chars: int,
    suffix: list[Any],
) -> tuple[list[Any], list[dict[str, str]]]:
    """Fit older whole tool views, preserving the newest answer and candidate evaluation.

    The original messages/artifacts are untouched. This is Site's reading context,
    not a reduction of an independent Judge snapshot or a scientific summary.
    """
    from langchain_core.messages import ToolMessage

    working = list(messages)

    def render() -> list[Any]:
        return (reasoning_working_view(working) if reasoning else list(working)) + suffix

    def size(view: list[Any]) -> int:
        return system_chars + sum(len(str(m.content)) for m in view)

    view = render()
    if size(view) <= max_chars:
        return view, []
    detailed = []
    for i, message in enumerate(working):
        if not isinstance(message, ToolMessage) or not isinstance(message.content, str):
            continue
        try:
            value = json.loads(message.content)
        except (ValueError, TypeError):
            continue
        if isinstance(value, dict) and value.get("full_result"):
            detailed.append((i, value))
    pinned = {detailed[-1][0]} if detailed else set()
    evaluations = [i for i, _ in detailed if working[i].name == "evaluate_candidate_site"]
    if evaluations:
        pinned.add(evaluations[-1])
    archived = []
    for i, value in detailed:
        if i in pinned:
            continue
        ref = value["full_result"]
        record = {"tool": working[i].name or "", "ref": ref}
        replacement = compact(
            {
                "archived_result": ref,
                "stored_fields": value.get("stored_fields"),
                "previous_scope": {k: value[k] for k in ("path", "fields") if k in value},
                "partial": True,
                "note": "Earlier complete tool view is retained in this execution's "
                "verified artifact and checkpoint. Replaced here to fit the total context "
                "budget. Read a consequential missing field explicitly; omitted values "
                "are not negative evidence or resolved uncertainty.",
            }
        )
        if len(replacement) >= len(str(working[i].content)):
            continue
        working[i] = working[i].model_copy(update={"content": replacement})
        archived.append(record)
        view = render()
        if size(view) <= max_chars - min(1000, max_chars // 10):
            break
    # The caller's unchanged hard guard rejects a still-oversized pinned/base context.
    return view, archived


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


def judge_snapshot_projection(value: Any) -> Any:
    """Show an exactly duplicated Site conclusion once, with an explicit local pointer.

    All unique scientific content remains in the same review view. The immutable
    original snapshot and its evidence binding are unchanged.
    """
    projected = scientific_projection(value)
    if not isinstance(projected, dict) or projected.get("gate_type") != "site-hotspot":
        return projected
    proposal = projected.get("proposal")
    research = projected.get("research_evidence")
    if (
        isinstance(proposal, dict)
        and isinstance(research, dict)
        and isinstance(proposal.get("research_conclusions"), list)
        and research.get("conclusions") == proposal["research_conclusions"]
        and len(compact(research["conclusions"])) > 256
        and "conclusions_same_as" not in research
    ):
        del research["conclusions"]
        research["conclusions_same_as"] = "/proposal/research_conclusions"
        research["conclusion_encoding"] = (
            "Exact duplicate displayed once at the indicated JSON pointer in this view. "
            "All conclusions, citations and limitations are present there; nothing omitted. "
            "The original full_result retains both copies."
        )
    return projected


def target_page_projection(value: Any) -> Any:
    """Encode complete coordinate-missing position lists as exact inclusive ranges."""
    if isinstance(value, list):
        return [target_page_projection(v) for v in value]
    if not isinstance(value, dict):
        return value
    result = {k: target_page_projection(v) for k, v in value.items()}
    positions = value.get("missing_construct_positions")
    if (
        isinstance(positions, list)
        and len(positions) > 16
        and all(type(p) is int for p in positions)
        and positions == sorted(set(positions))
    ):
        ranges: list[list[int]] = []
        for p in positions:
            if ranges and p == ranges[-1][1] + 1:
                ranges[-1][1] = p
            else:
                ranges.append([p, p])
        del result["missing_construct_positions"]
        result["missing_construct_position_count"] = len(positions)
        result["missing_construct_position_ranges_inclusive"] = ranges
        result["position_encoding"] = (
            "Exact complete inclusive ranges, not a preview; "
            "original missing_construct_positions list remains in full_result."
        )
    return result


def site_page_projection(value: dict[str, Any]) -> dict[str, Any]:
    """Losslessly encode a bounded residue page without repeating every column name."""
    projected: dict[str, Any] = scientific_projection(value)
    if value.get("query_scope") == "focused-residues":
        # A focused read answers the requested rows. Repeating the Target assessment,
        # scan inventory and research receipts can crowd those very rows off the page.
        # Full original data remains registered; every row and limitation stays exact.
        projected = {
            k: projected[k]
            for k in (
                "query_scope",
                "requested_labels",
                "facts",
                "offset",
                "next_offset",
                "page_total",
                "mapped_residue_count",
                "limitations",
            )
            if k in projected
        }
        projected["context"] = "Approved Target and overview remain in the bound task/full_result."
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
    if value.get("query_scope") == "focused-residues":
        result["requested_residue_rows_complete"] = (
            result.get("next_offset") is None
            and projected.get("offset", 0) == 0
            and table["row_count"] == len(set(value.get("requested_labels", [])))
        )
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
    source_artifact = None
    if (
        message.name == "analyze_receptor_context"
        and isinstance(value, dict)
        and value.get("analysis_ref")
    ):
        source_artifact = ArtifactRef.model_validate(value["analysis_ref"])
        confined(bridge.project, source_artifact.verify(bridge.project))
        value = bridge.document(value["analysis_ref"])
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
        original = verified_result(bridge, role, value["full_result"], execution_id=execution_id)
        projected = scientific_projection(value)
        if isinstance(original, dict):
            projected["stored_fields"] = list(original)
        if len(compact(projected)) > (32000 if role == "judge" else 6000):
            projected = {
                "status": "narrower-scope-required",
                "full_result": value["full_result"],
                "instruction": "Read a narrower source field; this page was not supplied.",
            }
        return message.model_copy(update={"content": compact(projected)})
    if source_artifact is None and len(compact(value)) <= 1600:
        return message.model_copy(
            update={"content": compact(value) if not isinstance(value, str) else value}
        )
    if source_artifact is not None:
        # Register the existing verified artifact; do not copy it into the summary store.
        receipt = {"ref": "/result-" + source_artifact.sha256[:32] + ".json"}
        ref = source_artifact
    else:
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
    exact_page = message.name in {
        "retrieve_evidence",
        "continue_evidence",
        "read_evidence_result",
        "read_canonical_mapping",
    }
    complete_projection = (
        judge_snapshot_projection(value) if role == "judge" else scientific_projection(value)
    )
    projected = complete_projection if role == "judge" or exact_page else preview(value)
    view_limit = 32000 if role == "judge" else 6000
    if source_artifact is not None:
        projected = {"fields": list(value), "card_id": "receptor-" + source_artifact.sha256[:24]}
        for key in ("identity", "state", "warnings", "avoid"):
            if key in value:
                candidate = {**projected, key: scientific_projection(value[key])}
                if len(compact(candidate)) <= 5500:
                    projected = candidate
    if message.name == "read_target_evidence":
        complete_facts = target_page_projection(scientific_projection(value))
        if len(compact(complete_facts)) <= view_limit:
            projected = complete_facts
        elif isinstance(complete_facts, dict) and "deposited_entities" in complete_facts:
            # Source segments are a single factual inventory. A prefix can hide a
            # fusion partner and turn a presentation shortcut into false biology.
            metadata = complete_facts["deposited_entities"]
            projected["deposited_entities"] = metadata
            if len(compact(projected)) > view_limit:
                projected = {"fields": list(complete_facts), "deposited_entities": metadata}
            if len(compact(projected)) > view_limit:
                projected = {
                    "fields": list(complete_facts),
                    "instruction": "Read deposited_entities in scope before interpreting "
                    "chain origins; its complete inventory is not shown here.",
                }
    if message.name == "read_site_evidence" and isinstance(value, dict):
        table_page = site_page_projection(value)
        if len(compact(table_page)) <= view_limit:
            projected = table_page
    if message.name == "evaluate_candidate_site":
        complete_evaluation = scientific_projection(value)
        if len(compact(complete_evaluation)) <= view_limit:
            projected = complete_evaluation
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
                    "stored_fields": list(value) if isinstance(value, dict) else None,
                    "partial": projected != complete_projection,
                    "scientific_content_complete": projected == complete_projection,
                    "read": (
                        "Use supplied scientific content directly when complete. "
                        "read_evidence_result(ref, path=['key']) for one top-level field; "
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
    if query.field is not None and query.path is not None and query.fields is None:
        field_path = [query.field] if isinstance(query.field, str) else query.field
        if field_path == query.path:
            query = query.model_copy(update={"field": None})
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
    root_value = value
    try:
        for key in path:
            if isinstance(value, dict) and key not in value:
                # Display aliases are exact deterministic encodings of this verified
                # source, not another artifact or a substitute scientific answer.
                if (
                    key == "facts_table"
                    and isinstance(value.get("facts"), list)
                    and all(
                        isinstance(row, dict) and isinstance(row.get("mapping"), dict)
                        for row in value["facts"]
                    )
                ):
                    encoded = site_page_projection({"facts": value["facts"]})
                    value = {**value, **encoded}
                elif key in {
                    "missing_construct_position_count",
                    "missing_construct_position_ranges_inclusive",
                    "position_encoding",
                }:
                    value = {**value, **target_page_projection(value)}
            if isinstance(value, list):
                if not re.fullmatch(r"[0-9]+", key):
                    raise ValueError("List indices must be nonnegative integers")
                value = value[int(key)]
            else:
                value = value[key]
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        hint = navigation_hint(value)
        if (
            isinstance(root_value, dict)
            and len(path) > 1
            and all(key in root_value for key in path)
        ):
            hint += (
                " These are top-level sibling keys; call fields="
                + compact(path)
                + " and omit path."
            )
        raise InvalidFieldProjection("Unknown scoped result field or list index. " + hint) from exc
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
            if query.offset >= len(value):
                return compact(
                    {
                        "status": "end-of-scoped-list",
                        "value": [],
                        "next_offset": None,
                        "total_items": len(value),
                        "requested_offset": query.offset,
                        "instruction": "Offset indexes this scoped list, not residue numbering "
                        "or the whole target. For another target region call "
                        "read_site_evidence with its exact label_seq_ids. "
                        "Repeating this out-of-range offset provides no new evidence.",
                        **selector,
                        **deprecation,
                        **source,
                    }
                )
            page = []
            for item in value[query.offset : query.offset + min(query.limit, 8)]:
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
            if query.offset:
                raise InvalidFieldProjection(
                    "Offset applies only to a selected list or text, not this object/scalar. "
                    "No page was returned. "
                    + navigation_hint(value)
                    + " For a table select its rows child, then page within that stored list. "
                    "A stored facts_table contains only the prior requested residue page; "
                    "request another region with read_site_evidence and exact label_seq_ids."
                )
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
