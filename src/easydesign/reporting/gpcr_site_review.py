"""Build and verify portable GPCR hotspot review reports.

The report renderer is part of the installed EasyDesign package.  Templates,
styles, JavaScript, and the pinned Mol* distribution are package resources, so
report generation does not depend on a source checkout or the current working
directory.

Public API
----------
``ReviewInput``
    Optional explicit pairing of one analysis JSON and its source structure.
``generate_review_report(input_source, output_dir, mode="both", ...)``
    Resolve 0/1/N analyses, publish a new immutable ``report-NNNN`` revision,
    update ``LATEST``, and return ``ReviewReportOutcome``.
``resolve_latest_review_report(output_dir)``
    Resolve and verify the report named by ``LATEST``.
``validate_review_report(report_or_base_dir)``
    Verify the manifest allowlist, file sizes, SHA-256 values, local-only
    resource references, and Mol* 5.11.0 asset identity; return the manifest.

The accepted ``input_source`` forms are a directory containing zero or more
``gpcr-hotspot-analysis.json`` files, one analysis JSON, a batch JSON/YAML
manifest with ``structures`` or ``entries``, or a sequence of ``ReviewInput``
and analysis paths. Paths in a batch manifest are resolved relative to that
manifest. The analysis schema is consumed defensively so the report remains a
presentation layer rather than a second scientific schema authority.
"""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
import shutil
import tempfile
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Any, Literal

try:
    import yaml  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover - JSON-only environments remain useful.
    yaml = None

Mode = Literal["both", "inhibit", "activate"]
REPORT_SCHEMA_VERSION = "1.0"
GENERATOR_VERSION = "0.1.0"
MOLSTAR_VERSION = "5.11.0"
LATEST_PATTERN = re.compile(r"^report-(?P<revision>[0-9]{4,})/review-manifest\.json$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
URL_PATTERN = re.compile(r"^https://", re.IGNORECASE)
WINDOWS_ABSOLUTE_PATTERN = re.compile(r"^[A-Za-z]:[\\/]")
SAFE_ID_PATTERN = re.compile(r"[^a-z0-9._-]+")

MOLSTAR_FILES = {
    "molstar.js": "7fad5561c74bc900930fb57d6ab028d1aafdda82223a901bf932b1098e84f1f3",
    "molstar.css": "5b68ceb6d3642549b4e9b2c071e58e41b98a5350ae269180587b39da86925d55",
    "LICENSE": "eabd1831ed605a29cf9d7e60221c019c1bc026add81e3c0686ce5f24b3d4d500",
}
STATIC_FILES = {
    "report.css": "assets/report.css",
    "index.js": "assets/index.js",
    "structure.js": "assets/structure.js",
}
REPORT_RESOURCE_ROOT = files("easydesign.reporting").joinpath(
    "static", "gpcr_site_review"
)
MOLSTAR_RESOURCE_ROOT = files("easydesign.reporting").joinpath(
    "static", "target_viewer", "vendor", "molstar"
)


class ReviewReportError(ValueError):
    """The report input, output revision, or integrity contract is invalid."""


@dataclass(frozen=True, slots=True)
class ReviewInput:
    """One analysis/structure pair supplied by a CLI or batch manifest."""

    analysis_path: Path
    structure_path: Path | None = None
    structure_id: str | None = None
    receptor_chain: str | None = None


@dataclass(frozen=True, slots=True)
class ReviewReportOutcome:
    """Paths and counts for a successfully published immutable revision."""

    report_root: Path
    manifest_path: Path
    index_path: Path
    revision: int
    structure_count: int


@dataclass(slots=True)
class GpcrReviewServer:
    server: ThreadingHTTPServer
    report_root: Path

    @property
    def url(self) -> str:
        raw_host, port = self.server.server_address[:2]
        host = raw_host.decode("ascii") if isinstance(raw_host, bytes) else str(raw_host)
        return f"http://{host}:{port}/index.html"

    def serve_forever(self) -> None:
        self.server.serve_forever()

    def close(self) -> None:
        self.server.server_close()


class _ReviewHandler(SimpleHTTPRequestHandler):
    def end_headers(self) -> None:
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self' blob: data:; script-src 'self' 'unsafe-inline' blob:; "
            "style-src 'self' 'unsafe-inline'; img-src 'self' blob: data:; "
            "connect-src 'self' blob:; worker-src 'self' blob:",
        )
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, _format: str, *_args: object) -> None:
        return


@dataclass(frozen=True, slots=True)
class _ResolvedInput:
    source: ReviewInput
    analysis: dict[str, Any]
    structure_path: Path
    structure_id: str
    slug: str
    structure_format: Literal["pdb", "mmcif"]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _json_dump(value: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def _write_exclusive(path: Path, content: str | bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = "xb" if isinstance(content, bytes) else "x"
    kwargs: dict[str, Any] = {}
    if isinstance(content, str):
        kwargs.update(encoding="utf-8", newline="\n")
    with path.open(mode, **kwargs) as handle:
        handle.write(content)


def _copy_exclusive(source: Path, destination: Path) -> None:
    if not source.is_file():
        raise ReviewReportError(f"Missing report source file: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with source.open("rb") as input_handle, destination.open("xb") as output_handle:
        shutil.copyfileobj(input_handle, output_handle)


def _load_mapping(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ReviewReportError(f"Input does not exist: {path}")
    try:
        text = path.read_text(encoding="utf-8")
        if path.suffix.lower() in {".yaml", ".yml"}:
            if yaml is None:
                raise ReviewReportError("PyYAML is required to read a YAML batch manifest")
            value = yaml.safe_load(text)
        else:
            value = json.loads(text)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ReviewReportError(f"Cannot parse report input {path}: {error}") from error
    if not isinstance(value, dict):
        raise ReviewReportError(f"Report input must be a mapping: {path}")
    return value


def _nested(mapping: Mapping[str, Any], *paths: str) -> Any:
    for path in paths:
        current: Any = mapping
        for part in path.split("."):
            if not isinstance(current, Mapping) or part not in current:
                current = None
                break
            current = current[part]
        if current not in (None, ""):
            return current
    return None


def _string(value: Any, default: str = "unresolved") -> str:
    if value is None or value == "":
        return default
    return str(value)


def _safe_slug(value: str) -> str:
    slug = SAFE_ID_PATTERN.sub("-", value.strip().lower()).strip("-._")
    if not slug:
        slug = "structure"
    return slug[:80]


def _is_analysis(mapping: Mapping[str, Any]) -> bool:
    keys = set(mapping)
    return bool(keys & {"identity", "topology", "candidates", "candidate_sets", "membrane"})


def _manifest_inputs(path: Path, mapping: Mapping[str, Any]) -> list[ReviewInput]:
    raw_entries = mapping.get("structures", mapping.get("entries", mapping.get("items")))
    if not isinstance(raw_entries, list):
        raise ReviewReportError(f"JSON/YAML is neither an analysis nor a batch manifest: {path}")
    resolved: list[ReviewInput] = []
    for index, item in enumerate(raw_entries):
        if not isinstance(item, Mapping):
            raise ReviewReportError(f"Batch entry {index} must be a mapping")
        analysis_value = _nested(
            item,
            "analysis_path",
            "analysis",
            "gpcr_hotspot_analysis",
            "path",
        )
        if not isinstance(analysis_value, str) or not analysis_value.strip():
            raise ReviewReportError(f"Batch entry {index} is missing analysis_path")
        structure_value = _nested(item, "structure_path", "structure.path", "structure")
        if isinstance(structure_value, Mapping):
            structure_value = structure_value.get("path")
        resolved.append(
            ReviewInput(
                analysis_path=(path.parent / analysis_value).resolve(),
                structure_path=(
                    (path.parent / structure_value).resolve()
                    if isinstance(structure_value, str) and structure_value.strip()
                    else None
                ),
                structure_id=(
                    str(_nested(item, "structure_id", "id"))
                    if _nested(item, "structure_id", "id") is not None
                    else None
                ),
                receptor_chain=(
                    str(_nested(item, "receptor_chain", "chain"))
                    if _nested(item, "receptor_chain", "chain") is not None
                    else None
                ),
            )
        )
    return resolved


def resolve_review_inputs(
    input_source: Path | str | Sequence[Path | str | ReviewInput],
) -> list[ReviewInput]:
    """Resolve the supported 0/1/N input forms without changing their order."""

    if isinstance(input_source, (str, Path)):
        path = Path(input_source).resolve()
        if path.is_dir():
            return [
                ReviewInput(analysis_path=item.resolve())
                for item in sorted(path.rglob("gpcr-hotspot-analysis.json"))
            ]
        mapping = _load_mapping(path)
        if _is_analysis(mapping):
            return [ReviewInput(analysis_path=path)]
        return _manifest_inputs(path, mapping)

    resolved: list[ReviewInput] = []
    for item in input_source:
        resolved.append(
            item
            if isinstance(item, ReviewInput)
            else ReviewInput(analysis_path=Path(item).resolve())
        )
    return resolved


def _structure_path(source: ReviewInput, analysis: Mapping[str, Any]) -> Path:
    if source.structure_path is not None:
        return source.structure_path.resolve()
    value = _nested(
        analysis,
        "structure.path",
        "structure_path",
        "input.structure_path",
        "inputs.structure_path",
        "provenance.structure_path",
        "source_structure.path",
    )
    if not isinstance(value, str) or not value.strip():
        raise ReviewReportError(
            f"Analysis does not identify a structure path: {source.analysis_path}"
        )
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = source.analysis_path.parent / candidate
    return candidate.resolve()


def _resolve_inputs(inputs: Iterable[ReviewInput]) -> list[_ResolvedInput]:
    resolved: list[_ResolvedInput] = []
    seen_ids: set[str] = set()
    seen_slugs: set[str] = set()
    for source in inputs:
        analysis_path = source.analysis_path.resolve()
        analysis = _load_mapping(analysis_path)
        structure_path = _structure_path(source, analysis)
        if not structure_path.is_file():
            raise ReviewReportError(f"Structure does not exist: {structure_path}")
        suffix = structure_path.suffix.lower()
        if suffix in {".cif", ".mmcif"}:
            structure_format: Literal["pdb", "mmcif"] = "mmcif"
        elif suffix in {".pdb", ".ent"}:
            structure_format = "pdb"
        else:
            raise ReviewReportError(f"Unsupported structure format: {structure_path}")
        structure_id = _string(
            source.structure_id
            or _nested(
                analysis,
                "identity.structure_id",
                "structure.id",
                "structure_id",
                "id",
            ),
            analysis_path.parent.name or analysis_path.stem,
        )
        slug = _safe_slug(structure_id)
        if structure_id in seen_ids or slug in seen_slugs:
            raise ReviewReportError(f"Duplicate report structure identity: {structure_id}")
        seen_ids.add(structure_id)
        seen_slugs.add(slug)
        resolved.append(
            _ResolvedInput(
                source=source,
                analysis=analysis,
                structure_path=structure_path,
                structure_id=structure_id,
                slug=slug,
                structure_format=structure_format,
            )
        )
    return resolved


def _items(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, Mapping):
        return list(value.values())
    return [value]


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _residue_rows(analysis: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw = _nested(
        analysis,
        "topology.residues",
        "residue_mapping.entries",
        "residue_mapping",
        "residues",
    )
    rows: list[dict[str, Any]] = []
    for item in _items(raw):
        if not isinstance(item, Mapping):
            continue
        label_chain = _string(
            _nested(
                item,
                "residue.label_chain_id",
                "residue.label_asym_id",
                "label_asym_id",
                "label.chain",
                "label_chain",
                "residue.chain_id",
                "chain",
            ),
            "",
        )
        label_seq = _int_or_none(
            _nested(
                item,
                "residue.label_seq_id",
                "label_seq_id",
                "label.seq_id",
                "label_residue_number",
            )
        )
        auth_chain = _string(
            _nested(
                item,
                "residue.chain_id",
                "residue.auth_asym_id",
                "auth_asym_id",
                "author.chain",
                "auth_chain",
                "chain",
            ),
            label_chain,
        )
        auth_seq = _string(
            _nested(
                item,
                "residue.auth_seq_id",
                "auth_seq_id",
                "author.seq_id",
                "auth_residue_number",
                "residue_number",
            ),
            str(label_seq) if label_seq is not None else "",
        )
        rows.append(
            {
                "label_asym_id": label_chain,
                "label_seq_id": label_seq,
                "auth_asym_id": auth_chain,
                "auth_seq_id": auth_seq,
                "insertion_code": _string(
                    _nested(
                        item,
                        "residue.insertion_code",
                        "insertion_code",
                        "author.insertion_code",
                    ),
                    "",
                ),
                "amino_acid": _string(_nested(item, "amino_acid", "residue_name", "name"), ""),
                "generic_number": _string(
                    _nested(
                        item,
                        "generic_number",
                        "gpcrdb_generic_number",
                        "display_generic_number",
                    ),
                    "",
                ),
                "segment": _string(
                    _nested(item, "segment", "protein_segment", "topology_segment"), ""
                ),
                "sequence_index": _int_or_none(_nested(item, "sequence_index", "seq_index")),
            }
        )
    return rows


def _candidate_nodes(analysis: Mapping[str, Any]) -> list[dict[str, Any]]:
    roots: list[tuple[str, Any]] = []
    candidates = analysis.get("candidates", analysis.get("candidate_sets"))
    if isinstance(candidates, Mapping):
        for mode in ("inhibit", "activate"):
            if mode in candidates:
                roots.append((mode, candidates[mode]))
    elif candidates is not None:
        roots.append(("", candidates))
    if "avoid" in analysis:
        roots.append(("", {"avoid": analysis["avoid"]}))

    nodes: list[dict[str, Any]] = []

    def walk(value: Any, mode: str, role: str, name: str) -> None:
        if isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, mode, role, f"{name}-{index + 1}")
            return
        if not isinstance(value, Mapping):
            return
        effective_mode = _string(value.get("mode"), mode)
        if effective_mode not in {"inhibit", "activate"}:
            effective_mode = mode or "both"
        effective_role = _string(
            _nested(value, "classification", "status"), role or "unresolved"
        ).lower()
        residue_value = _nested(value, "residues", "hotspots", "residue_ids", "sites")
        is_candidate = residue_value is not None or any(
            key in value
            for key in (
                "approach_direction",
                "falsifier",
                "evidence_tier",
                "geometry_metrics",
            )
        )
        if is_candidate:
            nodes.append(
                {
                    "id": _string(_nested(value, "id", "candidate_id", "name"), name),
                    "mode": effective_mode,
                    "role": effective_role,
                    "mechanism_role": _string(value.get("role"), ""),
                    "hypothesis": _string(_nested(value, "hypothesis", "label", "description"), ""),
                    "evidence_tier": _string(
                        _nested(value, "evidence_tier", "evidence.tier"), "unresolved"
                    ),
                    "approach_direction": _string(value.get("approach_direction"), "unresolved"),
                    "confidence": _string(value.get("confidence"), "unresolved"),
                    "falsifier": _string(value.get("falsifier"), ""),
                    "risks": [str(item) for item in _items(value.get("risks"))],
                    "geometry_metrics": value.get("geometry_metrics", {}),
                    "sources": [str(item) for item in _items(value.get("sources"))],
                    "residues": _items(residue_value),
                }
            )
            return
        for key, child in value.items():
            child_role = effective_role
            child_mode = effective_mode
            lowered = str(key).lower().replace("-", "_")
            if lowered in {"primary", "backup", "avoid", "unresolved", "hard_avoid", "soft_avoid"}:
                child_role = lowered
            elif lowered in {"inhibit", "activate"}:
                child_mode = lowered
            walk(child, child_mode, child_role, f"{name}-{lowered}")

    for root_mode, root in roots:
        walk(root, root_mode, "", root_mode or "candidate")
    return nodes


def _residue_identity(item: Mapping[str, Any]) -> tuple[str, int | None, str, str, str]:
    label_chain = _string(_nested(item, "label_asym_id", "label.chain", "label_chain", "chain"), "")
    label_seq = _int_or_none(_nested(item, "label_seq_id", "label.seq_id", "label_residue_number"))
    auth_chain = _string(
        _nested(item, "auth_asym_id", "author.chain", "auth_chain", "chain"), label_chain
    )
    auth_seq = _string(
        _nested(
            item,
            "auth_seq_id",
            "author.seq_id",
            "auth_residue_number",
            "residue_number",
        ),
        str(label_seq) if label_seq is not None else "",
    )
    insertion = _string(_nested(item, "insertion_code", "author.insertion_code"), "")
    return label_chain, label_seq, auth_chain, auth_seq, insertion


def _candidate_residues(
    candidates: list[dict[str, Any]],
    mapping_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_label = {
        (row["label_asym_id"], row["label_seq_id"]): row
        for row in mapping_rows
        if row["label_asym_id"] and row["label_seq_id"] is not None
    }
    by_author = {
        (row["auth_asym_id"], row["auth_seq_id"], row["insertion_code"]): row
        for row in mapping_rows
        if row["auth_asym_id"] and row["auth_seq_id"]
    }
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, int | None, str, str]] = set()
    for candidate in candidates:
        for raw in candidate["residues"]:
            if isinstance(raw, int):
                item: Mapping[str, Any] = {"auth_seq_id": str(raw)}
            elif isinstance(raw, str):
                match = re.fullmatch(
                    r"(?:(?P<chain>[^:]+):)?(?P<number>-?[0-9]+)(?P<ins>[A-Za-z]?)",
                    raw,
                )
                if not match:
                    continue
                item = {
                    "auth_asym_id": match.group("chain") or "",
                    "auth_seq_id": match.group("number"),
                    "insertion_code": match.group("ins"),
                }
            elif isinstance(raw, Mapping):
                item = raw
            else:
                continue
            label_chain, label_seq, auth_chain, auth_seq, insertion = _residue_identity(item)
            mapped = by_label.get((label_chain, label_seq))
            if mapped is None:
                mapped = by_author.get((auth_chain, auth_seq, insertion))
            if mapped is None and not auth_chain:
                matches = [
                    row
                    for (chain, seq, ins), row in by_author.items()
                    if seq == auth_seq and ins == insertion
                ]
                if len(matches) == 1:
                    mapped = matches[0]
            base = dict(mapped or {})
            base.update(
                {
                    key: value
                    for key, value in {
                        "label_asym_id": label_chain,
                        "label_seq_id": label_seq,
                        "auth_asym_id": auth_chain,
                        "auth_seq_id": auth_seq,
                        "insertion_code": insertion,
                        "amino_acid": _string(
                            _nested(item, "amino_acid", "residue_name", "name"), ""
                        ),
                        "generic_number": _string(
                            _nested(
                                item,
                                "generic_number",
                                "gpcrdb_generic_number",
                                "display_generic_number",
                            ),
                            "",
                        ),
                        "segment": _string(
                            _nested(item, "segment", "protein_segment", "topology_segment"), ""
                        ),
                    }.items()
                    if value not in (None, "")
                }
            )
            base.update(
                {
                    "candidate_id": candidate["id"],
                    "mode": candidate["mode"],
                    "role": candidate["role"],
                    "evidence_tier": candidate["evidence_tier"],
                    "approach_direction": candidate["approach_direction"],
                    "confidence": candidate["confidence"],
                }
            )
            key = (
                candidate["id"],
                candidate["mode"],
                candidate["role"],
                base.get("label_seq_id"),
                _string(base.get("auth_asym_id"), ""),
                _string(base.get("auth_seq_id"), ""),
            )
            if key not in seen:
                seen.add(key)
                rows.append(base)
    return rows


def _warnings(analysis: Mapping[str, Any]) -> list[str]:
    values: list[str] = []
    for source in (
        analysis.get("warnings"),
        _nested(analysis, "quality.warnings"),
        _nested(analysis, "validation.warnings"),
    ):
        for item in _items(source):
            if isinstance(item, Mapping):
                text = _nested(item, "message", "detail", "code")
            else:
                text = item
            if text not in (None, "") and str(text) not in values:
                values.append(str(text))
    return values


def _chain_rows(analysis: Mapping[str, Any]) -> list[dict[str, str]]:
    raw = _nested(analysis, "chain_graph.chains", "chains", "structure.chains")
    rows: list[dict[str, str]] = []
    for item in _items(raw):
        if not isinstance(item, Mapping):
            continue
        rows.append(
            {
                "label_asym_id": _string(
                    _nested(item, "label_asym_id", "label_chain", "chain_id", "id"), ""
                ),
                "role": _string(_nested(item, "role", "type", "classification"), "unknown"),
                "name": _string(_nested(item, "name", "label", "description"), ""),
            }
        )
    return rows


def _provenance_rows(analysis: Mapping[str, Any]) -> list[dict[str, str]]:
    raw = analysis.get("provenance", analysis.get("evidence", {}))
    rows: list[dict[str, str]] = []

    def append(label: str, value: Any) -> None:
        if value in (None, "") or isinstance(value, (Mapping, list, tuple)):
            return
        text = str(_portable_value(value))
        rows.append(
            {
                "label": label.replace("_", " "),
                "value": text,
                "url": text if URL_PATTERN.match(text) else "",
            }
        )

    def walk(label: str, value: Any, depth: int) -> None:
        if len(rows) >= 100:
            return
        if isinstance(value, Mapping) and depth < 4:
            for key, child in value.items():
                walk(f"{label}.{key}" if label else str(key), child, depth + 1)
            return
        if isinstance(value, (list, tuple)) and depth < 4:
            for index, child in enumerate(value, start=1):
                walk(f"{label}[{index}]", child, depth + 1)
            return
        append(label or "source", value)

    walk("", raw, 0)
    return rows


def _identity(analysis: Mapping[str, Any], resolved: _ResolvedInput) -> dict[str, str]:
    return {
        "structure_id": resolved.structure_id,
        "entry": _string(
            _nested(
                analysis,
                "identity.entry_name",
                "identity.gpcr_entry",
                "identity.entry",
                "gpcr_entry",
            )
        ),
        "accession": _string(_nested(analysis, "identity.accession", "accession")),
        "receptor_chain": _string(
            resolved.source.receptor_chain
            or _nested(
                analysis,
                "identity.receptor_chain",
                "structure.receptor_chain",
                "receptor_chain",
            )
        ),
        "family": _string(
            _nested(
                analysis,
                "identity.family",
                "family.name",
                "family",
                "gpcr_family",
                "identity.receptor_class",
            )
        ),
        "class": _string(
            _nested(
                analysis,
                "identity.receptor_class",
                "identity.class",
                "family.class",
                "gpcr_class",
            )
        ),
        "state": _string(
            _nested(
                analysis,
                "state.assignment",
                "state.label",
                "state.state",
                "state",
                "identity.state",
            )
        ),
    }


def _count_candidates(candidates: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    result = {
        "inhibit": {"primary": 0, "backup": 0, "avoid": 0, "unresolved": 0},
        "activate": {"primary": 0, "backup": 0, "avoid": 0, "unresolved": 0},
    }
    for candidate in candidates:
        modes = ("inhibit", "activate") if candidate["mode"] == "both" else (candidate["mode"],)
        role = candidate["role"]
        if "avoid" in role:
            role = "avoid"
        if role not in {"primary", "backup", "avoid", "unresolved"}:
            role = "unresolved"
        for candidate_mode in modes:
            if candidate_mode in result:
                result[candidate_mode][role] += 1
    return result


def _portable_value(value: Any) -> Any:
    """Remove machine-local absolute paths from browser-facing provenance."""

    if isinstance(value, Mapping):
        return {str(key): _portable_value(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_portable_value(child) for child in value]
    if isinstance(value, tuple):
        return [_portable_value(child) for child in value]
    if isinstance(value, str):
        path = Path(value)
        if path.is_absolute() or WINDOWS_ABSOLUTE_PATTERN.match(value):
            return path.name
    return value


def _gpcrdb_cache_paths(analysis: Mapping[str, Any]) -> list[Path]:
    provenance = analysis.get("provenance")
    records: Any = None
    if isinstance(provenance, Mapping):
        records = provenance.get("gpcrdb")
    if not isinstance(records, Sequence) or isinstance(records, (str, bytes, bytearray)):
        return []
    values: list[Path] = []
    seen: set[Path] = set()
    for record in records:
        if not isinstance(record, Mapping) or not record.get("cache_path"):
            continue
        path = Path(str(record["cache_path"])).expanduser().resolve()
        if not path.is_file():
            raise ReviewReportError(f"Declared GPCRdb cache record is missing: {path}")
        if path.suffix.lower() != ".json":
            raise ReviewReportError(f"GPCRdb cache record must be JSON: {path}")
        if path not in seen:
            seen.add(path)
            values.append(path)
    return sorted(values, key=lambda path: (path.name, str(path)))


def _viewer_data(resolved: _ResolvedInput, mode: Mode, structure_relative: str) -> dict[str, Any]:
    mapping_rows = _residue_rows(resolved.analysis)
    candidates = _candidate_nodes(resolved.analysis)
    candidate_residues = _candidate_residues(candidates, mapping_rows)
    identity = _identity(resolved.analysis, resolved)
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "read_only": True,
        "mode": mode,
        "identity": identity,
        "structure": {
            "format": resolved.structure_format,
            "relative_path": structure_relative,
            "sha256": _sha256(resolved.structure_path),
            "text": resolved.structure_path.read_text(encoding="utf-8", errors="replace"),
        },
        "residues": _portable_value(mapping_rows),
        "candidates": _portable_value(candidates),
        "candidate_residues": _portable_value(candidate_residues),
        "candidate_counts": _count_candidates(candidates),
        "chains": _portable_value(_chain_rows(resolved.analysis)),
        "warnings": _warnings(resolved.analysis),
        "provenance": _portable_value(_provenance_rows(resolved.analysis)),
        "membrane_status": _string(
            _nested(
                resolved.analysis,
                "membrane.orientation_status",
                "membrane.status",
                "membrane_orientation.status",
            )
        ),
    }


def _resource_bytes(resource: Traversable) -> bytes:
    try:
        return resource.read_bytes()
    except OSError as error:
        raise ReviewReportError(f"Missing packaged review resource: {resource}") from error


def _copy_resource(resource: Traversable, destination: Path) -> None:
    _write_exclusive(destination, _resource_bytes(resource))


def _copy_assets(staging: Path) -> None:
    for filename, expected in MOLSTAR_FILES.items():
        source = MOLSTAR_RESOURCE_ROOT.joinpath(filename)
        content = _resource_bytes(source)
        if hashlib.sha256(content).hexdigest() != expected:
            raise ReviewReportError(
                f"Mol* {MOLSTAR_VERSION} asset has unexpected SHA-256: {source}"
            )
        destination_name = "MOLSTAR_LICENSE.txt" if filename == "LICENSE" else filename
        _write_exclusive(staging / "assets" / destination_name, content)
    for filename, destination in STATIC_FILES.items():
        _copy_resource(REPORT_RESOURCE_ROOT.joinpath(filename), staging / destination)


def _template(name: str) -> str:
    resource = REPORT_RESOURCE_ROOT.joinpath(name)
    try:
        return resource.read_text(encoding="utf-8")
    except OSError as error:
        raise ReviewReportError(f"Missing packaged review template: {resource}") from error


def _replace(template: str, values: Mapping[str, str]) -> str:
    result = template
    for key, value in values.items():
        result = result.replace("{{" + key + "}}", value)
    leftovers = re.findall(r"\{\{[A-Z0-9_]+\}\}", result)
    if leftovers:
        raise ReviewReportError(f"Unresolved report template placeholders: {leftovers}")
    return result


def _index_row(entry: Mapping[str, Any]) -> str:
    identity = entry["identity"]
    counts = entry["candidate_counts"]
    warning_count = len(entry["warnings"])
    return (
        '<tr class="report-row" '
        f'data-family="{html.escape(identity["family"], quote=True)}" '
        f'data-state="{html.escape(identity["state"], quote=True)}" '
        f'data-search="{html.escape(" ".join(identity.values()).lower(), quote=True)}">'
        f'<td><a href="{html.escape(entry["page"], quote=True)}">'
        f"{html.escape(identity['structure_id'])}</a>"
        f'<span class="subline">{html.escape(identity["entry"])}</span></td>'
        f"<td>{html.escape(identity['state'])}</td>"
        f"<td>{html.escape(identity['family'])}</td>"
        f"<td>{counts['inhibit']['primary']} / {counts['inhibit']['backup']}</td>"
        f"<td>{counts['activate']['primary']} / {counts['activate']['backup']}</td>"
        f'<td><span class="warning-count">{warning_count}</span></td>'
        '<td><a class="review-link" '
        f'href="{html.escape(entry["page"], quote=True)}">Review</a></td>'
        "</tr>"
    )


def _options(values: Iterable[str]) -> str:
    unique = sorted({value for value in values if value})
    return "".join(
        f'<option value="{html.escape(value, quote=True)}">{html.escape(value)}</option>'
        for value in unique
    )


def _render_index(entries: list[dict[str, Any]], mode: Mode, revision: int) -> str:
    empty = (
        '<tr id="empty-row"><td colspan="7">'
        "No structures were supplied for this revision.</td></tr>"
        if not entries
        else ""
    )
    return _replace(
        _template("index.html"),
        {
            "REVISION": f"{revision:04d}",
            "MODE": html.escape(mode),
            "STRUCTURE_COUNT": str(len(entries)),
            "FAMILY_OPTIONS": _options(entry["identity"]["family"] for entry in entries),
            "STATE_OPTIONS": _options(entry["identity"]["state"] for entry in entries),
            "TABLE_ROWS": "".join(_index_row(entry) for entry in entries) + empty,
        },
    )


def _render_structure(viewer: Mapping[str, Any]) -> str:
    identity = viewer["identity"]
    return _replace(
        _template("structure.html"),
        {
            "STRUCTURE_ID": html.escape(identity["structure_id"]),
            "ENTRY": html.escape(identity["entry"]),
            "STATE": html.escape(identity["state"]),
            "FAMILY": html.escape(identity["family"]),
            "CLASS": html.escape(identity["class"]),
            "CHAIN": html.escape(identity["receptor_chain"]),
            "DATA_JS": html.escape(
                f"../data/{_safe_slug(identity['structure_id'])}/review-data.js",
                quote=True,
            ),
            "STRUCTURE_DOWNLOAD": html.escape(viewer["structure"]["relative_path"], quote=True),
        },
    )


def _role_for(path: str) -> str:
    if path == "index.html" or path.startswith("structures/"):
        return "html"
    if path.endswith(".js"):
        return "javascript"
    if path.endswith(".css"):
        return "css"
    if path.endswith(".json"):
        return "json"
    if path.endswith((".pdb", ".ent", ".cif", ".mmcif")):
        return "structure"
    if path.endswith(".txt"):
        return "license"
    return "data"


def _file_allowlist(report_root: Path) -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    for path in sorted(item for item in report_root.rglob("*") if item.is_file()):
        relative = path.relative_to(report_root).as_posix()
        if relative == "review-manifest.json":
            continue
        files.append(
            {
                "path": relative,
                "sha256": _sha256(path),
                "size_bytes": path.stat().st_size,
                "role": _role_for(relative),
            }
        )
    return files


def _next_revision(base: Path) -> int:
    pointer = base / "LATEST"
    reports = sorted(base.glob("report-[0-9][0-9][0-9][0-9]*")) if base.exists() else []
    if not pointer.exists():
        if reports:
            raise ReviewReportError("Report revisions exist but LATEST is missing")
        return 1
    report_root = resolve_latest_review_report(base)
    manifest = _load_mapping(report_root / "review-manifest.json")
    revision = manifest.get("revision")
    if not isinstance(revision, int) or revision < 1:
        raise ReviewReportError("Latest review manifest has an invalid revision")
    return revision + 1


def _publish(staging: Path, final_root: Path, base: Path) -> None:
    if final_root.exists():
        raise ReviewReportError(f"Refusing to overwrite report revision: {final_root}")
    staging.rename(final_root)
    pointer_content = f"{final_root.name}/review-manifest.json\n"
    pointer_temp = base / f".LATEST.{os.getpid()}.tmp"
    try:
        pointer_temp.write_text(pointer_content, encoding="ascii", newline="\n")
        os.replace(pointer_temp, base / "LATEST")
    finally:
        if pointer_temp.exists():
            pointer_temp.unlink()


def generate_review_report(
    input_source: Path | str | Sequence[Path | str | ReviewInput],
    output_dir: Path | str,
    *,
    mode: Mode = "both",
    repository_root: Path | str | None = None,
    generated_at: datetime | None = None,
) -> ReviewReportOutcome:
    """Publish a portable, read-only report without overwriting older revisions.

    ``repository_root`` is retained as a compatibility-only argument.  Assets
    always come from the installed package to keep report identity independent
    of a mutable source checkout.
    """

    if mode not in {"both", "inhibit", "activate"}:
        raise ReviewReportError(f"Unsupported review mode: {mode}")
    base = Path(output_dir).resolve()
    base.mkdir(parents=True, exist_ok=True)
    revision = _next_revision(base)
    final_root = base / f"report-{revision:04d}"
    if final_root.exists():
        raise ReviewReportError(f"Refusing to overwrite report revision: {final_root}")
    resolved_inputs = _resolve_inputs(resolve_review_inputs(input_source))
    staging = Path(tempfile.mkdtemp(prefix=f".report-{revision:04d}.creating-", dir=base))
    try:
        _ = repository_root
        _copy_assets(staging)
        entries: list[dict[str, Any]] = []
        for resolved in resolved_inputs:
            data_dir = staging / "data" / resolved.slug
            structure_name = f"structure.{resolved.structure_path.suffix.lower().lstrip('.')}"
            structure_destination = data_dir / structure_name
            analysis_destination = data_dir / "gpcr-hotspot-analysis.json"
            _copy_exclusive(resolved.structure_path, structure_destination)
            _json_dump(_portable_value(resolved.analysis), analysis_destination)
            cache_entries: list[dict[str, Any]] = []
            for cache_index, cache_source in enumerate(
                _gpcrdb_cache_paths(resolved.analysis), start=1
            ):
                cache_name = f"{cache_index:03d}-{cache_source.name}"
                cache_destination = data_dir / "gpcrdb-cache" / cache_name
                _copy_exclusive(cache_source, cache_destination)
                cache_entries.append(
                    {
                        "path": f"data/{resolved.slug}/gpcrdb-cache/{cache_name}",
                        "sha256": _sha256(cache_destination),
                    }
                )
            structure_relative_from_page = f"../data/{resolved.slug}/{structure_name}"
            viewer = _viewer_data(resolved, mode, structure_relative_from_page)
            review_data = (
                "window.__GPCR_REVIEW_DATA__ = "
                + json.dumps(viewer, ensure_ascii=True, separators=(",", ":"))
                + ";\n"
            )
            _write_exclusive(data_dir / "review-data.js", review_data)
            _write_exclusive(
                staging / "structures" / f"{resolved.slug}.html",
                _render_structure(viewer),
            )
            entries.append(
                {
                    "structure_id": resolved.structure_id,
                    "slug": resolved.slug,
                    "identity": viewer["identity"],
                    "page": f"structures/{resolved.slug}.html",
                    "analysis_path": f"data/{resolved.slug}/gpcr-hotspot-analysis.json",
                    "analysis_sha256": _sha256(analysis_destination),
                    "source_analysis_sha256": _sha256(resolved.source.analysis_path.resolve()),
                    "structure_path": f"data/{resolved.slug}/{structure_name}",
                    "structure_sha256": _sha256(structure_destination),
                    "gpcrdb_cache": cache_entries,
                    "candidate_counts": viewer["candidate_counts"],
                    "warnings": viewer["warnings"],
                }
            )
        _write_exclusive(staging / "index.html", _render_index(entries, mode, revision))
        created = generated_at or datetime.now(UTC)
        if created.tzinfo is None:
            raise ReviewReportError("generated_at must be timezone-aware")
        manifest = {
            "schema_version": REPORT_SCHEMA_VERSION,
            "report_id": "gpcr-hotspot-review",
            "revision": revision,
            "created_at": created.astimezone(UTC).isoformat().replace("+00:00", "Z"),
            "generator_version": GENERATOR_VERSION,
            "mode": mode,
            "viewer": {
                "name": "Mol*",
                "version": MOLSTAR_VERSION,
                "asset_sha256": {
                    "assets/molstar.js": MOLSTAR_FILES["molstar.js"],
                    "assets/molstar.css": MOLSTAR_FILES["molstar.css"],
                    "assets/MOLSTAR_LICENSE.txt": MOLSTAR_FILES["LICENSE"],
                },
            },
            "structure_count": len(entries),
            "entries": entries,
            "files": _file_allowlist(staging),
        }
        _json_dump(manifest, staging / "review-manifest.json")
        validate_review_report(staging)
        _publish(staging, final_root, base)
        return ReviewReportOutcome(
            report_root=final_root,
            manifest_path=final_root / "review-manifest.json",
            index_path=final_root / "index.html",
            revision=revision,
            structure_count=len(entries),
        )
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise


def _safe_manifest_path(root: Path, relative: str) -> Path:
    candidate = Path(relative)
    if candidate.is_absolute() or WINDOWS_ABSOLUTE_PATTERN.match(relative):
        raise ReviewReportError(f"Manifest contains an absolute path: {relative}")
    if "\\" in relative or not relative or relative.startswith("./"):
        raise ReviewReportError(f"Manifest path must use normalized POSIX syntax: {relative}")
    resolved = (root / candidate).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise ReviewReportError(f"Manifest path escapes report root: {relative}") from error
    return resolved


def validate_review_report(report_or_base_dir: Path | str) -> dict[str, Any]:
    """Validate one report revision or a base directory containing ``LATEST``."""

    supplied = Path(report_or_base_dir).resolve()
    root = supplied
    if not (root / "review-manifest.json").is_file():
        pointer = root / "LATEST"
        if not pointer.is_file():
            raise ReviewReportError(f"No review-manifest.json or LATEST under {root}")
        try:
            relative = pointer.read_text(encoding="ascii").strip()
        except OSError as error:
            raise ReviewReportError(f"Cannot read LATEST: {pointer}") from error
        if LATEST_PATTERN.fullmatch(relative) is None:
            raise ReviewReportError(f"Invalid LATEST pointer: {relative!r}")
        root = _safe_manifest_path(root, relative).parent

    manifest = _load_mapping(root / "review-manifest.json")
    if manifest.get("schema_version") != REPORT_SCHEMA_VERSION:
        raise ReviewReportError("Unsupported review manifest schema_version")
    if manifest.get("report_id") != "gpcr-hotspot-review":
        raise ReviewReportError("Unexpected review manifest report_id")
    if manifest.get("viewer", {}).get("version") != MOLSTAR_VERSION:
        raise ReviewReportError("Review manifest does not identify Mol* 5.11.0")
    revision_match = re.fullmatch(r"report-(?P<revision>[0-9]{4,})", root.name)
    revision = manifest.get("revision")
    if revision_match and revision != int(revision_match.group("revision")):
        raise ReviewReportError("Report directory and manifest revision differ")
    entries = manifest.get("entries")
    if not isinstance(entries, list) or manifest.get("structure_count") != len(entries):
        raise ReviewReportError("Review manifest structure_count is inconsistent")
    files = manifest.get("files")
    if not isinstance(files, list):
        raise ReviewReportError("Review manifest files must be an allowlist")
    declared: set[str] = set()
    for item in files:
        if not isinstance(item, Mapping):
            raise ReviewReportError("Review manifest file entry must be a mapping")
        file_relative = item.get("path")
        digest = item.get("sha256")
        size = item.get("size_bytes")
        if not isinstance(file_relative, str) or file_relative in declared:
            raise ReviewReportError(f"Duplicate or invalid manifest path: {file_relative!r}")
        if not isinstance(digest, str) or SHA256_PATTERN.fullmatch(digest) is None:
            raise ReviewReportError(f"Invalid SHA-256 for {file_relative}")
        if not isinstance(size, int) or size < 0:
            raise ReviewReportError(f"Invalid byte size for {file_relative}")
        path = _safe_manifest_path(root, file_relative)
        if not path.is_file() or path.is_symlink():
            raise ReviewReportError(
                f"Declared report file is missing or a symlink: {file_relative}"
            )
        if path.stat().st_size != size or _sha256(path) != digest:
            raise ReviewReportError(f"Report file integrity check failed: {file_relative}")
        declared.add(file_relative)
    actual = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path.name != "review-manifest.json"
    }
    if actual != declared:
        missing = sorted(declared - actual)
        unlisted = sorted(actual - declared)
        raise ReviewReportError(
            f"Report allowlist mismatch; missing={missing}, unlisted={unlisted}"
        )
    expected_assets = manifest["viewer"].get("asset_sha256", {})
    for relative, expected in expected_assets.items():
        if expected != _sha256(_safe_manifest_path(root, relative)):
            raise ReviewReportError(f"Mol* asset hash mismatch: {relative}")
    for page in [root / "index.html", *sorted((root / "structures").glob("*.html"))]:
        content = page.read_text(encoding="utf-8")
        if re.search(r"(?:src|href)=[\"'](?:https?:)?//", content, re.IGNORECASE):
            raise ReviewReportError(f"External page dependency is forbidden: {page.name}")
        if re.search(r"(?:src|href)=[\"'](?:file:|[A-Za-z]:[\\/]|/)", content):
            raise ReviewReportError(f"Absolute page dependency is forbidden: {page.name}")
    return manifest


def resolve_latest_review_report(output_dir: Path | str) -> Path:
    """Resolve ``LATEST`` and verify that the pointed revision is complete."""

    base = Path(output_dir).resolve()
    pointer = base / "LATEST"
    if not pointer.is_file():
        raise ReviewReportError(f"Review report LATEST is missing: {pointer}")
    relative = pointer.read_text(encoding="ascii").strip()
    if LATEST_PATTERN.fullmatch(relative) is None:
        raise ReviewReportError(f"Invalid LATEST pointer: {relative!r}")
    manifest_path = _safe_manifest_path(base, relative)
    report_root = manifest_path.parent
    validate_review_report(report_root)
    return report_root


def create_gpcr_review_server(
    report_or_base_dir: Path | str,
    *,
    port: int = 8000,
) -> GpcrReviewServer:
    """Serve one verified immutable report on loopback only."""

    supplied = Path(report_or_base_dir).expanduser().resolve(strict=True)
    if (supplied / "review-manifest.json").is_file():
        report_root = supplied
        validate_review_report(report_root)
    else:
        report_root = resolve_latest_review_report(supplied)
    handler = partial(_ReviewHandler, directory=str(report_root))
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    return GpcrReviewServer(server=server, report_root=report_root)


def export_gpcr_review_report(
    report_or_base_dir: Path | str,
    output_dir: Path | str,
) -> Path:
    """Copy one verified portable revision without overwriting a destination."""

    supplied = Path(report_or_base_dir).expanduser().resolve(strict=True)
    source = (
        supplied
        if (supplied / "review-manifest.json").is_file()
        else resolve_latest_review_report(supplied)
    )
    validate_review_report(source)
    destination = Path(output_dir).expanduser().resolve()
    if destination.exists():
        raise ReviewReportError(f"Refusing to overwrite report export: {destination}")
    shutil.copytree(source, destination, copy_function=shutil.copy2)
    validate_review_report(destination)
    return destination


__all__ = [
    "GpcrReviewServer",
    "ReviewInput",
    "ReviewReportError",
    "ReviewReportOutcome",
    "create_gpcr_review_server",
    "export_gpcr_review_report",
    "generate_review_report",
    "resolve_latest_review_report",
    "resolve_review_inputs",
    "validate_review_report",
]
