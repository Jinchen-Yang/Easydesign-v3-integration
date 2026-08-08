"""Thin CLI over the audited OpenFold3 release-bundle API."""

from __future__ import annotations

import argparse
from pathlib import Path

from easydesign.orchestration.openfold3_bundle import build_openfold3_release_bundle


def main() -> int:
    parser = argparse.ArgumentParser()
    for name in (
        "output",
        "source",
        "wheelhouse",
        "requirements",
        "raw-checkpoint",
        "first-conversion",
        "second-conversion",
        "first-log",
        "second-log",
        "validation-receipt",
    ):
        parser.add_argument(f"--{name}", required=True, type=Path)
    args = parser.parse_args()
    result = build_openfold3_release_bundle(
        output=args.output,
        source=args.source,
        wheelhouse=args.wheelhouse,
        requirements=args.requirements,
        raw_checkpoint=args.raw_checkpoint,
        first_conversion=args.first_conversion,
        second_conversion=args.second_conversion,
        first_log=args.first_log,
        second_log=args.second_log,
        validation_receipt=args.validation_receipt,
    )
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
