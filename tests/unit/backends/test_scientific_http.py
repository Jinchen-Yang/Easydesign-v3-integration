from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from easydesign.backends.target_sources.remote import (
    RCSB_SEQUENCE_RESULT_LIMIT,
    ScientificHttpClient,
    _scientific_ssl_context,
    rcsb_sequence_search,
)
from easydesign.core import BackendContractError


def test_scientific_ssl_context_keeps_certificate_verification_enabled() -> None:
    context = _scientific_ssl_context()

    assert context.verify_mode.name == "CERT_REQUIRED"
    assert context.check_hostname is True
    assert context.get_ca_certs()


def test_rcsb_sequence_search_uses_bounded_ranked_result_page(tmp_path: Path) -> None:
    request_body: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        request_body.update(json.loads(request.content))
        return httpx.Response(200, json={"result_set": []}, request=request)

    adapter = ScientificHttpClient(
        evidence_dir=tmp_path / "evidence",
        cache_root=tmp_path / "cache",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    rcsb_sequence_search(adapter, "ACDE")

    options = request_body["request_options"]
    assert isinstance(options, dict)
    assert options["paginate"] == {"start": 0, "rows": RCSB_SEQUENCE_RESULT_LIMIT}
    assert options["sort"] == [{"sort_by": "score", "direction": "desc"}]


def test_scientific_http_retries_429_and_snapshots_response(tmp_path: Path) -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(429, headers={"Retry-After": "0"}, request=request)
        return httpx.Response(
            200,
            json={"primaryAccession": "P00533"},
            headers={"ETag": "test-etag"},
            request=request,
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = ScientificHttpClient(
        evidence_dir=tmp_path / "evidence",
        cache_root=tmp_path / "cache",
        client=client,
        sleep=lambda _: None,
    )

    response = adapter.request(
        "GET",
        "https://example.test/uniprot/P00533.json",
        artifact_name="record.json",
    )

    assert attempts == 2
    assert response.json()["primaryAccession"] == "P00533"
    assert response.artifact_path.is_file()
    assert [record.status_code for record in adapter.records] == [429, 200]
    assert adapter.records[0].cache_status == "retryable-http-error"
    assert adapter.records[1].etag == "test-etag"


def test_scientific_http_404_is_not_retried_and_is_snapshotted(
    tmp_path: Path,
) -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(
            404,
            json={"message": "not found"},
            headers={"X-Request-Id": "missing"},
            request=request,
        )

    adapter = ScientificHttpClient(
        evidence_dir=tmp_path / "evidence",
        cache_root=tmp_path / "cache",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=lambda _: None,
    )

    with pytest.raises(BackendContractError, match="status=404"):
        adapter.request(
            "GET",
            "https://example.test/missing.json",
            artifact_name="missing.json",
        )

    assert attempts == 1
    assert len(adapter.records) == 1
    assert adapter.records[0].status_code == 404
    assert adapter.records[0].cache_status == "http-error"
    assert adapter.records[0].error_type == "http-status-error"
    assert (tmp_path / "evidence" / adapter.records[0].artifact_name).is_file()
    assert not list((tmp_path / "cache").glob("*.bin"))


def test_scientific_http_exhausted_5xx_preserves_every_attempt(
    tmp_path: Path,
) -> None:
    adapter = ScientificHttpClient(
        evidence_dir=tmp_path / "evidence",
        cache_root=tmp_path / "cache",
        max_attempts=3,
        client=httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    503,
                    content=b"temporarily unavailable",
                    request=request,
                )
            )
        ),
        sleep=lambda _: None,
    )

    with pytest.raises(BackendContractError, match="status=503"):
        adapter.request(
            "GET",
            "https://example.test/unavailable",
            artifact_name="unavailable.txt",
        )

    assert [record.status_code for record in adapter.records] == [503, 503, 503]
    assert len(
        {record.artifact_name for record in adapter.records}
    ) == 3
    assert all(record.cache_status == "retryable-http-error" for record in adapter.records)


def test_scientific_http_timeout_preserves_network_error_attempts(
    tmp_path: Path,
) -> None:
    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    adapter = ScientificHttpClient(
        evidence_dir=tmp_path / "evidence",
        cache_root=tmp_path / "cache",
        max_attempts=2,
        client=httpx.Client(transport=httpx.MockTransport(timeout)),
        sleep=lambda _: None,
    )

    with pytest.raises(BackendContractError, match="远程请求失败"):
        adapter.request(
            "GET",
            "https://example.test/timeout",
            artifact_name="timeout.json",
        )

    assert [record.status_code for record in adapter.records] == [0, 0]
    assert all(record.error_type == "ReadTimeout" for record in adapter.records)
    assert all(
        (tmp_path / "evidence" / record.artifact_name).is_file()
        for record in adapter.records
    )


def test_offline_cache_miss_is_explicit(tmp_path: Path) -> None:
    adapter = ScientificHttpClient(
        evidence_dir=tmp_path / "evidence",
        cache_root=tmp_path / "cache",
        cache_mode="offline",
        client=httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(500, request=request)
            )
        ),
    )

    with pytest.raises(BackendContractError, match="offline cache miss"):
        adapter.request(
            "GET",
            "https://example.test/data.json",
            artifact_name="data.json",
        )


def test_prefer_cache_copies_consumed_bytes_into_run(tmp_path: Path) -> None:
    body = json.dumps({"ok": True}).encode()
    first = ScientificHttpClient(
        evidence_dir=tmp_path / "run-one",
        cache_root=tmp_path / "cache",
        client=httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, content=body, request=request)
            )
        ),
    )
    first.request("GET", "https://example.test/data.json", artifact_name="data.json")
    second = ScientificHttpClient(
        evidence_dir=tmp_path / "run-two",
        cache_root=tmp_path / "cache",
        cache_mode="prefer-cache",
        client=httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(500, request=request)
            )
        ),
    )

    cached = second.request(
        "GET",
        "https://example.test/data.json",
        artifact_name="data.json",
    )

    assert cached.content == body
    assert cached.record.cache_status == "hit"
    assert cached.artifact_path.read_bytes() == body
