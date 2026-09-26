from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import gemmi
import pytest

from easydesign.backends.structure_prediction import OpenFold3TemplatePipelineAssets
from easydesign.core import ManifestStateError, sha256_file
from easydesign.orchestration.afo_template_protocol import (
    audit_final_input,
    prepare_binder_stage1_template,
    validate_target_processed_json,
)


def _file(path: Path, value: str) -> Path:
    path.write_text(value, encoding="utf-8")
    return path.resolve()


def _assets(tmp_path: Path) -> OpenFold3TemplatePipelineAssets:
    receipt = _file(tmp_path / "component.json", "{}\n")
    hmmbuild = _file(tmp_path / "hmmbuild", "hmmbuild\n")
    hmmsearch = _file(tmp_path / "hmmsearch", "hmmsearch\n")
    hmmalign = _file(tmp_path / "hmmalign", "hmmalign\n")
    seqres = _file(tmp_path / "pdb_seqres.fasta", ">x\nACD\n")
    mmcif = (tmp_path / "mmcif").resolve()
    mmcif.mkdir()
    mmcif_manifest = _file(tmp_path / "mmcif-manifest.json", "{}\n")
    disabled_search = _file(tmp_path / "disabled-msa-search", "disabled\n")
    unused_database = _file(tmp_path / "unused-msa-database.sentinel", "unused\n")
    return OpenFold3TemplatePipelineAssets(
        component_receipt=receipt,
        component_receipt_sha256=sha256_file(receipt),
        hmmbuild=hmmbuild,
        hmmbuild_sha256=sha256_file(hmmbuild),
        hmmsearch=hmmsearch,
        hmmsearch_sha256=sha256_file(hmmsearch),
        hmmalign=hmmalign,
        hmmalign_sha256=sha256_file(hmmalign),
        hmmer_version="3.4",
        disabled_msa_search_executable=disabled_search,
        disabled_msa_search_executable_sha256=sha256_file(disabled_search),
        unused_msa_database_sentinel=unused_database,
        unused_msa_database_sentinel_sha256=sha256_file(unused_database),
        seqres_database=seqres,
        seqres_database_sha256=sha256_file(seqres),
        seqres_database_version="test-2026-09-26",
        mmcif_database=mmcif,
        mmcif_manifest=mmcif_manifest,
        mmcif_manifest_sha256=sha256_file(mmcif_manifest),
        mmcif_database_version="test-2026-09-26",
        max_template_date=date(2026, 1, 1),
    )


def _structure_text(chains: tuple[tuple[str, str], ...]) -> str:
    names = {
        "A": "ALA",
        "C": "CYS",
        "D": "ASP",
        "F": "PHE",
        "G": "GLY",
        "H": "HIS",
        "I": "ILE",
    }
    structure = gemmi.Structure()
    structure.name = "test"
    model = gemmi.Model("1")
    for chain_id, sequence in chains:
        chain = gemmi.Chain(chain_id)
        for index, one_letter in enumerate(sequence, start=1):
            residue = gemmi.Residue()
            residue.name = names[one_letter]
            residue.seqid = gemmi.SeqId(index, " ")
            residue.label_seq = index
            residue.subchain = chain_id
            atom = gemmi.Atom()
            atom.name = "CA"
            atom.element = gemmi.Element("C")
            atom.pos = gemmi.Position(float(index), 0.0, 0.0)
            residue.add_atom(atom)
            chain.add_residue(residue)
        model.add_chain(chain)
    structure.add_model(model)
    structure.setup_entities()
    for entity, (_, sequence) in zip(structure.entities, chains, strict=True):
        entity.full_sequence = [names[letter] for letter in sequence]
    structure.assign_label_seq_id()
    return structure.make_mmcif_document().as_string()


def test_validates_native_processed_target_and_preserves_msa(tmp_path: Path) -> None:
    sequence = "ACD"
    unpaired = _file(tmp_path / "target.a3m", ">query\nACD\n>hit\nA-D\n")
    paired = _file(tmp_path / "paired.a3m", ">query\nACD\n")
    protein = {
        "id": "A",
        "sequence": sequence,
        "unpairedMsa": unpaired.read_text(),
        "pairedMsa": paired.read_text(),
        "templates": None,
    }
    source = _file(
        tmp_path / "input.json",
        json.dumps(
            {
                "name": "target-template",
                "sequences": [{"protein": protein}],
                "modelSeeds": [101],
                "dialect": "alphafold3",
                "version": 4,
            }
        ),
    )
    processed_protein = dict(protein)
    processed_protein["templates"] = [
        {
            "mmcif": _structure_text((("A", sequence),)),
            "queryIndices": [0, 1, 2],
            "templateIndices": [0, 1, 2],
        }
    ]
    processed = _file(
        tmp_path / "processed.json",
        json.dumps(
            {
                "name": "target-template",
                "sequences": [{"protein": processed_protein}],
                "modelSeeds": [101],
                "dialect": "alphafold3",
                "version": 4,
            }
        ),
    )

    template_path, receipt = validate_target_processed_json(
        source_input_json=source,
        processed_json=processed,
        target_sequence=sequence,
        target_unpaired_a3m=unpaired,
        target_paired_a3m=paired,
        assets=_assets(tmp_path),
        output_root=tmp_path / "frozen",
    )

    assert receipt.template_count == 1
    assert receipt.templates[0].mapped_residues == 3
    assert json.loads(template_path.read_text())[0]["queryIndices"] == [0, 1, 2]


def test_target_zero_hit_is_explicit_terminal_failure(tmp_path: Path) -> None:
    sequence = "ACD"
    unpaired = _file(tmp_path / "target.a3m", ">query\nACD\n")
    paired = _file(tmp_path / "paired.a3m", ">query\nACD\n")
    payload = {
        "name": "target-template",
        "sequences": [
            {
                "protein": {
                    "id": "A",
                    "sequence": sequence,
                    "unpairedMsa": unpaired.read_text(),
                    "pairedMsa": paired.read_text(),
                    "templates": [],
                }
            }
        ],
        "modelSeeds": [101],
        "dialect": "alphafold3",
        "version": 4,
    }
    source = _file(tmp_path / "input.json", json.dumps(payload))
    processed = _file(tmp_path / "processed.json", json.dumps(payload))

    with pytest.raises(ManifestStateError, match="zero-hit"):
        validate_target_processed_json(
            source_input_json=source,
            processed_json=processed,
            target_sequence=sequence,
            target_unpaired_a3m=unpaired,
            target_paired_a3m=paired,
            assets=_assets(tmp_path),
            output_root=tmp_path / "frozen",
        )


def test_extracts_only_exact_stage1_binder_chain_and_audits_final_input(
    tmp_path: Path,
) -> None:
    source = _file(
        tmp_path / "stage1.cif",
        _structure_text((("A", "ACD"), ("X", "FGHI"))),
    )

    template_path, receipt = prepare_binder_stage1_template(
        source_complex=source,
        binder_sequence="FGHI",
        output_root=tmp_path / "binder",
    )

    payload = json.loads(template_path.read_text())
    extracted = gemmi.read_structure_string(payload[0]["mmcif"])
    assert len(extracted[0]) == 1
    assert extracted[0][0].name == "B"
    assert receipt.source_chain_id == "X"
    assert receipt.mapped_residues == 4

    final_input = _file(
        tmp_path / "final-input.json",
        json.dumps(
            {
                "name": "final",
                "sequences": [
                    {
                        "protein": {
                            "id": "A",
                            "sequence": "ACD",
                            "unpairedMsa": ">query\nACD\n>hit\nA-D\n",
                            "pairedMsa": ">query\nACD\n",
                            "templates": [
                                {
                                    "mmcif": _structure_text((("A", "ACD"),)),
                                    "queryIndices": [0, 1, 2],
                                    "templateIndices": [0, 1, 2],
                                }
                            ],
                        }
                    },
                    {
                        "protein": {
                            "id": "B",
                            "sequence": "FGHI",
                            "unpairedMsa": ">query\nFGHI\n",
                            "pairedMsa": ">query\nFGHI\n",
                            "templates": payload,
                        }
                    },
                ],
                "modelSeeds": [101],
                "dialect": "alphafold3",
                "version": 4,
            }
        ),
    )
    audit = audit_final_input(
        input_json=final_input,
        output_path=tmp_path / "final-input-audit.json",
    )

    assert audit.chains[0].unpaired_msa_depth == 2
    assert audit.chains[1].paired_msa_depth == 1
    assert audit.chains[1].template_source == "boltzgen-stage1-vhh"
