"""Capacity fixtures exercise engineering scale, never claim new scientific results."""

import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.messages.utils import count_tokens_approximately
from langchain_core.utils.function_calling import convert_to_openai_tool

from easydesign.agent.context_policy import context_usage
from easydesign.agent.contracts import AgentBoundaryError
from easydesign.agent.phase3_capacity import (
    CONTEXT_METRICS,
    PROVENANCE_FIELDS,
    candidate_reference_map,
    ranking_decision_view,
    ranking_repair_context,
    ranking_submission_model,
)
from easydesign.agent.phase3_native import native_profile, project_native_measurement
from easydesign.agent.phase3_ranking import METRIC_DIRECTIONS, compact_native_packet
from easydesign.agent.phase34_model import (
    StructuredOpinionUnavailable,
    _ranking_schema,
    structured_opinion,
)
from easydesign.agent.phase34_opinions import PilotDiagnosisOpinion
from easydesign.agent.phase34_plan import PilotArmIntent
from easydesign.agent.phase34_science import bind_pilot_opinion
from easydesign.agent.session_store import SessionStore, compact, identity
from easydesign.core import ArtifactRef, canonical_model_sha256
from tests.agent_support import scripted_config
from tests.unit.agent.test_phase3_native_ranking import population

ROOT = Path(__file__).parents[3]


def capacity_population(tmp_path, arm_count=3, passes=20):
    """Realistic seven-scaffold context; varied synthetic rows avoid dedup-only success."""
    fixture = json.loads((ROOT / "tests/fixtures/phase3-ranking-capacity-context.json").read_text())
    counts = tuple(passes // 7 + (i < passes % 7) for i in range(7))
    measured, _, candidates, profile = population(
        tmp_path,
        tuple((f"arm-{a + 1}", counts) for a in range(arm_count)),
        per_strategy=max(counts),
    )
    arms = []
    for a in range(arm_count):
        source = deepcopy(fixture["design_arms"][a % 2])
        arm_id = f"arm-{a + 1}"
        source.update(arm_id=arm_id, hypothesis="Synthetic capacity case, not a biological result")
        for s, record in enumerate(source["compiled_settings"]):
            record.update(strategy_id=f"{arm_id}-scaffold-{s}", region_id=arm_id)
        source["strategy_ids"] = [s["strategy_id"] for s in source["compiled_settings"]]
        arms.append(PilotArmIntent.model_validate(source))
    extras, rows, profiles = {}, [], {}
    for i, c in enumerate(candidates):
        sample = fixture["native_examples"][i % 3]
        metrics = {
            k: v
            for k, v in sample["metrics"].items()
            if not (k.startswith("pass_") and k.endswith("_filter"))
        }
        metrics.update(c.metrics)
        for k in METRIC_DIRECTIONS:
            value = sample["metrics"].get(k)
            if isinstance(value, float):
                metrics[k] = round(value + (i + 1) / 100000, 5)
        metrics["designed_sequence"] = sample["metrics"]["designed_sequence"] + "A" * (i % 7)
        metrics["designed_chain_sequence"] = sample["metrics"]["designed_chain_sequence"] + "A" * (
            i % 7
        )
        rows.append(c.model_copy(update={"metrics": metrics}))
        extras[c.candidate_id] = {
            k: (round(v + (i + 1) / 100000, 5) if isinstance(v, float) else v)
            for k, v in sample["additional_metrics"].items()
        }
        if c.strategy_id not in profiles:
            path = tmp_path / "attempts" / c.strategy_id / "config/filtering.yaml"
            path.parent.mkdir(parents=True)
            path.write_text(f"# synthetic independent attempt {c.strategy_id}\n")
            ref = ArtifactRef.from_file(
                run_root=tmp_path,
                relative_path=path.relative_to(tmp_path).as_posix(),
                artifact_id=c.strategy_id + "-profile",
                role="synthetic-fixture",
                file_format="yaml",
            )
            profiles[c.strategy_id] = native_profile(profile.configuration, ref)
    measured = project_native_measurement(
        candidates=tuple(rows),
        profiles=profiles,
        planned={d.strategy_id: d.planned_candidates for d in measured.arms},
        source_sha256="a" * 64,
        execution=measured.execution,
        additional_metrics=extras,
    )
    packet = compact_native_packet(measured, tuple(arms))
    packet.update(
        evidence_refs=list(fixture["design_arms"][0]["evidence_refs"]),
        user_goal="Synthetic capacity validation only; rank all PASS, no compute or approval.",
        run_id="synthetic-capacity",
        gate_type="pilot-promotion",
    )
    packet["evidence_id"] = packet["request_identity"] = identity(packet)
    return measured, tuple(arms), packet


def prompt():
    root = ROOT / "src/easydesign/agent/skills/pilot-diagnosis"
    return (
        (root / "SKILL.md").read_text()
        + "\n"
        + (root / "references/boltzgen-pilot-ranking.md").read_text()
    )


def capacity_config():
    config = scripted_config()
    return config.model_copy(
        update={"default": config.default.model_copy(update={"max_output_tokens": 8192})}
    )


def opinion_for_capacity(measured, arms):
    ids = [c.candidate_id for c in measured.native_evidence.candidates if c.native_pass]
    support = [next(i for i in ids if i.startswith(a.arm_id + "-")) for a in arms]
    detailed = list(dict.fromkeys([*ids[:3], *support]))
    selected = [a.strategy_ids[0] for a in arms]
    return PilotDiagnosisOpinion(
        key_observations=["Synthetic populations test capacity only."],
        arm_findings=[
            dict(
                arm_id=a.arm_id,
                hypothesis_support="UNRESOLVED",
                observations=["Synthetic measurements"],
                interpretation="Capacity fixture",
                alternative_explanation="Not a biological result",
            )
            for a in arms
        ],
        arm_comparisons=["All Arms retained"],
        operational_confounders=["Synthetic fixture"],
        uncertainty=["Biology untested"],
        next_discriminating_experiment=["Scientist review"],
        recommended_action="PROMOTE_TO_SCALE",
        selected_strategy_ids=selected,
        scale_allocations={s: 10 for s in selected},
        supporting_candidate_ids=support,
        rationale="Bounded proposed mix only; no Scale authorization.",
        candidate_order=ids,
        candidate_rankings=[
            dict(
                candidate_id=i,
                rationale="Relative pose evidence",
                risks=["Unverified biology"],
                metric_refs=["bb_rmsd_design"],
            )
            for i in detailed
        ],
        ranked_arm_ids=[a.arm_id for a in arms],
    )


def merge(common, delta):
    out = deepcopy(common)
    for k, v in delta.items():
        out[k] = (
            merge(out[k], v)
            if isinstance(v, dict) and isinstance(out.get(k), dict)
            else deepcopy(v)
        )
    return out


def test_sixty_pass_projection_keeps_every_id_value_context_and_source(tmp_path):
    measured, arms, packet = capacity_population(tmp_path)
    before = compact(packet), canonical_model_sha256(measured)
    view = ranking_decision_view(packet)
    assert view["candidate_count"] == 60 and len(view["arms"]) == 3
    native = {c.candidate_id: c for c in measured.native_evidence.candidates if c.native_pass}
    references = candidate_reference_map(list(native))
    assert {references[r[0]] for r in view["candidates"]} == set(native)
    for row in view["candidates"]:
        d = dict(zip(view["candidate_columns"], row, strict=True))
        metric_view = {**view["candidate_common_metrics"], **d}
        for key, table in view["metric_value_tables"].items():
            if metric_view[key] is not None:
                metric_view[key] = table[metric_view[key]]
        c = native[references[row[0]]]
        original = {**c.metrics, **c.additional_metrics}
        for key in [*METRIC_DIRECTIONS, *CONTEXT_METRICS]:
            assert metric_view[key] == original.get(key)
        assert sorted(packet["filter_profiles"])[d["profile_index"]] == c.profile_sha256
        assert view["filter_profile_binding"] == identity(sorted(packet["filter_profiles"]))
    for a in arms:
        restored = merge(view["shared_design_intent"], view["arms"][a.arm_id]["design_delta"])
        compiled = restored["compiled_settings"]
        recovered = [
            merge(merge(view["shared_compiled_settings"], compiled["arm_common"]), s)
            for s in compiled["strategies"]
        ]
        assert recovered == [
            {k: v for k, v in s.items() if k not in PROVENANCE_FIELDS}
            for s in a.model_dump(mode="json")["compiled_settings"]
        ]
        assert restored["hypothesis"] == a.hypothesis
        context_id = restored["target_context"]["shared_context_id"]
        context = deepcopy(view["shared_target_contexts"][context_id])
        context["gpcr_exclusions"].pop("source_details_ref")
        expected = deepcopy(a.target_context)
        expected["gpcr_exclusions"].pop("sources")
        expected["gpcr_exclusions"].pop("source_refs")
        assert context == expected
    assert (compact(packet), canonical_model_sha256(measured)) == before
    assert view["source_packet_sha256"] == identity(packet)


def input_usage(view):
    return context_usage(
        SimpleNamespace(),
        capacity_config(),
        "pilot-diagnosis",
        [SystemMessage(content=prompt()), HumanMessage(content=compact(view))],
        len(compact(convert_to_openai_tool(_ranking_schema(PilotDiagnosisOpinion, view)))),
    )


def test_sixty_and_two_hundred_pass_capacity_with_realistic_background(tmp_path):
    measurements = []
    for arms, passes in [(3, 20), (5, 40)]:
        root = tmp_path / str(arms)
        root.mkdir()
        measured, intents, packet = capacity_population(root, arms, passes)
        view = ranking_decision_view(packet)
        usage = input_usage(view)
        assert len(view["candidates"]) == arms * passes
        assert len(view["arms"]) == arms
        assert usage["input_chars_with_schemas"] < (60000 if arms == 3 else 100000)
        measurements.append(usage["input_chars_with_schemas"])
        if arms == 3:
            opinion = opinion_for_capacity(measured, intents)
            diagnosis, proposal = bind_pilot_opinion(
                measured, intents, opinion, evidence_refs=("synthetic",)
            )
            assert len(diagnosis.ranked_pilot["candidate_leaderboard"]) == 60
            assert proposal.requested_scale_candidates == 30
            assert len(proposal.production_strategy_allocations) == 3
            assert (
                count_tokens_approximately(
                    [AIMessage(content=compact(opinion.model_dump(mode="json")))]
                )
                < 8192
            )
    # More candidates must not multiply shared background with every row.
    assert measurements[1] < measurements[0] * 200 / 60


class CapacityResponses:
    def __init__(self, responses):
        self.responses, self.calls, self.tools = list(responses), [], []

    def bind_tools(self, tools, **kwargs):
        self.tools.append(tools[0])
        assert tools[0].__name__ == "PilotDiagnosisOpinion"
        assert kwargs["tool_choice"] == "PilotDiagnosisOpinion"
        return self

    async def ainvoke(self, messages):
        self.calls.append(messages)
        return AIMessage(
            content="",
            tool_calls=[
                dict(
                    name="PilotDiagnosisOpinion",
                    args=self.responses.pop(0),
                    id="result",
                )
            ],
        )


async def run_capacity(runtime, model, measured, arms, packet):
    return await structured_opinion(
        bridge=runtime,
        model=model,
        config=capacity_config(),
        execution_id=runtime.execution_id,
        role="pilot-diagnosis",
        schema=PilotDiagnosisOpinion,
        packet=ranking_decision_view(packet),
        prompt=prompt(),
        delta_repair=True,
        validate=lambda o: bind_pilot_opinion(measured, arms, o, evidence_refs=("synthetic",)),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("repair", [False, True])
async def test_sixty_pass_first_call_or_delta_repair_and_durable_restart(tmp_path, repair):
    measured, arms, packet = capacity_population(tmp_path)
    raw = opinion_for_capacity(measured, arms).model_dump(mode="json")
    bad = {**raw, "candidate_order": ["foreign-candidate", *raw["candidate_order"][1:]]}
    model = CapacityResponses(
        [bad, {"candidate_order": raw["candidate_order"]}] if repair else [raw]
    )
    (tmp_path / "session").mkdir()
    store = SessionStore(tmp_path / "session")
    store.thread("capacity", "fixture", "synthetic")
    execution = store.begin_execution("capacity", "synthetic")
    runtime = SimpleNamespace(
        store=store, thread="capacity", execution_id=execution["execution_id"]
    )
    try:
        result = await run_capacity(runtime, model, measured, arms, packet)
        assert result.model_dump(mode="json") == raw
        assert len(model.calls) == (2 if repair else 1)
        events = store.events("capacity")
        sizes = [
            e["payload"]["input_chars_with_schemas"] for e in events if e["kind"] == "model-context"
        ]
        assert sizes[0] < 60000 and max(sizes) < 70000
        if repair:
            second = json.loads(model.calls[1][-1].content)
            assert "previous_unvalidated_submission" not in second
            assert (
                second["delta_repair"]["previous_unvalidated_fields"]["candidate_order"][0]
                == "foreign-candidate"
            )
            attempts = [e["payload"] for e in events if e["kind"] == "phase34-model-attempt"]
            assert attempts[-1]["wire_submission"] == {"candidate_order": raw["candidate_order"]}
            assert attempts[-1]["submission"] == raw
            assert result.candidate_rankings[0].risks == ["Unverified biology"]
    finally:
        store.close()
    # Reopen the persistent ledger, not just reuse an in-memory result.
    store = SessionStore(tmp_path / "session")
    runtime.store = store
    try:
        resumed = await run_capacity(runtime, CapacityResponses([]), measured, arms, packet)
        assert resumed == result
        assert sum(e["kind"] == "model-call" for e in store.events("capacity")) == len(model.calls)
    finally:
        store.close()


@pytest.mark.parametrize(
    "mutation", ["omit", "duplicate", "unknown", "missing-detail", "unknown-metric"]
)
def test_compact_output_cannot_lose_or_invent_scientific_population(tmp_path, mutation):
    measured, arms, _ = capacity_population(tmp_path)
    raw = opinion_for_capacity(measured, arms).model_dump(mode="json")
    if mutation == "omit":
        raw["candidate_order"].pop()
    if mutation == "duplicate":
        raw["candidate_order"][-1] = raw["candidate_order"][0]
    if mutation == "unknown":
        raw["candidate_order"][-1] = "foreign-candidate"
    if mutation == "missing-detail":
        raw["candidate_rankings"].pop(0)
    if mutation == "unknown-metric":
        raw["candidate_rankings"][0]["metric_refs"] = ["invented_affinity"]
    with pytest.raises(AgentBoundaryError):
        bind_pilot_opinion(
            measured,
            arms,
            PilotDiagnosisOpinion.model_validate(raw),
            evidence_refs=("synthetic",),
        )


@pytest.mark.asyncio
async def test_delta_repair_does_not_bypass_validation_or_reset_attempt_budget(
    tmp_path,
):
    measured, arms, packet = capacity_population(tmp_path)
    raw = opinion_for_capacity(measured, arms).model_dump(mode="json")
    raw["candidate_order"][0] = "foreign-candidate"
    # Malformed unbounded prose must not make the repair input unbounded.
    raw["rationale"] = "oversized " * 100000
    model = CapacityResponses([raw, {"rationale": "Fixed length only"}, {}])
    (tmp_path / "session").mkdir()
    store = SessionStore(tmp_path / "session")
    store.thread("capacity", "fixture", "synthetic")
    execution = store.begin_execution("capacity", "synthetic")
    runtime = SimpleNamespace(
        store=store, thread="capacity", execution_id=execution["execution_id"]
    )
    try:
        with pytest.raises(StructuredOpinionUnavailable):
            await run_capacity(runtime, model, measured, arms, packet)
        with pytest.raises(StructuredOpinionUnavailable):
            await run_capacity(runtime, CapacityResponses([]), measured, arms, packet)
        assert len(model.calls) == 3
        assert all(len(m[-1].content) < 70000 for m in model.calls)
        ledger = [
            e["payload"] for e in store.events("capacity") if e["kind"] == "phase34-model-attempt"
        ]
        assert ledger[0]["submission"]["rationale"] == raw["rationale"]
    finally:
        store.close()


def test_short_references_restore_every_canonical_candidate_and_support(tmp_path):
    measured, arms, packet = capacity_population(tmp_path)
    opinion = opinion_for_capacity(measured, arms)
    refs = candidate_reference_map(opinion.candidate_order)
    inverse = {v: k for k, v in refs.items()}
    encoded = opinion.model_copy(
        update={
            "candidate_order": [inverse[i] for i in opinion.candidate_order],
            "supporting_candidate_ids": [inverse[i] for i in opinion.supporting_candidate_ids],
            "candidate_rankings": [
                r.model_copy(update={"candidate_id": inverse[r.candidate_id]})
                for r in opinion.candidate_rankings
            ],
        }
    )
    full = bind_pilot_opinion(measured, arms, opinion, evidence_refs=("synthetic",))
    restored = bind_pilot_opinion(measured, arms, encoded, evidence_refs=("synthetic",))
    assert restored == full
    assert {r[0] for r in ranking_decision_view(packet)["candidates"]} == set(refs)
    assert set(candidate_reference_map(["c0001", "c0002"])) == {
        "view-c0001",
        "view-c0002",
    }


@pytest.mark.parametrize("incomplete", [False, True])
def test_projection_preserves_zero_pass_and_incomplete_modes(tmp_path, incomplete):
    measured, arms, _, _ = population(tmp_path, (("arm-a", (0,)),), incomplete=incomplete)
    packet = compact_native_packet(measured, arms)
    view = ranking_decision_view(packet)
    assert view["candidates"] == []
    assert view["arms"]["arm-a"]["mode"] == ("OPERATIONAL_INCOMPLETE" if incomplete else "RECOVERY")
    assert view["arms"]["arm-a"]["failure_dossier"] == packet["facts"]["arm-a"]["failure_dossier"]


def test_native_tool_first_uses_same_deepseek_without_mutating_shared_client():
    class Copyable:
        def __init__(self):
            self.thinking = {"type": "enabled", "budget_tokens": 1024}
            self.output_config = {"effort": "low"}
            self.max_tokens = 8192
            self.model = "deepseek-v4-pro"

        def model_copy(self, update):
            copied = deepcopy(self)
            copied.__dict__.update(update)
            return copied

    config = capacity_config()
    config = config.model_copy(
        update={
            "default": config.default.model_copy(
                update={
                    "provider": "deepseek",
                    "model": "deepseek-v4-pro",
                    "reasoning_effort": "low",
                }
            )
        }
    )
    original = Copyable()
    selected = ranking_submission_model(original, config)
    assert selected.model == original.model and selected.max_tokens == 8192
    assert selected.thinking == {"type": "disabled"} and selected.output_config == {}
    assert original.thinking["type"] == "enabled" and original.output_config == {"effort": "low"}
    assert ranking_submission_model(original, capacity_config()) is original


def test_native_wire_requires_all_fields_and_exact_population_size(tmp_path):
    measured, arms, packet = capacity_population(tmp_path)
    raw = opinion_for_capacity(measured, arms).model_dump(mode="json")
    wire = _ranking_schema(PilotDiagnosisOpinion, ranking_decision_view(packet))
    assert set(wire.model_json_schema()["required"]) == set(PilotDiagnosisOpinion.model_fields)
    wire.model_validate(raw)
    from pydantic import ValidationError

    missing = dict(raw)
    missing.pop("ranked_arm_ids")
    with pytest.raises(ValidationError):
        wire.model_validate(missing)
    with pytest.raises(ValidationError):
        wire.model_validate({**raw, "candidate_order": raw["candidate_order"][:-1]})
    # Persisted legacy opinions still accept their historical defaults.
    PilotDiagnosisOpinion.model_validate(missing)


def test_repair_reports_all_malformed_rows_and_correlated_required_notes():
    # Regression: real provider returned two malformed detail rows after valid notes.
    errors = [
        {"loc": ("candidate_rankings", row, field), "msg": "Field required", "type": "missing"}
        for row in (5, 6)
        for field in ("candidate_id", "rationale", "risks", "metric_refs")
    ]
    errors.append({"loc": ("key_observations",), "msg": "At most 5 items", "type": "too_long"})
    recovery = ranking_repair_context(
        {"candidate_order": ["c1", "c2", "c3"], "supporting_candidate_ids": ["c6"]}, errors
    )
    assert recovery["required_detailed_candidate_ids"] == ["c1", "c2", "c3", "c6"]
    assert len(recovery["errors"]) == 2
    assert "candidate_rankings.6.metric_refs" in recovery["errors"][0]["fields"]
    assert recovery["errors"][1]["fields"] == ["key_observations"]
