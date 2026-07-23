from __future__ import annotations

import hashlib

import pytest

from easydesign.core import ArtifactIntegrityError, ArtifactNotFoundError
from easydesign.core.hashing import sha256_file, verify_sha256


def test_sha256_file_and_verify(tmp_path) -> None:
    path = tmp_path / "artifact.bin"
    content = b"easydesign-contract"
    path.write_bytes(content)

    expected = hashlib.sha256(content).hexdigest()
    assert sha256_file(path) == expected
    assert verify_sha256(path, expected) is None


def test_sha256_rejects_missing_file(tmp_path) -> None:
    with pytest.raises(ArtifactNotFoundError):
        sha256_file(tmp_path / "missing.bin")


def test_verify_sha256_rejects_mismatch(tmp_path) -> None:
    path = tmp_path / "artifact.bin"
    path.write_bytes(b"actual")

    with pytest.raises(ArtifactIntegrityError, match="SHA-256"):
        verify_sha256(path, "0" * 64)


def test_sha256_rejects_nonpositive_chunk_size(tmp_path) -> None:
    path = tmp_path / "artifact.bin"
    path.write_bytes(b"data")

    with pytest.raises(ValueError, match="chunk_size"):
        sha256_file(path, chunk_size=0)
