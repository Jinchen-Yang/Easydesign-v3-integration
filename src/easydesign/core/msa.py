"""Portable contracts for precomputed MSA libraries and selected artifacts."""

from __future__ import annotations

from datetime import datetime
from pathlib import PurePosixPath
from typing import Literal, Self
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .artifacts import ID_PATTERN, SHA256_PATTERN
from .timestamps import normalize_aware_datetime


class MsaLibrarySource(BaseModel):
    """Content identity of the source collection used by an offline builder."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["stockholm-archive", "a3m-collection"]
    label: str = Field(min_length=1, max_length=256)
    sha256: str = Field(pattern=SHA256_PATTERN)
    size_bytes: int = Field(ge=1)

    @model_validator(mode="after")
    def reject_host_paths(self) -> Self:
        if self.label.startswith(("/", "\\")) or ":\\" in self.label:
            raise ValueError("MSA source label 不能包含主机绝对路径")
        return self


class MsaLibraryProducer(BaseModel):
    """Offline producer identity; it is evidence, not an execution request."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(pattern=ID_PATTERN)
    version: str = Field(min_length=1, max_length=64)
    code_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)


class MsaLibraryEntry(BaseModel):
    """One canonical-sequence-keyed A3M in an immutable release."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    canonical_sequence_sha256: str = Field(pattern=SHA256_PATTERN)
    a3m_path: str = Field(min_length=1, max_length=512)
    a3m_sha256: str = Field(pattern=SHA256_PATTERN)
    a3m_size_bytes: int = Field(ge=1)
    depth: int = Field(ge=2)
    query_name: str | None = Field(default=None, min_length=1, max_length=512)
    accessions: tuple[str, ...] = ()
    source_member: str | None = Field(default=None, min_length=1, max_length=1024)
    source_member_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    query_match: Literal["exact"] = "exact"

    @model_validator(mode="after")
    def validate_entry_path(self) -> Self:
        path = PurePosixPath(self.a3m_path)
        expected = PurePosixPath(
            "entries", f"{self.canonical_sequence_sha256}.a3m"
        )
        if path.is_absolute() or ".." in path.parts or path != expected:
            raise ValueError(
                "MSA library entry 必须位于 entries/<canonical-sequence-sha256>.a3m"
            )
        if len(self.accessions) != len(set(self.accessions)):
            raise ValueError("MSA library entry accession 不能重复")
        return self


class MsaLibraryManifest(BaseModel):
    """Schema emitted by the offline builder and consumed by EasyDesign."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    release_id: str = Field(pattern=ID_PATTERN)
    status: Literal["ready"] = "ready"
    created_at: datetime
    producer: MsaLibraryProducer
    source: MsaLibrarySource
    entries: tuple[MsaLibraryEntry, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_release(self) -> Self:
        object.__setattr__(self, "created_at", normalize_aware_datetime(self.created_at))
        sequence_hashes = [item.canonical_sequence_sha256 for item in self.entries]
        paths = [item.a3m_path for item in self.entries]
        if len(sequence_hashes) != len(set(sequence_hashes)):
            raise ValueError("MSA library canonical sequence SHA-256 不能重复")
        if len(paths) != len(set(paths)):
            raise ValueError("MSA library entry path 不能重复")
        if sequence_hashes != sorted(sequence_hashes):
            raise ValueError("MSA library entries 必须按 canonical sequence SHA-256 排序")
        return self


class MsaReleaseReceipt(BaseModel):
    """Small release seal binding the manifest to its immutable directory."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    release_id: str = Field(pattern=ID_PATTERN)
    status: Literal["ready"] = "ready"
    created_at: datetime
    library_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    entry_count: int = Field(ge=1)

    @model_validator(mode="after")
    def normalize_timestamp(self) -> Self:
        object.__setattr__(self, "created_at", normalize_aware_datetime(self.created_at))
        return self


class MsaSourceReceipt(BaseModel):
    """Per-target provenance frozen beside the A3M consumed by one run."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        populate_by_name=True,
    )

    schema_version: Literal["1.0"] = "1.0"
    type: Literal["precomputed-library", "precomputed-file"]
    release_id: str | None = Field(default=None, pattern=ID_PATTERN)
    library_schema_version: str | None = Field(default=None, min_length=1, max_length=32)
    library_manifest_sha256: str | None = Field(
        default=None,
        pattern=SHA256_PATTERN,
    )
    release_receipt_sha256: str | None = Field(
        default=None,
        pattern=SHA256_PATTERN,
    )
    library_entry_path: str | None = Field(default=None, min_length=1, max_length=512)
    source_name: str | None = Field(default=None, min_length=1, max_length=256)
    canonical_sequence_sha256: str = Field(pattern=SHA256_PATTERN)
    a3m_sha256: str = Field(pattern=SHA256_PATTERN)
    a3m_size_bytes: int = Field(ge=1)
    depth: int = Field(ge=2)
    query_match: Literal["exact"] = "exact"
    target_chain: Literal["A"] = "A"
    paired_msa: Literal["empty"] = "empty"
    template_mode: Literal["disabled", "precomputed"] = "disabled"
    fallback_policy: Literal["fail-closed"] = "fail-closed"
    fallback_used: Literal[False] = False

    @model_validator(mode="after")
    def validate_source_branch(self) -> Self:
        library_values = (
            self.release_id,
            self.library_schema_version,
            self.library_manifest_sha256,
            self.library_entry_path,
        )
        if self.type == "precomputed-library":
            if any(value is None for value in library_values):
                raise ValueError("precomputed-library receipt 缺少 release/manifest/entry")
            if self.source_name is not None:
                raise ValueError("precomputed-library receipt 不能伪造直接文件名")
        else:
            if self.source_name is None:
                raise ValueError("precomputed-file receipt 必须记录 source_name")
            if any(value is not None for value in (*library_values, self.release_receipt_sha256)):
                raise ValueError("precomputed-file receipt 不能声明 library release")
        return self

    @property
    def source_type(self) -> Literal["precomputed-library", "precomputed-file"]:
        return self.type


class RemoteMsaChainReceipt(BaseModel):
    """Identity of one chain returned by an external MSA provider."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    chain_id: str = Field(pattern=r"^[A-Za-z0-9]{1,4}$")
    canonical_sequence_sha256: str = Field(pattern=SHA256_PATTERN)
    unpaired_msa_path: str = Field(min_length=1, max_length=512)
    unpaired_msa_sha256: str = Field(pattern=SHA256_PATTERN)
    unpaired_msa_size_bytes: int = Field(ge=1)
    depth: int = Field(ge=2)

    @model_validator(mode="after")
    def validate_relative_path(self) -> Self:
        path = PurePosixPath(self.unpaired_msa_path)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("remote MSA receipt path 必须是安全相对路径")
        return self


class RemoteMsaReceipt(BaseModel):
    """Provider, privacy, and content evidence emitted before AFO inference."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    source_type: Literal["remote"] = "remote"
    provider: str = Field(pattern=ID_PATTERN)
    endpoint: str = Field(min_length=1, max_length=2048)
    created_at: datetime
    input_json_sha256: str = Field(pattern=SHA256_PATTERN)
    processed_json_sha256: str = Field(pattern=SHA256_PATTERN)
    chains: tuple[RemoteMsaChainReceipt, ...] = Field(min_length=1)
    target_sequence_transmitted: Literal[True] = True
    privacy_notice: Literal["external-provider-receives-target-sequence"] = (
        "external-provider-receives-target-sequence"
    )
    fallback_policy: Literal["fail-closed"] = "fail-closed"
    fallback_used: Literal[False] = False

    @model_validator(mode="after")
    def validate_remote_receipt(self) -> Self:
        object.__setattr__(self, "created_at", normalize_aware_datetime(self.created_at))
        parsed = urlsplit(self.endpoint)
        if (
            parsed.scheme not in {"http", "https"}
            or parsed.hostname is None
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("remote MSA endpoint 必须是无凭据、query 和 fragment 的 HTTP(S) URL")
        chain_ids = [item.chain_id for item in self.chains]
        if len(chain_ids) != len(set(chain_ids)):
            raise ValueError("remote MSA receipt chain ID 不能重复")
        return self


__all__ = [
    "MsaLibraryEntry",
    "MsaLibraryManifest",
    "MsaLibraryProducer",
    "MsaLibrarySource",
    "MsaReleaseReceipt",
    "MsaSourceReceipt",
    "RemoteMsaChainReceipt",
    "RemoteMsaReceipt",
]
