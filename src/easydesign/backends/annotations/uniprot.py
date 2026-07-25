"""UniProtKB accession 记录获取；不负责科学解释或自动身份猜测。"""

from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pydantic import BaseModel, ConfigDict, Field

from easydesign.core import BackendContractError
from easydesign.core.hashing import sha256_bytes


class FetchedUniProtRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    accession: str = Field(pattern=r"^[A-Z0-9]{6,10}(?:-[0-9]+)?$")
    source_url: str
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    uniprot_release: str | None = None
    payload: dict[str, object]


class UniProtAnnotationAdapter:
    """按明确 accession 读取一个 UniProtKB JSON 记录。"""

    def __init__(
        self,
        *,
        base_url: str = "https://rest.uniprot.org/uniprotkb",
        timeout_seconds: int = 30,
    ) -> None:
        if not base_url.startswith(("https://", "http://")):
            raise ValueError("UniProt base_url 必须是 HTTP(S)")
        if timeout_seconds < 1:
            raise ValueError("UniProt timeout_seconds 必须为正数")
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def fetch(self, accession: str) -> FetchedUniProtRecord:
        url = f"{self.base_url}/{accession}.json"
        request = Request(  # noqa: S310 - URL is an explicit adapter endpoint.
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "EasyDesign/0.1 scientific-annotation",
            },
            method="GET",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:  # noqa: S310
                body = response.read()
                release = response.headers.get("x-uniprot-release")
        except HTTPError as error:
            raise BackendContractError(
                f"UniProt 请求失败: accession={accession}, HTTP={error.code}"
            ) from error
        except (URLError, TimeoutError, OSError) as error:
            raise BackendContractError(
                f"UniProt 请求失败: accession={accession}, error={error}"
            ) from error
        try:
            payload = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise BackendContractError("UniProt 返回的不是有效 JSON") from error
        if not isinstance(payload, dict):
            raise BackendContractError("UniProt JSON 顶层必须是 object")
        primary = payload.get("primaryAccession")
        if primary != accession.split("-", maxsplit=1)[0] and primary != accession:
            raise BackendContractError(
                "UniProt 返回 accession 与请求不一致: "
                f"requested={accession}, returned={primary}"
            )
        return FetchedUniProtRecord(
            accession=accession,
            source_url=url,
            source_sha256=sha256_bytes(body),
            uniprot_release=release,
            payload=payload,
        )
