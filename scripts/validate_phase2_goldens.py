"""Real-model/source Phase 2 acceptance; scripted gate responses are validation fixtures.
No generation or prediction is authorized by this runner. All scientific jobs must be <= Stage 02.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import traceback
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import yaml

from easydesign.agent.cli import run_session
from easydesign.agent.design import DesignBridge
from easydesign.agent.evidence_corpus import EvidenceCorpus
from easydesign.agent.models import PHASE2_MODEL_CALL_LIMIT, ModelConfig, create_models
from easydesign.agent.native_strategy import import_native
from easydesign.agent.phase2 import Phase2Bridge
from easydesign.agent.session_store import SessionStore
from easydesign.orchestration.profile import initialize_runtime_profile
from easydesign.orchestration.research import initialize_research_project
from easydesign.workspace_context import WorkspaceContext
from tests.agent_golden_support import approved_identity, golden_truth
from tests.agent_phase2_support import configure_live_validation
from tests.unit.agent.test_phase22_native import expert_input

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(os.environ["EASYDESIGN_GOLDEN_SOURCE_ROOT"]).resolve()
STAMP = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
OUT = ROOT / "runtime/tmp/autonomous-v3-20260912" / f"phase2-goldens-{STAMP}"
ACTOR = "scripted-autonomous-validation-actor-not-biological-approval"
APPROVED_TARGET = os.environ.get("EASYDESIGN_GOLDEN_APPROVED_TARGET")
UNREVIEWED_SITE = os.environ.get("EASYDESIGN_GOLDEN_UNREVIEWED_SITE")
CASE_SCOPE = os.environ.get("EASYDESIGN_GOLDEN_CASE_SCOPE", "all")
assert CASE_SCOPE in {"all", "soluble", "gpcr"}
GOALS = {
    "soluble": (
        "Develop an inhibitory VHH against hen egg-white lysozyme using 1MEL auth chain L. "
        "Desired effect: reduce purified enzymatic "
        "activity; avoid apparent inhibition due to "
        "unfolding "
        "or assay interference. Before prepare_target, "
        "retrieve UniProt P00698 and propose it as the "
        "canonical reference with "
        "propose_canonical_identity. Reuse old "
        "deterministic mapping, expose "
        "precursor versus mature construct differences, and ask Gate 1 for my chain L choice. "
        "After my Gate 1 response, actively research the 1MEL primary publication PMID 8784355 and "
        "official structure/sequence evidence relevant to inhibitory cleft access. Compare "
        "literature-derived and scan-derived site hypotheses using the approved residue mapping; "
        "do not convert numbering by assumption. Select "
        "sources before acquisition; retrieve focused "
        "passages, batch independent queries, and retain contradictions/access limits. Propose a "
        "mechanistic site with an assay/falsifier and "
        "independent Judge review. Present Gate 2, then "
        "stop before approval or compute. This is a migration validation, not successful binding."
    ),
    "gpcr": (
        "Develop an extracellularly delivered VHH to modulate beta2-adrenoceptor signaling using "
        "3P0G auth chain A; avoid constitutive activation and expression/trafficking artifacts. "
        "Before prepare_target, retrieve UniProt P07550 "
        "and propose it as canonical reference using "
        "propose_canonical_identity. The deposited construct may contain fusion/sequence changes; "
        "reuse deterministic mapping and ask Gate 1 for "
        "my mapped chain A choice. After my response, "
        "actively research PMID 21228869, RCSB 3P0G and "
        "relevant UniProt/GPCRdb adrb2_human context "
        "(pdb_id=3P0G); analyze receptor topology and source chain A before proposing access. "
        "An intracellular nanobody interface is not automatically accessible extracellularly. "
        "Compare literature-derived and scan-derived "
        "sites, only on approved labels. Select sources "
        "before acquisition; use focused retrieval, batch independent queries, and retain relevant "
        "counterevidence. Give a mechanistic Site proposal with clear limitations, assay/falsifier "
        "and independent Judge review. Present Gate 2 and stop before approval or compute. This "
        "validates migration, not physiological efficacy."
    ),
}


def save(path, value, secrets):
    text = json.dumps(value, ensure_ascii=False, indent=2, default=str)
    for secret in secrets:
        if secret:
            text = text.replace(secret, "[REDACTED]")
    path.write_text(text)


def stats(bridge, *, source_threads=()):
    threads = list(dict.fromkeys([*source_threads, bridge.thread]))
    events = sorted(
        [dict(e, thread=t) for t in threads for e in bridge.store.events(t)], key=lambda e: e["seq"]
    )
    queries = [
        bridge.document(e["payload"]["ref"]) for e in events if e["kind"] == "evidence-research"
    ]
    docs = [
        d
        for d in EvidenceCorpus(bridge).documents()
        if d["binding_context"]["relation"] != "historical-target"
    ]
    contexts = [e["payload"] for e in events if e["kind"] == "model-context"]
    calls = [e["payload"] for e in events if e["kind"] == "model-call"]
    views = [bridge.document(e["payload"]["ref"]) for e in events if e["kind"] == "evidence-view"]
    search_queries = [
        q for q in queries if q.get("query", {}).get("operation", "").endswith("search")
    ]
    selection_events = [e["payload"] for e in events if e["kind"] == "evidence-selection"]
    selections = {}
    for event in selection_events:
        selections[(event["target_binding"], event["source_id"], event["need"])] = event[
            "selection"
        ]
    acquired_cards = [c for q in queries for c in q["cards"] if c.get("corpus_ref")]
    corpus_refs = {c["corpus_ref"]["sha256"]: c["corpus_ref"] for c in acquired_cards}
    raw_refs = {r["sha256"]: r for c in acquired_cards for r in c["source_refs"]}
    tool_events = [e["payload"] for e in events if e["kind"] == "tool"]
    specialist_tools = [e for e in tool_events if e["role"] != "coordinator"]
    return {
        "included_threads": threads,
        "search_queries": [q["query"] for q in search_queries],
        "search_query_count": len(search_queries),
        "selection_events": selection_events,
        "final_selection_counts_by_binding_source_need": dict(Counter(selections.values())),
        "deferred_sources": len(
            {e["source_id"] for e in selection_events if e["selection"] == "DEFERRED"}
        ),
        "excluded_sources": len(
            {e["source_id"] for e in selection_events if e["selection"] == "EXCLUDED"}
        ),
        "corpus_documents_all_bindings": len(corpus_refs),
        "corpus_chunks_all_bindings": sum(
            len(bridge.document(r)["chunks"]) for r in corpus_refs.values()
        ),
        "focused_retrieval_calls": len(views),
        "chunks_returned": sum(len(v["cards"]) for v in views),
        "evidence_cards_produced": len({c["card_id"] for v in views for c in v["cards"]}),
        "evidence_cards_passed_to_specialist": sum(
            e.get("focused_cards_in_model_result", 0) for e in specialist_tools
        ),
        "total_retrieved_raw_chars": sum(
            len(
                (bridge.project / r["relative_path"]).read_bytes().decode("utf-8", errors="replace")
            )
            for r in raw_refs.values()
        ),
        "total_chars_injected_into_specialist_tool_results": sum(
            e.get("model_result_chars") or 0 for e in specialist_tools
        ),
        "total_specialist_context_chars_over_model_calls": sum(
            c["context_chars"] for c in contexts if c["role"] != "coordinator"
        ),
        "total_specialist_tool_context_chars_over_model_calls": sum(
            c.get("tool_message_chars", 0) for c in contexts if c["role"] != "coordinator"
        ),
        "prerequisite_repairs": [
            e["payload"] for e in events if e["kind"] == "prerequisite-repair"
        ],
        "tool_argument_repairs": [
            e["payload"] for e in events if e["kind"] == "tool-argument-repair"
        ],
        "contract_repairs": [e["payload"] for e in events if e["kind"] == "contract-repair"],
        "consistency_findings": [
            e["payload"] for e in events if e["kind"] == "scientific-consistency-finding"
        ],
        "metric_definitions": {
            "raw_chars": "Unique retained source response contents, "
            "decoded UTF-8; not token billing.",
            "injected_chars": "Post-adapter tool result characters supplied to "
            "specialists, including skills; counts repeated "
            "deliveries.",
            "context_chars": "Actual per-call system/message working set; "
            "tool schemas recorded separately; repeated "
            "history counted each call.",
            "cards": "Unique produced focused passages; deliveries "
            "count post-adapter passage cards, including "
            "rereads. Acquisition receipts are not Evidence "
            "Cards.",
            "selection": "Counts retain binding/source/need distinctions; "
            "event timeline also retained.",
        },
        "search_result_count": sum(
            len(q["cards"])
            for q in queries
            if q.get("query", {}).get("operation", "").endswith("search")
        ),
        "selected_source_count": len(
            {
                e["payload"]["source_id"]
                for e in events
                if e["kind"] == "evidence-selection" and e["payload"]["selection"] == "SELECTED"
            }
        ),
        "full_sources_acquired": len(
            {
                r["sha256"]
                for q in queries
                for c in q["cards"]
                if c.get("corpus_ref")
                for r in c["source_refs"]
            }
        ),
        "source_bytes_retained": sum(
            {
                r["sha256"]: (bridge.project / r["relative_path"]).stat().st_size
                for q in queries
                for c in q["cards"]
                for r in c["source_refs"]
            }.values()
        ),
        "corpus_count_current_binding": len(docs),
        "chunk_count_current_binding": sum(c["chunk_count"] for c in docs),
        "evidence_cards_supplied": sum(
            e["payload"]["cards_supplied"] for e in events if e["kind"] == "evidence-view"
        ),
        "context_per_call": contexts,
        "framework_summary_calls": [
            e["payload"] for e in events if e["kind"] == "framework-summary-call"
        ],
        "framework_summary_usage": [
            e["payload"] for e in events if e["kind"] == "framework-summary-response"
        ],
        "site_dossiers": [e["payload"] for e in events if e["kind"] == "site-evidence-dossier"],
        "soft_target_overrun_calls": sum(c.get("soft_target_exceeded", False) for c in contexts),
        "site_context_by_stage": {
            stage: [c for c in contexts if c.get("site_stage") == stage]
            for stage in ("research", "synthesis")
        },
        "model_responses_usage_latency": [
            e["payload"] for e in events if e["kind"] == "model-response"
        ],
        "cost_status": "Usage retained; currency cost unavailable "
        "without verified pricing for the run.",
        "peak_context_chars": max((c["context_chars"] for c in contexts), default=0),
        "peak_estimated_input_chars_with_schemas": max(
            (c.get("estimated_input_chars_with_schemas", c["context_chars"]) for c in contexts),
            default=0,
        ),
        "calls_by_role": dict(Counter(c["role"] for c in calls)),
        "calls_by_execution": dict(Counter(c["execution_id"] for c in calls)),
        "events": events,
    }


def assert_runtime_dispatch(events, *, site_reused=False):
    """Engineering coverage: current runtime dispatch and actual specialist entry."""
    roles = {e["payload"]["role"] for e in events if e["kind"] == "model-call"}
    required_roles = {"judge"} if site_reused else {"site", "judge"}
    assert required_roles <= roles
    assert "coordinator" not in roles, "Workflow selection called the Coordinator model"
    dispatched = {
        e["payload"].get("specialist")
        for e in events
        if e["kind"] == "runtime-dispatch"
        and e["payload"].get("authority") == "verified-runtime-state"
        and e["payload"].get("model_call") is False
    }
    required_dispatch = {"evidence-judge"} if site_reused else {"site-mechanism", "evidence-judge"}
    assert required_dispatch <= dispatched


def response(card):
    assert card["judge_status"] != "BLOCKED", card
    if card["judge_status"] == "DISCOURAGED":
        return dict(
            decision="override",
            optional_reason="Bounded migration validation of a "
            "scientifically uncertain proposal; no efficacy "
            "or compute approval.",
            explicit_acknowledgement="I acknowledge the displayed scientific warnings "
            "for this validation fixture.",
        )
    return dict(decision="approve")


async def independent_review(case, label, evidence, secrets):
    # Validation-only checkpoint: external developer reviews the actual scientific content.
    # The product Agent has no access to this file and cannot approve itself.
    request_path = case / (label + "-review-request.json")
    receipt_path = case / (label + "-independent-review.json")
    binding = hashlib.sha256(json.dumps(evidence, sort_keys=True, default=str).encode()).hexdigest()
    save(
        request_path,
        {
            "snapshot_sha256": binding,
            "evidence": evidence,
            "required_review_sections": [
                "Hard Facts",
                "Scientific Interpretation",
                "Evidence",
                "Uncertainty",
                "Alternatives",
                "Decision",
            ],
        },
        secrets,
    )
    print("INDEPENDENT CONTENT REVIEW REQUIRED", request_path, flush=True)
    for _ in range(360):
        if receipt_path.exists():
            result = json.loads(receipt_path.read_text())
            assert result["snapshot_sha256"] == binding, "Reviewer inspected a different snapshot"
            assert result["reviewer"] == "development-scientific-content-review"
            assert all(
                result.get(k)
                for k in [
                    "Hard Facts",
                    "Scientific Interpretation",
                    "Evidence",
                    "Uncertainty",
                    "Alternatives",
                    "Decision",
                ]
            )
            assert result["Decision"] == "PASS", result
            return result
        await asyncio.sleep(5)
    raise AssertionError("Independent scientific content review was not completed; not a PASS")


def judge_record(bridge, card):
    return bridge.store.assessment(bridge.thread, card["assessment_id"]).model_dump(mode="json")


def check_pending_identity(pending, truth):
    assert pending["identity_evidence"]["canonical"]["accession"] == truth["accession"]
    actual = next(
        c
        for c in pending["identity_evidence"]["construct_comparisons"]
        if c["auth_chain"] == truth["auth_chain"]
    )
    for k in [
        "canonical_length",
        "construct_length",
        "relationship",
        "mapping_status",
        "review_requirement",
        "substitutions",
        "insertions",
        "deletions",
        "ambiguities",
    ]:
        assert actual[k] == truth["expected"][k], (k, actual[k], truth["expected"][k])
    return actual


def site_mapping_oracle(bridge, proposal, truth):
    from easydesign.core import load_model
    from easydesign.stages.s01_target_preparation.models import ResidueMapping, TargetBundle

    target = bridge.target_state()
    bundle = load_model(target["bundle_path"], TargetBundle)
    mapping = load_model(bundle.residue_mapping.verify(target["root"]), ResidueMapping)
    indexed = {r.label_seq_id: r for r in mapping.entries}
    result = {}
    for candidate in [proposal["intent"]["selected_site"], *proposal["intent"]["alternatives"]]:
        rows = []
        for label in candidate["hotspot_label_seq_ids"]:
            assert label in indexed, "Nonexistent hotspot label"
            row = indexed[label]
            assert row.coordinate_present, "Hotspot has no observed coordinates"
            assert row.source_author_chain_id == truth["auth_chain"], "Wrong source hotspot chain"
            assert row.construct_position in truth["coordinate_label_seq_ids"], (
                "Wrong construct/coordinate mapping"
            )
            assert row.canonical_position is not None, "Hotspot canonical numbering unresolved"
            assert row.canonical_residue == truth["canonical_sequence"][row.canonical_position - 1]
            if truth["accession"] == "P00698":
                assert row.canonical_position == row.construct_position + 18, (
                    "Wrong lysozyme offset"
                )
            rows.append(row.model_dump(mode="json"))
        result[candidate["name"] if "name" in candidate else str(len(result))] = rows
    return result


def check_binding_roundtrip(bridge, accession):
    events = bridge.store.events(bridge.thread)
    revisions = [
        e
        for e in events
        if e["kind"] == "canonical-reference-proposal" and e["payload"]["accession"] == accession
    ]
    assert len(revisions) == 1, "Expected one canonical reference proposal"
    revision = revisions[0]
    views = [
        (e, bridge.document(e["payload"]["ref"])) for e in events if e["kind"] == "evidence-view"
    ]
    before = [
        c
        for e, v in views
        if e["seq"] < revision["seq"]
        for c in v["cards"]
        if c["source_id"] == "UniProt:" + accession
    ]
    after = [
        c
        for e, v in views
        if e["seq"] > revision["seq"]
        for c in v["cards"]
        if c["source_id"] == "UniProt:" + accession
    ]
    assert before and after, (
        "Real focused retrieval must return cards before and after canonical revision"
    )
    stable = {c["project_evidence_id"] for c in before} & {c["project_evidence_id"] for c in after}
    assert stable and all(c["source_status"] == "VERIFIED" for c in before + after)
    assert any(c["binding_context"]["relation"] == "current-canonical-reference" for c in after)
    acquisitions = [
        bridge.document(e["payload"]["ref"]) for e in events if e["kind"] == "evidence-research"
    ]
    downloads = [
        q
        for q in acquisitions
        if q.get("query", {}).get("operation") == "uniprot-record"
        and q["query"].get("identifier") == accession
        and not q.get("reused_verified_source")
    ]
    assert len(downloads) == 1, "A canonical revision must not redownload the same full source"
    return {
        "stable_project_evidence_ids": sorted(stable),
        "before_cards": before,
        "after_cards": after,
        "source_acquisitions": len(downloads),
        "revision": revision["payload"],
        "status": "PASS",
    }


async def run_design_case(
    project, store, case, kind, config, models, secrets, emit, *, thread, steering=None
):
    """Run one reviewed Gate3 case on the existing approved Site, without compute."""
    design = DesignBridge(project, thread, store)
    if kind == "expert-native" and not steering:
        labels = tuple(design.approved_site()["hotspots"]["hotspot_sets"][0]["label_seq_ids"])
        expert = design.project / "inputs/expert/strategy.yaml"
        if not expert.exists():
            expert = expert_input(design, binding=labels)
        import_native(design, expert)
    goal = (
        "Review a VHH design specification on the "
        "already approved lysozyme hotspot. "
        "No binding efficacy is established. Keep "
        "upstream limitations and propose one "
        "bounded first-pilot condition, all seven "
        "official scaffolds and 40 candidates each. "
        "Use full target context. "
        + (
            "Use standard structured DesignArm with default scaffold/CDR settings. "
            if kind == "standard"
            else "Preserve the imported scientist native YAML "
            "bytes exactly; use "
            "strategy_source=expert-native and arms=[]. "
        )
        + "Inspect and validate the design, obtain "
        "independent Judge review and present "
        "Gate 3. Stop before approval or generation."
    )
    try:
        outcome = await run_session(design, config, models, goal, emit=emit, **(steering or {}))
    finally:
        save(case / (kind + "-metrics.json"), stats(design), secrets)
    save(case / (kind + "-gate3.json"), outcome, secrets)
    assert (
        outcome["status"] == "awaiting-human-approval"
        and outcome["card"]["gate_type"] == "design-specification"
    ), outcome
    assert outcome["card"]["judge_status"] != "BLOCKED", outcome
    if steering:
        assert steering["decision"] == "revise"
        assert outcome["card"]["parent_card_id"] == steering["card_id"]
    snapshot = design.design_snapshot(design.current_design())
    assert snapshot["evaluation"]["generation_started"] is False
    assert snapshot["evaluation"]["compiler_validation"] == "existing compiler and backend passed"
    save(case / (kind + "-snapshot.json"), snapshot, secrets)
    save(case / (kind + "-metrics.json"), stats(design), secrets)
    if kind == "expert-native":
        native = design.current_design()["native_input"]
        input_bytes = [
            (design.project / r["relative_path"]).read_bytes()
            for r in native["summary"]["input_refs"]
            if r["relative_path"].endswith(".yaml")
        ]
        compiled = [
            (design.project / r["relative_path"]).read_bytes()
            for r in design.document(design.current_design()["compiled_ref"])
            if r["relative_path"].endswith("/design.yaml")
        ]
        assert len(compiled) == 7 and all(raw in input_bytes for raw in compiled), (
            "Native YAML changed"
        )
    await independent_review(
        case,
        kind + "-gate3",
        {
            "card": outcome["card"],
            "snapshot": snapshot,
            "judge": judge_record(design, outcome["card"]),
            "approved_site": design.approved_site(),
        },
        secrets,
    )


async def main():
    OUT.mkdir(exist_ok=False)
    config = ModelConfig.model_validate(yaml.safe_load((ROOT / "config/llm.yaml").read_text()))
    assert config.max_input_chars == 60000 and config.max_model_calls == PHASE2_MODEL_CALL_LIMIT
    secrets = [os.environ.get(c.secret_env, "") for c in [config.default, *config.roles.values()]]
    # Provider/model are explicit engineering configuration, not scientific oracles.
    # Record the complete configuration below; never silently switch on a failure.
    assert (
        hashlib.sha256((ROOT / "docs/PHASE2_GOLDEN_CASE_SPEC.md").read_bytes()).hexdigest()
        == "434e442aa98206f92d72219833d05167d7775580679dfc70820657632fbbfb3d"
    )
    assert (
        hashlib.sha256(
            (ROOT / "tests/fixtures/agent/phase2_golden_truth.json").read_bytes()
        ).hexdigest()
        == "2e367355d197d541df7f77b87f6b505659a81997dc79db7a97a0b0e0ff3258c9"
    )

    def observe_request(metadata):
        with (OUT / "model-wire-metadata.jsonl").open("a") as handle:
            handle.write(json.dumps({"at": datetime.now(UTC).isoformat(), **metadata}) + "\n")

    models = create_models(config, request_observer=observe_request)
    truth = golden_truth()
    report = {
        "type": "REAL MODEL / REAL SOURCE / EXISTING DETERMINISTIC SERVICES",
        "model": config.default.model,
        "model_configuration": config.model_dump(mode="json"),
        "model_adapters": {r: config.for_role(r).adapter_provider for r in models},
        "http_observation_roles": [
            r for r in models if config.for_role(r).adapter_provider == "openai"
        ],
        "gate_response_actor": ACTOR,
        "generation_started": False,
        "case_scope": CASE_SCOPE,
        "cases": [],
        "formal_acceptance": "PENDING",
        "spec_sha256": hashlib.sha256(
            (ROOT / "docs/PHASE2_GOLDEN_CASE_SPEC.md").read_bytes()
        ).hexdigest(),
        "oracle_sha256": hashlib.sha256(
            (ROOT / "tests/fixtures/agent/phase2_golden_truth.json").read_bytes()
        ).hexdigest(),
    }
    save(OUT / "pre-live-contract.json", report, secrets)
    active_case = "case-3-identity-trap"
    print("Evidence directory:", OUT, flush=True)
    try:
        for name, code, chain, accession in [
            ("soluble", "1MEL", "L", "P00698"),
            ("gpcr", "3P0G", "A", "P07550"),
        ]:
            if CASE_SCOPE != "all" and name != CASE_SCOPE:
                continue
            active_case = "case-3-identity-trap" if name == "soluble" else "case-2-gpcr"
            assert (
                hashlib.sha256((SOURCE / name / f"rcsb-{code}.cif").read_bytes()).hexdigest()
                == truth[name]["structure_sha256"]
            )
            case = OUT / name
            case.mkdir()
            inherited = None
            if APPROVED_TARGET and Path(APPROVED_TARGET).name == name:
                origin = Path(APPROVED_TARGET).resolve()
                assert origin.is_relative_to(ROOT / "runtime/tmp/autonomous-v3-20260912")
                workspace = origin / "workspace-root"
                assert workspace.is_dir()
                inherited = origin
            else:
                workspace = case / "workspace-root"
                workspace.mkdir()
                (workspace / "easydesign-workspace.yaml").write_text(
                    'schema_version: "0.1"\nworkspace_id: v3-golden-validation\n'
                )
            os.environ["EASYDESIGN_WORKSPACE"] = str(workspace)
            context = WorkspaceContext.from_root(workspace)
            context.ensure_layout()
            project = context.projects_root / name
            if inherited is None:
                initialize_runtime_profile(context.profile_path)
                initialize_research_project(
                    project_root=project, target=SOURCE / name / f"rcsb-{code}.cif"
                )
            store = SessionStore(project)
            bridge = Phase2Bridge(
                project,
                "live-target-site" if inherited is None else "live-site-" + STAMP.lower(),
                store,
            )

            def emit(event, case=case):
                if event["kind"] in {
                    "model-call",
                    "model-context",
                    "tool",
                    "agent-terminal",
                    "evidence-selection",
                    "prerequisite-repair",
                    "tool-argument-repair",
                    "contract-repair",
                    "scientific-consistency-finding",
                }:
                    with (case / "progress.jsonl").open("a") as handle:
                        handle.write(json.dumps(event, ensure_ascii=False) + "\n")

            try:
                inherited_metrics = None
                continuity_threads = []
                if inherited is not None:
                    # Reuse approved science through project-global ownership, never edit
                    # an incompatible thread's fingerprint, checkpoint, budget or response.
                    old_bridge = Phase2Bridge(project, "live-target-site", store)
                    gate1 = json.loads((inherited / "gate1.json").read_text())
                    card = old_bridge.store.card(old_bridge.thread, gate1["card"]["card_id"])
                    assert card.model_dump(mode="json") == gate1["card"]
                    intent = store.response(old_bridge.thread, card.card_id)
                    assert intent and intent["delivered"] and intent["user"] == ACTOR
                    assert intent["response"] in {"approve", "override"}
                    request = json.loads((inherited / "gate1-review-request.json").read_text())
                    assert request["evidence"]["card"] == gate1["card"]
                    saved_review = json.loads(
                        (inherited / "gate1-independent-review.json").read_text()
                    )
                    save(case / "gate1-independent-review.json", saved_review, secrets)
                    await independent_review(case, "gate1", request["evidence"], secrets)
                    approved_identity(old_bridge, truth[name])
                    check_binding_roundtrip(old_bridge, accession)
                    assert bridge.target_run_id() == card.run_id
                    assert bridge.scientific_state()["scientific_state"] == "site-not-proposed"
                    inherited_metrics = stats(old_bridge)
                    save(case / "inherited-target-metrics.json", inherited_metrics, secrets)
                    save(
                        case / "inherited-target.json",
                        {
                            "origin": str(inherited),
                            "project": str(project),
                            "source_thread": old_bridge.thread,
                            "continuation_thread": bridge.thread,
                            "card_id": card.card_id,
                            "run_id": card.run_id,
                            "reason": "Developer retry after bounded Site failure; exact approved "
                            "target reused without pipeline restart or checkpoint rewrite",
                        },
                        secrets,
                    )
                    save(case / "gate1.json", gate1, secrets)
                    target = bridge.read_evidence()
                    identity_report = approved_identity(bridge, truth[name])
                    save(case / "approved-target.json", target, secrets)
                    save(case / "approved-identity-oracle.json", identity_report, secrets)
                    if UNREVIEWED_SITE:
                        source_case = Path(UNREVIEWED_SITE).resolve()
                        assert source_case.is_relative_to(
                            ROOT / "runtime/tmp/autonomous-v3-20260912"
                        )
                        assert source_case.name == name
                        source_report = json.loads((source_case.parent / "report.json").read_text())
                        assert source_report["formal_acceptance"] == "VALIDATION_ATTEMPT_FAILED"
                        source_info = json.loads(
                            (source_case / "inherited-target.json").read_text()
                        )
                        assert Path(source_info["project"]).resolve() == project.resolve()
                        source_thread = source_info["continuation_thread"]
                        source_bridge = Phase2Bridge(project, source_thread, store)
                        completed_proposal = source_bridge.current_site()
                        assert completed_proposal is not None
                        jobs_before = [j.job_id for j in bridge.controller.list(project_id=name)]
                        snapshot = bridge.transfer_unreviewed_site(
                            source_thread, expected_proposal_id=completed_proposal["proposal_id"]
                        )
                        assert snapshot == source_bridge.site_snapshot(completed_proposal)
                        assert jobs_before == [
                            j.job_id for j in bridge.controller.list(project_id=name)
                        ]
                        continuity_threads = []
                        ancestor = source_thread
                        while ancestor not in continuity_threads:
                            continuity_threads.append(ancestor)
                            ancestor_bridge = Phase2Bridge(project, ancestor, store)
                            received = ancestor_bridge.thread_latest("site-proposal-received")
                            if received is None:
                                break
                            assert received["proposal_id"] == completed_proposal["proposal_id"]
                            ancestor = received["source_thread"]
                        save(
                            case / "inherited-unreviewed-site.json",
                            {
                                "origin": str(source_case),
                                "source_thread": source_thread,
                                "continuation_thread": bridge.thread,
                                "source_threads": continuity_threads,
                                "source_model_configuration": source_report["model_configuration"],
                                "proposal_id": completed_proposal["proposal_id"],
                                "job_id": completed_proposal["job_id"],
                                "snapshot": snapshot,
                                "authority": "Completed Site job only; independent Judge "
                                "and Gate 2 still required",
                            },
                            secrets,
                        )
                    if name == "soluble":
                        await independent_review(
                            case,
                            "identity-trap",
                            {
                                "target": target,
                                "identity": identity_report,
                                "truth": truth[name],
                                "gate1": gate1["card"],
                            },
                            secrets,
                        )
                        report["cases"].append({"case": "case-3-identity-trap", "status": "PASS"})
                        active_case = "case-1-soluble"
                        save(OUT / "report.json", report, secrets)
                    gate2 = await run_session(bridge, config, models, GOALS[name], emit=emit)
                else:
                    gate1 = await run_session(bridge, config, models, GOALS[name], emit=emit)
                    save(case / "gate1.json", gate1, secrets)
                    assert (
                        gate1["status"] == "awaiting-human-approval"
                        and gate1["card"]["gate_type"] == "target-structure"
                    ), gate1
                    assert gate1["card"]["option_id"] == f"chain-{chain.lower()}", gate1
                    pending = bridge.read_evidence()
                    save(case / "pending-identity.json", pending, secrets)
                    check_pending_identity(pending, truth[name])
                    binding_check = check_binding_roundtrip(bridge, accession)
                    save(case / "canonical-binding-roundtrip.json", binding_check, secrets)
                    assert pending["hard_facts"]["canonical_length"] == len(
                        truth[name]["canonical_sequence"]
                    )
                    assert (
                        gate1["card"]["scientific_summary"]["hard_facts"] == pending["hard_facts"]
                    )
                    await independent_review(
                        case,
                        "gate1",
                        {
                            "card": gate1["card"],
                            "pending": pending,
                            "judge": judge_record(bridge, gate1["card"]),
                            "truth": truth[name],
                            "binding_roundtrip": binding_check,
                        },
                        secrets,
                    )
                    gate2 = await run_session(
                        bridge,
                        config,
                        models,
                        GOALS[name],
                        card_id=gate1["card"]["card_id"],
                        user=ACTOR,
                        emit=emit,
                        **response(gate1["card"]),
                    )
                save(case / "gate2.json", gate2, secrets)
                assert (
                    gate2["status"] == "awaiting-human-approval"
                    and gate2["card"]["gate_type"] == "site-hotspot"
                ), gate2
                target = bridge.read_evidence()
                assert target["identity"]["biological_identity_status"] == "resolved"
                assert target["identity"]["canonical"]["accession"] == accession
                save(case / "approved-target.json", target, secrets)
                identity_report = approved_identity(bridge, truth[name])
                save(case / "approved-identity-oracle.json", identity_report, secrets)
                if name == "soluble" and inherited is None:
                    await independent_review(
                        case,
                        "identity-trap",
                        {
                            "target": target,
                            "identity": identity_report,
                            "truth": truth[name],
                            "gate1": gate1["card"],
                        },
                        secrets,
                    )
                    report["cases"].append({"case": "case-3-identity-trap", "status": "PASS"})
                    active_case = "case-1-soluble"
                    save(OUT / "report.json", report, secrets)
                proposal = bridge.current_site()
                save(case / "site-snapshot.json", bridge.site_snapshot(proposal), secrets)
                metrics = stats(bridge, source_threads=continuity_threads)
                save(case / "metrics.json", metrics, secrets)
                assert metrics["peak_context_chars"] <= config.hard_input_chars
                assert metrics["search_query_count"] >= 1, (
                    "Active discovery search was not performed"
                )
                assert (
                    metrics["full_sources_acquired"] >= 2 and metrics["evidence_cards_supplied"] > 0
                )
                assert metrics["evidence_cards_passed_to_specialist"] > 0
                assert (
                    metrics["corpus_documents_all_bindings"] > 0
                    and metrics["total_retrieved_raw_chars"] > 0
                )
                target_metrics = inherited_metrics or metrics
                assert {"target", "site", "judge"} <= (
                    set(metrics["calls_by_role"]) | set(target_metrics["calls_by_role"])
                )
                assert_runtime_dispatch(
                    store.events(bridge.thread), site_reused=bool(inherited and UNREVIEWED_SITE)
                )
                tools = [
                    e["payload"]["name"]
                    for e in [*metrics["events"], *target_metrics["events"]]
                    if e["kind"] == "tool"
                ]
                assert "propose_canonical_identity" in tools and "retrieve_evidence" in tools
                if name == "soluble":
                    assert "analyze_receptor_context" not in tools
                else:
                    assert "analyze_receptor_context" in tools
                mapped = site_mapping_oracle(bridge, proposal, truth[name])
                save(case / "site-mapping-oracle.json", mapped, secrets)
                await independent_review(
                    case,
                    "gate2",
                    {
                        "card": gate2["card"],
                        "site": bridge.site_snapshot(proposal),
                        "mapped_hotspot_rows": mapped,
                        "identity": identity_report,
                        "truth": truth[name],
                        "judge": judge_record(bridge, gate2["card"]),
                        "metrics": {
                            k: v
                            for k, v in metrics.items()
                            if k not in {"events", "context_per_call"}
                        },
                    },
                    secrets,
                )
                report["cases"].append(
                    {
                        "case": active_case,
                        "status": "PASS",
                        "metrics": {
                            k: v
                            for k, v in metrics.items()
                            if k not in {"events", "context_per_call"}
                        },
                    }
                )
                save(OUT / "report.json", report, secrets)
                if name == "soluble":
                    approved = await run_session(
                        bridge,
                        config,
                        models,
                        GOALS[name],
                        card_id=gate2["card"]["card_id"],
                        user=ACTOR,
                        emit=emit,
                        **response(gate2["card"]),
                    )
                    assert bridge.approved_site() and approved["status"] == "finished", approved
                    assert all(
                        j.step <= 2 for j in bridge.controller.list(project_id=bridge.project_id)
                    ), "No generation or prediction before Gate 3"
                    assert os.environ.get("EASYDESIGN_AGENT_BOLTZGEN_RUNTIME"), (
                        "Current-worktree validator configuration required"
                    )
                    backend = configure_live_validation()
                    save(case / "backend-validation.json", backend, secrets)
                    for kind in ("standard", "expert-native"):
                        active_case = "case-4-standard" if kind == "standard" else "case-5-native"
                        await run_design_case(
                            project,
                            store,
                            case,
                            kind,
                            config,
                            models,
                            secrets,
                            emit,
                            thread="live-design-" + kind,
                        )
                        report["cases"].append({"case": active_case, "status": "PASS"})
                        save(OUT / "report.json", report, secrets)
                jobs = bridge.controller.list(project_id=bridge.project_id)
                assert all(j.step <= 2 for j in jobs)
                save(
                    case / "jobs.json",
                    [{"job_id": j.job_id, "step": j.step, "status": str(j.status)} for j in jobs],
                    secrets,
                )
                save(OUT / "report.json", report, secrets)
                print(name, "paths passed; content review pending", flush=True)
            finally:
                try:
                    save(
                        case / "final-thread-metrics.json",
                        stats(bridge, source_threads=continuity_threads),
                        secrets,
                    )
                except Exception:
                    save(
                        case / "metrics-export-error.json",
                        {"error": traceback.format_exc()},
                        secrets,
                    )
                jobs = bridge.controller.list(project_id=bridge.project_id)
                save(
                    case / "final-jobs.json",
                    [{"job_id": j.job_id, "step": j.step, "status": str(j.status)} for j in jobs],
                    secrets,
                )
                assert all(j.step <= 2 for j in jobs), (
                    "Validation cannot launch compute beyond Stage 02"
                )
                store.close()
        expected_cases = {"all": 5, "soluble": 4, "gpcr": 1}[CASE_SCOPE]
        assert len(report["cases"]) == expected_cases and all(
            c["status"] == "PASS" for c in report["cases"]
        )
        report["formal_acceptance"] = (
            "ALL_FIVE_SCIENTIFIC_ACCEPTANCE_PASS"
            if CASE_SCOPE == "all"
            else "PARTIAL_CASE_SCIENTIFIC_ACCEPTANCE_PASS"
        )
    except Exception:
        report["formal_acceptance"] = "VALIDATION_ATTEMPT_FAILED"
        report["error"] = traceback.format_exc()
        completed = {c["case"] for c in report["cases"]}
        if active_case not in completed:
            report["cases"].append({"case": active_case, "status": "FAIL"})
        for unrun in [
            "case-1-soluble",
            "case-2-gpcr",
            "case-3-identity-trap",
            "case-4-standard",
            "case-5-native",
        ]:
            if unrun not in {c["case"] for c in report["cases"]}:
                report["cases"].append({"case": unrun, "status": "NOT_RUN_IN_THIS_ATTEMPT"})
    save(OUT / "report.json", report, secrets)
    print(report["formal_acceptance"], OUT, flush=True)
    return 0 if report["formal_acceptance"].endswith("ACCEPTANCE_PASS") else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
