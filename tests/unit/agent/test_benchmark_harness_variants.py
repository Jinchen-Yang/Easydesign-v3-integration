import pytest

from easydesign.agent.contracts import AgentBoundaryError
from easydesign.agent.harness import fingerprint, site_synthesis_prompt
from tests.agent_support import scripted_config


def test_skill_ablation_has_distinct_identity_and_no_domain_synthesis_text() -> None:
    config = scripted_config()
    assert fingerprint(config, "full") != fingerprint(config, "no-domain-skill")
    prompt = site_synthesis_prompt("no-domain-skill")
    assert "site-mechanism" not in prompt
    assert "candidate IDs from that dossier" in prompt
    assert "Do not invent facts" in prompt


def test_unknown_harness_variant_fails_closed() -> None:
    with pytest.raises(AgentBoundaryError, match="Unknown Site Harness variant"):
        fingerprint(scripted_config(), "unregistered-control")  # type: ignore[arg-type]


def test_generic_control_preserves_model_candidate_order_for_shared_evaluator() -> None:
    from easydesign.agent.benchmark_controls import ranked_decision_from_control_handoff
    from easydesign.agent.site_dossier import SiteResearchHandoff

    handoff = SiteResearchHandoff.model_validate(
        {
            "candidates": [
                {
                    "name": "outer pore",
                    "hotspot_label_seq_ids": [10, 11],
                    "rationale": "Preferred mapped surface in this control run.",
                    "evidence_card_ids": ["passage-a"],
                },
                {
                    "name": "loop",
                    "hotspot_label_seq_ids": [20, 21],
                    "rationale": "Second mapped surface in this control run.",
                },
            ],
            "decision_questions": [],
            "contradiction_search_query_ids": [],
            "stopping_reason": "The single-loop budget is complete.",
            "unresolved_questions": ["Whole-binder access remains untested."],
        }
    )
    dossier = {
        "candidate_comparison": [
            {"candidate_id": "site-B"},
            {"candidate_id": "site-A"},
        ]
    }
    decision = ranked_decision_from_control_handoff(dossier, handoff)
    assert [candidate.candidate_id for candidate in decision.candidates] == ["site-B", "site-A"]
    assert {candidate.confidence for candidate in decision.candidates} == {"low"}
    assert decision.candidates[0].supporting_evidence == ["Handoff evidence refs: passage-a"]


def test_control_rank_selection_uses_displayed_rank_and_rejects_blocked() -> None:
    from easydesign.agent.benchmark_controls import resolve_control_site_selection

    options = [
        {"option_id": "site-2", "rank": "B", "eligible": True},
        {"option_id": "site-x", "rank": None, "eligible": False},
        {"option_id": "site-1", "rank": "A", "eligible": True},
    ]
    assert resolve_control_site_selection(options, "A") == "site-1"
    assert resolve_control_site_selection(options, "B") == "site-2"
    assert resolve_control_site_selection(options, "site-2") == "site-2"
    assert resolve_control_site_selection(options, None) is None
    with pytest.raises(ValueError, match="rank C is not selectable"):
        resolve_control_site_selection(options, "C")


def test_generic_control_disables_structured_output_repair(bridge) -> None:
    from easydesign.agent.harness import RoleBoundary

    execution = bridge.store.begin_execution(bridge.thread, "Synthetic generic control")
    boundary = RoleBoundary(
        bridge,
        "target",
        scripted_config(),
        "Synthetic control",
        execution_id=execution["execution_id"],
        domain_skills=False,
        allow_repairs=False,
    )
    with pytest.raises(AgentBoundaryError, match="no structured-output repair"):
        boundary.contract_error("synthetic malformed output")
    assert bridge.store.events(bridge.thread)[-1]["kind"] == "benchmark-repair-disabled"


def test_base_llm_tool_packet_binds_exact_inputs_and_outputs() -> None:
    from easydesign.agent.benchmark_controls import freeze_base_tool_packet

    first = freeze_base_tool_packet(
        case_id="case-a",
        source_snapshot_id="snapshot-1",
        goal="Design an extracellular VHH.",
        tool_records=[
            {
                "name": "read_site_evidence",
                "arguments": {},
                "result": {"approved_chain": "R"},
            }
        ],
    )
    second = freeze_base_tool_packet(
        case_id="case-a",
        source_snapshot_id="snapshot-1",
        goal="Design an extracellular VHH.",
        tool_records=[
            {
                "name": "read_site_evidence",
                "arguments": {},
                "result": {"approved_chain": "A"},
            }
        ],
    )
    assert first["packet_sha256"] != second["packet_sha256"]
    assert len(first["tool_records"][0]["arguments_sha256"]) == 64
    assert len(first["tool_records"][0]["result_sha256"]) == 64


def test_base_llm_tool_packet_rejects_skill_loader() -> None:
    from easydesign.agent.benchmark_controls import freeze_base_tool_packet

    with pytest.raises(ValueError, match="not an allowed Site scientific tool"):
        freeze_base_tool_packet(
            case_id="case-a",
            source_snapshot_id="snapshot-1",
            goal="Synthetic",
            tool_records=[
                {
                    "name": "read_file",
                    "arguments": {"file_path": "/skills/site-mechanism/SKILL.md"},
                    "result": "domain instructions",
                }
            ],
        )


def test_base_llm_tool_packet_detects_post_freeze_tampering() -> None:
    from easydesign.agent.benchmark_controls import (
        freeze_base_tool_packet,
        validate_base_tool_packet,
    )

    packet = freeze_base_tool_packet(
        case_id="case-a",
        source_snapshot_id="snapshot-1",
        goal="Synthetic",
        tool_records=[
            {
                "name": "read_site_evidence",
                "arguments": {},
                "result": {"approved_chain": "R"},
            }
        ],
    )
    validate_base_tool_packet(packet)
    packet["tool_records"][0]["result"]["approved_chain"] = "A"
    with pytest.raises(ValueError, match="hash mismatch"):
        validate_base_tool_packet(packet)


def test_control_handoff_is_bound_to_runtime_dossier_before_site_registration(
    site_bridge,
) -> None:
    from easydesign.agent.benchmark_controls import register_control_site
    from easydesign.agent.contracts import EvidenceBinding
    from easydesign.agent.phase2 import SITE_EVIDENCE
    from easydesign.agent.site_dossier import SiteResearchHandoff

    execution_id = site_bridge.store.begin_execution(
        site_bridge.thread, "Synthetic direct-control measurement"
    )["execution_id"]
    evidence = site_bridge.read_site_evidence()
    token = SITE_EVIDENCE.set(
        EvidenceBinding.model_validate(
            {key: evidence[key] for key in EvidenceBinding.model_fields}
        )
    )
    try:
        proposal = register_control_site(
            site_bridge,
            SiteResearchHandoff.model_validate(
                {
                    "candidates": [
                        {
                            "name": "preferred mapped patch",
                            "hotspot_label_seq_ids": [1, 2, 3],
                            "rationale": "First control-model choice within mapped structure.",
                        },
                        {
                            "name": "mapped alternative",
                            "hotspot_label_seq_ids": [4, 5, 6],
                            "rationale": "Second control-model choice retained for comparison.",
                        },
                    ],
                    "decision_questions": [],
                    "contradiction_search_query_ids": [],
                    "stopping_reason": "Synthetic direct-control evidence packet is complete.",
                    "unresolved_questions": ["Binding remains experimentally untested."],
                }
            ),
            execution_id,
        )
    finally:
        SITE_EVIDENCE.reset(token)

    assert proposal["proposal"]["portfolio"][0]["rank"] == "A"
    assert proposal["proposal"]["portfolio"][1]["rank"] == "B"
    decision = site_bridge.thread_latest("site-decision")
    dossier = site_bridge.thread_latest("site-evidence-dossier")
    assert decision["execution_id"] == execution_id
    assert decision["dossier_ref"] == dossier["ref"]
