"""Runtime facts, structured consistency and free scientific prose; no provider calls."""

from copy import deepcopy
from hashlib import sha256
from typing import Any

import pytest
from pydantic import ValidationError

from easydesign.agent.contracts import (
    ApplyDecision,
    EvidenceBinding,
    JudgeFactClaim,
    JudgeVerdict,
    ResearchConclusionMismatch,
)
from easydesign.agent.site_fact_integrity import (
    add_fact_references,
    canonical_reference,
    fact_paths,
    fact_value,
    peptide_occurrences,
    render_judge,
    validate_fact_references,
)
from easydesign.agent.tools import JUDGE_EVIDENCE
from tests.agent_golden_support import golden_truth
from tests.unit.agent import test_judge_packet

packet_case = test_judge_packet.packet_case


def fact_packet() -> dict[str, Any]:
    sequence = golden_truth()["gpcr"]["canonical_sequence"]
    return add_fact_references(
        {
            "evidence_id": "synthetic-revision",
            "approved_target": {"identity": {"auth_chain": "A"}},
            "residue_facts": {
                "facts_table": {
                    "mapping_columns": [
                        "label_seq_id",
                        "canonical_position",
                        "canonical_residue",
                        "amino_acid",
                        "label_chain_id",
                        "source_author_chain_id",
                        "source_author_residue_id",
                        "construct_position",
                        "mapping_status",
                    ],
                    "metric_columns": [],
                    "rows": [
                        [183, 183, "N", "N", "A", "A", "183", 191, "conditional"],
                        [192, 192, "D", "D", "A", "A", "192", 200, "conditional"],
                        [193, 193, "F", "F", "A", "A", "193", 201, "conditional"],
                        [414, 286, "W", "W", "A", "A", "286", 422, "conditional"],
                    ],
                }
            },
            "candidate_facts": [
                {
                    "candidate_id": "synthetic-candidate",
                    "design_labels": [183, 192, 193, 414],
                    "location": {
                        "sequence_topology": [
                            {
                                "canonical_position": 286,
                                "annotations": [{"description": "Cytoplasmic"}],
                            }
                        ],
                        "segments": ["TM6"],
                        "membrane_geometry": [],
                    },
                }
            ],
            "reference_annotations": [],
            "avoid_design_labels": [200],
            "prepared_target_context": {
                "sequence_motifs": [
                    {"label_seq_ids": [15, 16, 17], "interpretation": "sequence only"}
                ]
            },
            "decision_evidence": {
                "source_passages": [
                    {
                        "source_verified": True,
                        "passage": "AINCYANETCCD and AINCYAEETCCD",
                        "provider": "synthetic-source",
                        "identifier": "SYNTHETIC",
                        "card_id": "synthetic-passage",
                    }
                ]
            },
        },
        {
            "sequence": sequence,
            "sequence_sha256": sha256(sequence.encode()).hexdigest(),
            "source_ref": {"sha256": "synthetic-reference"},
        },
    )


def ref(packet: dict[str, Any], kind: str, index: int = 0) -> str:
    return f"[fact:{packet['fact_revision']}:{kind}:{index}]"


def verdict(reason: str) -> JudgeVerdict:
    return JudgeVerdict(
        verdict="ready-to-ask",
        reasons=[reason],
        limitations=["Functional transfer to a monovalent binder is unproven."],
    )


def test_exact_canonical_peptide_and_construct_variant_are_distinct():
    facts = fact_packet()["peptide_facts"]
    assert facts[0]["canonical_occurrences"] == [[181, 192]]
    assert facts[0]["status"] == "unique-exact-match"
    assert facts[1]["canonical_occurrences"] == []
    assert facts[1]["status"] == "no-exact-match"
    with pytest.raises(ValidationError):
        JudgeVerdict.model_validate(
            {**verdict("Risk remains.").model_dump(), "canonical_range": [184, 196]}
        )


@pytest.mark.parametrize(
    "sequence,peptide,expected",
    [
        ("AAAA", "AAA", [[1, 3], [2, 4]]),
        ("ACDEFG", "ACD", [[1, 3]]),
        ("ACDEFG", "AAA", []),
        ("ACD", "ACDEFG", []),
    ],
)
def test_occurrences_do_not_guess_missing_or_repeated_matches(sequence, peptide, expected):
    assert peptide_occurrences(sequence, peptide) == expected


def test_overlap_mapping_topology_exclusions_motifs_and_provenance_are_runtime_owned():
    p = fact_packet()
    assert [
        m["canonical_position"] for m in p["peptide_overlaps"][0]["occurrences"][0]["members"]
    ] == [183, 192]
    text = render_judge(
        verdict(
            "Relevant evidence: "
            + " ".join(
                ref(p, kind, index)
                for kind, index in [
                    ("peptide", 0),
                    ("overlap", 0),
                    ("mapping", 3),
                    ("topology", 0),
                    ("exclusions", 0),
                    ("motif", 0),
                    ("source", 0),
                ]
            )
        ),
        p,
    )["reasons"][0]
    assert "AINCYANETCCD (canonical 181–192" in text
    assert "W286 → design W414" in text
    assert "Cytoplasmic" in text and "no whole-binder clearance" in text
    assert "exclusions: [200]" in text and "[15,16,17]" in text
    assert "synthetic-source:SYNTHETIC" in text
    assert "184–196" not in text


@pytest.mark.parametrize(
    "field", ["reasons", "limitations", "warnings", "alternative", "qualification"]
)
@pytest.mark.parametrize(
    "text",
    [
        "The extracellular candidate still has uncertain whole-VHH accessibility.",
        "ECL2 and TM6 topology do not establish intracellular or extracellular access.",
        "AINCYANETCCD (181–192) is indirect evidence; 2 assays cannot prove transfer.",
        "残基编号和跨膜拓扑不等同于整个 VHH 的可达性。",
    ],
)
def test_normal_scientific_language_is_preserved_in_every_opinion_field(field, text):
    p = fact_packet()
    raw = verdict("The risk is indirect.").model_dump()
    if field in {"reasons", "limitations"}:
        raw[field] = [text]
    elif field == "qualification":
        raw["site_claim_corrections"] = [{"claim": "quoted old claim", "qualification": text}]
    else:
        raw["recommendation"] = {
            "option_id": "site",
            "status": "SUPPORTED",
            **({"warnings": [text]} if field == "warnings" else {"alternative": text}),
        }
    original = deepcopy(raw)
    parsed = JudgeVerdict.model_validate(raw)
    assert render_judge(parsed, p) == parsed.model_dump(mode="json")
    assert raw == original


@pytest.mark.parametrize(
    "kind,index,path,bad",
    [
        ("peptide", 0, ["canonical_occurrences"], [[184, 196]]),
        ("peptide", 0, ["sequence"], "AINCYAEETCCD"),
        ("mapping", 3, ["label_seq_id"], 286),
        ("mapping", 3, ["canonical_position"], 414),
        ("mapping", 3, ["label_chain_id"], "B"),
        ("candidate", 0, ["design_labels"], [183, 192, 200, 414]),
        ("topology", 0, ["sequence_topology", 0, "annotations", 0, "description"], "Extracellular"),
        ("topology", 0, ["segments"], ["ECL2"]),
        ("exclusions", 0, [], []),
        ("overlap", 0, ["occurrences", 0, "members", 0, "canonical_position"], 184),
        ("target", 0, ["auth_chain"], "B"),
        ("source", 0, ["source_verified"], False),
        ("mapping", 3, ["canonical_position"], "286"),
        ("mapping", 3, ["canonical_position"], 286.0),
        ("source", 0, ["source_verified"], 1),
    ],
)
def test_structured_fact_conflicts_reject_without_changing_facts(kind, index, path, bad):
    p = fact_packet()
    original = deepcopy(p)
    key = f"{p['fact_revision']}:{kind}:{index}"
    expected = fact_value(p, key)
    for part in path:
        expected = expected[part]
    # Claims compare a direct field (or whole value), including complete nested values.
    field = path[0] if path and isinstance(path[0], str) else None
    whole = fact_value(p, key)
    expected_field = deepcopy(whole[field] if field else whole)
    bad_field = deepcopy(expected_field)
    remainder = path[1:] if field else path
    if remainder:
        parent = bad_field
        for part in remainder[:-1]:
            parent = parent[part]
        parent[remainder[-1]] = bad
    else:
        bad_field = bad
    good = JudgeFactClaim(fact_ref=key, field=field, value=expected_field)
    opinion = verdict("The extracellular accessibility implication remains uncertain.")
    validate_fact_references(opinion.model_copy(update={"fact_claims": [good]}), p)
    # Negative reviews also cannot submit conflicting facts.
    for state in ("ready-to-ask", "reject"):
        wrong = opinion.model_copy(
            update={
                "verdict": state,
                "fact_claims": [good.model_copy(update={"value": bad_field})],
            }
        )
        with pytest.raises(ResearchConclusionMismatch, match="JUDGE_FACT_CONFLICT"):
            render_judge(wrong, p)
    assert p == original


@pytest.mark.parametrize("field", ["missing", "segments.0", "features[0].location"])
def test_claim_fields_address_only_existing_direct_object_fields(field):
    p = fact_packet()
    claim = JudgeFactClaim(fact_ref=f"{p['fact_revision']}:topology:0", field=field, value="x")
    with pytest.raises(ResearchConclusionMismatch, match="unknown fact field"):
        validate_fact_references(verdict("Risk.").model_copy(update={"fact_claims": [claim]}), p)


def test_claim_field_contract_does_not_require_model_authored_json_paths():
    with pytest.raises(ValidationError):
        JudgeFactClaim.model_validate({"fact_ref": "topology:0", "path": [0], "value": "x"})


def test_all_reference_objects_roundtrip_and_legacy_prose_does_not_change_runtime_facts():
    p = fact_packet()
    original = deepcopy(p)
    opinion = verdict("Legacy unverified prose: AINCYANETCCD = 184–196.")
    for key in fact_paths(p):
        claim = JudgeFactClaim(fact_ref=key, value=fact_value(p, key))
        checked = opinion.model_copy(update={"fact_refs": [key], "fact_claims": [claim]})
        rendered = render_judge(checked, p)
        assert rendered["reasons"] == opinion.reasons
        assert rendered["fact_claims"][0] == claim.model_dump(mode="json")
    assert p == original
    # A prose assertion is never promoted to the authoritative precise-fact channel.
    assert p["peptide_facts"][0]["canonical_occurrences"] == [[181, 192]]


@pytest.mark.parametrize("field", ["fact_refs", "fact_claims"])
def test_structured_references_must_exist_and_match_current_revision(field):
    p = fact_packet()
    for key in ("0000000000000000:peptide:0", f"{p['fact_revision']}:peptide:999"):
        entry = key if field == "fact_refs" else JudgeFactClaim(fact_ref=key, value=None)
        with pytest.raises(ResearchConclusionMismatch, match="unknown or stale"):
            validate_fact_references(verdict("Risk.").model_copy(update={field: [entry]}), p)
        with pytest.raises(ResearchConclusionMismatch, match="no supplied fact collection"):
            validate_fact_references(verdict("Risk.").model_copy(update={field: [entry]}), {})


def test_unknown_and_stale_fact_ids_reject_and_scientific_opinions_can_differ():
    p = fact_packet()
    original = deepcopy(p)
    positive = verdict(ref(p, "peptide") + " provides indirect support.")
    negative = verdict(ref(p, "peptide") + " raises a substantial biological risk.")
    assert render_judge(positive, p)["reasons"] != render_judge(negative, p)["reasons"]
    assert p == original
    stale = deepcopy(p)
    stale["evidence_id"] = "new-revision"
    stale = add_fact_references(stale, None)
    with pytest.raises(ResearchConclusionMismatch, match="unknown or stale"):
        validate_fact_references(positive, stale)
    with pytest.raises(ResearchConclusionMismatch):
        validate_fact_references(verdict("[fact:0000000000000000:peptide:0]"), p)


def test_current_binding_is_required_for_canonical_reference(packet_case):
    case = packet_case
    bad = deepcopy(case["dossier"])
    bad["reference_annotations"] = [{"source_ref": {"bad": True}}]

    class Reader:
        def document(self, _: Any) -> dict[str, Any]:
            return {"primaryAccession": "wrong", "sequence": {"value": "ACDEFG"}}

    from easydesign.agent.contracts import AgentBoundaryError

    with pytest.raises(AgentBoundaryError, match="reference mismatch"):
        canonical_reference(Reader(), bad)


def test_registration_and_saved_assessment_cannot_bypass_structured_guard(packet_case):
    b = packet_case["bridge"]
    p = b.judge_evidence()
    token = JUDGE_EVIDENCE.set(
        EvidenceBinding.model_validate({k: p[k] for k in EvidenceBinding.model_fields})
    )
    try:
        bad_claim = JudgeFactClaim(
            fact_ref=f"{p['fact_revision']}:candidate:0", field="design_labels", value=[999]
        )
        with pytest.raises(ResearchConclusionMismatch):
            b.register_judge(verdict("Risk.").model_copy(update={"fact_claims": [bad_claim]}))
        assessment = b.register_judge(
            verdict(
                "The extracellular candidate remains conditional; canonical length 2 is a "
                "hypothetical example, not a runtime fact. " + ref(p, "candidate")
            )
        )
    finally:
        JUDGE_EVIDENCE.reset(token)
    card = b.decision_card(ApplyDecision(assessment_id=assessment.assessment_id, option_id="site"))
    facts = card.scientific_summary["independent_review"]["runtime_facts"]
    assert facts and "canonical→design" in str(card.scientific_summary)
    # Card construction revalidates stored structured assertions instead of trusting persistence.
    legacy = assessment.model_copy(
        update={"assessment_id": "synthetic-invalid-saved", "fact_claims": [bad_claim]}
    )
    b.store.save_assessment(b.thread, legacy)
    with pytest.raises(ResearchConclusionMismatch):
        b.decision_card(ApplyDecision(assessment_id=legacy.assessment_id, option_id="site"))
    assert not b.store.db.execute(
        "SELECT id FROM cards WHERE json_extract(payload,'$.assessment_id')=?",
        (legacy.assessment_id,),
    ).fetchone()


@pytest.mark.asyncio
@pytest.mark.parametrize("repeat_bad", [False, True])
async def test_actual_harness_uses_existing_repairs_for_fact_contract(site_bridge, repeat_bad):
    from langchain_core.messages import AIMessage

    from easydesign.agent.cli import run_session
    from easydesign.agent.contracts import AgentBoundaryError
    from easydesign.agent.phase2_tools import PHASE2_ALLOWED
    from tests.agent_support import scripted_config
    from tests.unit.agent.test_site_harness import SiteModel

    class FactModel(SiteModel):
        submissions: int = 0

        def answer(self, messages: Any) -> AIMessage:
            result = super().answer(messages)
            if self.role == "judge":
                for call in result.tool_calls:
                    if call["name"] in {
                        "JudgeVerdict",
                        "SiteJudgeVerdict",
                        "RecoverySiteJudgeVerdict",
                    }:
                        self.submissions += 1
                        if self.submissions == 1 or repeat_bad:
                            call["args"]["fact_claims"] = [
                                {
                                    "fact_ref": "mapping:0",
                                    "field": "canonical_position",
                                    "value": 999,
                                }
                            ]
            return result

    models = {role: FactModel(role=role) for role in PHASE2_ALLOWED}
    if repeat_bad:
        with pytest.raises(AgentBoundaryError, match="unresolved substantive findings"):
            await run_session(
                site_bridge,
                scripted_config(),
                models,
                "SYNTHETIC obtain an independent review of a structural site.",
            )
        assert models["judge"].submissions == 3
    else:
        result = await run_session(
            site_bridge,
            scripted_config(),
            models,
            "SYNTHETIC obtain an independent review of a structural site.",
        )
        assert result["status"] == "awaiting-human-approval"
        assert result["card"]["scientific_summary"]["independent_review"]["runtime_facts"]
        assert "184-196" not in str(result["card"])
        assert models["judge"].submissions == 2
    events = site_bridge.store.events(site_bridge.thread)
    rejected = [e for e in events if e["kind"] == "rejected-submission"]
    assert len(rejected) == (3 if repeat_bad else 1)
    assert all("JUDGE_FACT_CONFLICT" in e["payload"]["diagnostic"] for e in rejected)
    assert all("999" in str(e["payload"]["submitted_opinion"]) for e in rejected)
    assert sum(e["kind"] == "contract-repair" for e in events) == (2 if repeat_bad else 1)
    assert sum(e["kind"] == "judge-assessment" for e in events) == (0 if repeat_bad else 1)
    assert not any(e["kind"] == "human-response" for e in events)


def test_fact_value_cannot_change_under_an_existing_reference():
    p = fact_packet()
    opinion = verdict(ref(p, "peptide") + " has limited transfer evidence.")
    p["peptide_facts"][0]["canonical_occurrences"] = [[184, 196]]
    with pytest.raises(ResearchConclusionMismatch, match="changed referenced fact"):
        render_judge(opinion, p)
