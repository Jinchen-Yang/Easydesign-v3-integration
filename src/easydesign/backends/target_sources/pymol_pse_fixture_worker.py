"""Create a runtime-only PSE from an explicitly supplied structure.

This worker belongs to the developer backend self-test.  It runs inside the
isolated PyMOL environment and deliberately has no EasyDesign dependency.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main() -> int:
    arguments = _parser().parse_args()
    if not arguments.input.is_file():
        raise FileNotFoundError(arguments.input)
    if arguments.output.exists():
        raise FileExistsError(arguments.output)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)

    import pymol  # type: ignore[import-not-found]

    pymol.finish_launching(["pymol", "-cq"])
    try:
        pymol.cmd.load(str(arguments.input), "validation_target")
        pymol.cmd.remove("solvent")
        pymol.cmd.remove("not polymer.protein")
        if pymol.cmd.count_atoms("validation_target and polymer.protein") < 20:
            raise RuntimeError("validation fixture does not contain a protein")
        pymol.cmd.color("gray80", "validation_target")
        pymol.cmd.save(str(arguments.output), "validation_target", state=1)
    finally:
        pymol.cmd.quit()
    sys.stdout.write("created\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
