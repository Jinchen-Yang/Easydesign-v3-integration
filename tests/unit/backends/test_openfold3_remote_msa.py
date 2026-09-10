from __future__ import annotations

import hashlib
import http.client
import json
import os
import signal
import sys
import tarfile
import urllib.request
from pathlib import Path
from types import ModuleType

import pytest

from easydesign.backends.structure_prediction.openfold3_remote_msa import (
    _harden_tar_extraction,
    _install_scoped_msa_proxy,
    _RequestsCompat,
    _RequestsCompatTimeout,
    run_remote_msa,
)


class _FakeFoldInput:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def to_json(self) -> str:
        return json.dumps(self.payload, sort_keys=True)


class _FakeUrlResponse:
    def __init__(
        self,
        content: bytes,
        *,
        status: int = 200,
        incomplete_expected: int | None = None,
    ) -> None:
        self.content = content
        self.status = status
        self.incomplete_expected = incomplete_expected
        self._read = False

    def __enter__(self) -> _FakeUrlResponse:
        return self

    def __exit__(self, *args: object) -> None:
        del args

    def read(self, size: int = -1) -> bytes:
        del size
        if self._read:
            return b""
        self._read = True
        if self.incomplete_expected is not None:
            raise http.client.IncompleteRead(
                self.content,
                self.incomplete_expected,
            )
        return self.content


class _ChunkThenTimeoutResponse(_FakeUrlResponse):
    def read(self, size: int = -1) -> bytes:
        del size
        if not self._read:
            self._read = True
            return self.content
        raise TimeoutError("timed out after a complete chunk")


def test_requests_compat_posts_form_data_and_decodes_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: list[tuple[urllib.request.Request, float]] = []

    def fake_urlopen(
        request: urllib.request.Request,
        *,
        timeout: float,
    ) -> _FakeUrlResponse:
        observed.append((request, timeout))
        return _FakeUrlResponse(b'{"status":"COMPLETE","id":"ticket-1"}')

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    response = _RequestsCompat.post(
        "https://api.colabfold.com/ticket/msa",
        data={"q": ">101\\nAC DE\\n", "mode": "env"},
        timeout=6.02,
        headers={"User-Agent": "easydesign-test"},
    )

    assert response.json() == {"status": "COMPLETE", "id": "ticket-1"}
    request, timeout = observed[0]
    assert request.method == "POST"
    assert request.data == b"q=%3E101%5CnAC+DE%5Cn&mode=env"
    assert request.headers["User-agent"] == "easydesign-test"
    assert timeout == 6.02


def test_requests_compat_maps_socket_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def timeout_urlopen(*args: object, **kwargs: object) -> _FakeUrlResponse:
        del args, kwargs
        raise TimeoutError("timed out")

    monkeypatch.setattr(urllib.request, "urlopen", timeout_urlopen)

    with pytest.raises(_RequestsCompatTimeout):
        _RequestsCompat.get("https://api.colabfold.com/ticket/1", timeout=6.02)


def test_requests_compat_resumes_incomplete_result_download(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses = iter(
        (
            _FakeUrlResponse(b"abc", incomplete_expected=3),
            _FakeUrlResponse(b"def", status=206),
        )
    )
    observed_ranges: list[str | None] = []

    def fake_urlopen(
        request: urllib.request.Request,
        *,
        timeout: float,
    ) -> _FakeUrlResponse:
        del timeout
        observed_ranges.append(request.headers.get("Range"))
        return next(responses)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    response = _RequestsCompat.get(
        "https://api.colabfold.com/result/download/ticket-1",
        timeout=60,
    )

    assert response.content == b"abcdef"
    assert observed_ranges == [None, "bytes=3-"]


def test_requests_compat_preserves_complete_chunks_before_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses = iter(
        (
            _ChunkThenTimeoutResponse(b"abc"),
            _FakeUrlResponse(b"def", status=206),
        )
    )
    observed_ranges: list[str | None] = []

    def fake_urlopen(
        request: urllib.request.Request,
        *,
        timeout: float,
    ) -> _FakeUrlResponse:
        del timeout
        observed_ranges.append(request.headers.get("Range"))
        return next(responses)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    response = _RequestsCompat.get(
        "https://api.colabfold.com/result/download/ticket-1",
        timeout=60,
    )

    assert response.content == b"abcdef"
    assert observed_ranges == [None, "bytes=3-"]


def test_scoped_msa_proxy_does_not_require_global_proxy_variables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed_handlers: list[urllib.request.ProxyHandler] = []
    installed: list[object] = []

    def fake_build_opener(handler: urllib.request.ProxyHandler) -> object:
        observed_handlers.append(handler)
        return object()

    monkeypatch.setenv(
        "EASYDESIGN_AFO_MSA_HTTPS_PROXY",
        "http://127.0.0.1:7897",
    )
    monkeypatch.delenv("HTTPS_PROXY", raising=False)
    monkeypatch.delenv("HTTP_PROXY", raising=False)
    monkeypatch.setattr(urllib.request, "build_opener", fake_build_opener)
    monkeypatch.setattr(urllib.request, "install_opener", installed.append)

    _install_scoped_msa_proxy()

    assert observed_handlers[0].proxies == {
        "http": "http://127.0.0.1:7897",
        "https": "http://127.0.0.1:7897",
    }
    assert len(installed) == 1


def test_remote_msa_enables_safe_tar_extraction() -> None:
    original = tarfile.TarFile.extraction_filter
    try:
        _harden_tar_extraction()
        assert tarfile.TarFile.extraction_filter is not None
    finally:
        tarfile.TarFile.extraction_filter = original


def _install_fake_alphafold3(
    monkeypatch: pytest.MonkeyPatch,
    *,
    filled_input: _FakeFoldInput,
) -> list[tuple[str, str]]:
    calls: list[tuple[str, str]] = []
    alphafold3 = ModuleType("alphafold3")
    common = ModuleType("alphafold3.common")
    folding_input = ModuleType("alphafold3.common.folding_input")
    data = ModuleType("alphafold3.data")
    msa_server = ModuleType("alphafold3.data.msa_server")

    def load_fold_inputs_from_path(input_json: Path) -> tuple[_FakeFoldInput, ...]:
        calls.append(("load", str(input_json)))
        return (_FakeFoldInput({"name": "before"}),)

    def fill_missing_msas(
        fold_input: _FakeFoldInput,
        *,
        host_url: str,
        user_agent: str,
    ) -> _FakeFoldInput:
        del fold_input, user_agent
        calls.append(("fill", host_url))
        return filled_input

    def save_msas(fold_input: _FakeFoldInput, output_dir: Path) -> None:
        del fold_input
        msa_dir = output_dir / "msas"
        msa_dir.mkdir()
        (msa_dir / "A_unpaired.a3m").write_text(
            ">query\nACDE\n>hit\nAC-E\n",
            encoding="utf-8",
        )
        calls.append(("save", str(output_dir)))

    folding_input.load_fold_inputs_from_path = load_fold_inputs_from_path  # type: ignore[attr-defined]
    msa_server.fill_missing_msas = fill_missing_msas  # type: ignore[attr-defined]
    msa_server.save_msas = save_msas  # type: ignore[attr-defined]
    common.folding_input = folding_input  # type: ignore[attr-defined]
    data.msa_server = msa_server  # type: ignore[attr-defined]
    for name, module in (
        ("alphafold3", alphafold3),
        ("alphafold3.common", common),
        ("alphafold3.common.folding_input", folding_input),
        ("alphafold3.data", data),
        ("alphafold3.data.msa_server", msa_server),
    ):
        monkeypatch.setitem(sys.modules, name, module)
    return calls


def test_remote_msa_helper_uses_input_filename_for_runner_compatible_layout(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    input_json = (tmp_path / "protenix-input.json").resolve()
    input_json.write_text('{"name":"adrb2-p07550"}\n', encoding="utf-8")
    filled_input = _FakeFoldInput(
        {
            "name": "adrb2-p07550",
            "sequences": [
                {
                    "protein": {
                        "id": "A",
                        "sequence": "ACDE",
                        "unpairedMsa": ">query\nACDE\n>hit\nAC-E\n",
                    }
                }
            ],
        }
    )
    calls = _install_fake_alphafold3(monkeypatch, filled_input=filled_input)

    updated_input = run_remote_msa(
        input_json=input_json,
        output_dir=(tmp_path / "msa-output").resolve(),
        msa_server_url="https://api.colabfold.com",
    )

    job_dir = tmp_path / "msa-output" / "protenix-input"
    assert updated_input == job_dir / "protenix-input_data.json"
    assert json.loads(updated_input.read_text(encoding="utf-8"))["sequences"]
    assert (job_dir / "msas/A_unpaired.a3m").is_file()
    receipt = json.loads(
        (job_dir / "remote-msa-receipt.json").read_text(encoding="utf-8")
    )
    assert receipt["provider"] == "colabfold-public"
    assert receipt["target_sequence_transmitted"] is True
    assert receipt["fallback_used"] is False
    assert receipt["chains"][0]["canonical_sequence_sha256"] == hashlib.sha256(
        b"ACDE"
    ).hexdigest()
    assert calls[:2] == [
        ("load", str(input_json)),
        ("fill", "https://api.colabfold.com"),
    ]
    staging = Path(calls[2][1])
    assert staging.parent == tmp_path / "msa-output"
    assert staging.name.startswith(".protenix-input.creating-")
    assert calls[2:] == [
        ("save", str(staging)),
        ("load", str(staging / "protenix-input_data.json")),
    ]


def test_remote_msa_helper_refuses_nonempty_output(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    input_json = (tmp_path / "target.json").resolve()
    input_json.write_text("{}\n", encoding="utf-8")
    job_dir = tmp_path / "msa-output" / "target"
    job_dir.mkdir(parents=True)
    (job_dir / "existing.txt").write_text("protected\n", encoding="utf-8")
    _install_fake_alphafold3(
        monkeypatch,
        filled_input=_FakeFoldInput({"name": "target"}),
    )

    with pytest.raises(FileExistsError, match="not empty"):
        run_remote_msa(
            input_json=input_json,
            output_dir=(tmp_path / "msa-output").resolve(),
            msa_server_url="https://api.colabfold.com",
        )


def test_remote_msa_failure_removes_staging_directory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    input_json = (tmp_path / "target.json").resolve()
    input_json.write_text("{}\n", encoding="utf-8")
    _install_fake_alphafold3(
        monkeypatch,
        filled_input=_FakeFoldInput({"name": "target"}),
    )
    msa_server = sys.modules["alphafold3.data.msa_server"]

    def fail_fill(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise RuntimeError("server unavailable")

    msa_server.fill_missing_msas = fail_fill  # type: ignore[attr-defined]
    output_dir = (tmp_path / "msa-output").resolve()

    with pytest.raises(RuntimeError, match="server unavailable"):
        run_remote_msa(
            input_json=input_json,
            output_dir=output_dir,
            msa_server_url="https://api.colabfold.com",
        )

    assert not (output_dir / "target").exists()
    assert not tuple(output_dir.glob(".target.creating-*"))


def test_remote_msa_sigterm_removes_staging_directory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    input_json = (tmp_path / "target.json").resolve()
    input_json.write_text("{}\n", encoding="utf-8")
    _install_fake_alphafold3(
        monkeypatch,
        filled_input=_FakeFoldInput({"name": "target"}),
    )
    msa_server = sys.modules["alphafold3.data.msa_server"]

    def terminate_fill(*args: object, **kwargs: object) -> None:
        del args, kwargs
        os.kill(os.getpid(), signal.SIGTERM)

    msa_server.fill_missing_msas = terminate_fill  # type: ignore[attr-defined]
    output_dir = (tmp_path / "msa-output").resolve()

    with pytest.raises(InterruptedError, match="interrupted by signal"):
        run_remote_msa(
            input_json=input_json,
            output_dir=output_dir,
            msa_server_url="https://api.colabfold.com",
        )

    assert not (output_dir / "target").exists()
    assert not tuple(output_dir.glob(".target.creating-*"))
