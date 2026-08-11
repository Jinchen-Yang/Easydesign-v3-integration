"""Thin CLI over the audited OpenFold3 release-bundle API."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from easydesign.core import sha256_file
from easydesign.orchestration.openfold3_bundle import (
    build_openfold3_release_bundle,
    create_deterministic_tar_zst,
)


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
        "validation-receipt",
        "openfold3-source",
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
        validation_receipt=args.validation_receipt,
        openfold3_source=args.openfold3_source,
    )
    archive = result.with_suffix(".tar.zst")
    create_deterministic_tar_zst(bundle=result, archive=archive)
    print(
        json.dumps(
            {
                "bundle": str(result),
                "archive": str(archive),
                "size_bytes": archive.stat().st_size,
                "sha256": sha256_file(archive),
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
