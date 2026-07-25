"""UniProt/RCSB 官方 HTTP 服务的有界、可缓存、可留痕客户端。"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from platformdirs import user_cache_path
from pydantic import BaseModel, ConfigDict, Field

from easydesign.core import BackendContractError, sha256_file

UNIPROT_BASE = "https://rest.uniprot.org"
RCSB_SEARCH_URL = "https://search.rcsb.org/rcsbsearch/v2/query"
RCSB_DATA_BASE = "https://data.rcsb.org/rest/v1/core"
RCSB_FILE_BASE = "https://files.rcsb.org/download"


class RetrievalRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    request_id: str
    method: str
    url: str
    parameters: dict[str, Any] | None = None
    request_body_sha256: str | None = None
    status_code: int
    retrieved_at: datetime
    etag: str | None = None
    last_modified: str | None = None
    response_sha256: str
    response_bytes: int = Field(ge=0)
    cache_status: str
    artifact_name: str
    error_type: str | None = None
    error_message: str | None = None


@dataclass(frozen=True, slots=True)
class RetrievedResponse:
    content: bytes
    record: RetrievalRecord
    artifact_path: Path

    def json(self) -> Any:
        try:
            return json.loads(self.content)
        except json.JSONDecodeError as error:
            raise BackendContractError(
                f"远程响应不是合法 JSON: {self.record.url}"
            ) from error


class ScientificHttpClient:
    """明确 online/prefer-cache/offline；online 失败不会偷偷使用旧缓存。"""

    def __init__(
        self,
        *,
        evidence_dir: Path,
        cache_mode: str = "online",
        cache_root: Path | None = None,
        connect_timeout: float = 20,
        read_timeout: float = 120,
        max_attempts: int = 3,
        client: httpx.Client | None = None,
        sleep: Any = time.sleep,
    ) -> None:
        if cache_mode not in {"online", "prefer-cache", "offline"}:
            raise BackendContractError(f"未知 cache_mode: {cache_mode}")
        if max_attempts < 1:
            raise BackendContractError("max_attempts 必须至少为 1")
        self.evidence_dir = evidence_dir
        self.cache_mode = cache_mode
        self.cache_root = (
            cache_root
            if cache_root is not None
            else user_cache_path("easydesign") / "remote-v1"
        )
        self.max_attempts = max_attempts
        self._client = client or httpx.Client(
            timeout=httpx.Timeout(
                connect=connect_timeout,
                read=read_timeout,
                write=read_timeout,
                pool=connect_timeout,
            ),
            follow_redirects=True,
            headers={"User-Agent": "EasyDesign/0.1 Stage01"},
        )
        self._owns_client = client is None
        self._sleep = sleep
        self.records: list[RetrievalRecord] = []

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> ScientificHttpClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    @staticmethod
    def _key(method: str, url: str, params: Any, body: bytes | None) -> str:
        payload = json.dumps(
            {
                "method": method,
                "url": url,
                "params": params,
                "body_sha256": (
                    hashlib.sha256(body).hexdigest() if body is not None else None
                ),
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(payload).hexdigest()

    def request(
        self,
        method: str,
        url: str,
        *,
        artifact_name: str,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> RetrievedResponse:
        body = (
            json.dumps(json_body, sort_keys=True, separators=(",", ":")).encode()
            if json_body is not None
            else None
        )
        key = self._key(method, url, params, body)
        cache_content = self.cache_root / f"{key}.bin"
        cache_meta = self.cache_root / f"{key}.json"
        if self.cache_mode in {"prefer-cache", "offline"} and cache_content.is_file():
            content = cache_content.read_bytes()
            try:
                metadata = json.loads(cache_meta.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                metadata = {}
            return self._publish(
                content=content,
                method=method,
                url=url,
                params=params,
                body=body,
                status_code=int(metadata.get("status_code", 200)),
                headers=metadata.get("headers", {}),
                artifact_name=artifact_name,
                cache_status="hit",
            )
        if self.cache_mode == "offline":
            raise BackendContractError(
                f"offline cache miss: method={method}, url={url}, key={key}"
            )

        last_error: Exception | None = None
        response: httpx.Response | None = None
        for attempt in range(1, self.max_attempts + 1):
            response = None
            try:
                response = self._client.request(
                    method,
                    url,
                    params=params,
                    content=body,
                    headers=(
                        {"Content-Type": "application/json"}
                        if json_body is not None
                        else None
                    ),
                )
            except httpx.RequestError as error:
                last_error = error
                error_name = f"{artifact_name}.network-error.json"
                error_content = json.dumps(
                    {
                        "error_type": type(error).__name__,
                        "message": str(error),
                        "method": method.upper(),
                        "url": url,
                        "attempt": attempt,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ).encode()
                self._publish(
                    content=error_content,
                    method=method,
                    url=url,
                    params=params,
                    body=body,
                    status_code=0,
                    headers={},
                    artifact_name=error_name,
                    cache_status="network-error",
                    error_type=type(error).__name__,
                    error_message=str(error),
                )
                if attempt < self.max_attempts:
                    self._sleep(min(2 ** (attempt - 1), 8))
                    continue
                break
            if response.status_code == 429 or 500 <= response.status_code < 600:
                self._publish(
                    content=response.content,
                    method=method,
                    url=str(response.url),
                    params=params,
                    body=body,
                    status_code=response.status_code,
                    headers=response.headers,
                    artifact_name=artifact_name,
                    cache_status="retryable-http-error",
                    error_type="http-status-error",
                    error_message=f"HTTP {response.status_code}",
                )
                if attempt < self.max_attempts:
                    retry_after = response.headers.get("Retry-After")
                    delay = (
                        float(retry_after)
                        if retry_after is not None and retry_after.isdigit()
                        else min(2 ** (attempt - 1), 8)
                    )
                    self._sleep(delay)
                    continue
            break
        if response is None:
            raise BackendContractError(
                f"远程请求失败: method={method}, url={url}, error={last_error}"
            ) from last_error
        if response.status_code >= 400:
            if response.status_code != 429 and not (
                500 <= response.status_code < 600
            ):
                self._publish(
                    content=response.content,
                    method=method,
                    url=str(response.url),
                    params=params,
                    body=body,
                    status_code=response.status_code,
                    headers=response.headers,
                    artifact_name=artifact_name,
                    cache_status="http-error",
                    error_type="http-status-error",
                    error_message=f"HTTP {response.status_code}",
                )
            raise BackendContractError(
                "远程请求返回错误；不能解释为空候选: "
                f"method={method}, url={url}, status={response.status_code}, "
                f"body={response.text[:512]}"
            )
        content = response.content
        self.cache_root.mkdir(parents=True, exist_ok=True)
        cache_content.write_bytes(content)
        cache_meta.write_text(
            json.dumps(
                {
                    "status_code": response.status_code,
                    "headers": {
                        "etag": response.headers.get("ETag"),
                        "last-modified": response.headers.get("Last-Modified"),
                    },
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        return self._publish(
            content=content,
            method=method,
            url=str(response.url),
            params=params,
            body=body,
            status_code=response.status_code,
            headers=response.headers,
            artifact_name=artifact_name,
            cache_status="miss",
        )

    def _publish(
        self,
        *,
        content: bytes,
        method: str,
        url: str,
        params: dict[str, Any] | None,
        body: bytes | None,
        status_code: int,
        headers: Any,
        artifact_name: str,
        cache_status: str,
        error_type: str | None = None,
        error_message: str | None = None,
    ) -> RetrievedResponse:
        destination = self.evidence_dir / artifact_name
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            counter = 2
            while True:
                candidate = destination.with_name(
                    f"{destination.stem}-{counter:04d}{destination.suffix}"
                )
                if not candidate.exists():
                    destination = candidate
                    artifact_name = candidate.relative_to(
                        self.evidence_dir
                    ).as_posix()
                    break
                counter += 1
        destination.write_bytes(content)
        record = RetrievalRecord(
            request_id=f"request-{len(self.records) + 1:04d}",
            method=method.upper(),
            url=url,
            parameters=params,
            request_body_sha256=(
                hashlib.sha256(body).hexdigest() if body is not None else None
            ),
            status_code=status_code,
            retrieved_at=datetime.now(UTC),
            etag=headers.get("etag") if hasattr(headers, "get") else None,
            last_modified=(
                headers.get("last-modified") if hasattr(headers, "get") else None
            ),
            response_sha256=sha256_file(destination),
            response_bytes=destination.stat().st_size,
            cache_status=cache_status,
            artifact_name=artifact_name,
            error_type=error_type,
            error_message=error_message,
        )
        self.records.append(record)
        return RetrievedResponse(content=content, record=record, artifact_path=destination)


def uniprot_accession(
    client: ScientificHttpClient,
    accession: str,
) -> RetrievedResponse:
    return client.request(
        "GET",
        f"{UNIPROT_BASE}/uniprotkb/{accession}.json",
        artifact_name=f"uniprot-{accession}.json",
    )


def uniprot_search(
    client: ScientificHttpClient,
    *,
    query: str,
    taxon_id: int,
) -> RetrievedResponse:
    return client.request(
        "GET",
        f"{UNIPROT_BASE}/uniprotkb/search",
        params={
            "query": f"({query}) AND (organism_id:{taxon_id})",
            "format": "json",
            "size": 25,
        },
        artifact_name="uniprot-search.json",
    )


def rcsb_sequence_search(
    client: ScientificHttpClient,
    sequence: str,
) -> RetrievedResponse:
    body = {
        "query": {
            "type": "terminal",
            "service": "sequence",
            "parameters": {
                "evalue_cutoff": 1,
                "identity_cutoff": 0.9,
                "sequence_type": "protein",
                "value": sequence,
            },
        },
        "return_type": "polymer_entity",
        "request_options": {
            "results_content_type": ["experimental"],
            "paginate": {"start": 0, "rows": 100},
            "sort": [{"sort_by": "score", "direction": "desc"}],
        },
    }
    return client.request(
        "POST",
        RCSB_SEARCH_URL,
        json_body=body,
        artifact_name="rcsb-sequence-search.json",
    )


def rcsb_entry(client: ScientificHttpClient, pdb_id: str) -> RetrievedResponse:
    return client.request(
        "GET",
        f"{RCSB_DATA_BASE}/entry/{pdb_id}",
        artifact_name=f"rcsb-entry-{pdb_id}.json",
    )


def rcsb_polymer_entity(
    client: ScientificHttpClient,
    pdb_id: str,
    entity_id: str,
) -> RetrievedResponse:
    return client.request(
        "GET",
        f"{RCSB_DATA_BASE}/polymer_entity/{pdb_id}/{entity_id}",
        artifact_name=f"rcsb-polymer-entity-{pdb_id}-{entity_id}.json",
    )


def rcsb_mmcif(client: ScientificHttpClient, pdb_id: str) -> RetrievedResponse:
    return client.request(
        "GET",
        f"{RCSB_FILE_BASE}/{pdb_id}.cif",
        artifact_name=f"rcsb-{pdb_id}.cif",
    )
