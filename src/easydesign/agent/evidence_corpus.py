"""Small scoped reading views over existing project evidence ArtifactRefs.

No downloader, database, artifact registry or scientific authority lives here.
Original responses and derived chunks stay durable; only selected passages enter tools.
"""

from __future__ import annotations

import base64
import json
import re
from typing import Any, Literal

from pydantic import Field

from easydesign.core import ArtifactRef

from .contracts import AgentBoundaryError, ShortText, SourceSelectionRequired, StrictDTO
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
    source_id: str = Field(default="", max_length=80)
    cursor: str = Field(default="", max_length=2000)
    page_size: int = Field(default=2, ge=1, le=3)


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

    def selections(self) -> dict[str, Any]:
        binding = identity(self.bridge.binding())
        rows = self.bridge.store.db.execute(
            "SELECT payload FROM events WHERE thread=? AND kind='evidence-selection' ORDER BY seq",
            (self.bridge.thread,),
        )
        result = {}
        for row in rows:
            value = json.loads(row[0])
            if value["target_binding"] == binding:
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
        binding = identity(self.bridge.binding())
        documents = {}
        for row in rows:
            event = json.loads(row[0])
            if event["target_binding"] != binding:
                continue
            value = self.bridge.document(event["ref"])
            for card in value["cards"]:
                if not card.get("corpus_ref"):
                    continue
                for ref in card["source_refs"]:
                    confined(
                        self.bridge.project,
                        ArtifactRef.model_validate(ref).verify(self.bridge.project),
                    )
                documents[card["corpus_ref"]["sha256"]] = card
        return list(documents.values())

    def retrieve(self, request: RetrieveEvidence) -> dict[str, Any]:
        selected = self.selections()
        docs = [
            c
            for c in self.documents()
            if c["need"] == request.need
            and (
                not request.source_id
                or source_key(c["provider"], c["identifier"]) == request.source_id
            )
            and selected.get(
                source_key(c["provider"], c["identifier"]) + ":" + request.need, {}
            ).get("selection")
            == "SELECTED"
        ]
        view = identity(
            {
                "thread": self.bridge.thread,
                "binding": self.bridge.binding(),
                "need": request.need,
                "question": request.question,
                "source": request.source_id,
                "docs": [c["corpus_ref"] for c in docs],
            }
        )
        offset = 0
        if request.cursor:
            try:
                decoded = json.loads(base64.urlsafe_b64decode(request.cursor))
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
        for card in docs:
            corpus = self.bridge.document(card["corpus_ref"])
            for chunk in corpus["chunks"]:
                score = sum(t in (chunk["location"] + " " + chunk["text"]).lower() for t in terms)
                if score or request.source_id:
                    hits.append((score, card, chunk))
        hits.sort(key=lambda hit: (-hit[0], hit[1]["card_id"], hit[2]["chunk"]))
        cards = []
        for _, source, chunk in hits[offset : offset + request.page_size]:
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
            "topic": next(k for k, v in NEEDS.items() if v == request.need),
            "question": request.question,
            "need": request.need,
            "status": "UNRESOLVED",
            "cards": cards,
            "errors": [],
            "matching_chunks": len(hits),
            "next_cursor": cursor,
            "target_binding": identity(self.bridge.binding()),
            "authority": (
                "Partial source passages; relevance and entailment require owner/Judge review."
            ),
        }
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
        return {k: v for k, v in result.items() if k not in {"target_binding", "query_id"}} | {
            "cards": [{k: v for k, v in c.items() if k != "source_refs"} for c in cards]
        }


def corpus_tools(bridge: Any) -> list[Any]:
    from langchain_core.tools import StructuredTool

    async def select(**arguments: Any) -> str:
        return compact(EvidenceCorpus(bridge).select(SelectEvidence.model_validate(arguments)))

    async def retrieve(**arguments: Any) -> str:
        return compact(EvidenceCorpus(bridge).retrieve(RetrieveEvidence.model_validate(arguments)))

    return [
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
                "rot:P07550). Returns at most 3 chunks with location and continuation"
                " cursor; use cursor for the next page. Full sources stay durable out"
                "side conversation."
            ),
        ),
    ]
