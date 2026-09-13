"""Small scoped reading views over existing project evidence ArtifactRefs.

No downloader, database, artifact registry or scientific authority lives here.
Original responses and derived chunks stay durable; only selected passages enter tools.
"""

from __future__ import annotations

import base64
import json
import re
from typing import Any, Literal

from pydantic import Field, model_validator

from easydesign.core import ArtifactRef

from .contracts import (
    AgentBoundaryError,
    EvidenceCursorQueryMismatch,
    EvidenceRetrievalQueryMismatch,
    ShortText,
    SourceSelectionRequired,
    StaleEvidenceCursor,
    StrictDTO,
)
from .session_store import compact, confined, identity

EvidenceNeed = Literal[
    "TARGET_IDENTITY",
    "STRUCTURE_STATE",
    "LIGAND_PARTNER",
    "MUTAGENESIS",
    "FUNCTIONAL_MECHANISM",
    "KNOWN_EPITOPE",
    "COMPETITION",
    "PPI_INTERFACE",
    "GLYCAN_PTM",
    "CONSERVATION",
]
NEEDS = {
    "identity": "TARGET_IDENTITY",
    "state": "STRUCTURE_STATE",
    "ligand-partner": "LIGAND_PARTNER",
    "mutagenesis": "MUTAGENESIS",
    "function": "FUNCTIONAL_MECHANISM",
    "epitope": "KNOWN_EPITOPE",
    "competition": "COMPETITION",
    "structure-complex": "PPI_INTERFACE",
    "ptm-glycan": "GLYCAN_PTM",
    "conservation": "CONSERVATION",
}


class SelectEvidence(StrictDTO):
    provider: Literal["EuropePMC", "UniProt", "RCSB", "GPCRdb"]
    identifier: str = Field(min_length=1, max_length=40, pattern=r"^[A-Za-z0-9_.-]+$")
    need: EvidenceNeed
    selection: Literal["SELECTED", "DEFERRED", "EXCLUDED"]
    reason: ShortText


class RetrieveEvidence(StrictDTO):
    need: EvidenceNeed
    question: ShortText
    source_id: str = Field(
        default="",
        max_length=80,
        description="Exact Provider:IDENTIFIER source_id from acquisition, never a source card_id.",
    )
    selection_reason: ShortText | None = Field(
        default=None,
        description="For a new query with exact source_id: explicitly SELECT this acquired "
        "source for need with your scientific reason, then read it in the same call. "
        "Include when changing need or unsure of its selection. Omit only when already "
        "selected for this exact need. Not scientific approval; not allowed with cursor.",
    )
    feature_types: list[str] = Field(
        default_factory=list,
        max_length=8,
        description="Optional exact UniProt feature types, e.g. "
        "['Topological domain','Transmembrane'] or ['Glycosylation','Disulfide bond']. "
        "Restrict to these original source annotations; omit for ordinary text research.",
    )
    cursor: str = Field(
        default="",
        max_length=2000,
        description=(
            "Opaque next_cursor. Keep need, source_id and question EXACTLY unchanged when "
            "continuing; omit cursor to ask a new question."
        ),
    )
    page_size: int = Field(default=2, ge=1, le=3)

    @model_validator(mode="after")
    def explicit_selection_scope(self) -> RetrieveEvidence:
        if self.selection_reason is not None:
            if not self.selection_reason.strip() or not self.source_id or self.cursor:
                raise ValueError(
                    "selection_reason needs a nonblank reason, exact source_id and a new "
                    "query without cursor; use continue_evidence for an issued cursor"
                )
        return self


class ContinueEvidence(StrictDTO):
    cursor: str = Field(
        min_length=1,
        max_length=2000,
        description="Copy the exact next_cursor for the desired source view. "
        "Runtime restores its query; never edit or decode it.",
    )


def source_key(provider: str, identifier: str) -> str:
    return f"{provider}:{identifier.upper()}"


def chunk_sections(sections: list[dict[str, str]]) -> list[dict[str, Any]]:
    chunks = []
    for section in sections:
        text = section["text"]
        start = 0
        while start < len(text):
            end = min(start + 1500, len(text))
            if end < len(text):
                boundary = text.rfind(" ", start + 900, end)
                if boundary > start:
                    end = boundary
            chunks.append(
                {
                    "location": section["location"],
                    "start": start,
                    "end": end,
                    "text": text[start:end],
                }
            )
            start = end if end == len(text) else max(start + 1, end - 120)
    return [{"chunk": i, **chunk} for i, chunk in enumerate(chunks)]


class EvidenceCorpus:
    def __init__(self, bridge: Any) -> None:
        self.bridge = bridge

    def current_relation(self, source_id: str, acquired_binding: str, refs: Any = None) -> str:
        """Only the exact verified canonical proposal can carry its source across a revision.

        Other old sources remain durable, but need an explicit current selection. This is
        one existing event relation, not transitive binding inference or a new graph store.
        """
        current = identity(self.bridge.binding())
        if acquired_binding == current:
            return "current-state-selection"
        rows = self.bridge.store.db.execute(
            "SELECT payload FROM events WHERE kind='canonical-reference-proposal' ORDER BY seq"
        )
        for row in rows:
            event = json.loads(row[0])
            if (
                event["prior_binding"] == acquired_binding
                and event["target_binding"] == current
                and source_id == source_key("UniProt", event["accession"])
                and (refs is None or refs == event["source_refs"])
            ):
                records = [self.bridge.document(ref) for ref in event["source_refs"]]
                if not any(r.get("primaryAccession") == event["accession"] for r in records):
                    raise AgentBoundaryError("Canonical binding source identity changed")
                return "current-canonical-reference"
        return "historical-target"

    def source_view(self, card: dict[str, Any], acquired_binding: str) -> dict[str, Any]:
        acquired_binding = card.get("binding_context", {}).get("acquired_binding", acquired_binding)
        for ref in card["source_refs"]:
            confined(
                self.bridge.project, ArtifactRef.model_validate(ref).verify(self.bridge.project)
            )
        source_id = source_key(card["provider"], card["identifier"])
        return {
            **card,
            "source_id": source_id,
            "source_status": "VERIFIED"
            if card.get("corpus_ref") or card["card_id"].startswith("passage-")
            else "VERIFIED_DERIVATION"
            if card["evidence_level"].startswith("deterministic-")
            else "DISCOVERY_LEAD",
            "project_evidence_id": identity(
                {
                    "project": self.bridge.project.name,
                    "source": source_id,
                    "refs": card["source_refs"],
                }
            ),
            "binding_context": {
                "acquired_binding": acquired_binding,
                "current_binding": identity(self.bridge.binding()),
                "relation": self.current_relation(source_id, acquired_binding, card["source_refs"]),
                "relevance": "unresolved; selection is not entailment or target equivalence",
            },
        }

    def selections(self) -> dict[str, Any]:
        binding = identity(self.bridge.binding())
        rows = self.bridge.store.db.execute(
            "SELECT payload FROM events WHERE thread=? AND kind='evidence-selection' ORDER BY seq",
            (self.bridge.thread,),
        )
        result = {}
        for row in rows:
            value = json.loads(row[0])
            if (
                value["target_binding"] == binding
                or self.current_relation(value["source_id"], value["target_binding"])
                == "current-canonical-reference"
            ):
                result[value["source_id"] + ":" + value["need"]] = value
        return result

    def select(self, request: SelectEvidence) -> dict[str, Any]:
        value = {
            **request.model_dump(mode="json"),
            "source_id": source_key(request.provider, request.identifier),
            "target_binding": identity(self.bridge.binding()),
        }
        self.bridge.store.event(self.bridge.thread, "evidence-selection", value)
        return {k: v for k, v in value.items() if k != "target_binding"}

    def require_selected(self, provider: str, identifier: str, topic: str) -> None:
        key = source_key(provider, identifier) + ":" + NEEDS[topic]
        if self.selections().get(key, {}).get("selection") != "SELECTED":
            raise SourceSelectionRequired(provider, identifier, NEEDS[topic])

    def index(self, card: dict[str, Any], topic: str) -> dict[str, Any]:
        sections = card.pop("_sections", None) or [
            {"location": card["evidence_level"], "text": card["passage"]}
        ]
        corpus = {
            "source_id": source_key(card["provider"], card["identifier"]),
            "need": NEEDS[topic],
            "source_refs": card["source_refs"],
            "chunks": chunk_sections(sections),
        }
        ref = self.bridge.persist("evidence-corpus", corpus)
        return {
            **card,
            "corpus_ref": ref,
            "chunk_count": len(corpus["chunks"]),
            "need": NEEDS[topic],
        }

    def documents(self) -> list[dict[str, Any]]:
        """Project durable corpus; this does not inject other threads' current views."""
        rows = self.bridge.store.db.execute(
            "SELECT payload FROM events WHERE kind='evidence-research' ORDER BY seq"
        )
        documents = {}
        for row in rows:
            event = json.loads(row[0])
            value = self.bridge.document(event["ref"])
            for card in value["cards"]:
                if not card.get("corpus_ref"):
                    continue
                for ref in card["source_refs"]:
                    confined(
                        self.bridge.project,
                        ArtifactRef.model_validate(ref).verify(self.bridge.project),
                    )
                documents[card["corpus_ref"]["sha256"]] = self.source_view(
                    card, event["target_binding"]
                )
        return list(documents.values())

    def uniprot_features(self, card: dict[str, Any]) -> list[dict[str, Any]]:
        records = [self.bridge.document(ref) for ref in card["source_refs"]]
        matching = [v for v in records if v.get("primaryAccession") == card["identifier"]]
        if card["provider"] != "UniProt" or len(matching) != 1:
            raise AgentBoundaryError("Feature scope requires one verified UniProt record")
        return list(matching[0].get("features", []))

    def continue_page(self, request: ContinueEvidence) -> dict[str, Any]:
        """Continue a verified issued view without model retyping its scientific query."""
        owned = []
        for event in reversed(self.bridge.store.events(self.bridge.thread)):
            if event["kind"] != "evidence-view":
                continue
            prior = self.bridge.document(event["payload"]["ref"])
            if prior["next_cursor"] == request.cursor:
                # The existing reader independently checks current binding, selection,
                # source bytes and the exact issued cursor; no stale-view auto-reset.
                return self.retrieve(
                    RetrieveEvidence(
                        need=prior["need"],
                        question=prior["question"],
                        source_id=prior["source_id"],
                        feature_types=prior.get("feature_types", []),
                        page_size=prior.get("page_size", 2),
                        cursor=request.cursor,
                    )
                )
            owned.append(prior.get("query_id", "").rsplit("-", 1)[0])
        try:
            decoded = json.loads(base64.urlsafe_b64decode(request.cursor))
        except (ValueError, TypeError):
            decoded = None
        if isinstance(decoded, dict) and decoded.get("view") in owned:
            raise EvidenceRetrievalQueryMismatch(
                "Unissued cursor for an owned view rejected without reading/advancing. "
                "Copy its exact returned next_cursor; never reset the encoded offset."
            )
        raise AgentBoundaryError("Unknown or foreign continuation cursor")

    def retrieve(self, request: RetrieveEvidence) -> dict[str, Any]:
        candidates = [
            c
            for c in self.documents()
            if (
                not request.source_id
                or source_key(c["provider"], c["identifier"]) == request.source_id
            )
        ]
        if request.selection_reason is not None:
            # documents() verifies original ArtifactRefs before any selection mutation.
            # Only the exact named, already acquired source is selected; no discovery,
            # inferred relevance, cross-need propagation or automatic approval occurs.
            if not candidates:
                raise EvidenceRetrievalQueryMismatch(
                    "Atomic selection requires an exact acquired source_id. No source was "
                    "selected or acquired. Use an acquisition receipt's source_id."
                )
            for candidate in candidates:
                self.bridge.document(candidate["corpus_ref"])
            source = candidates[0]
            self.select(
                SelectEvidence(
                    provider=source["provider"],
                    identifier=source["identifier"],
                    need=request.need,
                    selection="SELECTED",
                    reason=request.selection_reason,
                )
            )
        selected = self.selections()
        docs = [
            c
            for c in candidates
            if selected.get(
                source_key(c["provider"], c["identifier"]) + ":" + request.need, {}
            ).get("selection")
            == "SELECTED"
        ]
        if not request.cursor and request.source_id and candidates and not docs:
            # An acquired source selected for another need is not an empty evidence
            # search. Ask for an explicit relevance choice before reading any passage.
            source = candidates[0]
            raise SourceSelectionRequired(source["provider"], source["identifier"], request.need)
        view = identity(
            {
                "thread": self.bridge.thread,
                "binding": self.bridge.binding(),
                "need": request.need,
                "question": request.question,
                "source": request.source_id,
                **({"feature_types": request.feature_types} if request.feature_types else {}),
                "docs": [c["corpus_ref"] for c in docs],
            }
        )
        offset = 0
        if request.cursor:
            try:
                decoded = json.loads(base64.urlsafe_b64decode(request.cursor))
                if not isinstance(decoded, dict):
                    raise ValueError("invalid cursor object")
                prior_view = None
                issued = False
                owned_view = False
                for event in reversed(self.bridge.store.events(self.bridge.thread)):
                    if event["kind"] != "evidence-view":
                        continue
                    prior = self.bridge.document(event["payload"]["ref"])
                    if prior["next_cursor"] == request.cursor:
                        prior_view, issued = prior, True
                        break
                    if prior.get("query_id", "").rsplit("-", 1)[0] == decoded.get("view"):
                        owned_view = True
                if not issued:
                    if owned_view:
                        raise EvidenceRetrievalQueryMismatch(
                            "The cursor names a verified view in this thread but its bytes/offset "
                            "were never issued. The altered token is rejected; no page was read "
                            "or advanced. Omit cursor for a new question, or copy an exact "
                            "returned next_cursor. Never decode and reset its offset."
                        )
                    raise ValueError("unknown or foreign cursor")
                if decoded.get("view") != view:
                    if prior_view is not None:
                        prior = prior_view
                        same_scope = (
                            prior["target_binding"] == identity(self.bridge.binding())
                            and prior["need"] == request.need
                            and prior.get("source_id") == request.source_id
                            and prior.get("feature_types", []) == request.feature_types
                        )
                        expected_view = identity(
                            {
                                "thread": self.bridge.thread,
                                "binding": self.bridge.binding(),
                                "need": request.need,
                                "question": prior["question"],
                                "source": request.source_id,
                                **(
                                    {"feature_types": request.feature_types}
                                    if request.feature_types
                                    else {}
                                ),
                                "docs": [c["corpus_ref"] for c in docs],
                            }
                        )
                        if same_scope and expected_view == decoded["view"]:
                            raise EvidenceCursorQueryMismatch(
                                "This verified cursor continues question="
                                + compact(prior["question"])
                                + ". Repeat that exact question, need and source_id to continue, "
                                "or omit cursor to start a new question. No page was delivered."
                            )
                        raise StaleEvidenceCursor(
                            "Cursor belongs to another question/thread/evidence view; "
                            "the known owned view is no longer current"
                        )
                if (
                    decoded["view"] != view
                    or not isinstance(decoded["offset"], int)
                    or decoded["offset"] < 0
                ):
                    raise ValueError("wrong view")
                offset = decoded["offset"]
            except (ValueError, KeyError, TypeError) as exc:
                raise AgentBoundaryError(
                    "Cursor belongs to another question/thread/evidence view"
                ) from exc
        terms = set(re.findall(r"[a-z0-9]{3,}", request.question.lower())) - {
            "the",
            "and",
            "does",
            "this",
            "that",
            "with",
            "for",
            "are",
            "what",
        }
        hits = []
        feature_scope = {}
        for card in docs:
            corpus = self.bridge.document(card["corpus_ref"])
            feature_locations = None
            if request.feature_types:
                if card["provider"] != "UniProt":
                    continue
                features = self.uniprot_features(card)
                available_types = sorted(
                    {feature["type"] for feature in features if feature.get("type")}
                )
                feature_scope[card["source_id"]] = {
                    "available_types": available_types,
                    "unmatched_requested_types": sorted(
                        set(request.feature_types) - set(available_types)
                    ),
                    "note": "Literal source types only; "
                    "an unmatched filter is not biological absence.",
                }
                feature_locations = {
                    f"features[{i}]"
                    for i, feature in enumerate(features)
                    if feature.get("type") in request.feature_types
                }
            for chunk in corpus["chunks"]:
                if feature_locations is not None and chunk["location"] not in feature_locations:
                    continue
                score = sum(t in (chunk["location"] + " " + chunk["text"]).lower() for t in terms)
                if score or request.source_id or request.feature_types:
                    hits.append((score, card, chunk))
        hits.sort(key=lambda hit: (-hit[0], hit[1]["card_id"], hit[2]["chunk"]))
        cards = []
        for _, source, chunk in hits[offset : offset + request.page_size]:
            selection = selected[source["source_id"] + ":" + request.need]
            cards.append(
                {
                    **{
                        k: v
                        for k, v in source.items()
                        if k not in {"passage", "corpus_ref", "chunk_count"}
                    },
                    "card_id": "passage-"
                    + identity({"source": source["corpus_ref"], "chunk": chunk["chunk"]})[:24],
                    "source_id": source_key(source["provider"], source["identifier"]),
                    "need": request.need,
                    "selection_provenance": {
                        "thread": self.bridge.thread,
                        "need": selection["need"],
                        "reason": selection["reason"],
                        "selection": selection["selection"],
                        "selected_binding": selection["target_binding"],
                    },
                    "passage": chunk["text"],
                    "location": chunk["location"],
                    "chunk": chunk["chunk"],
                    "partial": True,
                }
            )
        next_offset = offset + len(cards)
        cursor = (
            base64.urlsafe_b64encode(
                compact({"view": view, "offset": next_offset}).encode()
            ).decode()
            if next_offset < len(hits)
            else ""
        )
        result = {
            "query_id": view + f"-{offset}",
            "page_size": request.page_size,
            "topic": next(k for k, v in NEEDS.items() if v == request.need),
            "question": request.question,
            "source_id": request.source_id,
            "feature_types": request.feature_types,
            **({"feature_scope": feature_scope} if feature_scope else {}),
            "need": request.need,
            "status": "UNRESOLVED",
            "cards": cards,
            "source_scope": {
                "project_documents": len(candidates),
                "selected_documents": len(docs),
                "selection_required": bool(candidates and not docs),
                "note": (
                    "Selection is per thread and evidence need; "
                    "an empty view is not absence of source evidence."
                ),
            },
            "errors": [],
            "matching_chunks": len(hits),
            "next_cursor": cursor,
            "target_binding": identity(self.bridge.binding()),
            "authority": (
                "Partial source passages; relevance and entailment require owner/Judge review."
            ),
        }
        # Size the exact page after attaching source/binding metadata. A smaller
        # page advances its cursor only over delivered cards; no passage is cut.
        from .evidence_output import scientific_projection

        while len(cards) > 1 and len(compact(scientific_projection(result))) > 4800:
            cards.pop()
            result["next_cursor"] = base64.urlsafe_b64encode(
                compact({"view": view, "offset": offset + len(cards)}).encode()
            ).decode()
        ref = self.bridge.persist("evidence-view", result)
        execution = self.bridge.store.latest_execution(self.bridge.thread)
        self.bridge.store.event(
            self.bridge.thread,
            "evidence-view",
            {
                "target_binding": result["target_binding"],
                "ref": ref,
                "execution_id": execution["execution_id"] if execution else None,
                "cards_supplied": len(cards),
            },
        )
        return {k: v for k, v in result.items() if k != "target_binding"} | {
            "cards": [{k: v for k, v in c.items() if k != "source_refs"} for c in cards]
        }


def corpus_tools(bridge: Any) -> list[Any]:
    from langchain_core.tools import StructuredTool

    async def select(**arguments: Any) -> str:
        return compact(EvidenceCorpus(bridge).select(SelectEvidence.model_validate(arguments)))

    async def retrieve(**arguments: Any) -> str:
        return compact(EvidenceCorpus(bridge).retrieve(RetrieveEvidence.model_validate(arguments)))

    async def continue_page(**arguments: Any) -> str:
        return compact(
            EvidenceCorpus(bridge).continue_page(ContinueEvidence.model_validate(arguments))
        )

    return [
        StructuredTool.from_function(
            name="continue_evidence",
            coroutine=continue_page,
            args_schema=ContinueEvidence,
            description="Read the next page of one issued evidence view. Supply only its exact "
            "next_cursor; runtime restores the same source/question/need/filter and checks "
            "current authority. For a new question use retrieve_evidence without a cursor.",
        ),
        StructuredTool.from_function(
            name="select_evidence",
            coroutine=select,
            args_schema=SelectEvidence,
            description=(
                "Select/defer/exclude one discovered or user-supplied source for a pr"
                "otein-design evidence need, with a scientific reason. Only SELECTED "
                "sources may be acquired deeply or read. Selection is thread-local, n"
                "ot scientific approval."
            ),
        ),
        StructuredTool.from_function(
            name="retrieve_evidence",
            coroutine=retrieve,
            args_schema=RetrieveEvidence,
            description=(
                "Find focused source passages for one evidence need/question in the l"
                "ocal selected corpus. Optional source_id confines reading (e.g. UniP"
                "rot:P07550). Include selection_reason with an exact source_id to select "
                "and read atomically, especially when changing need or unsure of prior "
                "selection. Without it, the exact source/need must already be SELECTED. "
                "Returns at most 3 chunks with location and continuation"
                " cursor; use cursor for the next page. Full sources stay durable out"
                "side conversation."
            ),
        ),
    ]
