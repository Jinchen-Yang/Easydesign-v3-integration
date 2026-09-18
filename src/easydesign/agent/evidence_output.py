"""Bounded tool-owned views and exact on-demand reading of existing offloads."""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import Field, ValidationError, field_validator, model_validator

from easydesign.core import ArtifactRef

from .contracts import AgentBoundaryError, InvalidFieldProjection, StrictDTO, UnknownEvidenceResult
from .session_store import compact, confined

RESULT_REF_PATTERN = r"^(?:/result-[a-f0-9]+\.json|result:[1-9][0-9]{0,17})$"
TARGET_DECISION_VIEW_LIMIT = 24000


class ReadEvidenceResult(StrictDTO):
    ref: str = Field(pattern=RESULT_REF_PATTERN)
    field: str | None = Field(
        default=None,
        description="One top-level key for internal readers; model uses fields or path.",
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
    """Inspect a result's types first, then select an explicit scoped value."""

    ref: str = Field(
        pattern=RESULT_REF_PATTERN,
        description="Exact supplied result or short result:N handle from runtime navigation. "
        "Prefer the short handle when offered. Omit fields/path to inspect its field types and "
        "navigation without reading source content; do this when its schema is unknown.",
    )
    fields: list[str] | None = Field(
        default=None,
        min_length=1,
        max_length=10,
        description="Top-level sibling keys or declared projection_aliases, "
        "e.g. ['state','membrane','topology_summary']. Omit path.",
    )
    path: list[str | int] | None = Field(
        default=None,
        min_length=1,
        max_length=10,
        description="One exact path from stored_fields or declared projection_aliases, then "
        "existing child keys/indices. "
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
        if self.fields is not None and self.path is not None:
            raise ValueError(
                "Use at most one selector: fields for siblings OR path for nested keys. "
                "Omit both to inspect the result's field types."
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
            payload = {
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
            output.append(HumanMessage(content=compact(payload)))
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
    if "offset" in projected and value.get("query_scope") != "focused-residues":
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


def alias_navigation(value: Any, *, source: bool = False) -> dict[str, Any]:
    """Advertise exact readable projections separately from stored source keys."""
    if not isinstance(value, dict):
        return {}
    aliases = value.get("projection_aliases", [])
    if source:
        aliases = []
        if isinstance(value.get("candidates"), dict):
            aliases.append("candidate_overview")
            if isinstance(value.get("topology"), dict):
                aliases.append("topology_summary")
    return {"projection_aliases": aliases} if aliases else {}


def result_navigation(value: Any) -> dict[str, Any]:
    """Bounded structural metadata from the verified object, without scientific inference."""

    def kind(item: Any) -> str:
        if item is None:
            return "null"
        return {
            dict: "object",
            list: "array",
            str: "text",
            bool: "boolean",
            int: "integer",
            float: "number",
        }[type(item)]

    result: dict[str, Any] = {"value_type": kind(value)}
    if isinstance(value, dict):
        keys = list(value)[:30]
        result.update(
            field_types={key: kind(value[key]) for key in keys},
            array_lengths={key: len(value[key]) for key in keys if isinstance(value[key], list)},
            field_count=len(value),
            field_index_complete=len(keys) == len(value),
            **alias_navigation(value, source=True),
        )
        if (
            isinstance(value.get("cards"), list)
            and type(value.get("matching_chunks")) is int
            and isinstance(value.get("query_id"), str)
            and isinstance(value.get("next_cursor"), str)
        ):
            result["retrieval_page"] = {
                "stored_cards": len(value["cards"]),
                "matching_chunk_count": value["matching_chunks"],
                "cards_path": ["cards"],
                "continue": {
                    "tool": "continue_evidence",
                    "arguments": {"cursor": value["next_cursor"]},
                }
                if value["next_cursor"]
                else None,
                "instruction": "cards contains only this saved retrieval page. matching_chunks "
                "is a count, not an array. Read cards here; use the exact continuation cursor "
                "for further source passages. A saved-page offset cannot retrieve later pages.",
            }
    elif isinstance(value, (list, str)):
        result["length"] = len(value)
    return result


def receptor_overview_projection(value: dict[str, Any]) -> dict[str, Any]:
    """Expose existing candidate reasoning and source-coordinate rows in one scoped view.

    This is a declared field projection of the existing analysis, not a new candidate
    ranking, mapping, access calculation, or claim of a complete receptor analysis.
    """
    fields = ("identity", "state", "structure", "membrane", "warnings", "avoid")
    result = {key: scientific_projection(value[key]) for key in fields if key in value}
    if "approved_design_mapping" in value:
        result["approved_design_mapping"] = site_page_projection(value["approved_design_mapping"])
    topology = value.get("topology")
    if isinstance(topology, dict):
        result["topology_summary"] = {
            key: scientific_projection(item)
            for key, item in topology.items()
            if key not in {"residues", "unmapped_residues"}
        }
    columns = (
        "gpcrdb_sequence_number",
        "amino_acid",
        "observed_amino_acid",
        "observed",
        "auth_asym_id",
        "auth_seq_id",
        "label_asym_id",
        "label_seq_id",
        "insertion_code",
        "model_id",
        "mapping_status",
        "segment",
        "membrane_facing",
        "functional_role",
    )
    candidates = value.get("candidates")
    if isinstance(candidates, dict):
        overview = {}
        for mode, items in candidates.items():
            if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
                overview[mode] = scientific_projection(items)
                continue
            overview[mode] = []
            for index, item in enumerate(items):
                entry = {k: scientific_projection(v) for k, v in item.items() if k != "residues"}
                rows = item.get("residues")
                if isinstance(rows, list) and all(isinstance(row, dict) for row in rows):
                    approved = value.get("approved_design_mapping", {})
                    if "facts" in approved:
                        positions = {
                            row["gpcrdb_sequence_number"]
                            for row in rows
                            if row.get("gpcrdb_sequence_number") is not None
                        }
                        matches = [
                            row["mapping"]
                            for row in approved["facts"]
                            if row.get("coordinate_observed")
                            and row["mapping"].get("canonical_position") in positions
                        ]
                        entry["approved_design_membership"] = {
                            "hotspot_label_seq_ids": sorted({r["label_seq_id"] for r in matches}),
                            "unobserved_or_unmapped_canonical_positions": sorted(
                                positions - {r["canonical_position"] for r in matches}
                            ),
                            "source_members_without_canonical_position": sum(
                                r.get("gpcrdb_sequence_number") is None for r in rows
                            ),
                            "mapping_statuses": sorted({r["mapping_status"] for r in matches}),
                            "authority": "Exact lookup in approved Target rows; no offset or "
                            "new alignment. Preserve the supplied mapping qualifications. "
                            "These design labels are ready for Site candidate selection; "
                            "source label/auth numbers below are provenance, not design labels.",
                        }
                    source_identifiers = {
                        "auth_asym_id",
                        "auth_seq_id",
                        "label_asym_id",
                        "label_seq_id",
                        "insertion_code",
                        "model_id",
                    }
                    records = [
                        {
                            ("source_" + key if key in source_identifiers else key): row[key]
                            for key in columns
                            if key in row
                        }
                        for row in rows
                    ]
                    if records and all(set(row) == set(records[0]) for row in records):
                        names = list(records[0])
                        entry["residue_table"] = {
                            "columns": names,
                            "rows": [[row[key] for key in names] for row in records],
                            "encoding": "Every source member, in order; "
                            "values follow columns; nulls retained.",
                        }
                    else:
                        entry["residue_records"] = records
                    entry["full_residues_path"] = ["candidates", mode, index, "residues"]
                elif "residues" in item:
                    entry["residues"] = rows
                overview[mode].append(entry)
        result["candidate_overview"] = overview
    result["query_scope"] = "receptor-candidate-overview"
    result["declared_scope_complete"] = True
    result["scope_limits"] = (
        "All candidate non-residue fields and all members in the listed residue columns are "
        "supplied without reranking. Other residue columns, full topology/residue_regions, "
        "chain_graph, evidence inventory and provenance remain in full_result. source_* columns "
        "are original structure identifiers; gpcrdb_sequence_number is the receptor reference "
        "position. Neither is an approved design label. Read a specific "
        "source path if needed. Source auth/label numbering is NOT approved design numbering; "
        "use each candidate's approved_design_membership for its exact design labels, and "
        "approved_design_mapping or read_canonical_mapping for correspondence details "
        "and preserve its qualifiers. Never infer a global offset. "
        "Candidates and mode names are generated by the EasyDesign kernel using source facts; "
        "they are not GPCRdb-curated antibody epitopes or measured functional effects. "
        "Kernel candidate confidence/hard_gates are scoped heuristics, not full VHH access, "
        "functional efficacy, or independent scientific approval."
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
    if (
        message.status == "error"
        and message.name == "read_evidence_result"
        and isinstance(value, dict)
        and value.get("error_code") == "UNKNOWN_EVIDENCE_RESULT"
        and len(compact(value)) <= 6000
    ):
        # This bounded runtime catalog is repair feedback, not a scientific result.
        # Do not mint another result ID just to explain how to recover a result ID.
        return message
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
            projected.update(alias_navigation(original, source=True))
        if role != "judge" and len(compact(projected)) > 6000:
            projected = {
                "status": "narrower-scope-required",
                "full_result": value["full_result"],
                "instruction": "Read a narrower source field; this page was not supplied.",
            }
        projected["navigation"] = result_navigation(original)
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
    complete_projection = scientific_projection(value)
    complete_design = role == "binder" and message.name == "read_design_evidence"
    if role == "judge" or complete_design:
        if isinstance(value, dict) and value.get("kind") == "site-judge-review-packet-v1":
            # The packet already has one scientific representation. Preserve its exact
            # source provenance too; no generic metadata stripping or preview is needed.
            complete_projection = value
        # Decision owners receive the complete scientific snapshot. In particular,
        # a design preview must never reduce approved hotspots or scaffold coverage.
        # The shared model-input hard guard includes Skill text, history and schemas;
        # a second per-tool
        # cap must not reject valid reviews or motivate lossy evidence compression.
        return message.model_copy(
            update={
                "content": compact(
                    {
                        **complete_projection,
                        "full_result": receipt["ref"],
                        "partial": False,
                        "scientific_content_complete": True,
                    }
                    if isinstance(complete_projection, dict)
                    else {
                        "view": complete_projection,
                        "full_result": receipt["ref"],
                        "partial": False,
                        "scientific_content_complete": True,
                    }
                )
            }
        )
    projected = complete_projection if exact_page else preview(value)
    view_limit = 6000
    if source_artifact is not None:
        receptor_card_id = "receptor-" + source_artifact.sha256[:24]
        projected = {"fields": list(value), "card_id": receptor_card_id}
        overview = {**projected, **receptor_overview_projection(value)}
        if role == "site":
            # The kernel artifact contains fine-grained claim identifiers named
            # ``evidence-*``. They are useful within the deterministic analysis but
            # are not EvidenceResearch cards and therefore cannot populate a
            # SiteResearchHandoff.evidence_card_ids field. Make that distinction
            # explicit in the decision view instead of asking the model to infer it
            # from two similarly named identifier families.
            overview["citation_contract"] = {
                "citable_evidence_card_ids": [receptor_card_id],
                "instruction": "For any candidate supported by this deterministic receptor "
                "analysis, cite the receptor-* card_id in SiteResearchHandoff.evidence_card_ids. "
                "kernel_claim_ids are internal claim handles and are not citable card IDs.",
            }
            for candidates in overview.get("candidate_overview", {}).values():
                for candidate in candidates:
                    if "evidence" in candidate:
                        candidate["kernel_claims"] = candidate.pop("evidence")
                    if "evidence_ids" in candidate:
                        candidate["kernel_claim_ids"] = candidate.pop("evidence_ids")
                    candidate["citable_evidence_card_ids"] = [receptor_card_id]
            # This declared scientific view includes exact candidate membership.
            # Do not silently downgrade it to a partial preview at an unrelated
            # per-tool threshold. The shared model-input hard guard owns admission.
            projected = overview
            view_limit = len(compact(overview))
        else:
            for key in ("identity", "state", "warnings", "avoid"):
                if key in value:
                    candidate = {**projected, key: scientific_projection(value[key])}
                    if len(compact(candidate)) <= 5500:
                        projected = candidate
    if message.name == "read_target_evidence":
        complete_facts = target_page_projection(scientific_projection(value))
        decision_view = (
            isinstance(complete_facts, dict)
            and complete_facts.get("decision_kind") is not None
            and isinstance(complete_facts.get("options"), list)
            and isinstance(complete_facts.get("hard_facts"), dict)
        )
        if decision_view and len(compact(complete_facts)) <= TARGET_DECISION_VIEW_LIMIT:
            # A pending Target gate is already a bounded decision packet. Supplying its
            # complete, losslessly range-encoded facts once avoids a model paging every
            # field of the same immutable result and exhausting the shared context guard.
            projected = {
                **complete_facts,
                "declared_scope_complete": True,
                "projection_scope": "target-gate-decision",
                "scope_limits": "Scientific decision fields are complete. Provenance hashes and "
                "the original uncompressed coordinate-missing lists remain in full_result.",
            }
            view_limit = len(compact(projected))
        elif len(compact(complete_facts)) <= view_limit:
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
        if role == "site" and value.get("query_scope") == "focused-residues":
            view_limit = len(compact(site_page_projection(value)))
        table_page = site_page_projection(value)
        if len(compact(table_page)) <= view_limit:
            projected = table_page
    if message.name == "evaluate_candidate_site":
        complete_evaluation = scientific_projection(value)
        if role == "site":
            view_limit = len(compact(complete_evaluation))
        if len(compact(complete_evaluation)) <= view_limit:
            projected = complete_evaluation
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
                    "navigation": result_navigation(value),
                    **alias_navigation(value, source=True),
                    "partial": not (
                        isinstance(projected, dict)
                        and projected.get("declared_scope_complete") is True
                    )
                    and projected != complete_projection,
                    "scientific_content_complete": (
                        isinstance(projected, dict)
                        and projected.get("declared_scope_complete") is True
                    )
                    or projected == complete_projection,
                    "read": (
                        "Use supplied scientific content directly when complete, or the "
                        "declared fields when declared_scope_complete=true. Other analysis "
                        "fields are optional scoped reads, not required full-file paging. "
                        "If field types are unknown, call read_evidence_result(ref) with no "
                        "selector to inspect navigation; do not guess another tool's fields. "
                        "read_evidence_result(ref, path=['key']) for one top-level field; "
                        "fields=['a','b'] for siblings; path=['a','b'] for nested traversal. "
                        "Use offset/limit for list pages. Full result retained."
                        + (
                            " Read projection_aliases as paths or sibling fields. "
                            "topology_summary excludes per-residue arrays; candidate_overview "
                            "preserves every candidate/member in the declared columns."
                            if alias_navigation(value, source=True)
                            else ""
                        )
                    ),
                }
            )
        }
    )


def verified_result(bridge: Any, role: str, ref: Any, *, execution_id: str | None = None) -> Any:
    """Authorization and integrity precede all recoverable argument diagnostics."""
    # A model may mix a result file's hash with the numeric handle syntax. Treat
    # that as unissued: offer owned IDs below, never resolve the hash implicitly.
    malformed_handle = isinstance(ref, str) and bool(
        re.fullmatch(r"result:[a-f0-9]{32,64}", ref)
    )
    if not isinstance(ref, str) or (
        not re.fullmatch(RESULT_REF_PATTERN, ref) and not malformed_handle
    ):
        raise AgentBoundaryError("Invalid scoped result reference")
    execution = bridge.store.latest_execution(bridge.thread)
    if execution_id is not None and (
        execution is None or execution["execution_id"] != execution_id
    ):
        raise AgentBoundaryError("Result read is not bound to the current execution")
    handle = ref.startswith("result:")
    if handle and not malformed_handle:
        issued = bridge.store.db.execute(
            "SELECT thread,payload FROM events WHERE seq=? AND kind='tool-view'",
            (int(ref.split(":", 1)[1]),),
        ).fetchone()
        if issued is not None:
            payload = json.loads(issued[1])
            if (
                issued[0] != bridge.thread
                or payload.get("role") != role
                or execution is None
                or payload.get("execution_id") != execution["execution_id"]
            ):
                raise AgentBoundaryError("Result handle belongs to another role/thread/execution")
            ref = payload["ref"]
    row = bridge.store.db.execute(
        "SELECT payload FROM events WHERE thread=? AND kind='tool-view' "
        "AND json_extract(payload,'$.role')=? AND json_extract(payload,'$.ref')=? "
        "AND json_extract(payload,'$.execution_id')=? ORDER BY seq DESC LIMIT 1",
        (bridge.thread, role, ref, execution["execution_id"] if execution else None),
    ).fetchone()
    if row is None:
        known = bridge.store.db.execute(
            "SELECT 1 FROM events WHERE kind='tool-view' "
            "AND json_extract(payload,'$.ref')=? LIMIT 1",
            (ref,),
        ).fetchone()
        unregistered = bridge.store.root / "agent-work" / bridge.thread / ref[1:]
        if (
            known
            or execution is None
            or role not in {"target", "site"}
            or (not handle and (unregistered.exists() or unregistered.is_symlink()))
        ):
            raise AgentBoundaryError("Result was not supplied to this role/execution")
        # No fuzzy matching or implicit reads. A mistyped, never-issued ID can be
        # repaired using only IDs already supplied to this role and execution.
        recent = bridge.store.db.execute(
            "SELECT json_extract(payload,'$.ref') AS ref, MAX(seq) AS issuance FROM events "
            "WHERE thread=? AND kind='tool-view' AND json_extract(payload,'$.role')=? "
            "AND json_extract(payload,'$.execution_id')=? "
            "GROUP BY ref ORDER BY MAX(seq) DESC LIMIT 21",
            (bridge.thread, role, execution["execution_id"]),
        ).fetchall()
        raise UnknownEvidenceResult(
            [{"ref": f"result:{r[1]}", "original_ref": r[0]} for r in recent[:20]],
            more_available=len(recent) > 20,
        )
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
    return query


def navigation_hint(value: Any) -> str:
    if isinstance(value, dict):
        return (
            "Available object keys: "
            + compact(list(value)[:30])[:2000]
            + "; field types: "
            + compact(result_navigation(value)["field_types"])[:2000]
            + (
                "; readable projection aliases: " + compact(alias_navigation(value, source=True))
                if alias_navigation(value, source=True)
                else ""
            )
        )
    if isinstance(value, list):
        return f"This is a list of {len(value)} items; use a nonnegative index within its length."
    return "This is a scalar; read this value without an additional child selector."


def scoped_value(value: Any, query: ReadEvidenceResult) -> tuple[Any, list[str]]:
    if query.fields is not None:
        if not isinstance(value, dict) or len(set(query.fields)) != len(query.fields):
            raise InvalidFieldProjection(
                "Sibling projection requires distinct existing object keys. "
                + navigation_hint(value)
            )
        return {
            key: scoped_value(value, ReadEvidenceResult(ref=query.ref, path=[key]))[0]
            for key in query.fields
        }, []
    path = [query.field] if query.field is not None else query.path or []
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
                elif key in {"candidate_overview", "topology_summary"} and isinstance(
                    value.get("candidates"), dict
                ):
                    value = {**value, **receptor_overview_projection(value)}
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
        if all(item is None for item in (query.field, query.fields, query.path)):
            if query.offset:
                raise InvalidFieldProjection("Choose a list/text path before using an offset.")
            return compact(
                {
                    "status": "result-navigation",
                    "full_result": query.ref,
                    "navigation": result_navigation(full),
                    "instruction": "No source content was read. Select an existing typed field; "
                    "use path for one field/nested traversal or fields for siblings.",
                }
            )
        value, selected_path = scoped_value(full, query)
        source = {"full_result": query.ref, **alias_navigation(full, source=True)}
        selector = {"path": selected_path}
        if query.fields is not None:
            selector = {"fields": query.fields}
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
                    + "Selected type: "
                    + result_navigation(value)["value_type"]
                    + ". "
                    + navigation_hint(full)
                    + " Call read_evidence_result(ref) without selectors for typed navigation "
                    "and any retrieval continuation. Then select an actual list/text field."
                )
            page, next_offset = value, None
            if len(compact(page)) > 4400:
                return compact(
                    {
                        "status": "narrower-scope-required",
                        **selector,
                        "available_fields": list(value)[:30] if isinstance(value, dict) else [],
                        "instruction": (
                            "Read a child field; the full object was not supplied. "
                            "For receptor topology metadata use path=['topology_summary']; "
                            "state/membrane can be read with fields=['state','membrane',"
                            "'topology_summary']. For one candidate use "
                            "path=['candidate_overview', MODE, INDEX]. Full residue arrays "
                            "remain available at their original paths."
                            if alias_navigation(full, source=True)
                            else "Read a child field; the full object was not supplied."
                        ),
                        **source,
                    }
                )
        return compact({"value": page, "next_offset": next_offset, **selector, **source})

    return StructuredTool.from_function(
        name="read_evidence_result",
        coroutine=read,
        args_schema=ReadEvidenceResult,
        description=(
            "Read a verified full_result supplied to this role/execution. Choose keys from "
            "that actual result, not from another gate's schema. With only ref, inspect "
            "its field types/navigation without source content. Otherwise use one of field "
            "(one top-level key), fields (sibling keys), or path (nested traversal). "
            "Use offset/limit for list pages, offset for text pages. Use focused fields; "
            "do not read the whole artifact sequentially."
        ),
    )
