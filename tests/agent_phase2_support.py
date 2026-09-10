"""Synthetic geometry fixtures, not biological validation or a design benchmark."""

from __future__ import annotations

import math
from typing import Any


def gpcr_like_structure() -> tuple[str, dict[str, Any]]:
    rows: list[str] = []
    topology: list[dict[str, Any]] = []
    serial = 1
    residue_id = 0
    glycan_labels: list[int] = []
    for helix in range(1, 8):
        angle = (helix - 1) * 2 * math.pi / 7
        x, y = 12 * math.cos(angle), 12 * math.sin(angle)
        segments = [(f"TM{helix}", 10)]
        if helix < 7:
            segments.append((f"ICL{(helix + 1) // 2}" if helix % 2 else f"ECL{helix // 2}", 5))
        for segment, count in segments:
            for index in range(count):
                residue_id += 1
                if segment.startswith("TM"):
                    z = 13.5 - index * 3 if helix % 2 else -13.5 + index * 3
                    px, py = x, y
                else:
                    z = -20.0 if segment.startswith("ICL") else 20.0
                    px, py = x + index * 1.0, y + math.sin(index)
                residue = "ALA"
                if segment == "ECL1" and index in {1, 2, 3}:
                    residue = {1: "ASN", 2: "GLY", 3: "THR"}[index]
                    glycan_labels.append(residue_id)
                topology.append({"label_seq_id": residue_id, "segment": segment})
                for atom, dx, dy, dz, element in (
                    ("N", -1.0, 0, 0, "N"),
                    ("CA", 0, 0, 0, "C"),
                    ("C", 1.0, 0, 0, "C"),
                    ("O", 1.7, 0, 0, "O"),
                    ("CB", 0, 1.5, 0.3, "C"),
                ):
                    rows.append(
                        f"ATOM  {serial:5d} {atom:^4s} {residue} A{residue_id:4d}    "
                        f"{px + dx:8.3f}{py + dy:8.3f}{z + dz:8.3f}  "
                        f"1.00 20.00          {element:>2s}"
                    )
                    serial += 1
    context = {
        "target_auth_chain": "A",
        "target_kind": "gpcr",
        "structural_state": "active-like hypothesis, not established",
        "state_source": (
            "synthetic regression annotation; no independent biological state evidence"
        ),
        "topology_source": "synthetic seven-helix coordinate fixture",
        "topology": topology,
        "features": [
            {
                "kind": "glycan",
                "label_seq_ids": glycan_labels,
                "description": "Supplied candidate glycosylation region; occupancy not observed",
                "source": "synthetic annotation for limitation testing",
            }
        ],
        "limitations": [
            ("Synthetic geometry tests tool semantics, not native GPCR topology or binding.")
        ],
    }
    return "\n".join(rows) + "\nTER\nEND\n", context
