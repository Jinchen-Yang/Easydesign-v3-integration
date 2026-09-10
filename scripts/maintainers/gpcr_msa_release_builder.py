"""Maintainer-only builder for immutable GPCR MSA library releases.

This tool is deliberately outside the installed EasyDesign package and public
research CLI.  EasyDesign consumes its versioned output; it does not produce
the underlying Stockholm/A3M database during a research run.
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import TextIO

from easydesign.backends.target_sources import normalize_fasta
from easydesign.backends.target_sources.sequence import CANONICAL_AMINO_ACIDS
from easydesign.core import (
    ConfigurationError,
    MsaLibraryManifest,
    MsaReleaseReceipt,
    dump_model,
    sha256_file,
)
from easydesign.workspace_context import WorkspaceContext

SCHEMA_VERSION = "1.0"
CONVERTER_VERSION = "1.0"
DEFAULT_MEMBER_ROOT = "msa_results"
_GAP_CHARS = frozenset("-.")
_EXTERNAL_CONVERTER_THRESHOLD_BYTES = 64 * 1024 * 1024


class MsaPrecomputeError(ConfigurationError):
    """A source, conversion, or target-specific A3M contract failure."""


def _temporary_path(*, prefix: str, suffix: str, directory: Path) -> Path:
    """Create a named temporary path and close mkstemp's descriptor."""

    descriptor, name = tempfile.mkstemp(prefix=prefix, suffix=suffix, dir=directory)
    os.close(descriptor)
    return Path(name)


def _publish_no_replace(source: Path, destination: Path) -> None:
    """Publish a same-directory staging file without replacing a prior file."""

    if destination.exists():
        raise MsaPrecomputeError(f"输出已存在，拒绝覆盖: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        # Hard-link creation is atomic and has no replace semantics on POSIX and
        # Windows when source and destination share the same filesystem.
        os.link(source, destination)
    except FileExistsError as error:
        raise MsaPrecomputeError(f"输出已存在，拒绝覆盖: {destination}") from error
    except OSError as error:
        # Do not fall back to rename: POSIX rename may replace a destination
        # that appeared after the existence check. Fail closed instead.
        raise MsaPrecomputeError(f"文件系统不支持安全 no-replace 发布: {destination}") from error
    source.unlink()


def _publish_directory_no_replace(source: Path, destination: Path) -> None:
    """Atomically publish a completed directory without replacing a target."""

    if destination.exists():
        raise MsaPrecomputeError(f"输出已存在，拒绝覆盖: {destination}")
    if os.name == "nt":
        try:
            os.rename(source, destination)
        except FileExistsError as error:
            raise MsaPrecomputeError(f"输出已存在，拒绝覆盖: {destination}") from error
        return
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        renameat2 = libc.renameat2
    except (AttributeError, OSError) as error:
        raise MsaPrecomputeError("当前 Linux 不支持安全的目录 no-replace 发布") from error
    renameat2.argtypes = [
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    ]
    renameat2.restype = ctypes.c_int
    result = renameat2(
        -100,
        os.fsencode(source),
        -100,
        os.fsencode(destination),
        1,  # renameat2(2): RENAME_NOREPLACE
    )
    if result != 0:
        error_number = ctypes.get_errno()
        if error_number == 17:
            raise MsaPrecomputeError(f"输出已存在，拒绝覆盖: {destination}")
        raise MsaPrecomputeError(
            f"library staging 无法原子发布: {source} -> {destination} (errno={error_number})"
        )


@dataclass(frozen=True, slots=True)
class StockholmRecord:
    name: str
    sequence: str


@dataclass(frozen=True, slots=True)
class MsaConversionResult:
    output_path: Path
    manifest_path: Path
    accession: str
    member: str
    depth: int
    query_sequence_sha256: str
    a3m_sha256: str
    source_sha256: str
    source_size_bytes: int
    member_sha256: str
    status: str

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "status": self.status,
            "accession": self.accession,
            "member": self.member,
            "output_path": str(self.output_path),
            "manifest_path": str(self.manifest_path),
            "depth": self.depth,
            "query_sequence_sha256": self.query_sequence_sha256,
            "a3m_sha256": self.a3m_sha256,
            "source_sha256": self.source_sha256,
            "source_size_bytes": self.source_size_bytes,
            "member_sha256": self.member_sha256,
        }


def _read_target_fasta(path: Path, accession: str) -> str:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise MsaPrecomputeError(f"target FASTA 无法读取: {path}") from error
    try:
        # Accessions such as UniProt ``P21462`` are intentionally preserved in
        # manifests, but the general EasyDesign target-id contract is lowercase.
        # Here we only need the one-record FASTA parser and sequence validation.
        return normalize_fasta(text, target_id="msa-target").sequence
    except Exception as error:
        raise MsaPrecomputeError(
            f"target FASTA 不符合单条 canonical 蛋白序列契约: {path}"
        ) from error


def _validate_member_name(member: str) -> str:
    normalized = member.replace("\\", "/")
    if (
        not normalized
        or normalized.startswith("/")
        or any(part in {"", ".", ".."} for part in normalized.split("/"))
    ):
        raise MsaPrecomputeError(f"MSA archive member 不是安全相对路径: {member}")
    if not normalized.lower().endswith(".sto"):
        raise MsaPrecomputeError(f"MSA archive member 必须是 Stockholm .sto: {member}")
    return normalized


def default_member(accession: str) -> str:
    if not accession or "/" in accession or "\\" in accession:
        raise MsaPrecomputeError(f"accession 不是安全 ID: {accession!r}")
    return f"{DEFAULT_MEMBER_ROOT}/{accession}.sto"


def parse_stockholm(stream: TextIO) -> tuple[StockholmRecord, ...]:
    """Parse one Stockholm alignment, including interleaved sequence blocks."""

    order: list[str] = []
    chunks: dict[str, list[str]] = {}
    saw_header = False
    terminated = False
    for line_number, raw in enumerate(stream, start=1):
        line = raw.strip()
        if not line:
            continue
        if line.startswith("# STOCKHOLM"):
            if saw_header:
                raise MsaPrecomputeError("Stockholm 文件包含多个 header")
            saw_header = True
            continue
        if line == "//":
            terminated = True
            break
        if line.startswith("#"):
            if not saw_header:
                raise MsaPrecomputeError(f"Stockholm 注释出现在 header 前: line={line_number}")
            continue
        if not saw_header:
            raise MsaPrecomputeError(f"Stockholm 缺少 '# STOCKHOLM 1.0' header: line={line_number}")
        fields = line.split()
        if len(fields) != 2:
            raise MsaPrecomputeError(
                f"Stockholm sequence 行必须是 name + sequence: line={line_number}"
            )
        name, sequence = fields
        if not sequence or any(
            not (char.isascii() and (char.isalpha() or char in _GAP_CHARS or char == "*"))
            for char in sequence
        ):
            raise MsaPrecomputeError(f"Stockholm sequence 含非法字符: line={line_number}")
        if name not in chunks:
            order.append(name)
            chunks[name] = []
        chunks[name].append(sequence)
    if not saw_header or not terminated:
        raise MsaPrecomputeError("Stockholm 缺少终止符 //")
    if not order:
        raise MsaPrecomputeError("Stockholm alignment 为空")
    records = tuple(StockholmRecord(name, "".join(chunks[name])) for name in order)
    lengths = {len(record.sequence) for record in records}
    if len(lengths) != 1:
        raise MsaPrecomputeError(f"Stockholm 对齐长度不一致: lengths={sorted(lengths)}")
    return records


def _ungapped(sequence: str) -> str:
    return "".join(char for char in sequence if char not in _GAP_CHARS)


def _choose_query(
    records: tuple[StockholmRecord, ...],
    *,
    expected_query: str,
    query_name: str | None,
) -> int:
    if query_name is not None:
        matches = [index for index, record in enumerate(records) if record.name == query_name]
        if len(matches) != 1:
            raise MsaPrecomputeError(f"query_name 未唯一命中 Stockholm row: {query_name}")
        index = matches[0]
        if _ungapped(records[index].sequence).upper() != expected_query:
            raise MsaPrecomputeError("指定 query row 与 canonical target 不一致")
        return index
    matches = [
        index
        for index, record in enumerate(records)
        if _ungapped(record.sequence).upper() == expected_query
    ]
    if len(matches) != 1:
        raise MsaPrecomputeError(
            f"无法唯一确定 canonical query row; exact_matches={len(matches)}，请显式提供 query_name"
        )
    return matches[0]


def stockholm_to_a3m(
    records: tuple[StockholmRecord, ...],
    *,
    expected_query: str,
    query_name: str | None = None,
    wrap: int = 80,
) -> tuple[str, int, str]:
    """Convert aligned Stockholm rows to target-first A3M text."""

    if wrap < 1:
        raise ValueError("A3M wrap 必须为正数")
    query_index = _choose_query(records, expected_query=expected_query, query_name=query_name)
    aligned_query = records[query_index].sequence
    converted: list[tuple[str, str]] = []
    order = (query_index, *[i for i in range(len(records)) if i != query_index])
    for index in order:
        record = records[index]
        output: list[str] = []
        for query_char, row_char in zip(aligned_query, record.sequence, strict=True):
            if query_char in _GAP_CHARS:
                if row_char not in _GAP_CHARS and index != query_index:
                    output.append(row_char.upper().lower())
                continue
            output.append("-" if row_char in _GAP_CHARS else row_char.upper())
        sequence = "".join(output)
        if index == query_index and sequence != expected_query:
            raise MsaPrecomputeError("转换后 query 与 canonical target 不一致")
        converted.append((record.name, sequence))
    if len(converted) < 2:
        raise MsaPrecomputeError("MSA depth 必须至少为 2")
    lines: list[str] = []
    for name, sequence in converted:
        lines.append(f">{name}")
        lines.extend(sequence[offset : offset + wrap] for offset in range(0, len(sequence), wrap))
    return "\n".join(lines) + "\n", len(converted), expected_query


def _read_stockholm_bytes(data: bytes) -> tuple[StockholmRecord, ...]:
    try:
        return parse_stockholm(io.StringIO(data.decode("utf-8")))
    except UnicodeDecodeError as error:
        raise MsaPrecomputeError("Stockholm member 不是 UTF-8 文本") from error


def _query_from_stockholm_file(
    path: Path, *, preferred_name: str | None = None, require_standard: bool = True
) -> tuple[str, str]:
    """Read only the first biological Stockholm row as a provisional query.

    The GPCR archive is a source library rather than a target identity registry.
    When a canonical FASTA is not available during the one-time build, retaining
    this source query lets the later ``resolve`` step perform the exact identity
    check without loading the whole alignment into memory.
    """

    chunks: list[str] = []
    first_chunks: list[str] = []
    first_name: str | None = None
    query_name: str | None = preferred_name
    annotated_id: str | None = None
    saw_header = False
    terminated = False
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line_number, raw in enumerate(handle, start=1):
                line = raw.strip()
                if not line:
                    continue
                if line.startswith("# STOCKHOLM"):
                    if saw_header:
                        raise MsaPrecomputeError("Stockholm 文件包含多个 header")
                    saw_header = True
                    continue
                if line.startswith("#=GF ID"):
                    fields = line.split(maxsplit=2)
                    if len(fields) == 3:
                        annotated_id = fields[2].split()[0]
                    continue
                if line == "//":
                    terminated = True
                    break
                if line.startswith("#"):
                    if not saw_header:
                        raise MsaPrecomputeError(
                            f"Stockholm 注释出现在 header 前: line={line_number}"
                        )
                    continue
                if not saw_header:
                    raise MsaPrecomputeError(
                        f"Stockholm 缺少 '# STOCKHOLM 1.0' header: line={line_number}"
                    )
                fields = line.split()
                if len(fields) != 2:
                    raise MsaPrecomputeError(
                        f"Stockholm sequence 行必须是 name + sequence: line={line_number}"
                    )
                name, sequence = fields
                if first_name is None:
                    first_name = name
                if (
                    preferred_name is None
                    and query_name is None
                    and annotated_id is not None
                    and name
                    in {
                        annotated_id,
                        re.sub(r"-i\d+$", "", annotated_id),
                    }
                ):
                    query_name = name
                if name == query_name:
                    if not sequence or any(
                        not (
                            char.isascii() and (char.isalpha() or char in _GAP_CHARS or char == "*")
                        )
                        for char in sequence
                    ):
                        raise MsaPrecomputeError(
                            f"Stockholm query sequence 含非法字符: line={line_number}"
                        )
                    chunks.append(sequence)
                if name == first_name:
                    first_chunks.append(sequence)
    except UnicodeDecodeError as error:
        raise MsaPrecomputeError("Stockholm member 不是 UTF-8 文本") from error
    if not saw_header or not terminated or first_name is None:
        raise MsaPrecomputeError("Stockholm 缺少有效 query row 或终止符 //")
    if preferred_name is not None and not chunks:
        raise MsaPrecomputeError(f"指定 source query row 不存在: {preferred_name}")
    if not chunks:
        query_name = first_name
        chunks = first_chunks
    query = _ungapped("".join(chunks)).upper()
    if not query:
        raise MsaPrecomputeError("Stockholm source query 为空")
    if require_standard and any(char not in CANONICAL_AMINO_ACIDS for char in query):
        raise MsaPrecomputeError("Stockholm source query 不是标准蛋白序列")
    assert query_name is not None
    return query, query_name


def _find_esl_reformat(context: WorkspaceContext | None) -> Path | None:
    candidates: list[Path] = []
    # A bound runtime tool is reproducible; only fall back to PATH when the
    # current clone does not provide one (for direct developer conversion).
    if context is not None:
        candidates.extend(sorted((context.runtime_root / "tools").glob("hmmer/*/bin/esl-reformat")))
    located = shutil.which("esl-reformat")
    if located:
        candidates.append(Path(located))
    for candidate in candidates:
        resolved = candidate.expanduser().resolve(strict=False)
        if resolved.is_file() and (os.name == "nt" or os.access(resolved, os.X_OK)):
            return resolved
    return None


def _find_esl_alimanip(context: WorkspaceContext | None) -> Path | None:
    candidates: list[Path] = []
    if context is not None:
        candidates.extend(sorted((context.runtime_root / "tools").glob("hmmer/*/bin/esl-alimanip")))
    located = shutil.which("esl-alimanip")
    if located:
        candidates.append(Path(located))
    for candidate in candidates:
        resolved = candidate.expanduser().resolve(strict=False)
        if resolved.is_file() and (os.name == "nt" or os.access(resolved, os.X_OK)):
            return resolved
    return None


def _stockholm_first_sequence_name(path: Path) -> str:
    """Read the first biological row without scanning a giant alignment twice."""

    try:
        with path.open("r", encoding="utf-8") as handle:
            saw_header = False
            for line_number, raw in enumerate(handle, start=1):
                line = raw.strip()
                if not line:
                    continue
                if line.startswith("# STOCKHOLM"):
                    saw_header = True
                    continue
                if line == "//":
                    break
                if line.startswith("#"):
                    if not saw_header:
                        raise MsaPrecomputeError(
                            f"Stockholm 注释出现在 header 前: line={line_number}"
                        )
                    continue
                if not saw_header:
                    raise MsaPrecomputeError(
                        f"Stockholm 缺少 '# STOCKHOLM 1.0' header: line={line_number}"
                    )
                fields = line.split()
                if len(fields) != 2:
                    raise MsaPrecomputeError(
                        f"Stockholm sequence 行必须是 name + sequence: line={line_number}"
                    )
                return fields[0]
    except UnicodeDecodeError as error:
        raise MsaPrecomputeError("Stockholm member 不是 UTF-8 文本") from error
    raise MsaPrecomputeError("Stockholm alignment 没有 biological sequence row")


def _stockholm_sequence_names(path: Path) -> tuple[str, ...]:
    """Collect unique sequence names in source order for esl-alimanip reorder."""

    names: list[str] = []
    seen: set[str] = set()
    try:
        with path.open("r", encoding="utf-8") as handle:
            saw_header = False
            terminated = False
            for line_number, raw in enumerate(handle, start=1):
                line = raw.strip()
                if not line:
                    continue
                if line.startswith("# STOCKHOLM"):
                    if saw_header:
                        raise MsaPrecomputeError("Stockholm 文件包含多个 header")
                    saw_header = True
                    continue
                if line == "//":
                    terminated = True
                    break
                if line.startswith("#"):
                    if not saw_header:
                        raise MsaPrecomputeError(
                            f"Stockholm 注释出现在 header 前: line={line_number}"
                        )
                    continue
                if not saw_header:
                    raise MsaPrecomputeError(
                        f"Stockholm 缺少 '# STOCKHOLM 1.0' header: line={line_number}"
                    )
                fields = line.split()
                if len(fields) != 2:
                    raise MsaPrecomputeError(
                        f"Stockholm sequence 行必须是 name + sequence: line={line_number}"
                    )
                name = fields[0]
                if name not in seen:
                    seen.add(name)
                    names.append(name)
            if not saw_header or not terminated or not names:
                raise MsaPrecomputeError("Stockholm 缺少有效 sequence row 或终止符 //")
    except UnicodeDecodeError as error:
        raise MsaPrecomputeError("Stockholm member 不是 UTF-8 文本") from error
    return tuple(names)


def _stockholm_rows_matching_query(path: Path, expected_query: str) -> tuple[str, ...]:
    """Find rows whose ungapped sequence exactly matches a canonical target."""

    expected_digest = hashlib.sha256(expected_query.encode("ascii")).hexdigest()
    digests: dict[str, hashlib._Hash] = {}
    lengths: dict[str, int] = {}
    order: list[str] = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            saw_header = False
            terminated = False
            for line_number, raw in enumerate(handle, start=1):
                line = raw.strip()
                if not line:
                    continue
                if line.startswith("# STOCKHOLM"):
                    if saw_header:
                        raise MsaPrecomputeError("Stockholm 文件包含多个 header")
                    saw_header = True
                    continue
                if line == "//":
                    terminated = True
                    break
                if line.startswith("#"):
                    if not saw_header:
                        raise MsaPrecomputeError(
                            f"Stockholm 注释出现在 header 前: line={line_number}"
                        )
                    continue
                if not saw_header:
                    raise MsaPrecomputeError(
                        f"Stockholm 缺少 '# STOCKHOLM 1.0' header: line={line_number}"
                    )
                fields = line.split()
                if len(fields) != 2:
                    raise MsaPrecomputeError(
                        f"Stockholm sequence 行必须是 name + sequence: line={line_number}"
                    )
                name, sequence = fields
                if not sequence or not all(
                    char.isascii() and (char.isalpha() or char in _GAP_CHARS or char == "*")
                    for char in sequence
                ):
                    raise MsaPrecomputeError(
                        f"Stockholm sequence 含非法字符: line={line_number}"
                    )
                if name not in digests:
                    digests[name] = hashlib.sha256()
                    lengths[name] = 0
                    order.append(name)
                ungapped = _ungapped(sequence).upper()
                digests[name].update(ungapped.encode("ascii"))
                lengths[name] += len(ungapped)
            if not saw_header or not terminated or not order:
                raise MsaPrecomputeError("Stockholm 缺少有效 sequence row 或终止符 //")
    except UnicodeDecodeError as error:
        raise MsaPrecomputeError("Stockholm member 不是 UTF-8 文本") from error
    return tuple(
        name
        for name in order
        if lengths[name] == len(expected_query) and digests[name].hexdigest() == expected_digest
    )


def _reorder_stockholm_query_first(
    source: Path,
    *,
    query_name: str,
    context: WorkspaceContext | None,
    directory: Path | None = None,
) -> Path:
    """Use Easel to reorder a Stockholm source while preserving RF/GR markup."""

    alimanip = _find_esl_alimanip(context)
    if alimanip is None:
        raise MsaPrecomputeError(
            "Stockholm query 不在首行，需要 HMMER esl-alimanip --reorder；"
            "请在当前 runtime/tools/hmmer 安装完整 HMMER 3.4"
        )
    names = _stockholm_sequence_names(source)
    if query_name not in names:
        raise MsaPrecomputeError(f"指定 query row 不存在于 Stockholm: {query_name}")
    ordered_names = (query_name, *[name for name in names if name != query_name])
    work_directory = directory or source.parent
    work_directory.mkdir(parents=True, exist_ok=True)
    names_file = _temporary_path(prefix="msa-order-", suffix=".names", directory=work_directory)
    reordered = _temporary_path(prefix="msa-reordered-", suffix=".sto", directory=work_directory)
    try:
        names_file.write_text("\n".join(ordered_names) + "\n", encoding="utf-8", newline="\n")
        completed = subprocess.run(
            [
                str(alimanip),
                "--informat",
                "stockholm",
                "--outformat",
                "stockholm",
                "--reorder",
                str(names_file),
                "-o",
                str(reordered),
                str(source),
            ],
            capture_output=True,
            check=False,
            text=False,
        )
        if completed.returncode != 0:
            stderr = completed.stderr.decode("utf-8", errors="replace")
            raise MsaPrecomputeError(
                f"esl-alimanip 重排失败 (returncode={completed.returncode}): {stderr[-2000:]}"
            )
        return reordered
    except OSError as error:
        reordered.unlink(missing_ok=True)
        raise MsaPrecomputeError("esl-alimanip 无法启动") from error
    except Exception:
        reordered.unlink(missing_ok=True)
        raise
    finally:
        names_file.unlink(missing_ok=True)


@lru_cache(maxsize=8)
def _esl_reformat_provenance(path_text: str) -> dict[str, object]:
    """Capture the executable identity used for reproducible conversion."""

    path = Path(path_text)
    record: dict[str, object] = {
        "path": str(path),
        "sha256": sha256_file(path),
    }
    last_error: BaseException | None = None
    for option in ("-h", "--version"):
        try:
            completed = subprocess.run(
                [str(path), option],
                capture_output=True,
                check=False,
                text=False,
                timeout=30,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            last_error = error
            continue
        version_output = (completed.stdout + completed.stderr).decode(
            "utf-8", errors="replace"
        )
        version_line = next(
            (
                line.strip()
                for line in version_output.splitlines()
                if "Easel " in line or "HMMER " in line
            ),
            "",
        )
        if version_line:
            record["version"] = version_line[:256]
            record["version_command"] = option
            record["version_returncode"] = completed.returncode
            return record
        last_error = MsaPrecomputeError(
            f"HMMER esl-reformat {option} 未返回版本信息 "
            f"(returncode={completed.returncode})"
        )
    if last_error is not None:
        raise MsaPrecomputeError(f"无法读取 HMMER esl-reformat 版本: {path}") from last_error
    raise MsaPrecomputeError(f"无法读取 HMMER esl-reformat 版本: {path}")


def _conversion_tool_record(
    *, context: WorkspaceContext | None, used: bool
) -> dict[str, object]:
    """Return a stable toolchain record without probing PATH repeatedly."""

    if not used:
        return {"used": False, "name": "python-stockholm"}
    reformatter = _find_esl_reformat(context)
    if reformatter is None:
        # _convert_member_file raises a more specific error before this can
        # normally happen; keep the record fail-closed for direct callers.
        raise MsaPrecomputeError("转换需要 HMMER esl-reformat，但当前 runtime 未找到")
    return {
        "used": True,
        "name": "hmmer-esl-reformat",
        **_esl_reformat_provenance(str(reformatter)),
    }


def _validate_a3m_file(
    path: Path,
    *,
    expected_query: str,
    query_name: str | None,
) -> tuple[int, str]:
    records = 0
    first_name: str | None = None
    first_sequence: list[str] = []
    current: list[str] | None = None
    current_has_sequence = False
    try:
        # FASTA/A3M headers are UTF-8 in the upstream HMMER output (for
        # example, some GPCR names contain Greek symbols); sequence rows stay
        # strictly ASCII so downstream model alphabets remain unambiguous.
        with path.open("r", encoding="utf-8") as handle:
            for line_number, raw in enumerate(handle, start=1):
                line = raw.strip()
                if not line:
                    continue
                if line.startswith(">"):
                    if current is not None and not current_has_sequence:
                        raise MsaPrecomputeError("A3M 包含空 sequence record")
                    records += 1
                    current = []
                    current_has_sequence = False
                    if records == 1:
                        first_name = line[1:].strip().split(maxsplit=1)[0]
                        first_sequence = current
                    continue
                if current is None:
                    raise MsaPrecomputeError(f"A3M 在首个 header 前出现序列: line={line_number}")
                if not line.isascii() or any(
                    not (char.isalpha() or char in "-.*") for char in line
                ):
                    raise MsaPrecomputeError(f"A3M 含非法字符: line={line_number}")
                current.append(line)
                current_has_sequence = True
    except UnicodeDecodeError as error:
        raise MsaPrecomputeError("转换输出不是合法 UTF-8 A3M") from error
    if current is not None and not current_has_sequence:
        raise MsaPrecomputeError("A3M 包含空 sequence record")
    if records < 2 or not first_sequence:
        raise MsaPrecomputeError(f"转换后 MSA depth 不足: depth={records}")
    if query_name is not None and first_name != query_name:
        raise MsaPrecomputeError(
            f"转换输出首条 query 不是指定 row: expected={query_name}, actual={first_name}"
        )
    query = "".join(first_sequence)
    if query != expected_query:
        raise MsaPrecomputeError("转换输出首条 query 与 canonical target 不一致")
    return records, query


def _run_external_conversion(
    source: Path,
    destination: Path,
    *,
    expected_query: str,
    query_name: str | None,
    reformatter: Path,
) -> tuple[int, str]:
    try:
        with destination.open("wb") as output:
            completed = subprocess.run(
                [str(reformatter), "a2m", str(source)],
                stdout=output,
                stderr=subprocess.PIPE,
                check=False,
                text=False,
            )
    except OSError as error:
        raise MsaPrecomputeError("esl-reformat 无法启动") from error
    if completed.returncode != 0:
        stderr = completed.stderr.decode("utf-8", errors="replace")
        raise MsaPrecomputeError(
            f"esl-reformat 转换失败 (returncode={completed.returncode}): {stderr[-2000:]}"
        )
    return _validate_a3m_file(destination, expected_query=expected_query, query_name=query_name)


def _stockholm_has_rf(path: Path) -> bool:
    """Return whether a Stockholm member carries a reference (RF) annotation."""

    try:
        with path.open("r", encoding="utf-8") as handle:
            for raw in handle:
                if raw.lstrip().startswith("#=GC RF"):
                    return True
                if raw.strip() == "//":
                    break
    except UnicodeDecodeError as error:
        raise MsaPrecomputeError("Stockholm member 不是 UTF-8 文本") from error
    return False


def _requires_external_conversion(path: Path) -> bool:
    if path.stat().st_size >= _EXTERNAL_CONVERTER_THRESHOLD_BYTES:
        return True
    # RF defines consensus/insertion columns. The pure Python fallback cannot
    # safely reproduce that semantic, so it must defer to HMMER whenever RF is
    # present, even for a small member.
    return _stockholm_has_rf(path)


def _write_temp_member(
    source: Path,
    *,
    member: str,
    directory: Path,
) -> tuple[Path, int, str]:
    """Extract one member to a temporary file while hashing its raw bytes."""

    safe = _validate_member_name(member)
    try:
        archive = tarfile.open(source, mode="r|gz")
    except KeyError as error:
        raise MsaPrecomputeError(f"MSA archive 中找不到 member: {safe}") from error
    except (OSError, tarfile.TarError) as error:
        raise MsaPrecomputeError(f"MSA archive 无法打开: {source}") from error
    temporary = _temporary_path(prefix="msa-member-", suffix=".sto", directory=directory)
    digest = hashlib.sha256()
    success = False
    try:
        for info in archive:
            if info.name != safe:
                continue
            if not info.isfile():
                raise MsaPrecomputeError(f"archive member 不是普通文件: {safe}")
            extracted = archive.extractfile(info)
            if extracted is None:
                raise MsaPrecomputeError(f"archive member 无法读取: {safe}")
            with extracted, temporary.open("wb") as destination:
                while True:
                    chunk = extracted.read(1024 * 1024)
                    if not chunk:
                        break
                    digest.update(chunk)
                    destination.write(chunk)
                destination.flush()
                os.fsync(destination.fileno())
            success = True
            return temporary, info.size, digest.hexdigest()
        raise MsaPrecomputeError(f"MSA archive 中找不到 member: {safe}")
    except (OSError, tarfile.TarError) as error:
        raise MsaPrecomputeError(f"MSA archive member 无法读取: {safe}") from error
    finally:
        archive.close()
        if not success:
            temporary.unlink(missing_ok=True)


def _extract_open_member(
    archive: tarfile.TarFile,
    info: tarfile.TarInfo,
    *,
    directory: Path,
) -> tuple[Path, int, str]:
    """Stream one already-selected tar member into a temporary file."""

    safe = _validate_member_name(info.name)
    if not info.isfile():
        raise MsaPrecomputeError(f"archive member 不是普通文件: {safe}")
    extracted = archive.extractfile(info)
    if extracted is None:
        raise MsaPrecomputeError(f"archive member 无法读取: {safe}")
    temporary = _temporary_path(prefix="msa-member-", suffix=".sto", directory=directory)
    digest = hashlib.sha256()
    try:
        with extracted, temporary.open("wb") as destination:
            while True:
                chunk = extracted.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
                destination.write(chunk)
            destination.flush()
            os.fsync(destination.fileno())
        return temporary, info.size, digest.hexdigest()
    except (OSError, tarfile.TarError) as error:
        temporary.unlink(missing_ok=True)
        raise MsaPrecomputeError(f"archive member 无法读取: {safe}") from error
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _exclusive_json(path: Path, payload: dict[str, object]) -> None:
    if path.exists():
        raise MsaPrecomputeError(f"manifest 已存在，拒绝覆盖: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = _temporary_path(prefix=f".{path.name}.", suffix=".tmp", directory=path.parent)
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        _publish_no_replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _exclusive_bytes(path: Path, data: bytes) -> None:
    if path.exists():
        raise MsaPrecomputeError(f"A3M 输出已存在，拒绝覆盖: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = _temporary_path(prefix=f".{path.name}.", suffix=".tmp", directory=path.parent)
    try:
        with temporary.open("wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        _publish_no_replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _exclusive_copy_verified(source: Path, destination: Path, *, expected_sha256: str) -> str:
    """Stream-copy a verified A3M and publish it without replacing output."""

    if destination.exists():
        raise MsaPrecomputeError(f"输出已存在，拒绝覆盖: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = _temporary_path(
        prefix=f".{destination.name}.", suffix=".tmp", directory=destination.parent
    )
    digest = hashlib.sha256()
    try:
        with source.open("rb") as input_handle, temporary.open("wb") as output_handle:
            while True:
                chunk = input_handle.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
                output_handle.write(chunk)
            output_handle.flush()
            os.fsync(output_handle.fileno())
        actual_sha256 = digest.hexdigest()
        if actual_sha256 != expected_sha256:
            raise MsaPrecomputeError("MSA library A3M SHA-256 不一致")
        _publish_no_replace(temporary, destination)
        return actual_sha256
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _exclusive_move(source: Path, destination: Path) -> None:
    """Publish a completed temporary file without replacing user data."""

    _publish_no_replace(source, destination)


def _convert_member_file(
    source_file: Path,
    *,
    expected_query: str,
    query_name: str | None,
    context: WorkspaceContext | None,
    destination: Path,
    member_sha256: str | None = None,
    member_size_bytes: int | None = None,
) -> tuple[int, str, str]:
    """Convert one member file and return (depth, member_sha, a3m_sha)."""

    if destination.exists():
        raise MsaPrecomputeError(f"A3M 输出已存在，拒绝覆盖: {destination}")
    member_sha = member_sha256 or sha256_file(source_file)
    if member_size_bytes is not None and source_file.stat().st_size != member_size_bytes:
        raise MsaPrecomputeError("Stockholm member size 与 archive header 不一致")
    temporary_a3m = _temporary_path(prefix="msa-a3m-", suffix=".tmp", directory=destination.parent)
    reordered_source: Path | None = None
    try:
        if _requires_external_conversion(source_file):
            reformatter = _find_esl_reformat(context)
            if reformatter is None:
                raise MsaPrecomputeError(
                    "大型 Stockholm member 需要 HMMER esl-reformat；"
                    "请在当前 runtime/tools/hmmer 安装 HMMER 3.4"
                )
            conversion_source = source_file
            if query_name is not None and _stockholm_first_sequence_name(source_file) != query_name:
                reordered_source = _reorder_stockholm_query_first(
                    source_file,
                    query_name=query_name,
                    context=context,
                    directory=destination.parent,
                )
                conversion_source = reordered_source
            depth, _query = _run_external_conversion(
                conversion_source,
                temporary_a3m,
                expected_query=expected_query,
                query_name=query_name,
                reformatter=reformatter,
            )
        else:
            data = source_file.read_bytes()
            records = _read_stockholm_bytes(data)
            a3m_text, depth, _query = stockholm_to_a3m(
                records, expected_query=expected_query, query_name=query_name
            )
            temporary_a3m.write_text(a3m_text, encoding="utf-8", newline="\n")
        a3m_sha = sha256_file(temporary_a3m)
        _exclusive_move(temporary_a3m, destination)
        return depth, member_sha, a3m_sha
    except Exception:
        temporary_a3m.unlink(missing_ok=True)
        raise
    finally:
        if reordered_source is not None:
            reordered_source.unlink(missing_ok=True)


def _source_identity(source: Path) -> tuple[int, str]:
    return source.stat().st_size, sha256_file(source)


def convert_stockholm_to_a3m(
    *,
    source: Path,
    accession: str,
    target_fasta: Path,
    output: Path,
    member: str | None = None,
    query_name: str | None = None,
    context: WorkspaceContext | None = None,
    source_sha256: str | None = None,
    source_size_bytes: int | None = None,
) -> MsaConversionResult:
    """Convert one target entry without extracting or modifying the source."""

    source_path = source.expanduser().resolve(strict=True)
    output_path = output.expanduser().resolve(strict=False)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path = output_path.with_name(f"{output_path.name}.manifest.json")
    expected_query = _read_target_fasta(target_fasta.expanduser().resolve(strict=True), accession)
    source_size_before, source_sha_before = _source_identity(source_path)
    if source_size_bytes is not None and source_size_bytes != source_size_before:
        raise MsaPrecomputeError("source archive size identity 与实际文件不一致")
    if source_sha256 is not None and source_sha256 != source_sha_before:
        raise MsaPrecomputeError("source archive SHA-256 identity 与实际文件不一致")
    temporary_member: Path | None = None
    member_size: int
    member_sha: str
    if source_path.suffix.lower() == ".sto":
        if member is not None:
            raise MsaPrecomputeError(
                "直接 .sto source 不接受 --member；请把 member 仅用于 tar.gz source"
            )
        selected_member = source_path.name
        member_file = source_path
        member_size = source_size_before
        member_sha = source_sha_before
    else:
        selected_member = _validate_member_name(member or default_member(accession))
        temporary_member, member_size, member_sha = _write_temp_member(
            source_path,
            member=selected_member,
            directory=output_path.parent,
        )
        member_file = temporary_member
    effective_query_name = query_name
    if effective_query_name is None:
        source_query, effective_query_name = _query_from_stockholm_file(
            member_file, require_standard=False
        )
        if source_query != expected_query:
            matches = _stockholm_rows_matching_query(member_file, expected_query)
            if len(matches) != 1:
                raise MsaPrecomputeError(
                    "Stockholm 中没有唯一 row 与 canonical target 完全匹配; "
                    f"exact_matches={len(matches)}，请显式提供 query_name"
                )
            effective_query_name = matches[0]
    source_size_after_extract, source_sha_after_extract = _source_identity(source_path)
    if (source_size_after_extract, source_sha_after_extract) != (
        source_size_before,
        source_sha_before,
    ):
        if temporary_member is not None:
            temporary_member.unlink(missing_ok=True)
        raise MsaPrecomputeError("source archive 在 member 提取期间发生变化，拒绝转换")
    uses_hmmer = False
    try:
        uses_hmmer = _requires_external_conversion(member_file)
        conversion_tool = _conversion_tool_record(context=context, used=uses_hmmer)
        depth, member_sha, a3m_sha = _convert_member_file(
            member_file,
            expected_query=expected_query,
            query_name=effective_query_name,
            context=context,
            destination=output_path,
            member_sha256=member_sha,
            member_size_bytes=member_size,
        )
    finally:
        if temporary_member is not None:
            temporary_member.unlink(missing_ok=True)
    source_size_after, source_sha_after = _source_identity(source_path)
    if (source_size_after, source_sha_after) != (source_size_before, source_sha_before):
        output_path.unlink(missing_ok=True)
        raise MsaPrecomputeError("source archive 在转换期间发生变化，拒绝发布 A3M")
    actual_size, actual_sha = source_size_before, source_sha_before
    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "converter": "easydesign-stockholm-to-a3m",
        "converter_version": CONVERTER_VERSION,
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "accession": accession,
        "source": {
            "path": str(source_path),
            "size_bytes": actual_size,
            "sha256": actual_sha,
            "member": selected_member,
            "member_sha256": member_sha,
        },
        "target": {
            "sequence_sha256": hashlib.sha256(expected_query.encode("ascii")).hexdigest(),
            "length": len(expected_query),
            "query_name": effective_query_name,
            "query_identity": "canonical-target",
        },
        "conversion": {
            "backend": "hmmer-esl-reformat-a2m" if uses_hmmer else "python-stockholm",
            "rf_policy": "delegated-to-hmmer" if uses_hmmer else "not-present",
            "encoding_policy": "utf8-header/ascii-sequence",
            "tool": conversion_tool,
        },
        "a3m": {
            "path": output_path.name,
            "sha256": a3m_sha,
            "size_bytes": output_path.stat().st_size,
            "depth": depth,
            "query_first_exact": True,
        },
    }
    try:
        _exclusive_json(manifest_path, payload)
    except Exception:
        output_path.unlink(missing_ok=True)
        raise
    return MsaConversionResult(
        output_path=output_path,
        manifest_path=manifest_path,
        accession=accession,
        member=selected_member,
        depth=depth,
        query_sequence_sha256=hashlib.sha256(expected_query.encode("ascii")).hexdigest(),
        a3m_sha256=a3m_sha,
        source_sha256=actual_sha,
        source_size_bytes=actual_size,
        member_sha256=member_sha,
        status="converted",
    )


def _target_file(targets: Path, accession: str) -> Path | None:
    if not targets.is_dir():
        raise MsaPrecomputeError(f"targets 必须是目录: {targets}")
    for suffix in (".fasta", ".fa", ".faa", ".fas"):
        candidate = targets / f"{accession}{suffix}"
        if candidate.is_file():
            return candidate
    return None


def build_stockholm_library(
    *,
    source: Path,
    targets: Path,
    output_root: Path,
    release_id: str,
    member_root: str = DEFAULT_MEMBER_ROOT,
    query_names: dict[str, str] | None = None,
    context: WorkspaceContext | None = None,
    progress: Callable[[dict[str, object]], None] | None = None,
) -> dict[str, object]:
    """Build one immutable, canonical-sequence-keyed A3M release."""

    source_path = source.expanduser().resolve(strict=True)
    targets_path = targets.expanduser().resolve(strict=True)
    if not targets_path.is_dir():
        raise MsaPrecomputeError(f"targets 必须是目录: {targets_path}")
    output_root = output_root.expanduser().resolve(strict=False)
    if output_root.name != release_id:
        raise MsaPrecomputeError("output root 必须以 release ID 命名")
    if output_root.exists():
        raise MsaPrecomputeError(f"library output 已存在，拒绝覆盖: {output_root}")
    source_size, source_sha = _source_identity(source_path)
    output_root.parent.mkdir(parents=True, exist_ok=True)
    staging_root = Path(
        tempfile.mkdtemp(prefix=f".{output_root.name}.staging-", dir=output_root.parent)
    )
    a3m_root = staging_root / "entries"
    a3m_root.mkdir()
    member_staging = Path(tempfile.mkdtemp(prefix="members-", dir=staging_root))
    entries: list[dict[str, object]] = []
    seen_accessions: set[str] = set()
    seen_sequences: set[str] = set()
    member_prefix = member_root.rstrip("/").replace("\\", "/")

    def report(item: dict[str, object]) -> None:
        if progress is not None:
            progress(item)

    try:
        archive_context = tarfile.open(source_path, mode="r|gz")
    except (OSError, tarfile.TarError) as error:
        shutil.rmtree(staging_root, ignore_errors=True)
        raise MsaPrecomputeError(f"MSA archive 无法打开: {source_path}") from error
    with archive_context as archive:
        for info in archive:
            member = info.name.replace("\\", "/")
            if not info.isfile() or not member.lower().endswith(".sto"):
                continue
            if member_prefix and not member.startswith(member_prefix + "/"):
                continue
            try:
                safe_member = _validate_member_name(member)
            except MsaPrecomputeError as error:
                invalid_item: dict[str, object] = {
                    "member": member,
                    "status": "conversion-failed",
                    "error": str(error),
                }
                entries.append(invalid_item)
                report(invalid_item)
                continue
            accession = Path(safe_member).stem
            if accession in seen_accessions:
                duplicate_item: dict[str, object] = {
                    "accession": accession,
                    "member": safe_member,
                    "status": "duplicate-accession",
                    "error": "同一 archive 中 accession 出现多次",
                }
                entries.append(duplicate_item)
                report(duplicate_item)
                continue
            seen_accessions.add(accession)
            target = _target_file(targets_path, accession)
            if target is None:
                missing_item: dict[str, object] = {
                    "accession": accession,
                    "member": safe_member,
                    "status": "missing-target-fasta",
                }
                entries.append(missing_item)
                report(missing_item)
                continue
            temporary_member: Path | None = None
            try:
                temporary_member, member_size, member_sha = _extract_open_member(
                    archive, info, directory=member_staging
                )
                explicit_query_name = (query_names or {}).get(accession)
                source_query, source_query_name = _query_from_stockholm_file(
                    temporary_member,
                    preferred_name=explicit_query_name,
                    require_standard=False,
                )
                expected = _read_target_fasta(target, accession)
                if explicit_query_name is not None:
                    conversion_query_name = explicit_query_name
                elif source_query == expected:
                    conversion_query_name = source_query_name
                else:
                    exact_matches = _stockholm_rows_matching_query(temporary_member, expected)
                    if len(exact_matches) != 1:
                        raise MsaPrecomputeError(
                            "Stockholm 中没有唯一 row 与 canonical target 完全匹配; "
                            f"exact_matches={len(exact_matches)}，请显式提供 query_name"
                        )
                    conversion_query_name = exact_matches[0]
                query_sha = hashlib.sha256(expected.encode("ascii")).hexdigest()
                if query_sha in seen_sequences:
                    raise MsaPrecomputeError(
                        "多个 source member 映射到同一 canonical sequence SHA-256"
                    )
                uses_hmmer = _requires_external_conversion(temporary_member)
                _conversion_tool_record(context=context, used=uses_hmmer)
                output = a3m_root / f"{query_sha}.a3m"
                depth, converted_member_sha, a3m_sha = _convert_member_file(
                    temporary_member,
                    expected_query=expected,
                    query_name=conversion_query_name,
                    context=context,
                    destination=output,
                    member_sha256=member_sha,
                    member_size_bytes=member_size,
                )
                if converted_member_sha != member_sha:
                    raise MsaPrecomputeError("临时 member checksum/size 在转换期间发生变化")
                seen_sequences.add(query_sha)
                entry: dict[str, object] = {
                    "canonical_sequence_sha256": query_sha,
                    "a3m_path": output.relative_to(staging_root).as_posix(),
                    "a3m_sha256": a3m_sha,
                    "a3m_size_bytes": output.stat().st_size,
                    "depth": depth,
                    "query_name": conversion_query_name,
                    "accessions": [accession],
                    "source_member": safe_member,
                    "source_member_sha256": member_sha,
                    "query_match": "exact",
                }
                entries.append(entry)
                report(entry)
            except (MsaPrecomputeError, OSError) as error:
                failed_item: dict[str, object] = {
                    "accession": accession,
                    "member": safe_member,
                    "status": "conversion-failed",
                    "error": str(error),
                }
                entries.append(failed_item)
                report(failed_item)
            finally:
                if temporary_member is not None:
                    temporary_member.unlink(missing_ok=True)
    member_staging.rmdir()
    converted_count = sum("canonical_sequence_sha256" in item for item in entries)
    failed_count = len(entries) - converted_count
    build_status = "ready" if converted_count > 0 and failed_count == 0 else "failed"
    manifest: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "release_id": release_id,
        "status": build_status,
        "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "producer": {
            "name": "gpcr-msa-release-builder",
            "version": CONVERTER_VERSION,
        },
        "source": {
            "kind": "stockholm-archive",
            "label": source_path.name,
            "size_bytes": source_size,
            "sha256": source_sha,
        },
        "entries": sorted(entries, key=lambda item: str(item.get("canonical_sequence_sha256", ""))),
    }
    if build_status != "ready":
        raise MsaPrecomputeError(
            "MSA library 不是全量成功；"
            f"converted={converted_count}, failed={failed_count}, "
            f"staging={staging_root}，拒绝发布"
        )
    validated_manifest = MsaLibraryManifest.model_validate(manifest)
    manifest_path = dump_model(validated_manifest, staging_root / "library-manifest.json")
    receipt = MsaReleaseReceipt(
        release_id=release_id,
        created_at=validated_manifest.created_at,
        library_manifest_sha256=sha256_file(manifest_path),
        entry_count=len(validated_manifest.entries),
    )
    dump_model(receipt, staging_root / "release-receipt.json")
    final_size, final_sha = _source_identity(source_path)
    if final_size != source_size or final_sha != source_sha:
        raise MsaPrecomputeError("MSA archive 在构建期间发生变化；staging 已保留，拒绝发布")
    _publish_directory_no_replace(staging_root, output_root)
    return validated_manifest.model_dump(mode="json")


def _query_names(path: Path | None) -> dict[str, str] | None:
    if path is None:
        return None
    try:
        payload = json.loads(path.expanduser().resolve(strict=True).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise MsaPrecomputeError(f"query-names JSON 无法读取: {path}") from error
    if not isinstance(payload, dict) or any(
        not isinstance(key, str)
        or not key
        or not isinstance(value, str)
        or not value
        for key, value in payload.items()
    ):
        raise MsaPrecomputeError("query-names 必须是非空 accession 到 row name 的 mapping")
    return payload


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build", help="build one immutable MSA library release")
    build.add_argument("--source", type=Path, required=True)
    build.add_argument("--targets", type=Path, required=True)
    build.add_argument("--release-id", required=True)
    build.add_argument("--output-root", type=Path, required=True)
    build.add_argument("--member-root", default=DEFAULT_MEMBER_ROOT)
    build.add_argument("--query-names", type=Path)
    convert = commands.add_parser("convert", help="convert and audit one Stockholm member")
    convert.add_argument("--source", type=Path, required=True)
    convert.add_argument("--accession", required=True)
    convert.add_argument("--target-fasta", type=Path, required=True)
    convert.add_argument("--output", type=Path, required=True)
    convert.add_argument("--member")
    convert.add_argument("--query-name")
    return parser


def main() -> int:
    arguments = _parser().parse_args()
    context = WorkspaceContext.discover()
    if arguments.command == "build":
        result = build_stockholm_library(
            source=arguments.source,
            targets=arguments.targets,
            output_root=arguments.output_root,
            release_id=arguments.release_id,
            member_root=arguments.member_root,
            query_names=_query_names(arguments.query_names),
            context=context,
        )
    else:
        result = convert_stockholm_to_a3m(
            source=arguments.source,
            accession=arguments.accession,
            target_fasta=arguments.target_fasta,
            output=arguments.output,
            member=arguments.member,
            query_name=arguments.query_name,
            context=context,
        ).as_dict()
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
