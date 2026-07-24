"""在独立 PyMOL 环境中执行的 PSE 提取 worker。

本文件刻意只依赖 Python 标准库和运行时导入的 PyMOL。它作为脚本执行，不导入
EasyDesign，也不要求在 ``pymol-pse`` 环境中安装 EasyDesign。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

THREE_TO_ONE = {
    "ALA": "A",
    "ARG": "R",
    "ASN": "N",
    "ASP": "D",
    "CYS": "C",
    "GLN": "Q",
    "GLU": "E",
    "GLY": "G",
    "HIS": "H",
    "ILE": "I",
    "LEU": "L",
    "LYS": "K",
    "MET": "M",
    "PHE": "F",
    "PRO": "P",
    "SER": "S",
    "THR": "T",
    "TRP": "W",
    "TYR": "Y",
    "VAL": "V",
}
WATER_RESIDUES = {"HOH", "WAT", "H2O"}
RESIDUE_ID_PATTERN = re.compile(r"^(-?[0-9]+)([A-Za-z]?)$")


class WorkerFailure(Exception):
    """稳定、可序列化的 worker 失败。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _exclusive_json(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(
            payload,
            handle,
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
            sort_keys=True,
        )
        handle.write("\n")


def _safe_source(run_root: Path, relative_path: str) -> Path:
    if "\\" in relative_path or relative_path.startswith("/"):
        raise WorkerFailure("invalid-source-path", "PSE source 必须是 POSIX run 相对路径")
    parts = relative_path.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise WorkerFailure("invalid-source-path", "PSE source 路径包含不安全片段")
    root = run_root.resolve()
    source = (root / relative_path).resolve()
    try:
        source.relative_to(root)
    except ValueError as error:
        raise WorkerFailure("invalid-source-path", "PSE source 逃出 run 根目录") from error
    if not source.is_file():
        raise WorkerFailure("source-not-found", f"PSE source 不存在: {source}")
    return source


def _selection(object_name: str, suffix: str = "") -> str:
    escaped = object_name.replace("\\", "\\\\").replace('"', '\\"')
    base = f'model "{escaped}"'
    return f"({base}) and ({suffix})" if suffix else base


def _parse_author_residue_id(resi: str) -> tuple[str, str | None]:
    match = RESIDUE_ID_PATTERN.fullmatch(resi)
    if match is None:
        raise WorkerFailure(
            "ambiguous-residue-numbering",
            f"无法无歧义解析 author residue id: {resi!r}",
        )
    return match.group(1), match.group(2) or None


def _rgb(cmd: Any, color_index: int) -> tuple[float, float, float]:
    value = cmd.get_color_tuple(color_index)
    if value is None or len(value) != 3:
        raise WorkerFailure("invalid-color", f"无法解析 PyMOL color index: {color_index}")
    return (
        round(float(value[0]), 6),
        round(float(value[1]), 6),
        round(float(value[2]), 6),
    )


def _hex_color(rgb: tuple[float, float, float]) -> str:
    channels = [max(0, min(255, round(value * 255))) for value in rgb]
    return "#" + "".join(f"{channel:02X}" for channel in channels)


def _inventory(cmd: Any) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for name in sorted(cmd.get_names("all")):
        object_type = str(cmd.get_type(name))
        state_count = int(cmd.count_states(name)) if object_type == "object:molecule" else 0
        atom_count = int(cmd.count_atoms(name)) if object_type == "object:molecule" else 0
        protein_atom_count = (
            int(cmd.count_atoms(_selection(name, "polymer.protein")))
            if object_type == "object:molecule"
            else 0
        )
        entries.append(
            {
                "name": name,
                "object_type": object_type,
                "state_count": state_count,
                "atom_count": atom_count,
                "protein_atom_count": protein_atom_count,
                "ignored": object_type != "object:molecule",
            }
        )
    return entries


def _extract(
    *,
    request: dict[str, Any],
    run_root: Path,
    output_pdb: Path,
) -> dict[str, Any]:
    try:
        import pymol  # type: ignore[import-not-found]
    except Exception as error:
        raise WorkerFailure("pymol-import-failed", f"PyMOL 导入失败: {error}") from error

    pymol.finish_launching(["pymol", "-cq"])
    cmd = pymol.cmd
    version = str(cmd.get_version()[0])
    if version != "3.1.0":
        raise WorkerFailure(
            "pymol-version-mismatch",
            f"PyMOL 版本不匹配: expected=3.1.0, actual={version}",
        )

    source = _safe_source(run_root, str(request["source_relative_path"]))
    actual_sha256 = _sha256_file(source)
    expected_sha256 = str(request["source_sha256"]).lower()
    if actual_sha256 != expected_sha256:
        raise WorkerFailure(
            "source-checksum-mismatch",
            f"PSE SHA-256 不一致: expected={expected_sha256}, actual={actual_sha256}",
        )

    try:
        cmd.reinitialize()
        cmd.load(str(source))
    except Exception as error:
        raise WorkerFailure("pse-load-failed", f"PyMOL 无法读取 PSE: {error}") from error

    inventory = _inventory(cmd)
    protein_objects = [
        entry["name"] for entry in inventory if entry["protein_atom_count"] > 0
    ]
    if len(protein_objects) != 1:
        raise WorkerFailure(
            "protein-object-count",
            f"PSE 必须恰好包含一个 protein molecule object，发现 {len(protein_objects)} 个",
        )
    selected_object = str(protein_objects[0])
    state_count = int(cmd.count_states(selected_object))
    if state_count != 1:
        raise WorkerFailure(
            "coordinate-state-count",
            f"protein object 必须恰好一个 coordinate state，发现 {state_count} 个",
        )

    protein_selection = _selection(selected_object, "polymer.protein")
    protein_model = cmd.get_model(protein_selection, state=1)
    chains = sorted({str(atom.chain) for atom in protein_model.atom})
    if len(chains) != 1 or not chains[0]:
        raise WorkerFailure(
            "protein-chain-count",
            f"protein object 必须恰好一条非空 chain，发现 {chains!r}",
        )
    chain_id = chains[0]
    noncanonical_protein_residues = sorted(
        {str(atom.resn).upper() for atom in protein_model.atom} - set(THREE_TO_ONE)
    )
    if noncanonical_protein_residues:
        raise WorkerFailure(
            "non-canonical-residue",
            "PSE protein 含非标准氨基酸残基: "
            + ",".join(noncanonical_protein_residues),
        )

    molecule_objects = [
        entry["name"] for entry in inventory if entry["object_type"] == "object:molecule"
    ]
    water_keys: set[tuple[str, str, str]] = set()
    ligand_heavy_atoms = 0
    for object_name in molecule_objects:
        model = cmd.get_model(_selection(str(object_name)), state=1)
        for atom in model.atom:
            resn = str(atom.resn).upper()
            element = str(atom.symbol).upper()
            if resn in WATER_RESIDUES:
                water_keys.add((str(object_name), str(atom.chain), str(atom.resi)))
            elif resn not in THREE_TO_ONE and element not in {"H", "D"}:
                ligand_heavy_atoms += 1
    if ligand_heavy_atoms:
        raise WorkerFailure(
            "non-protein-heavy-atoms",
            f"PSE 含配体、非标准残基或其他非溶剂重原子: {ligand_heavy_atoms}",
        )

    grouped: dict[tuple[str, str], list[Any]] = {}
    order: list[tuple[str, str]] = []
    for atom in protein_model.atom:
        key = (str(atom.chain), str(atom.resi))
        if key not in grouped:
            grouped[key] = []
            order.append(key)
        grouped[key].append(atom)

    ca_colors: dict[tuple[str, int], int] = {}
    cmd.iterate(
        f"({protein_selection}) and name CA",
        "ca_colors[(model, index)] = color",
        space={"ca_colors": ca_colors},
    )

    if len(order) < 20:
        raise WorkerFailure(
            "protein-too-short",
            f"单 Target PSE 至少需要 20 个标准残基，发现 {len(order)} 个",
        )

    residues: list[dict[str, Any]] = []
    seen_numbering: set[tuple[str, str, str | None]] = set()
    for sequence_index, key in enumerate(order, start=1):
        atoms = grouped[key]
        residue_names = {str(atom.resn).upper() for atom in atoms}
        if len(residue_names) != 1:
            raise WorkerFailure(
                "ambiguous-residue-identity",
                f"同一 author residue 出现多个 residue name: key={key}, names={residue_names}",
            )
        residue_name = next(iter(residue_names))
        amino_acid = THREE_TO_ONE.get(residue_name)
        if amino_acid is None:
            raise WorkerFailure(
                "non-canonical-residue",
                f"PSE 含非标准氨基酸残基: chain={key[0]}, resi={key[1]}, resn={residue_name}",
            )
        ca_atoms = [atom for atom in atoms if str(atom.name).upper() == "CA"]
        if len(ca_atoms) != 1:
            raise WorkerFailure(
                "ca-atom-count",
                f"每个残基必须恰好一个 CA: chain={key[0]}, resi={key[1]}, count={len(ca_atoms)}",
            )
        author_residue_id, insertion_code = _parse_author_residue_id(key[1])
        numbering_key = (key[0], author_residue_id, insertion_code)
        if numbering_key in seen_numbering:
            raise WorkerFailure(
                "ambiguous-residue-numbering",
                f"author numbering 重复: {numbering_key}",
            )
        seen_numbering.add(numbering_key)
        ca = ca_atoms[0]
        color_key = (str(ca.model), int(ca.index))
        if color_key not in ca_colors:
            raise WorkerFailure(
                "invalid-color",
                f"无法取得残基 CA 的 PyMOL color: model={color_key[0]}, index={color_key[1]}",
            )
        color_index = ca_colors[color_key]
        rgb = _rgb(cmd, color_index)
        residues.append(
            {
                "sequence_index": sequence_index,
                "residue_name": residue_name,
                "amino_acid": amino_acid,
                "author_chain_id": key[0],
                "author_residue_id": author_residue_id,
                "insertion_code": insertion_code,
                "ca_color_index": color_index,
                "ca_color_rgb": list(rgb),
                "ca_color_hex": _hex_color(rgb),
            }
        )

    if output_pdb.exists():
        raise WorkerFailure("output-exists", f"worker 不可覆盖 PDB: {output_pdb}")
    output_pdb.parent.mkdir(parents=True, exist_ok=True)
    try:
        cmd.save(str(output_pdb), protein_selection, state=1, format="pdb")
    except Exception as error:
        raise WorkerFailure("pdb-export-failed", f"PyMOL 导出蛋白 PDB 失败: {error}") from error
    if not output_pdb.is_file() or output_pdb.stat().st_size == 0:
        raise WorkerFailure("pdb-output-missing", "PyMOL 没有生成原始蛋白 PDB")

    return {
        "schema_version": "0.1",
        "status": "succeeded",
        "pymol_version": version,
        "source_sha256": actual_sha256,
        "inventory": inventory,
        "selected_object": selected_object,
        "chain_id": chain_id,
        "state": 1,
        "water_residue_count": len(water_keys),
        "ligand_heavy_atom_count": ligand_heavy_atoms,
        "residues": residues,
        "raw_pdb_sha256": _sha256_file(output_pdb),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-pdb", type=Path, required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    started = time.monotonic()
    try:
        request = json.loads(args.request.read_text(encoding="utf-8"))
        if not isinstance(request, dict):
            raise WorkerFailure("invalid-request", "PSE request 顶层必须是 JSON object")
        payload = _extract(
            request=request,
            run_root=args.run_root,
            output_pdb=args.output_pdb,
        )
        payload["worker_runtime_seconds"] = round(time.monotonic() - started, 6)
        _exclusive_json(payload, args.output_json)
        print("PyMOL PSE extraction succeeded.")
        return 0
    except WorkerFailure as error:
        payload = {
            "schema_version": "0.1",
            "status": "failed",
            "error_code": error.code,
            "message": str(error),
            "worker_runtime_seconds": round(time.monotonic() - started, 6),
        }
        try:
            _exclusive_json(payload, args.output_json)
        except FileExistsError:
            pass
        print(f"{error.code}: {error}", file=sys.stderr)
        return 2
    except Exception as error:
        payload = {
            "schema_version": "0.1",
            "status": "failed",
            "error_code": "unexpected-worker-error",
            "message": f"{type(error).__name__}: {error}",
            "worker_runtime_seconds": round(time.monotonic() - started, 6),
        }
        try:
            _exclusive_json(payload, args.output_json)
        except FileExistsError:
            pass
        print(payload["message"], file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
