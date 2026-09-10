"""Run the alphafold3-open remote MSA client without local AF3 databases."""

from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import os
import shutil
import signal
import sys
import tarfile
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from types import FrameType, ModuleType
from typing import Any


class _RequestsCompatTimeout(TimeoutError):
    pass


class _RequestsCompatExceptions:
    Timeout = _RequestsCompatTimeout


class _RequestsCompatResponse:
    def __init__(self, content: bytes) -> None:
        self.content = content

    def json(self) -> Any:
        return json.loads(self.content.decode("utf-8"))


class _RequestsCompat(ModuleType):
    """Subset of requests used by alphafold3.data.msa_server."""

    exceptions = _RequestsCompatExceptions()

    def __init__(self) -> None:
        super().__init__("requests")

    @staticmethod
    def _request(
        method: str,
        url: str,
        *,
        data: dict[str, str] | None,
        timeout: float,
        headers: dict[str, str] | None,
    ) -> _RequestsCompatResponse:
        encoded = urllib.parse.urlencode(data).encode("utf-8") if data else None
        partial = bytearray()
        resumable_download = method == "GET" and "/result/download/" in url
        read_attempts = 6 if resumable_download else 1
        for read_attempt in range(read_attempts):
            request_headers = dict(headers or {})
            request_headers.setdefault("Accept-Encoding", "identity")
            if partial:
                request_headers["Range"] = f"bytes={len(partial)}-"
            request = urllib.request.Request(
                url,
                data=encoded,
                headers=request_headers,
                method=method,
            )
            try:
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    if partial and getattr(response, "status", None) != 206:
                        partial.clear()
                    try:
                        while chunk := response.read(64 * 1024):
                            partial.extend(chunk)
                    except http.client.IncompleteRead as error:
                        partial.extend(error.partial)
                        if read_attempt + 1 < read_attempts:
                            continue
                        raise
                    return _RequestsCompatResponse(bytes(partial))
            except TimeoutError as error:
                if resumable_download and partial and read_attempt + 1 < read_attempts:
                    continue
                raise _RequestsCompatTimeout(str(error)) from error
            except urllib.error.URLError as error:
                if isinstance(error.reason, TimeoutError):
                    if (
                        resumable_download
                        and partial
                        and read_attempt + 1 < read_attempts
                    ):
                        continue
                    raise _RequestsCompatTimeout(str(error)) from error
                raise
        raise RuntimeError("unreachable resumable download state")

    @classmethod
    def post(
        cls,
        url: str,
        *,
        data: dict[str, str],
        timeout: float,
        headers: dict[str, str] | None = None,
    ) -> _RequestsCompatResponse:
        return cls._request(
            "POST", url, data=data, timeout=timeout, headers=headers
        )

    @classmethod
    def get(
        cls,
        url: str,
        *,
        timeout: float,
        headers: dict[str, str] | None = None,
    ) -> _RequestsCompatResponse:
        return cls._request(
            "GET", url, data=None, timeout=timeout, headers=headers
        )


def _install_requests_compat() -> None:
    try:
        __import__("requests")
    except ModuleNotFoundError:
        sys.modules["requests"] = _RequestsCompat()


def _install_scoped_msa_proxy() -> None:
    proxy_url = os.environ.get("EASYDESIGN_AFO_MSA_HTTPS_PROXY")
    if proxy_url is None:
        return
    parsed = urllib.parse.urlparse(proxy_url)
    if parsed.scheme not in {"http", "https"} or parsed.hostname is None:
        raise ValueError(
            "EASYDESIGN_AFO_MSA_HTTPS_PROXY must be an http or https URL"
        )
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({"http": proxy_url, "https": proxy_url})
    )
    urllib.request.install_opener(opener)
    endpoint = parsed.hostname
    if parsed.port is not None:
        endpoint = f"{endpoint}:{parsed.port}"
    print(f"Using scoped MSA HTTPS proxy at {endpoint}")


def _harden_tar_extraction() -> None:
    """Reject traversal, device, and unsafe-link members in server archives."""

    data_filter = getattr(tarfile, "data_filter", None)
    if data_filter is None:
        raise RuntimeError("AFO remote MSA requires Python tarfile.data_filter")
    tarfile.TarFile.extraction_filter = staticmethod(data_filter)


def _termination_requested(signum: int, _frame: FrameType | None) -> None:
    raise InterruptedError(f"remote MSA interrupted by signal {signum}")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _a3m_identity(path: Path, *, expected_query: str) -> tuple[str, int, int]:
    records = 0
    query_parts: list[str] = []
    has_sequence = False
    with path.open("r", encoding="utf-8") as handle:
        for raw in handle:
            line = raw.strip()
            if not line:
                continue
            if line.startswith(">"):
                if records and not has_sequence:
                    raise ValueError(f"remote A3M contains an empty record: {path}")
                records += 1
                has_sequence = False
                continue
            if records == 0:
                raise ValueError(f"remote A3M sequence precedes first header: {path}")
            if records == 1:
                query_parts.append(line)
            has_sequence = True
    if records < 2 or not has_sequence:
        raise ValueError(f"remote A3M has insufficient depth: {path}, depth={records}")
    if "".join(query_parts) != expected_query:
        raise ValueError(f"remote A3M query does not match canonical sequence: {path}")
    return _sha256_file(path), path.stat().st_size, records


def _remote_receipt(
    *,
    staging: Path,
    input_json: Path,
    staged_input: Path,
    serialized_payload: dict[str, Any],
    provider: str,
    endpoint: str,
    requested_chain_ids: tuple[str, ...] | None,
) -> dict[str, Any]:
    chains: list[dict[str, Any]] = []
    for item in serialized_payload.get("sequences", []):
        protein = item.get("protein") if isinstance(item, dict) else None
        if not isinstance(protein, dict):
            continue
        chain_id = protein.get("id")
        sequence = protein.get("sequence")
        if not isinstance(chain_id, str) or not isinstance(sequence, str):
            raise ValueError("remote MSA output protein is missing string id/sequence")
        if requested_chain_ids is not None and chain_id not in requested_chain_ids:
            continue
        msa_path = staging / "msas" / f"{chain_id}_unpaired.a3m"
        digest, size, depth = _a3m_identity(msa_path, expected_query=sequence)
        chains.append(
            {
                "chain_id": chain_id,
                "canonical_sequence_sha256": hashlib.sha256(
                    sequence.encode("ascii")
                ).hexdigest(),
                "unpaired_msa_path": f"msas/{chain_id}_unpaired.a3m",
                "unpaired_msa_sha256": digest,
                "unpaired_msa_size_bytes": size,
                "depth": depth,
            }
        )
    if not chains:
        raise ValueError("remote MSA output contains no protein chain receipt")
    return {
        "schema_version": "1.0",
        "source_type": "remote",
        "provider": provider,
        "endpoint": endpoint,
        "created_at": datetime.now(UTC).isoformat(),
        "input_json_sha256": _sha256_file(input_json),
        "processed_json_sha256": _sha256_file(staged_input),
        "chains": chains,
        "target_sequence_transmitted": True,
        "privacy_notice": "external-provider-receives-target-sequence",
        "fallback_policy": "fail-closed",
        "fallback_used": False,
    }


def run_remote_msa(
    *,
    input_json: Path,
    output_dir: Path,
    msa_server_url: str,
    provider: str = "colabfold-public",
    chain_ids: tuple[str, ...] | None = None,
) -> Path:
    """Fill missing MSAs and publish the runner-compatible files."""

    _install_scoped_msa_proxy()
    _install_requests_compat()
    from alphafold3.common import folding_input  # type: ignore[import-not-found]
    from alphafold3.data import msa_server  # type: ignore[import-not-found]

    if not input_json.is_absolute() or not input_json.is_file():
        raise ValueError(f"input JSON must be an existing absolute file: {input_json}")
    if not output_dir.is_absolute():
        raise ValueError(f"output directory must be absolute: {output_dir}")
    if not msa_server_url.startswith(("http://", "https://")):
        raise ValueError("MSA server URL must use http or https")
    if not provider or any(character.isspace() for character in provider):
        raise ValueError("remote MSA provider must be a non-empty token")
    if chain_ids is not None and (not chain_ids or len(chain_ids) != len(set(chain_ids))):
        raise ValueError("remote MSA chain IDs must be non-empty and unique")

    fold_inputs: tuple[Any, ...] = tuple(
        folding_input.load_fold_inputs_from_path(input_json)
    )
    if len(fold_inputs) != 1:
        raise ValueError(
            f"remote MSA helper requires exactly one fold input, got {len(fold_inputs)}"
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    job_dir = output_dir / input_json.stem
    if job_dir.exists():
        if any(job_dir.iterdir()):
            raise FileExistsError(f"remote MSA output is not empty: {job_dir}")
        job_dir.rmdir()

    _harden_tar_extraction()
    previous_sigterm = signal.getsignal(signal.SIGTERM)
    signal.signal(signal.SIGTERM, _termination_requested)
    staging: Path | None = None
    try:
        staging = Path(
            tempfile.mkdtemp(prefix=f".{input_json.stem}.creating-", dir=output_dir)
        )
        print(
            "Privacy notice: the external MSA provider receives the target sequence.",
            file=sys.stderr,
        )
        filled_input = msa_server.fill_missing_msas(
            fold_inputs[0],
            host_url=msa_server_url,
            user_agent="easydesign-openfold3-af3-jax/1",
        )
        msa_server.save_msas(filled_input, staging)
        staged_input = staging / f"{input_json.stem}_data.json"
        serialized = filled_input.to_json()
        serialized_payload = json.loads(serialized)
        if not isinstance(serialized_payload, dict):
            raise ValueError("remote MSA processed JSON must be an object")
        staged_input.write_text(serialized, encoding="utf-8", newline="\n")
        receipt = _remote_receipt(
            staging=staging,
            input_json=input_json,
            staged_input=staged_input,
            serialized_payload=serialized_payload,
            provider=provider,
            endpoint=msa_server_url,
            requested_chain_ids=chain_ids,
        )
        (staging / "remote-msa-receipt.json").write_text(
            json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        verified = tuple(folding_input.load_fold_inputs_from_path(staged_input))
        if len(verified) != 1:
            raise ValueError(
                "remote MSA output must contain exactly one reloadable fold input"
            )
        os.replace(staging, job_dir)
    except BaseException:
        if staging is not None and staging.exists():
            shutil.rmtree(staging)
        raise
    finally:
        signal.signal(signal.SIGTERM, previous_sigterm)
    updated_input = job_dir / f"{input_json.stem}_data.json"
    print(f"Remote MSA input written to {updated_input}")
    return updated_input


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json_path", type=Path, required=True)
    parser.add_argument("--output_dir", type=Path, required=True)
    parser.add_argument("--msa_server_url", required=True)
    parser.add_argument("--provider", required=True)
    parser.add_argument("--chain_ids", required=True)
    return parser


def main() -> int:
    arguments = _parser().parse_args()
    run_remote_msa(
        input_json=arguments.json_path,
        output_dir=arguments.output_dir,
        msa_server_url=arguments.msa_server_url,
        provider=arguments.provider,
        chain_ids=tuple(
            item.strip() for item in arguments.chain_ids.split(",") if item.strip()
        ),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
