"""Global scientific visibility and capacity controls, using explicitly synthetic facts."""

import json
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage

from easydesign.agent.contracts import AgentBoundaryError
from easydesign.agent.phase4_ranking import (
    ScaleRankingOpinion,
    compact_selection_packet,
    select_native_panel,
    validate_ranking,
)
from easydesign.agent.session_store import SessionStore, compact
from tests.agent_support import scripted_config


def ranking_config():
    config = scripted_config()
    return config.model_copy(
        update={"default": config.default.model_copy(update={"max_output_tokens": 8192})}
    )


def packet_for(count=60):
    alphabet = "ACDEFGHIKLMNPQRSTVWY"
    facts = {}
    for i in range(count):
        cid = f"candidate-{i:032d}"
        facts[cid] = {
            "strategy_id": f"arm-{i % 3}-scaffold-a",
            "sequence": "ACDF" + alphabet[i % 20] + alphabet[(i // 20) % 20],
            "native_profile_ref": f"profile-{i % 3}",
            "native_pass": True,
            "metrics": {"group_0": [0.5 + i / count, 0.5, 0.4, 0.4, 100, 1]},
            "development_rank": i + 1,
            "independent_prediction_status": "not-requested",
            "independent_metrics": {},
            "risks": ["Synthetic metrics; no biological conclusion."],
            "uncertainties": ["Whole VHH function and experimental binding unknown."],
            "full_dossier_ref": f"{i:064x}",
        }
    # Previously invisible beyond the RMSD Top30; all other scientific dimensions improve.
    winner = list(facts)[-1]
    facts[winner]["metrics"]["group_0"] = [1.5, 0.8, 0.95, 0.95, 800, 5]
    return {
        "version": "native-final-selection-view-v1",
        "evidence_id": "synthetic-evidence",
        "global_pool_sha256": "a" * 64,
        "facts": facts,
        "requested_primary_count": 1,
        "requested_backup_count": 2,
        "metric_columns": {
            "group_0": [
                "bb_rmsd_design",
                "bb_target_aligned_rmsd_design",
                "design_to_target_iptm",
                "hotspot_contact_fraction",
                "delta_sasa_refolded",
                "plip_hbonds_refolded",
            ]
        },
        "native_profiles": {f"profile-{i}": {"rules": [], "scope": "synthetic"} for i in range(3)},
        "user_goal": "Synthetic comparison only, no experimental authority.",
    }, winner


def decode(view):
    return {
        row[0]: {
            key: view["value_tables"][key][index]
            for key, index in zip(view["candidate_columns"][1:], row[1:], strict=True)
        }
        for row in view["candidate_matrix"]
    }


class Scientist:
    """A scripted scientific opinion tests reachability, not real biological ranking accuracy."""

    def __init__(self, winner, malformed=False, interrupt_at=None):
        self.winner, self.malformed, self.interrupt_at = winner, malformed, interrupt_at
        self.calls = []

    def bind_tools(self, tools, **kwargs):
        self.schema = tools[0]
        return self

    async def ainvoke(self, messages):
        view = json.loads(messages[-1].content)
        if self.interrupt_at == len(self.calls):
            raise RuntimeError("synthetic process interruption")
        self.calls.append((self.schema.__name__, view))
        ids = list(decode(view))
        order = ([self.winner] if self.winner in ids else []) + [i for i in ids if i != self.winner]
        if self.schema is ScaleRankingOpinion:
            output = dict(
                candidate_order=order,
                advance_candidate_ids=order[: view["advance_count"]],
                tradeoff_candidate_ids=[],
                rationale=["Retain the interface tradeoff."],
            )
        else:
            output = dict(
                primary_candidate_ids=order[:1],
                backup_candidate_ids=order[1:3],
                selection_rationale=["Interface evidence outweighs slightly worse RMSD."],
                major_risks=["Synthetic evidence only."],
                diversity_coverage=["Distinct synthetic sequences."],
                unresolved_questions=["No experimental evidence."],
            )
        if self.malformed:
            self.malformed = False
            key = (
                "candidate_order" if self.schema is ScaleRankingOpinion else "primary_candidate_ids"
            )
            output[key][0] = "foreign-candidate"
        assert len(compact(output)) // 2 < 8192
        return AIMessage(
            content="", tool_calls=[dict(name=self.schema.__name__, args=output, id="opinion")]
        )


def bridge_for(tmp_path):
    project = tmp_path / "session"
    project.mkdir()
    store = SessionStore(project)
    store.thread("ranking", "synthetic", "synthetic ranking only")
    execution = store.begin_execution("ranking", "validation")["execution_id"]
    return SimpleNamespace(store=store, thread="ranking"), execution


async def invoke(bridge, execution, model, packet, config=None, still_current=lambda: None):
    return await select_native_panel(
        bridge=bridge,
        model=model,
        config=config or ranking_config(),
        execution_id=execution,
        packet=packet,
        prompt="Choose the strongest primary and two backups using all evidence.",
        validate=lambda _: None,
        still_current=still_current,
    )


def test_compaction_is_lossless_for_metrics_profiles_missing_values_and_provenance():
    packet, _ = packet_for()
    cid = next(iter(packet["facts"]))
    packet["facts"][cid]["metrics"]["group_0"][2] = None
    view = compact_selection_packet(packet, tuple(packet["facts"]))
    assert decode(view) == packet["facts"]
    assert view["native_profiles"] == packet["native_profiles"]
    assert len(compact(view)) < len(compact(packet))


@pytest.mark.asyncio
@pytest.mark.parametrize("malformed", [False, True])
async def test_all_sixty_pass_compete_and_low_rmsd_rank_candidate_can_win(tmp_path, malformed):
    packet, winner = packet_for()
    bridge, execution = bridge_for(tmp_path)
    model = Scientist(winner, malformed)
    try:
        opinion, audit = await invoke(bridge, execution, model, packet)
        assert opinion.primary_candidate_ids == [winner]
        assert audit["mode"] == "global-direct"
        assert set(audit["reviewed_candidate_ids"]) == set(packet["facts"])
        assert len(model.calls) == 1 + malformed
        assert all(len(view["candidate_matrix"]) == 60 for _, view in model.calls)
        contexts = [
            e["payload"] for e in bridge.store.events(bridge.thread) if e["kind"] == "model-context"
        ]
        assert contexts[0]["input_chars_with_schemas"] < 60_000
        assert all(e["input_chars_with_schemas"] < 70_000 for e in contexts)
    finally:
        bridge.store.close()


@pytest.mark.asyncio
async def test_size_driven_hierarchy_covers_all_candidates_and_retains_tradeoff(tmp_path):
    packet, winner = packet_for(200)
    bridge, execution = bridge_for(tmp_path)
    model = Scientist(winner, malformed=True)
    config = ranking_config().model_copy(update={"max_input_chars": 24000})
    try:
        opinion, audit = await invoke(bridge, execution, model, packet, config)
        assert opinion.primary_candidate_ids == [winner]
        assert audit["mode"] == "hierarchical"
        assert len(audit["reviewed_candidate_ids"]) == 200
        assert audit["steps"] and "approximate" in audit["limitation"]
        assert all(len(set(step["input_ids"])) == len(step["input_ids"]) for step in audit["steps"])
        for _, view in model.calls:
            assert len(compact(view)) < 24000
        contexts = [
            e["payload"] for e in bridge.store.events(bridge.thread) if e["kind"] == "model-context"
        ]
        assert all(c["input_chars_with_schemas"] < config.hard_input_chars for c in contexts)
    finally:
        bridge.store.close()


@pytest.mark.asyncio
async def test_restart_reuses_completed_comparisons_and_changed_evidence_invalidates(tmp_path):
    packet, winner = packet_for(100)
    bridge, execution = bridge_for(tmp_path)
    config = ranking_config().model_copy(update={"max_input_chars": 22000})
    interrupted = Scientist(winner, interrupt_at=1)
    try:
        with pytest.raises(RuntimeError, match="interruption"):
            await invoke(bridge, execution, interrupted, packet, config)
        first_ids = interrupted.calls[0][1]["candidate_matrix"]
        recovered = Scientist(winner)
        new_execution = bridge.store.begin_execution(bridge.thread, "restart")["execution_id"]
        opinion, audit = await invoke(bridge, new_execution, recovered, packet, config)
        assert opinion.primary_candidate_ids == [winner]
        assert all(view["candidate_matrix"] != first_ids for _, view in recovered.calls)
        assert len(audit["reviewed_candidate_ids"]) == 100
        changed = {**packet, "evidence_id": "changed-evidence"}
        fresh = Scientist(winner)
        changed_execution = bridge.store.begin_execution(bridge.thread, "changed")["execution_id"]
        await invoke(bridge, changed_execution, fresh, changed, config)
        assert fresh.calls[0][1]["candidate_matrix"] == first_ids
    finally:
        bridge.store.close()


def test_ranking_rejects_missing_foreign_or_silently_discarded_tradeoff():
    good = dict(
        candidate_order=["a", "b", "c"],
        advance_candidate_ids=["a", "c"],
        tradeoff_candidate_ids=["c"],
        rationale=["Complementary evidence."],
    )
    validate_ranking(ScaleRankingOpinion(**good), ("a", "b", "c"), 2)
    for patch in [
        {"candidate_order": ["a", "b"]},
        {"candidate_order": ["a", "b", "foreign"]},
        {"tradeoff_candidate_ids": ["b"]},
        {"advance_candidate_ids": ["b", "c"]},
    ]:
        with pytest.raises(AgentBoundaryError):
            validate_ranking(ScaleRankingOpinion(**{**good, **patch}), ("a", "b", "c"), 2)


@pytest.mark.asyncio
async def test_hard_context_limit_never_silently_truncates_or_falls_back(tmp_path):
    packet, winner = packet_for()
    packet["user_goal"] = "x" * 120000
    bridge, execution = bridge_for(tmp_path)
    model = Scientist(winner)
    try:
        with pytest.raises(AgentBoundaryError, match="single candidate"):
            await invoke(bridge, execution, model, packet)
        assert not model.calls
    finally:
        bridge.store.close()


def test_native_publication_keeps_all_pass_even_with_requested_top30(tmp_path):
    from easydesign.agent.phase34_contracts import ScientificContextReferences
    from easydesign.agent.phase34_scale import publish_review_inputs
    from easydesign.core import canonical_model_sha256
    from tests.unit.agent.test_phase4_native import native_fixture, observations, pool_for

    measured, campaign, _, _ = native_fixture(tmp_path, count=31)
    context = ScientificContextReferences(
        target_identity="synthetic",
        target_snapshot_sha256="a" * 64,
        site_intent_sha256="b" * 64,
        design_specification_sha256="c" * 64,
        pilot_dossier_sha256="d" * 64,
        evidence_refs=("target", "site", "design", "pilot"),
    )
    pilot = SimpleNamespace(
        model_dump=lambda **_: {"synthetic": "publication boundary only"},
        upstream_fixture=SimpleNamespace(
            target_identity=context.target_identity,
            target_bundle_sha256=context.target_snapshot_sha256,
            site_intent_sha256=context.site_intent_sha256,
            strategy_sha256=context.design_specification_sha256,
        ),
        diagnosis=SimpleNamespace(design_arms=[]),
    )
    sha = canonical_model_sha256(pilot)
    context = context.model_copy(update={"pilot_dossier_sha256": sha})
    authority = campaign.promotion_authority.model_copy(update={"pilot_dossier_sha256": sha})
    campaign = campaign.model_copy(update={"promotion_authority": authority})
    pool = pool_for(campaign, observations(tmp_path, measured, campaign))
    published = {}
    bridge = SimpleNamespace(
        project_id="synthetic",
        thread="synthetic",
        current_pilot_dossier=lambda: pilot,
        project_latest=lambda _: {"ref": "synthetic-authority"},
        document=lambda _: authority.model_dump(mode="json"),
        publish_contract=lambda **kw: published.update({kw["kind"]: kw["contract"]}),
        store=SimpleNamespace(event=lambda *args: None),
        controller=SimpleNamespace(list=lambda **kw: []),
    )
    ids = set(pool.global_ranking_candidate_ids)
    sequences = {
        c.lineage.candidate_id: c.native_evidence.metrics["designed_chain_sequence"]
        for c in pool.candidates
    }
    publish_review_inputs(
        bridge,
        pool,
        context=context,
        sequences=sequences,
        concerns={cid: ("synthetic",) for cid in ids},
        uncertainties={cid: ("unknown biology",) for cid in ids},
        provenance={cid: ("synthetic",) for cid in ids},
        primary_count=1,
        backup_count=2,
        review_count=30,
    )
    dossiers = published["phase34-final-selection-input"].candidate_dossiers
    assert len(dossiers) == len(ids) == 61
    assert {d.candidate.lineage.candidate_id for d in dossiers} == ids
    assert len({d.sequence for d in dossiers}) < len(dossiers)  # duplicate observations preserved
