"""Independent fixed-source factual oracles for migration acceptance, never model approval."""

import hashlib
import json
from pathlib import Path
from typing import Any


def golden_truth() -> dict[str, Any]:
    return json.loads(
        (Path(__file__).parent / "fixtures/agent/phase2_golden_truth.json").read_text()
    )


def check_identity_report(report: dict[str, Any], truth: dict[str, Any]) -> None:
    """Check source facts independently of the model's prose or a Gate response."""
    canonical, construct = report["canonical"], report["construct"]
    assert canonical["accession"] == truth["accession"], "Wrong canonical accession"
    assert canonical["taxon_id"] == truth["taxon_id"], "Wrong canonical species"
    assert canonical["sequence_length"] == len(truth["canonical_sequence"])
    assert (
        canonical["sequence_sha256"]
        == hashlib.sha256(truth["canonical_sequence"].encode("ascii")).hexdigest()
    ), "Wrong canonical sequence"
    assert construct["auth_chain_id"] == truth["auth_chain"], "Wrong source chain"
    assert construct["label_chain_id"] == truth["label_chain"], "Wrong source label chain"
    assert construct["sequence_length"] == len(truth["construct_sequence"])
    assert (
        construct["sequence_sha256"]
        == hashlib.sha256(truth["construct_sequence"].encode("ascii")).hexdigest()
    ), "Wrong construct sequence"
    observed = set(truth["coordinate_label_seq_ids"])
    rows = report["design_scope"]["residues"]
    assert rows, "Missing design mapping"
    for row in rows:
        position = row["construct_position"]
        assert 1 <= position <= len(truth["construct_sequence"]), "Nonexistent construct residue"
        assert row["construct_residue"] == truth["construct_sequence"][position - 1]
        assert row["coordinate_present"] == (position in observed), "Wrong coordinate presence"
        if truth["accession"] == "P00698":
            assert row["canonical_position"] == position + 18, "Wrong precursor offset"
            assert row["canonical_residue"] == row["construct_residue"]
    if truth["accession"] == "P07550":
        assert "multiple-equally-optimal-sequence-alignments" in report["ambiguities"], (
            "Construct ambiguity must not disappear through human approval"
        )


def approved_identity(bridge: Any, truth: dict[str, Any]) -> dict[str, Any]:
    from easydesign.core import load_model
    from easydesign.core.target_identity import TargetIdentityReport
    from easydesign.stages.s01_target_preparation.models import TargetBundle

    target = bridge.target_state()  # Existing runtime validates manifests and authoritative state.
    bundle = load_model(target["bundle_path"], TargetBundle)
    assert bundle.identity_report is not None
    report = load_model(bundle.identity_report.verify(target["root"]), TargetIdentityReport)
    result = report.model_dump(mode="json", by_alias=True)
    check_identity_report(result, truth)
    return result
