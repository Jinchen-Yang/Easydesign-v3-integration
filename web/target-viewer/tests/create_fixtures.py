#!/usr/bin/env python3
"""为 Playwright 创建两个不依赖真实 run 的自包含 Viewer report。"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import UTC, datetime
from importlib.resources import files
from pathlib import Path

from easydesign.core import ArtifactRef, ExecutionStatus, dump_model, sha256_file
from easydesign.reporting import (
    TargetViewerData,
    TargetViewerReportManifest,
    ViewerAnnotationSummary,
    ViewerColorCount,
    ViewerDownload,
    ViewerMetric,
    ViewerResidue,
)

STATIC = files("easydesign.reporting").joinpath("static", "target_viewer")
STATIC_FILES = {
    "index.html": "index.html",
    "assets/molstar.js": "vendor/molstar/molstar.js",
    "assets/molstar.css": "vendor/molstar/molstar.css",
    "assets/MOLSTAR_LICENSE.txt": "vendor/molstar/LICENSE",
    "assets/easydesign-viewer.js": "easydesign-viewer.js",
    "assets/easydesign-viewer.css": "easydesign-viewer.css",
}
SEQUENCE = "ACDEFGHIKLMNPQRSTVWY"
THREE_LETTER = {
    "A": "ALA",
    "C": "CYS",
    "D": "ASP",
    "E": "GLU",
    "F": "PHE",
    "G": "GLY",
    "H": "HIS",
    "I": "ILE",
    "K": "LYS",
    "L": "LEU",
    "M": "MET",
    "N": "ASN",
    "P": "PRO",
    "Q": "GLN",
    "R": "ARG",
    "S": "SER",
    "T": "THR",
    "V": "VAL",
    "W": "TRP",
    "Y": "TYR",
}
FORMATS = {
    ".html": "html",
    ".json": "json",
    ".cif": "mmcif",
    ".fasta": "fasta",
    ".js": "javascript",
    ".css": "css",
    ".txt": "text",
}


def _write_structure(path: Path, *, label_chain: str, author_start: int) -> None:
    headers = [
        "data_target",
        "loop_",
        "_atom_site.group_PDB",
        "_atom_site.id",
        "_atom_site.type_symbol",
        "_atom_site.label_atom_id",
        "_atom_site.label_alt_id",
        "_atom_site.label_comp_id",
        "_atom_site.label_asym_id",
        "_atom_site.label_entity_id",
        "_atom_site.label_seq_id",
        "_atom_site.pdbx_PDB_ins_code",
        "_atom_site.Cartn_x",
        "_atom_site.Cartn_y",
        "_atom_site.Cartn_z",
        "_atom_site.occupancy",
        "_atom_site.B_iso_or_equiv",
        "_atom_site.auth_seq_id",
        "_atom_site.auth_comp_id",
        "_atom_site.auth_asym_id",
        "_atom_site.auth_atom_id",
        "_atom_site.pdbx_PDB_model_num",
    ]
    lines = list(headers)
    serial = 1
    for residue_index, amino_acid in enumerate(SEQUENCE, start=1):
        author_id = author_start + residue_index - 1
        x = residue_index * 3.7
        for atom_name, element, dx, dy in (
            ("N", "N", 0.0, 0.0),
            ("CA", "C", 1.2, 0.6),
            ("C", "C", 2.4, 0.0),
            ("O", "O", 3.1, -0.7),
        ):
            comp = THREE_LETTER[amino_acid]
            lines.append(
                f"ATOM {serial} {element} {atom_name} . {comp} {label_chain} 1 "
                f"{residue_index} ? {x + dx:.3f} {dy:.3f} 0.000 1.00 70.00 "
                f"{author_id} {comp} A {atom_name} 1"
            )
            serial += 1
    lines.append("#")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _artifact(root: Path, relative_path: str, artifact_id: str) -> ArtifactRef:
    return ArtifactRef.from_file(
        run_root=root,
        relative_path=relative_path,
        artifact_id=artifact_id,
        role="target-viewer-report",
        file_format=FORMATS[Path(relative_path).suffix.lower()],
    )


def _create_report(root: Path, *, pse: bool) -> None:
    root.mkdir(parents=True)
    for destination, source in STATIC_FILES.items():
        target = root / destination
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(STATIC.joinpath(*source.split("/")).read_bytes())
    label_chain = "Axp" if pse else "A"
    author_start = 23 if pse else 1
    structure = root / "data/target.cif"
    structure.parent.mkdir(parents=True)
    _write_structure(structure, label_chain=label_chain, author_start=author_start)
    fasta = root / "data/sequence.fasta"
    fasta.write_text(f">browser-fixture\n{SEQUENCE}\n", encoding="utf-8")
    mapping = root / "data/residue-mapping.json"
    mapping.write_text(
        '{"schema_version":"0.1","target_id":"browser-fixture",'
        f'"sequence_sha256":"{hashlib.sha256(SEQUENCE.encode()).hexdigest()}",'
        '"entries":[]}\n',
        encoding="utf-8",
    )
    palette = ("#00FF00", "#FF0000", "#0000FF", "#FFFF00")
    colors = [palette[min(index // 5, 3)] for index in range(len(SEQUENCE))]
    residues = tuple(
        ViewerResidue(
            sequence_index=index,
            amino_acid=amino_acid,
            label_asym_id=label_chain,
            label_seq_id=index,
            auth_asym_id="A",
            auth_seq_id=str(author_start + index - 1),
            pse_color_hex=colors[index - 1] if pse else None,
        )
        for index, amino_acid in enumerate(SEQUENCE, start=1)
    )
    annotation = (
        ViewerAnnotationSummary(
            status="available",
            annotation_type="pymol-ca-color",
            interpretation="uninterpreted",
            color_counts=tuple(
                ViewerColorCount(color_hex=color, residue_count=5)
                for color in palette
            ),
        )
        if pse
        else ViewerAnnotationSummary(status="not_applicable")
    )
    downloads = (
        ViewerDownload(
            label="下载 target.cif",
            relative_path="data/target.cif",
            sha256=sha256_file(structure),
        ),
        ViewerDownload(
            label="下载 sequence.fasta",
            relative_path="data/sequence.fasta",
            sha256=sha256_file(fasta),
        ),
        ViewerDownload(
            label="下载 residue-mapping.json",
            relative_path="data/residue-mapping.json",
            sha256=sha256_file(mapping),
        ),
    )
    dump_model(
        TargetViewerData(
            target_id="browser-pse" if pse else "browser-protenix",
            origin="imported" if pse else "predicted",
            sequence_length=len(SEQUENCE),
            sequence_sha256=hashlib.sha256(SEQUENCE.encode()).hexdigest(),
            structure_sha256=sha256_file(structure),
            coordinate_model_count=1,
            coordinate_model_ids=("1",),
            representative_model_id="1",
            quality_metrics=(
                ViewerMetric(key="plddt", label="整体 pLDDT", value=84.0),
            ),
            provenance_metrics=(
                ViewerMetric(
                    key="backend",
                    label="结构后端",
                    value="pymol-pse" if pse else "protenix",
                ),
                ViewerMetric(
                    key="msa-depth",
                    label="MSA depth",
                    value="not_applicable" if pse else 609,
                ),
            ),
            annotation=annotation,
            residues=residues,
            downloads=downloads,
        ),
        root / "viewer-data.json",
    )
    output_specs = (
        ("index.html", "viewer-html"),
        ("viewer-data.json", "viewer-data"),
        ("data/target.cif", "viewer-target-structure"),
        ("data/sequence.fasta", "viewer-target-sequence"),
        ("data/residue-mapping.json", "viewer-residue-mapping"),
        ("assets/molstar.js", "molstar-js"),
        ("assets/molstar.css", "molstar-css"),
        ("assets/easydesign-viewer.js", "easydesign-viewer-js"),
        ("assets/easydesign-viewer.css", "easydesign-viewer-css"),
        ("assets/MOLSTAR_LICENSE.txt", "molstar-license"),
    )
    now = datetime.now(UTC)
    dump_model(
        TargetViewerReportManifest(
            revision=1,
            status=ExecutionStatus.SUCCEEDED,
            created_at=now,
            completed_at=now,
            source_run_manifest_sha256="1" * 64,
            source_stage_manifest_sha256="2" * 64,
            source_target_bundle_sha256="3" * 64,
            source_target_structure_sha256=sha256_file(structure),
            output_artifacts=tuple(
                _artifact(root, relative_path, artifact_id)
                for relative_path, artifact_id in output_specs
            ),
        ),
        root / "report-manifest.json",
    )
    if not pse:
        (root / "stage02-test-overlay.json").write_text(
            json.dumps(
                {
                    "schema_version": "0.1",
                    "layers": [
                        {
                            "id": layer_id,
                            "label": label,
                            "approved": layer_id == "approved",
                            "regions": [
                                {
                                    "id": region_id,
                                    "color_hex": color,
                                    "source_region_id": f"{layer_id}-{region_id}",
                                    "residues": [
                                        {
                                            "label_asym_id": label_chain,
                                            "label_seq_id": offset,
                                        }
                                    ],
                                }
                                for region_id, color, offset in (
                                    ("A", "#EF4444", 2),
                                    ("B", "#3B82F6", 8),
                                    ("C", "#FACC15", 14),
                                )
                            ],
                        }
                        for layer_id, label in (
                            ("sasa", "SASA surface diversity"),
                            ("scannet", "ScanNet epitope no-MSA"),
                            ("approved", "Approved hotspots"),
                        )
                    ],
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    arguments = parser.parse_args()
    output = arguments.output.resolve()
    if output.exists():
        shutil.rmtree(output)
    _create_report(output / "sequence", pse=False)
    _create_report(output / "pse", pse=True)
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
