"""Fixed real-source sequence/coordinate oracles, independent of Agent/Judge answers."""

import copy
from typing import Any

import pytest

from easydesign.core.target_identity import resolve_target_identity
from tests.agent_golden_support import check_identity_report, golden_truth


def resolve(truth: Any) -> Any:
    return resolve_target_identity(
        target_id="golden-target",
        canonical_sequence=truth["canonical_sequence"],
        construct_sequence=truth["construct_sequence"],
        accession=truth["accession"],
        taxon_id=truth["taxon_id"],
        auth_chain_id=truth["auth_chain"],
        label_chain_id=truth["label_chain"],
        coordinate_present_construct_positions=tuple(truth["coordinate_label_seq_ids"]),
    )


@pytest.mark.parametrize("name", ["soluble", "gpcr"])
def test_fixed_golden_sequence_mapping_oracle(name: str) -> None:
    truth = golden_truth()[name]
    report = resolve(truth)
    check_identity_report(report.model_dump(mode="json", by_alias=True), truth)
    expected = truth["expected"]
    assert str(report.relationship) == expected["relationship"]
    assert str(report.review_requirement) == expected["review_requirement"]
    assert str(report.design_scope.mapping_status) == expected["mapping_status"]
    assert len(truth["coordinate_sequence"]) == expected["observed_count"]
    assert len(truth["coordinate_label_seq_ids"]) == expected["observed_count"]
    assert report.alignment is not None
    for field in ("substitutions", "insertions", "deletions"):
        assert len(getattr(report.alignment, field)) == expected[field]
    if name == "soluble":
        assert truth["canonical_sequence"][18:] == truth["construct_sequence"]
        assert set(range(1, 130)) - set(truth["coordinate_label_seq_ids"]) == {128, 129}
    else:
        extracellular = [
            (f["location"]["start"]["value"], f["location"]["end"]["value"])
            for f in truth["features"]
            if f["type"] == "Topological domain" and f["description"] == "Extracellular"
        ]
        assert extracellular == [(1, 29), (97, 103), (172, 197), (299, 304)]


@pytest.mark.parametrize("error", ["chain", "accession", "offset", "missing-coordinate"])
def test_golden_oracle_rejects_consequential_errors_even_with_approval(error: str) -> None:
    truth = golden_truth()["soluble"]
    report = copy.deepcopy(resolve(truth).model_dump(mode="json", by_alias=True))
    report["human_approved"] = True  # Neither this nor an opinion can repair a false hard fact.
    if error == "chain":
        report["construct"]["auth_chain_id"] = "A"
    elif error == "accession":
        report["canonical"]["accession"] = "P07550"
    elif error == "offset":
        report["design_scope"]["residues"][0]["canonical_position"] = 1
    else:
        row = next(r for r in report["design_scope"]["residues"] if r["construct_position"] == 128)
        row["coordinate_present"] = True
    with pytest.raises(AssertionError):
        check_identity_report(report, truth)
