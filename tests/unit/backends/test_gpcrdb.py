from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from easydesign.backends.gpcrdb import GpcrdbAdapter
from easydesign.backends.target_sources.remote import ScientificHttpClient
from easydesign.core import BackendContractError


def _client(tmp_path: Path, handler: httpx.MockTransport) -> ScientificHttpClient:
    return ScientificHttpClient(
        evidence_dir=tmp_path / "evidence",
        cache_root=tmp_path / "cache",
        client=httpx.Client(transport=handler),
        sleep=lambda _: None,
    )


def test_gpcrdb_adapter_preserves_typed_context_and_retrieval_evidence(
    tmp_path: Path,
) -> None:
    responses: dict[str, object] = {
        "/services/protein/adrb2_human/": {
            "entry_name": "adrb2_human",
            "accession": "P07550",
            "family": "001_001_003_008",
            "residue_numbering_scheme": "gpcrdba",
        },
        "/services/proteinfamily/001_001_003_008/": {
            "slug": "001_001_003_008",
            "name": "Beta-2 adrenergic receptor",
            "parent": {"slug": "001", "name": "Class A (Rhodopsin)"},
        },
        "/services/proteinfamily/001/": {
            "slug": "001",
            "name": "Class A (Rhodopsin)",
            "parent": {"slug": "000", "name": "Parent family"},
        },
        "/services/residues/extended/adrb2_human/": [
            {
                "sequence_number": 113,
                "amino_acid": "D",
                "protein_segment": "TM3",
                "display_generic_number": "3x32",
            }
        ],
        "/services/structure/protein/adrb2_human/": [],
        "/services/structure/protein/adrb2_human/representative/": [],
        "/services/mutants/adrb2_human/": [],
        "/services/ligands/adrb2_human/": [],
    }

    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=responses[request.url.path], request=request)

    client = _client(tmp_path, httpx.MockTransport(respond))
    context = GpcrdbAdapter(client).fetch_receptor_context(entry="adrb2_human")

    assert context.status == "resolved"
    assert context.identity.accession == "P07550"
    assert context.family["class"] == "Class A (Rhodopsin)"
    assert context.topology["residues"][0]["display_generic_number"] == "3x32"
    assert len(context.retrieval_records) == len(responses)
    assert all(record.method == "GET" for record in context.retrieval_records)
    assert all(record.response_sha256 for record in context.retrieval_records)
    assert all(
        (tmp_path / "evidence" / record.artifact_name).is_file()
        for record in context.retrieval_records
    )
    legacy = context.legacy_projection()
    assert len(legacy["provenance"]) == len(responses)
    assert legacy["provenance"][0]["data_sha256"]


def test_gpcrdb_identifier_conflict_is_retained_and_blocks_resolved_status(
    tmp_path: Path,
) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/services/structure/2RH1/":
            payload: object = {
                "pdb_code": "2RH1",
                "protein": "adrb1_human",
                "preferred_chain": "A",
                "state": "inactive",
            }
        elif path == "/services/protein/adrb2_human/":
            payload = {
                "entry_name": "adrb2_human",
                "accession": "P07550",
                "family": "001_001",
            }
        elif path == "/services/proteinfamily/001_001/":
            payload = {"slug": "001_001", "name": "Aminergic receptors"}
        else:
            payload = []
        return httpx.Response(200, json=payload, request=request)

    context = GpcrdbAdapter(
        _client(tmp_path, httpx.MockTransport(respond))
    ).fetch_receptor_context(entry="adrb2_human", pdb_code="2rh1")

    assert context.status == "identifier_conflict"
    assert context.identity.status == "identifier_conflict"
    assert any(item.code == "identifier_conflict" for item in context.warnings)
    assert context.structures["selected"]["protein"] == "adrb1_human"


def test_optional_gpcrdb_failure_is_partial_not_an_empty_biological_result(
    tmp_path: Path,
) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/services/protein/adrb2_human/":
            return httpx.Response(
                200,
                json={
                    "entry_name": "adrb2_human",
                    "accession": "P07550",
                    "family": "001_001",
                },
                request=request,
            )
        if path == "/services/proteinfamily/001_001/":
            return httpx.Response(
                200,
                json={"slug": "001_001", "name": "Aminergic receptors"},
                request=request,
            )
        if path == "/services/residues/extended/adrb2_human/":
            return httpx.Response(404, json={"detail": "missing"}, request=request)
        return httpx.Response(200, json=[], request=request)

    context = GpcrdbAdapter(
        _client(tmp_path, httpx.MockTransport(respond))
    ).fetch_receptor_context(entry="adrb2_human")

    assert context.status == "partial"
    assert context.topology["residues"] is None
    assert any(
        item.code == "optional_gpcrdb_endpoint_failed" for item in context.warnings
    )
    assert any(
        record.status_code == 404 and record.error_type == "http-status-error"
        for record in context.retrieval_records
    )


def test_gpcrdb_identifier_rejects_path_injection_before_http(tmp_path: Path) -> None:
    requests = 0

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal requests
        requests += 1
        return httpx.Response(200, json={}, request=request)

    adapter = GpcrdbAdapter(_client(tmp_path, httpx.MockTransport(respond)))

    with pytest.raises(BackendContractError, match="非法 GPCRdb entry"):
        adapter.fetch_receptor_context(entry="../adrb2")

    assert requests == 0
