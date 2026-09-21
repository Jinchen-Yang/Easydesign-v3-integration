"""Real old Stage 01 jobs against deterministic cached UniProt fixtures."""

import json
from typing import Any

import gemmi
import httpx
import pytest

from easydesign.agent.evidence_corpus import EvidenceCorpus, RetrieveEvidence, SelectEvidence
from easydesign.agent.evidence_research import EvidenceResearch, ResearchHttpClient, ResearchQuery
from easydesign.agent.phase2 import Phase2Bridge
from easydesign.agent.target_identity import CanonicalProposal, propose_canonical
from easydesign.orchestration.config import EasyDesignRunConfig
from easydesign.orchestration.local_project import publish_config_revision
from tests.agent_support import judge_card, make_project, terminal


def test_inactive_uniprot_record_exposes_successors_without_selecting_one(
    tmp_path: Any, monkeypatch: Any
) -> None:
    from easydesign.agent.contracts import CanonicalReferenceMismatch

    old = make_project(tmp_path, monkeypatch, chains="A")
    bridge = Phase2Bridge(old.project, old.thread, old.store)
    bridge.store.begin_execution(bridge.thread, "Resolve an inactive canonical accession")
    record = {
        "primaryAccession": "P02928",
        "uniProtkbId": "MALE_ECOLI",
        "entryType": "Inactive",
        "inactiveReason": {
            "inactiveReasonType": "DEMERGED",
            "mergeDemergeTo": ["P0AEX9", "P0AEY0"],
        },
    }
    monkeypatch.setattr(
        EvidenceResearch,
        "client",
        lambda self, directory: ResearchHttpClient(
            evidence_dir=directory,
            max_attempts=1,
            client=httpx.Client(
                transport=httpx.MockTransport(lambda request: httpx.Response(200, json=record))
            ),
        ),
    )
    try:
        EvidenceCorpus(bridge).select(
            SelectEvidence(
                provider="UniProt",
                identifier="P02928",
                need="TARGET_IDENTITY",
                selection="SELECTED",
                reason="Resolve the depositor-supplied legacy accession",
            )
        )
        acquired = EvidenceResearch(bridge).acquire(
            ResearchQuery(
                topic="identity",
                question="Is this accession an active canonical reference?",
                operation="uniprot-record",
                identifier="P02928",
            ),
            role="target",
        )
        card = acquired["cards"][0]
        assert card["source_verified"] is True
        assert card["canonical_reference_eligible"] is False
        assert card["identifier_resolution"] == {
            "status": "inactive",
            "type": "DEMERGED",
            "replacement_accessions": ["P0AEX9", "P0AEY0"],
        }
        assert json.loads(card["passage"])["canonical_reference_eligible"] is False
        focused = EvidenceCorpus(bridge).retrieve(
            RetrieveEvidence(
                need="TARGET_IDENTITY",
                source_id="UniProt:P02928",
                question="Inactive accession and successor identities",
            )
        )
        assert focused["cards"][0]["identifier_resolution"] == card[
            "identifier_resolution"
        ]

        before = bridge.binding()
        with pytest.raises(CanonicalReferenceMismatch) as caught:
            propose_canonical(
                bridge,
                CanonicalProposal(
                    uniprot_card_id=card["card_id"],
                    reason="Resolve the legacy accession without choosing a successor",
                ),
            )
        result = caught.value.result()
        assert result["error_code"] == "INACTIVE_CANONICAL_REFERENCE"
        assert result["identifier_resolution"]["replacement_accessions"] == [
            "P0AEX9",
            "P0AEY0",
        ]
        assert bridge.binding() == before
        assert bridge.validate_project().config.target.source.identity.uniprot_accession is None
        assert not bridge._jobs()
        assert not [
            event
            for event in bridge.store.events(bridge.thread)
            if event["kind"] == "canonical-reference-proposal"
        ]
        assert not [
            document
            for document in EvidenceCorpus(bridge).documents()
            if document["identifier"] in {"P0AEX9", "P0AEY0"}
        ]
    finally:
        bridge.store.close()


@pytest.mark.parametrize(
    "record",
    [
        {
            "primaryAccession": "P12345",
            "entryType": "UniProtKB reviewed (Swiss-Prot)",
            "organism": {"taxonId": 9606},
        },
        {
            "primaryAccession": "P02928",
            "entryType": "Inactive",
            "inactiveReason": {
                "inactiveReasonType": "DEMERGED",
                "mergeDemergeTo": [],
            },
        },
        {
            "primaryAccession": "P02928",
            "entryType": "Inactive",
            "inactiveReason": {
                "inactiveReasonType": "DEMERGED",
                "mergeDemergeTo": ["P02928"],
            },
        },
        {
            "primaryAccession": "P02928",
            "entryType": "Inactive",
            "inactiveReason": {
                "inactiveReasonType": "DEMERGED",
                "mergeDemergeTo": ["P0AEX9", "P0AEX9"],
            },
        },
    ],
)
def test_incomplete_or_malformed_uniprot_record_remains_hard_failure(
    tmp_path: Any, monkeypatch: Any, record: dict[str, Any]
) -> None:
    from easydesign.core import TargetInputError

    old = make_project(tmp_path, monkeypatch, chains="A")
    bridge = Phase2Bridge(old.project, old.thread, old.store)
    bridge.store.begin_execution(bridge.thread, "Reject an incomplete canonical source")
    monkeypatch.setattr(
        EvidenceResearch,
        "client",
        lambda self, directory: ResearchHttpClient(
            evidence_dir=directory,
            max_attempts=1,
            client=httpx.Client(
                transport=httpx.MockTransport(lambda request: httpx.Response(200, json=record))
            ),
        ),
    )
    try:
        accession = record["primaryAccession"]
        EvidenceCorpus(bridge).select(
            SelectEvidence(
                provider="UniProt",
                identifier=accession,
                need="TARGET_IDENTITY",
                selection="SELECTED",
                reason="Validate a supplied canonical source",
            )
        )
        acquired = EvidenceResearch(bridge).acquire(
            ResearchQuery(
                topic="identity",
                question="Is this a complete canonical source?",
                operation="uniprot-record",
                identifier=accession,
            ),
            role="target",
        )
        with pytest.raises(TargetInputError, match="accession/sequence/taxonomy"):
            propose_canonical(
                bridge,
                CanonicalProposal(
                    uniprot_card_id=acquired["cards"][0]["card_id"],
                    reason="Reject incomplete identity evidence",
                ),
            )
        assert bridge.validate_project().config.target.source.identity.uniprot_accession is None
        assert not bridge._jobs()
    finally:
        bridge.store.close()


@pytest.mark.parametrize(
    "canonical,chains,complete_coordinates,expected_gate",
    [
        ("AGSLVK", "A", True, None),
        ("MAGSLVK", "A", False, "target-identity-review"),
        ("MAGSLVK", "A", True, None),
        ("AGSLVK", "AB", True, "chain-selection"),
        ("AGTLVK", "A", True, "target-identity-review"),
    ],
)
def test_canonical_identity_reuses_existing_decision_and_bundle(
    tmp_path: Any,
    monkeypatch: Any,
    canonical: str,
    chains: str,
    complete_coordinates: bool,
    expected_gate: str | None,
) -> None:
    old = make_project(tmp_path, monkeypatch, chains=chains)
    record = {
        "primaryAccession": "P12345",
        "entryType": "UniProtKB reviewed (Swiss-Prot)",
        "organism": {"taxonId": 9606},
        "sequence": {"value": canonical},
        "features": [],
    }
    config = old.validate_project().config.model_dump(mode="json")
    # A clean canonical match also needs deposited sequence/coordinate labels.
    # The generic PDB fixture intentionally has neither; use a complete mmCIF.
    # Keep an independent non-protein chain to exercise the identity boundary.
    if complete_coordinates:
        source = old.validate_project().config.target.source.path
        structure = gemmi.read_structure(str(old.project / source))
        glycan = gemmi.Chain("Z")
        glycan_residue = gemmi.Residue()
        glycan_residue.name = "NAG"
        glycan_residue.seqid = gemmi.SeqId(1, " ")
        glycan_residue.subchain = "Z"
        glycan_atom = gemmi.Atom()
        glycan_atom.name = "C1"
        glycan_atom.element = gemmi.Element("C")
        glycan_residue.add_atom(glycan_atom)
        glycan.add_residue(glycan_residue)
        structure[0].add_chain(glycan)
        structure.setup_entities()
        for entity in structure.entities:
            if entity.entity_type == gemmi.EntityType.Polymer:
                entity.full_sequence = ["ALA", "GLY", "SER", "LEU", "VAL", "LYS"]
        structure.assign_label_seq_id()
        complete = old.project / "canonical-input.cif"
        complete.write_text(structure.make_mmcif_document().as_string())
        config["stage01"]["target"]["source"].update(path=str(complete), format="auto")
    config["workflow"]["cache_mode"] = "offline"
    publish_config_revision(old.project, EasyDesignRunConfig.model_validate(config))
    bridge = Phase2Bridge(old.project, old.thread, old.store)
    bridge.store.begin_execution(bridge.thread, "Resolve the construct against canonical identity")
    monkeypatch.setattr(
        EvidenceResearch,
        "client",
        lambda self, directory: ResearchHttpClient(
            evidence_dir=directory,
            max_attempts=1,
            client=httpx.Client(
                transport=httpx.MockTransport(lambda request: httpx.Response(200, json=record))
            ),
        ),
    )
    try:
        EvidenceCorpus(bridge).select(
            SelectEvidence(
                provider="UniProt",
                identifier="P12345",
                need="TARGET_IDENTITY",
                selection="SELECTED",
                reason="Verify canonical identity before preparation",
            )
        )
        acquired = EvidenceResearch(bridge).acquire(
            ResearchQuery(
                topic="identity",
                question="Which canonical sequence is this construct from?",
                operation="uniprot-record",
                identifier="P12345",
            ),
            role="target",
        )
        proposal = CanonicalProposal(
            uniprot_card_id=acquired["cards"][0]["card_id"],
            reason="Propose the verified canonical source; old mapping must review differences",
        )
        before = bridge.binding()
        blocked = propose_canonical(bridge, proposal)
        assert blocked["status"] == "REQUIRES_ACTION"
        assert bridge.binding() == before and not bridge._jobs()
        EvidenceCorpus(bridge).retrieve(
            RetrieveEvidence(
                need="TARGET_IDENTITY",
                source_id="UniProt:P12345",
                question="Canonical sequence and construct features",
            )
        )
        result = propose_canonical(bridge, proposal)
        assert result["accession"] == "P12345"
        assert propose_canonical(bridge, proposal)["accession"] == "P12345"
        assert (
            len(
                [
                    e
                    for e in bridge.store.events(bridge.thread)
                    if e["kind"] == "canonical-reference-proposal"
                ]
            )
            == 1
        )
        assert not bridge._jobs()  # A reference proposal is not scientific authority.
        bridge.prepare_target()
        terminal(bridge)
        evidence = bridge.read_evidence()
        if expected_gate:
            assert evidence["decision_kind"] == expected_gate
            assert evidence["identity_evidence"]["canonical"]["accession"] == "P12345"
            assert evidence["identity_evidence"]["construct_comparisons"]
            assert {
                row["auth_chain"] for row in evidence["identity_evidence"]["construct_comparisons"]
            } == set(chains)
            card = judge_card(bridge)
            assert (
                "Canonical biological identity is unconfirmed; "
                "species, isoform and native construct are not established." not in card.limitations
            )
            assert (
                "Reference completeness is unknown. "
                "Chain selection does not confirm biological identity." not in card.limitations
            )
            assert evidence["limitations"][0] in card.limitations
            bridge.store.respond(bridge.thread, card.card_id, "approve", "fixture-scientist")
            bridge.apply_decision(card)
            terminal(bridge)
            evidence = bridge.read_evidence()
        assert evidence["status"] == "succeeded"
        assert evidence["identity"]["biological_identity_status"] == "resolved"
        assert evidence["identity"]["canonical"]["accession"] == "P12345"
        assert not any("identity is unconfirmed" in t for t in evidence["limitations"])
        assert bridge.target_state()["evidence"]["identity"] == evidence["identity"]
        assert not any(j.step > 1 for j in bridge.controller.list(project_id=bridge.project_id))
    finally:
        bridge.store.close()


def test_canonical_proposal_cannot_replace_scientist_species(
    tmp_path: Any, monkeypatch: Any
) -> None:
    from easydesign.agent.contracts import AgentBoundaryError

    old = make_project(tmp_path, monkeypatch, chains="A")
    config = old.validate_project().config.model_dump(mode="json")
    config["stage01"]["target"]["source"]["identity"]["taxon_id"] = 9606
    publish_config_revision(old.project, EasyDesignRunConfig.model_validate(config))
    bridge = Phase2Bridge(old.project, old.thread, old.store)
    bridge.store.begin_execution(bridge.thread, "Verify the declared human target")
    record = {
        "primaryAccession": "P12345",
        "organism": {"taxonId": 10090},
        "sequence": {"value": "AGSLVK"},
        "features": [],
    }
    monkeypatch.setattr(
        EvidenceResearch,
        "client",
        lambda self, directory: ResearchHttpClient(
            evidence_dir=directory,
            max_attempts=1,
            client=httpx.Client(
                transport=httpx.MockTransport(lambda request: httpx.Response(200, json=record))
            ),
        ),
    )
    try:
        EvidenceCorpus(bridge).select(
            SelectEvidence(
                provider="UniProt",
                identifier="P12345",
                need="TARGET_IDENTITY",
                selection="SELECTED",
                reason="Verify reference species",
            )
        )
        acquired = EvidenceResearch(bridge).acquire(
            ResearchQuery(
                topic="identity",
                question="Is this the declared species?",
                operation="uniprot-record",
                identifier="P12345",
            ),
            role="target",
        )
        with pytest.raises(AgentBoundaryError, match="scientist-configured species"):
            propose_canonical(
                bridge,
                CanonicalProposal(
                    uniprot_card_id=acquired["cards"][0]["card_id"],
                    reason="Inspect source mismatch",
                ),
            )
        assert bridge.validate_project().config.target.source.identity.taxon_id == 9606
        assert not bridge._jobs()
    finally:
        bridge.store.close()


def test_constant_offset_is_projected_from_all_kernel_rows_and_not_ambiguous_counts() -> None:
    from easydesign.agent.target_identity import constant_canonical_offset
    from tests.agent_golden_support import golden_truth
    from tests.unit.agent.test_phase2_golden_spec import resolve

    soluble = resolve(golden_truth()["soluble"])
    assert constant_canonical_offset(soluble) == 18
    assert all(
        r.canonical_position == r.construct_position + 18 for r in soluble.design_scope.residues
    )
    # The last two residues are aligned correctly even though their coordinates are absent.
    assert [
        (r.construct_position, r.canonical_position)
        for r in soluble.design_scope.residues
        if not r.coordinate_present
    ] == [(128, 146), (129, 147)]
    gpcr = resolve(golden_truth()["gpcr"])
    assert gpcr.ambiguities and constant_canonical_offset(gpcr) is None
