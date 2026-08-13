#!/usr/bin/env python3
# ruff: noqa: E501
"""Build a read-only EasyDesign result review from verified run artifacts."""

from __future__ import annotations

import argparse
import base64
import html
import json
import os
import shutil
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from statistics import median
from typing import Any
from uuid import uuid4

from easydesign.core import RunManifest, StageId, StageManifest, load_model, sha256_file
from easydesign.safe_writes import read_last_text_line
from easydesign.stages.s03_boltzgen_configuration import StrategyBundle
from easydesign.stages.s04_pilot_generation import CandidateIndex
from easydesign.stages.s05_pilot_filtering import (
    PilotFilterReport,
    PilotFilterReportV1_6,
)
from easydesign.workspace_context import WorkspaceContext

GENERATOR_ID = "easydesign-result-review"
GENERATOR_VERSION = "0.2.0"
SUPPORTED_MODE = "pilot-review"
VIEWER_ASSETS = {
    "molstar.js": "7fad5561c74bc900930fb57d6ab028d1aafdda82223a901bf932b1098e84f1f3",
    "molstar.css": "5b68ceb6d3642549b4e9b2c071e58e41b98a5350ae269180587b39da86925d55",
    "LICENSE": "eabd1831ed605a29cf9d7e60221c019c1bc026add81e3c0686ce5f24b3d4d500",
}


def _json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _write_exclusive(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _relative_to_run(root: Path, path: Path) -> str:
    try:
        return path.resolve(strict=True).relative_to(root).as_posix()
    except ValueError as error:
        raise ValueError(f"来源 artifact 逃出 run root: {path}") from error


def _copy_viewer_assets(repo_root: Path, output: Path) -> list[Path]:
    source_root = (
        repo_root
        / "src/easydesign/reporting/static/target_viewer/vendor/molstar"
    )
    copied: list[Path] = []
    for name, expected_sha256 in VIEWER_ASSETS.items():
        source = source_root / name
        if not source.is_file() or sha256_file(source) != expected_sha256:
            raise ValueError(f"本地 Mol* asset identity 不一致: {source}")
        destination = output / "assets" / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("xb") as writer, source.open("rb") as reader:
            shutil.copyfileobj(reader, writer)
            writer.flush()
            os.fsync(writer.fileno())
        if sha256_file(destination) != expected_sha256:
            raise ValueError(f"本地 Mol* asset 副本 SHA-256 不一致: {name}")
        copied.append(destination)
    return copied


def _current_run(root: Path) -> tuple[RunManifest, Path]:
    name = read_last_text_line(root / "manifests/LATEST")
    path = root / "manifests" / name
    return load_model(path, RunManifest), path


def _stage(root: Path, run: RunManifest, stage_id: StageId) -> tuple[StageManifest, Path]:
    matches = [
        reference
        for reference in run.stage_manifest_refs
        if reference.producer_stage == str(stage_id)
    ]
    if len(matches) != 1:
        raise ValueError(f"RunManifest 必须声明恰好一个 {stage_id} manifest")
    path = matches[0].verify(root)
    stage = load_model(path, StageManifest)
    if stage.stage_id is not stage_id or str(stage.status) != "succeeded":
        raise ValueError(f"Result review 只接受 succeeded {stage_id}")
    return stage, path


def _output(stage: StageManifest, root: Path, artifact_id: str) -> Path:
    return stage.require_output(artifact_id).verify(root)


def _metric_map(record: Any) -> dict[str, Any]:
    return {metric.metric_id: metric for metric in record.metrics}


def _metric_payload(record: Any) -> dict[str, Any]:
    return {
        metric.metric_id: {
            "value": metric.value,
            "available": metric.available,
            "missing_reason": metric.missing_reason,
            "source": metric.source,
            "unit": metric.unit,
            "definition_version": metric.definition_version,
        }
        for metric in record.metrics
    }


def _select_representatives(records: list[Any]) -> dict[str, list[str]]:
    selected: dict[str, list[str]] = defaultdict(list)
    passing = [item for item in records if item.eligible_unique_pass]
    if passing:
        best = min(passing, key=lambda item: (-item.score_screen, item.candidate_id))
        selected[best.candidate_id].append("best-pass")
        middle = median(item.score_screen for item in passing)
        typical = min(
            passing,
            key=lambda item: (abs(item.score_screen - middle), item.candidate_id),
        )
        selected[typical.candidate_id].append("typical-pass")
    failing = [item for item in records if not item.eligible_unique_pass]
    if failing:
        signatures: dict[str, tuple[str, ...]] = {
            item.candidate_id: tuple(
                sorted(
                    decision.rule_id
                    for decision in item.hard_gate_decisions
                    if not decision.passed
                )
            )
            or (("duplicate-sequence",) if item.duplicate_of else ("unclassified-failure",))
            for item in failing
        }
        counts = Counter(signatures.values())
        failure = min(
            failing,
            key=lambda item: (
                -counts[signatures[item.candidate_id]],
                -item.score_screen,
                item.candidate_id,
            ),
        )
        selected[failure.candidate_id].append("representative-failure")
    return dict(selected)


def _display_metrics(records: list[Any]) -> list[dict[str, Any]]:
    preferred = (
        "hotspot-coverage",
        "target-ca-rmsd",
        "design-to-target-iptm",
        "min-design-to-target-pae",
        "cdr-dominance",
        "cdr-utilization",
        "interface-bsa",
        "severe-clash-count",
        "moderate-clash-count",
    )
    available_ids = {metric.metric_id for item in records for metric in item.metrics}
    output: list[dict[str, Any]] = []
    for metric_id in preferred:
        if metric_id not in available_ids:
            continue
        values: list[float] = []
        missing = 0
        sources: set[str] = set()
        definitions: set[str] = set()
        unit: str | None = None
        for record in records:
            metric = _metric_map(record).get(metric_id)
            if metric is None or not metric.available:
                missing += 1
                continue
            sources.add(str(metric.source))
            definitions.add(metric.definition_version)
            unit = metric.unit
            if isinstance(metric.value, (int, float)) and not isinstance(metric.value, bool):
                values.append(float(metric.value))
        output.append(
            {
                "metric_id": metric_id,
                "unit": unit,
                "observed_count": len(values),
                "missing_count": missing,
                "median": None if not values else median(values),
                "minimum": None if not values else min(values),
                "maximum": None if not values else max(values),
                "sources": sorted(sources),
                "definition_versions": sorted(definitions),
            }
        )
    return output


def _candidate_structure(
    *,
    output: Path,
    run_root: Path,
    candidate: Any,
    roles: list[str],
) -> dict[str, Any]:
    source = candidate.refolded_structure.verify(run_root)
    relative = Path("structures") / f"{candidate.candidate_id}.cif"
    destination = output / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("xb") as handle:
        with source.open("rb") as reader:
            shutil.copyfileobj(reader, handle)
        handle.flush()
        os.fsync(handle.fileno())
    actual = sha256_file(destination)
    if actual != candidate.refolded_structure.sha256:
        raise ValueError(f"结构副本 SHA-256 不一致: {candidate.candidate_id}")
    return {
        "candidate_id": candidate.candidate_id,
        "strategy_id": candidate.strategy_id,
        "roles": roles,
        "relative_path": relative.as_posix(),
        "sha256": actual,
        "source_artifact_id": candidate.refolded_structure.artifact_id,
        "source_relative_path": candidate.refolded_structure.relative_path,
    }


def _render_html(
    data: dict[str, Any], embedded_structures: dict[str, str]
) -> str:
    browser_data = {**data, "embedded_structures": embedded_structures}
    embedded = json.dumps(browser_data, ensure_ascii=False).replace("</", "<\\/")
    title = html.escape(f"EasyDesign Pilot Review · {data['run']['run_id']}")
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'self' 'unsafe-inline' 'unsafe-eval' blob:; style-src 'self' 'unsafe-inline'; connect-src blob:; img-src 'self' data: blob:; worker-src blob:; object-src 'none'; base-uri 'none'; form-action 'none'">
<title>{title}</title>
<link rel="stylesheet" href="assets/molstar.css">
<style>
:root{{--navy:#16324f;--blue:#2563eb;--ink:#172033;--muted:#64748b;--line:#d9e1ea;--page:#f4f6f8;--ok:#1f7a44;--bad:#b42318;--warn:#9a6700}}
*{{box-sizing:border-box}}html,body{{height:100%;margin:0;font-family:Inter,"PingFang SC","Microsoft YaHei",system-ui,sans-serif;color:var(--ink);background:var(--page)}}
body{{display:grid;grid-template-rows:auto 1fr;overflow:hidden}}header{{display:flex;align-items:center;justify-content:space-between;padding:14px 22px;background:var(--navy);color:#fff}}header h1{{margin:2px 0;font-size:21px}}header p{{margin:0;color:#d9e7f5;font-size:12px}}.readonly{{padding:7px 10px;border:1px solid #8eabc4;font-size:12px}}
.shell{{display:grid;grid-template-columns:320px minmax(0,1fr);min-height:0}}aside{{overflow:auto;background:#fff;border-right:1px solid var(--line);padding:14px}}main{{overflow:auto;padding:18px}}
button{{width:100%;padding:10px;margin:0 0 8px;text-align:left;border:1px solid var(--line);background:#fff;color:var(--ink);cursor:pointer}}button.active{{border-color:var(--blue);background:#eef4ff}}button small{{display:block;color:var(--muted);margin-top:4px}}
.panel{{background:#fff;border:1px solid var(--line);padding:16px;margin-bottom:14px}}h2{{font-size:16px;margin:0 0 12px}}h3{{font-size:14px;margin:14px 0 8px}}.grid{{display:grid;grid-template-columns:repeat(4,minmax(120px,1fr));gap:10px}}.metric{{padding:10px;background:#f8fafc;border:1px solid #e8edf3}}.metric b{{display:block;font-size:21px}}.metric span{{font-size:11px;color:var(--muted)}}
table{{width:100%;border-collapse:collapse;font-size:12px}}th,td{{border-bottom:1px solid var(--line);padding:8px;text-align:left;vertical-align:top}}th{{position:sticky;top:0;background:#f8fafc}}.ok{{color:var(--ok)}}.bad{{color:var(--bad)}}.warn{{color:var(--warn)}}
.bar{{height:8px;background:#e5eaf0;margin-top:5px}}.bar i{{display:block;height:100%;background:var(--blue)}}.structure-picker{{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px}}.structure-picker button{{width:auto;margin:0}}#molstar-viewer{{position:relative;height:480px;border:1px solid var(--line);background:#eef1f6}}#viewer-empty{{min-height:180px;border:1px dashed #9aa8b7;background:#f8fafc;display:grid;place-items:center;text-align:center}}#viewer-status{{margin:8px 0 0}}
.note{{font-size:12px;color:var(--muted);line-height:1.6}}@media(max-width:900px){{body{{overflow:auto}}.shell{{display:block}}aside{{max-height:300px}}main{{overflow:visible}}.grid{{grid-template-columns:repeat(2,1fr)}}}}
</style>
</head>
<body>
<header><div><p>EasyDesign Local · Manifest-verified evidence</p><h1>{title}</h1><p id="identity"></p></div><div class="readonly">只读派生报告 · 无审批/运行入口</div></header>
<div class="shell"><aside><h2>Experiment strategies</h2><div id="strategy-list"></div></aside><main><section id="overview" class="panel"></section><section id="details" class="panel"></section><section id="candidates" class="panel"></section><section id="structure" class="panel"><h2>结构审阅</h2><div id="structure-picker" class="structure-picker"></div><div id="viewer-empty" hidden></div><div id="molstar-viewer"></div><p id="viewer-status" class="note">选择代表结构后加载本地 Mol*。</p></section><section id="provenance" class="panel"></section></main></div>
<script src="assets/molstar.js"></script>
<script>const DATA={embedded};
const STATE={{viewer:null,structureUrl:null,loading:false}};
const fmt=v=>v===null||v===undefined?'N/A':(typeof v==='number'?Number(v.toFixed(4)):String(v));
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));
document.getElementById('identity').textContent=`${{DATA.run.project_id}} · ${{DATA.run.run_id}} · ${{DATA.profile.profile_id}}`;
function table(headers,rows){{return `<div style="overflow:auto"><table><thead><tr>${{headers.map(x=>`<th>${{esc(x)}}</th>`).join('')}}</tr></thead><tbody>${{rows.map(r=>`<tr>${{r.map(x=>`<td>${{x}}</td>`).join('')}}</tr>`).join('')}}</tbody></table></div>`}}
function renderOverview(){{const d=DATA.denominator;document.getElementById('overview').innerHTML=`<h2>完整 denominator</h2><div class="grid">${{[['Planned',d.planned],['Generated',d.generated],['Evaluable',d.evaluable],['Unique pass',d.eligible_unique_pass]].map(x=>`<div class="metric"><b>${{fmt(x[1])}}</b><span>${{x[0]}}</span></div>`).join('')}}</div><p class="note">页面 shortlist 不改变以上分母；missing 不转换为 0。</p>`}}
function bytesFromBase64(value){{const raw=atob(value);const bytes=new Uint8Array(raw.length);for(let i=0;i<raw.length;i++)bytes[i]=raw.charCodeAt(i);return bytes}}
async function ensureViewer(){{if(STATE.viewer)return STATE.viewer;if(!window.molstar||!molstar.Viewer)throw new Error('Mol* 5.11.0 本地资源未加载');STATE.viewer=await molstar.Viewer.create('molstar-viewer',{{extensions:['mvs'],layoutIsExpanded:false,layoutShowControls:true,layoutShowRemoteState:false,layoutShowSequence:true,layoutShowLog:false,layoutShowLeftPanel:false,collapseRightPanel:true,viewportShowExpand:false,viewportShowToggleFullscreen:false,viewportShowScreenshotControls:false,volumeStreamingDisabled:true,pluginStateServer:'',powerPreference:'high-performance',allowMajorPerformanceCaveat:true,viewportBackgroundColor:'#EEF1F6'}});return STATE.viewer}}
async function loadStructure(item,strategy){{if(STATE.loading)return;STATE.loading=true;document.getElementById('viewer-status').textContent=`正在加载 ${{item.candidate_id}}…`;try{{const viewer=await ensureViewer();if(STATE.structureUrl)URL.revokeObjectURL(STATE.structureUrl);const encoded=DATA.embedded_structures[item.candidate_id];if(!encoded)throw new Error('报告缺少对应的 checksum-verified 结构副本');STATE.structureUrl=URL.createObjectURL(new Blob([bytesFromBase64(encoded)],{{type:'chemical/x-mmcif'}}));const mvs=molstar.PluginExtensions.mvs;const builder=mvs.createBuilder();builder.canvas({{background_color:'#EEF1F6'}});const structure=builder.download({{url:STATE.structureUrl}}).parse({{format:'mmcif'}}).modelStructure();const representation=structure.component({{selector:'polymer'}}).representation({{type:'cartoon'}});representation.color({{color:'#1D4ED8'}});representation.color({{selector:{{label_asym_id:DATA.profile.target_chain_id}},color:'#94A3B8'}});for(const residue of strategy.binding_label_seq_ids)representation.color({{selector:{{label_asym_id:DATA.profile.target_chain_id,label_seq_id:residue}},color:'#EF4444'}});await mvs.loadMVS(viewer.plugin,builder.getState({{title:item.candidate_id,description:'EasyDesign result review'}}),{{replaceExisting:true,keepCamera:false}});document.getElementById('viewer-status').textContent=`${{item.candidate_id}} · ${{item.roles.join(', ')}} · SHA-256 ${{item.sha256}}`;window.__EASYDESIGN_RESULT_REVIEW_READY__=true}}catch(error){{document.getElementById('viewer-status').textContent=`结构加载失败：${{error instanceof Error?error.message:String(error)}}`;window.__EASYDESIGN_RESULT_REVIEW_ERROR__=String(error)}}finally{{STATE.loading=false}}}}
function renderStructures(strategy){{const structures=DATA.structures.filter(x=>x.strategy_id===strategy.strategy_id);const picker=document.getElementById('structure-picker');picker.replaceChildren();document.getElementById('viewer-empty').hidden=structures.length>0;document.getElementById('molstar-viewer').hidden=structures.length===0;if(!structures.length){{document.getElementById('viewer-empty').textContent='该组没有可复制的代表结构。';document.getElementById('viewer-status').textContent='无结构可审阅。';return}}structures.forEach((item,index)=>{{const button=document.createElement('button');button.textContent=`${{item.roles.join(', ')}} · ${{item.candidate_id}}`;button.title=`SHA-256: ${{item.sha256}}`;button.onclick=()=>{{picker.querySelectorAll('button').forEach(value=>value.classList.toggle('active',value===button));loadStructure(item,strategy)}};picker.appendChild(button);if(index===0)button.click()}})}}
function renderStrategy(id){{document.querySelectorAll('button[data-id]').forEach(b=>b.classList.toggle('active',b.dataset.id===id));const s=DATA.strategies.find(x=>x.strategy_id===id);document.getElementById('details').innerHTML=`<h2>${{esc(s.strategy_id)}}</h2><p><b>${{esc(s.role||'unspecified')}}</b> · scaffold ${{esc(s.scaffold_id)}} · tier ${{esc(s.tier)}} · score_yaml ${{fmt(s.score_yaml)}}</p><div class="grid"><div class="metric"><b>${{s.candidate_count}}</b><span>generated</span></div><div class="metric"><b>${{s.final_gate_pass_count}}</b><span>final gate pass</span></div><div class="metric"><b>${{fmt(s.final_gate_pass_rate)}}</b><span>pass rate</span><div class="bar"><i style="width:${{100*s.final_gate_pass_rate}}%"></i></div></div><div class="metric"><b>${{s.missing_metric_count}}</b><span>missing metric cells</span></div></div><h3>Experiment contract</h3><p class="note">changed: ${{esc((s.changed_factors||[]).join(', ')||'未声明')}}<br>held: ${{esc((s.held_constant||[]).join(', ')||'未声明')}}<br>expected: ${{esc(s.expected_result||'未声明')}}<br>failure: ${{esc(s.failure_interpretation||'未声明')}}</p><h3>Failure rules</h3>${{table(['rule','count'],Object.entries(s.failure_rule_counts).map(([k,v])=>[esc(k),fmt(v)]))}}<h3>Metric summaries</h3>${{table(['metric','observed','missing','median','range','source'],s.metric_summaries.map(m=>[esc(m.metric_id),fmt(m.observed_count),fmt(m.missing_count),fmt(m.median),`${{fmt(m.minimum)}} – ${{fmt(m.maximum)}}`,esc(m.sources.join(', '))]))}}`;
const records=DATA.candidates.filter(x=>x.strategy_id===id);document.getElementById('candidates').innerHTML=`<h2>Candidate evidence</h2>${{table(['candidate','status','score','failed rules','shortlist role'],records.map(c=>[esc(c.candidate_id),c.eligible_unique_pass?'<span class="ok">unique pass</span>':'<span class="bad">failed/duplicate</span>',fmt(c.score_screen),esc(c.failed_rules.join(', ')||'—'),esc(c.review_roles.join(', ')||'—')]))}}`;
renderStructures(s)}}
function init(){{renderOverview();const list=document.getElementById('strategy-list');DATA.strategies.forEach((s,i)=>{{const b=document.createElement('button');b.dataset.id=s.strategy_id;b.innerHTML=`<b>${{esc(s.strategy_id)}}</b><small>${{esc(s.role||'unspecified')}} · ${{esc(s.scaffold_id)}} · ${{s.final_gate_pass_count}}/${{s.candidate_count}}</small>`;b.onclick=()=>renderStrategy(s.strategy_id);list.appendChild(b);if(i===0)renderStrategy(s.strategy_id)}});document.getElementById('provenance').innerHTML=`<h2>Provenance</h2>${{table(['artifact','sha256'],Object.entries(DATA.provenance.source_artifacts).map(([k,v])=>[esc(k),`<code>${{esc(v.sha256)}}</code>`]))}}<p class="note">generator ${{esc(DATA.generator.id)}} ${{esc(DATA.generator.version)}} · ${{esc(DATA.generated_at)}}</p>`}}init();</script>
</body></html>"""


def build_pilot_review(run_root: Path, output_root: Path) -> Path:
    root = run_root.expanduser().resolve(strict=True)
    context = WorkspaceContext.discover(root)
    destination = context.require_write_path(
        output_root.expanduser(), purpose="Result review 输出必须位于 current workspace"
    )
    if destination.exists():
        raise ValueError(f"Result review 输出目录必须不存在: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging_parent = context.runtime_root / "tmp"
    staging_parent.mkdir(parents=True, exist_ok=True)
    output = staging_parent / f".result-review-{uuid4().hex}.staging"
    output.mkdir()

    run, run_manifest_path = _current_run(root)
    stage03, stage03_path = _stage(root, run, StageId.BOLTZGEN_CONFIGURATION)
    stage04, stage04_path = _stage(root, run, StageId.PILOT_GENERATION)
    stage05, stage05_path = _stage(root, run, StageId.PILOT_FILTERING)
    strategy_path = _output(stage03, root, "strategy-bundle")
    candidate_path = _output(stage04, root, "candidate-index")
    report_path = _output(stage05, root, "pilot-filter-report")
    strategies = load_model(strategy_path, StrategyBundle)
    candidates = load_model(candidate_path, CandidateIndex)
    schema = json.loads(report_path.read_text(encoding="utf-8")).get("schema_version")
    report = load_model(
        report_path,
        PilotFilterReportV1_6 if schema == "0.2" else PilotFilterReport,
    )
    if strategies.target_structure_sha256 == "" or (
        strategies.run_id != run.run_id
        or candidates.strategy_bundle_sha256 != stage03.require_output("strategy-bundle").sha256
        or report.candidate_index_sha256 != stage04.require_output("candidate-index").sha256
    ):
        raise ValueError("Pilot review 输入 artifact identity 不一致")

    records_by_strategy: dict[str, list[Any]] = defaultdict(list)
    for record in report.candidate_records:
        records_by_strategy[record.strategy_id].append(record)
    index_by_id = {item.candidate_id: item for item in candidates.candidates}
    strategy_contract = {item.strategy_id: item for item in strategies.strategies}
    summaries = {item.strategy_id: item for item in report.strategy_summaries}
    if set(records_by_strategy) != set(summaries) or not set(summaries).issubset(
        strategy_contract
    ):
        raise ValueError("Pilot report、StrategyBundle 与 CandidateIndex strategy identity 不一致")

    structures: list[dict[str, Any]] = []
    representative_roles: dict[str, list[str]] = {}
    for _strategy_id, records in sorted(records_by_strategy.items()):
        selected = _select_representatives(records)
        representative_roles.update(selected)
        for candidate_id, roles in selected.items():
            candidate = index_by_id.get(candidate_id)
            if candidate is None:
                raise ValueError(f"shortlisted candidate 不在 CandidateIndex: {candidate_id}")
            structures.append(
                _candidate_structure(
                    output=output,
                    run_root=root,
                    candidate=candidate,
                    roles=roles,
                )
            )

    strategy_payload: list[dict[str, Any]] = []
    candidate_payload: list[dict[str, Any]] = []
    missing_total = 0
    for strategy_id, records in sorted(records_by_strategy.items()):
        summary = summaries[strategy_id]
        contract = strategy_contract[strategy_id]
        failures = Counter(
            decision.rule_id
            for record in records
            for decision in record.hard_gate_decisions
            if not decision.passed
        )
        missing_count = sum(
            1 for record in records for metric in record.metrics if not metric.available
        )
        missing_total += missing_count
        strategy_payload.append(
            {
                "strategy_id": strategy_id,
                "role": None if contract.role is None else str(contract.role),
                "hypothesis_id": contract.hypothesis_id,
                "scaffold_id": contract.scaffold_id,
                "region_id": contract.region_id,
                "binding_label_seq_ids": list(contract.binding_label_seq_ids),
                "candidate_count": summary.candidate_count,
                "unique_sequence_count": summary.unique_sequence_count,
                "final_gate_pass_count": summary.final_gate_pass_count,
                "final_gate_pass_rate": summary.final_gate_pass_rate,
                "score_yaml": summary.score_yaml,
                "tier": str(summary.tier),
                "changed_factors": list(contract.changed_factors),
                "held_constant": list(contract.held_constant),
                "expected_result": contract.expected_result,
                "failure_interpretation": contract.failure_interpretation,
                "failure_rule_counts": dict(sorted(failures.items())),
                "missing_metric_count": missing_count,
                "metric_summaries": _display_metrics(records),
            }
        )
        for record in sorted(records, key=lambda item: item.candidate_id):
            candidate_payload.append(
                {
                    "candidate_id": record.candidate_id,
                    "strategy_id": record.strategy_id,
                    "hard_gate_pass": record.hard_gate_pass,
                    "eligible_unique_pass": record.eligible_unique_pass,
                    "duplicate_of": record.duplicate_of,
                    "score_screen": record.score_screen,
                    "failed_rules": [
                        item.rule_id for item in record.hard_gate_decisions if not item.passed
                    ],
                    "review_roles": representative_roles.get(record.candidate_id, []),
                    "metrics": _metric_payload(record),
                }
            )

    source_artifacts = {
        "run-manifest": {
            "path": _relative_to_run(root, run_manifest_path),
            "sha256": sha256_file(run_manifest_path),
        },
        "stage03-manifest": {
            "path": _relative_to_run(root, stage03_path),
            "sha256": sha256_file(stage03_path),
        },
        "strategy-bundle": {
            "path": _relative_to_run(root, strategy_path),
            "sha256": sha256_file(strategy_path),
        },
        "stage04-manifest": {
            "path": _relative_to_run(root, stage04_path),
            "sha256": sha256_file(stage04_path),
        },
        "candidate-index": {
            "path": _relative_to_run(root, candidate_path),
            "sha256": sha256_file(candidate_path),
        },
        "stage05-manifest": {
            "path": _relative_to_run(root, stage05_path),
            "sha256": sha256_file(stage05_path),
        },
        "pilot-filter-report": {
            "path": _relative_to_run(root, report_path),
            "sha256": sha256_file(report_path),
        },
    }
    generated = datetime.now(tz=UTC).isoformat().replace("+00:00", "Z")
    payload: dict[str, Any] = {
        "schema_version": "0.1",
        "mode": SUPPORTED_MODE,
        "generated_at": generated,
        "generator": {"id": GENERATOR_ID, "version": GENERATOR_VERSION},
        "run": {
            "project_id": run.project_id,
            "run_id": run.run_id,
            "status": str(run.status),
            "evidence_status": str(run.evidence_status),
        },
        "profile": {
            "profile_id": report.profile_id,
            "profile_sha256": report.profile_sha256,
            "candidate_index_sha256": report.candidate_index_sha256,
            "target_chain_id": "A",
        },
        "denominator": {
            "planned": sum(item.candidates_per_strategy for item in strategies.strategies),
            "generated": len(candidates.candidates),
            "evaluable": len(report.candidate_records),
            "hard_gate_pass": sum(item.hard_gate_pass for item in report.candidate_records),
            "eligible_unique_pass": sum(
                item.eligible_unique_pass for item in report.candidate_records
            ),
            "missing_metric_cells": missing_total,
        },
        "strategies": strategy_payload,
        "candidates": candidate_payload,
        "structures": structures,
        "provenance": {"source_artifacts": source_artifacts},
        "limitations": [
            "This report does not recompute filters or scientific decisions.",
            "Shortlisted structures do not replace the complete denominator.",
            "Browser filtering cannot create promotion or selection receipts.",
        ],
    }
    data_path = output / "review-data.json"
    _write_exclusive(data_path, _json_bytes(payload))
    viewer_files = _copy_viewer_assets(context.root, output)
    embedded_structures = {
        item["candidate_id"]: base64.b64encode(
            (output / item["relative_path"]).read_bytes()
        ).decode("ascii")
        for item in structures
    }
    html_path = output / "index.html"
    _write_exclusive(
        html_path,
        _render_html(payload, embedded_structures).encode("utf-8"),
    )
    output_files = [
        data_path,
        html_path,
        *viewer_files,
        *(output / item["relative_path"] for item in structures),
    ]
    manifest = {
        "schema_version": "0.1",
        "report_type": "easydesign-result-review",
        "mode": SUPPORTED_MODE,
        "generated_at": generated,
        "generator": payload["generator"],
        "project_id": run.project_id,
        "run_id": run.run_id,
        "source_artifacts": source_artifacts,
        "files": [
            {
                "relative_path": path.relative_to(output).as_posix(),
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
            for path in sorted(output_files)
        ],
        "read_only": True,
        "scientific_artifact": False,
    }
    _write_exclusive(output / "review-manifest.json", _json_bytes(manifest))
    _fsync_directory(output)
    output.replace(destination)
    _fsync_directory(destination.parent)
    return destination / "index.html"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument(
        "--mode",
        choices=("pilot-review", "scale-selection-review"),
        default="pilot-review",
    )
    args = parser.parse_args(argv)
    if args.mode != SUPPORTED_MODE:
        parser.error(
            "scale-selection-review 尚未实现；需要正式 Stage 06/07 cluster/selection artifact 合同"
        )
    try:
        path = build_pilot_review(args.run_root, args.output_root)
    except Exception as error:  # deterministic CLI boundary
        print(f"result-review failed: {error}", file=sys.stderr)
        return 2
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
