import { useEffect, useMemo, useState } from "react";
import { api } from "./api";
import { MolViewer } from "./MolViewer";
import { stateCopy } from "./product";
import type {
  CandidateDetail,
  CandidatePage,
  FilterOverview,
  MetricPresentation,
  Run,
  Stage,
  Strategy,
} from "./types";

const phaseCopy = {
  pilot: "840 个小规模候选",
  expansion: "100 个扩展候选",
  "full-target": "10 个 Protenix 复核候选",
} as const;

const defaultColumns = [
  "hotspot-coverage",
  "design-to-target-iptm",
  "min-design-to-target-pae",
  "filter-rmsd-design",
  "bb_target_aligned_rmsd_design",
  "target-ca-rmsd",
];

function number(value: unknown, digits = 2) {
  if (typeof value !== "number") return value == null ? "—" : String(value);
  return new Intl.NumberFormat("zh-CN", { maximumFractionDigits: digits }).format(value);
}

function ruleName(value: string) {
  const names: Record<string, string> = {
    "require-boltzgen-pass": "BoltzGen 原始筛选未通过",
    "require-hotspot-coverage": "结合区域覆盖率未达门槛",
    "hotspot-coverage-gate": "结合区域覆盖率未达门槛",
    "require-iptm": "界面置信度未达门槛",
    "iptm-gate": "界面置信度未达门槛",
    "require-interface-pae": "界面预测误差未达门槛",
    "require-target-rmsd": "目标结构偏差超过门槛",
    "require-target-ca-rmsd": "目标结构偏差超过门槛",
    "forbid-severe-clash": "存在严重原子冲突",
    "require-zero-severe-clash": "存在严重原子冲突",
    "limit-moderate-clash": "中等原子冲突过多",
    "deduplicate-sequence": "序列重复",
    "require-binder-pose-rmsd": "结合位姿不稳定",
  };
  return names[value] || "其他已记录筛选规则";
}

function tierName(value: string) {
  const suffix = value.split("-").at(-1)?.toUpperCase();
  return suffix ? `等级 ${suffix}` : "—";
}

function aggregateName(value: string) {
  const names: Record<string, string> = {
    "hotspot-coverage": "结合区域覆盖率",
    "design-to-target-iptm": "界面 iPTM",
    "min-design-to-target-pae": "最小界面 PAE",
    "filter-rmsd-design": "设计链 RMSD",
    bb_target_aligned_rmsd_design: "目标对齐设计链 RMSD",
    "target-ca-rmsd": "目标 CA RMSD",
    "interface-bsa": "界面 BSA",
    "severe-clash-count": "严重冲突",
    "moderate-clash-count": "中等冲突",
  };
  return names[value] || value;
}

function structureDisplayName(value: string) {
  const names: Record<string, string> = {
    original: "BoltzGen 原始结构",
    refold: "BoltzGen 重折叠结构",
    protenix: "Protenix 复核结构",
  };
  return names[value] || value;
}

function thresholdText(metric: MetricPresentation) {
  if (metric.threshold == null || !metric.operator) return "未设置硬门";
  const operators: Record<string, string> = { ge: "≥", le: "≤", eq: "=", unique: "必须唯一" };
  return `${operators[metric.operator] || metric.operator} ${metric.threshold}`;
}

function Conclusion({
  overview,
  onSelect,
}: {
  overview: FilterOverview;
  onSelect: (tab: string) => void;
}) {
  return (
    <div className="filter-section">
      <section className="conclusion-panel">
        <div className="conclusion-icon">i</div>
        <div>
          <p className="section-label">本次运行结论</p>
          <h3>{overview.conclusion_title}</h3>
          <p>{overview.conclusion}</p>
        </div>
        <span className={`status status-${overview.state}`}>
          <span className="status-mark" />
          {stateCopy[overview.state].label}
        </span>
      </section>

      <section className="panel">
        <div className="panel-heading">
          <div>
            <p className="section-label">筛选步骤与真实数量</p>
            <h3>候选如何一步步减少</h3>
          </div>
          <span>点击步骤查看相应候选</span>
        </div>
        <div className="selection-chain">
          {overview.step_chain.map((step, index) => (
            <button
              type="button"
              key={step.id}
              onClick={() => onSelect(index < 2 ? "candidates" : index < 5 ? "strategies" : "candidates")}
            >
              <strong>{number(step.count, 0)}</strong>
              <span>{step.label}</span>
              {index < overview.step_chain.length - 1 && <i>→</i>}
            </button>
          ))}
        </div>
      </section>

      <div className="two-column">
        <section className="panel">
          <div className="panel-heading">
            <div><p className="section-label">最常见的淘汰原因</p><h3>硬门失败统计</h3></div>
          </div>
          <div className="failure-list">
            {Object.entries(overview.failed_rule_counts)
              .sort((a, b) => b[1] - a[1])
              .slice(0, 8)
              .map(([rule, count]) => (
                <div key={rule}>
                  <span>{ruleName(rule)}</span>
                  <div><i style={{ width: `${Math.min(100, count / Math.max(overview.counts.pilot, 1) * 100)}%` }} /></div>
                  <strong>{count}</strong>
                </div>
              ))}
          </div>
        </section>
        <section className="panel next-actions">
          <div className="panel-heading">
            <div><p className="section-label">下一步建议</p><h3>如何处理这个科学负结果</h3></div>
          </div>
          <ol>{overview.next_actions.map((action) => <li key={action}>{action}</li>)}</ol>
          <p>当前结论保持冻结，不会为了得到结果而自动降低门槛。</p>
        </section>
      </div>
    </div>
  );
}

function StrategyHeatmap({ strategies }: { strategies: Strategy[] }) {
  const regions = [...new Set(strategies.map((item) => item.region_id))];
  const scaffolds = [...new Set(strategies.map((item) => item.scaffold_id))];
  const byIdentity = new Map(strategies.map((item) => [`${item.region_id}:${item.scaffold_id}`, item]));
  return (
    <section className="panel">
      <div className="panel-heading">
        <div><p className="section-label">结合区域 × VHH 骨架</p><h3>21 个设计策略的真实表现</h3></div>
        <span>数字为最终门通过数，蓝框表示进入扩展</span>
      </div>
      <div className="strategy-heatmap">
        <div className="heatmap-corner">结合区域</div>
        {scaffolds.map((scaffold) => <strong key={scaffold}>{scaffold}</strong>)}
        {regions.flatMap((region) => [
          <strong className="heatmap-region" key={`${region}-label`}>{region}</strong>,
          ...scaffolds.map((scaffold) => {
            const item = byIdentity.get(`${region}:${scaffold}`);
            const intensity = Math.min(1, (item?.final_gate_pass_rate || 0) * 8);
            return (
              <button
                type="button"
                key={`${region}-${scaffold}`}
                className={item?.selected_for_expansion ? "selected" : ""}
                style={{ "--heat": intensity } as React.CSSProperties}
                title={item ? `${item.final_gate_pass_count}/${item.candidate_count} 通过` : "无数据"}
              >
                <b>{item?.final_gate_pass_count ?? "—"}</b>
                <small>{item ? tierName(item.tier) : "—"}</small>
              </button>
            );
          }),
        ])}
      </div>
    </section>
  );
}

function Strategies({ strategies }: { strategies: Strategy[] }) {
  return (
    <div className="filter-section">
      <StrategyHeatmap strategies={strategies} />
      <section className="panel table-panel">
        <div className="panel-heading">
          <div><p className="section-label">可排序明细</p><h3>全部策略</h3></div>
          <span>{strategies.length} 个策略</span>
        </div>
        <div className="table-wrap">
          <table>
            <thead><tr><th>区域</th><th>VHH 骨架</th><th>候选</th><th>去重序列</th><th>BoltzGen 硬门通过</th><th>最终门通过</th><th>通过率</th><th>策略等级</th><th>筛选中位数</th><th>前四分位均值</th><th>策略得分</th><th>配置</th><th>扩展</th></tr></thead>
            <tbody>
              {strategies.map((item) => (
                <tr key={item.strategy_id}>
                  <td><b>{item.region_id}</b></td>
                  <td>{item.scaffold_id}</td>
                  <td>{item.candidate_count}</td>
                  <td>{item.unique_sequence_count}</td>
                  <td>{item.hard_pass_count}</td>
                  <td>{item.final_gate_pass_count}</td>
                  <td>{number(item.final_gate_pass_rate * 100, 1)}%</td>
                  <td><span className={`tier tier-${item.tier.at(-1)?.toLowerCase()}`}>{tierName(item.tier)}</span></td>
                  <td>{number(item.score_screen, 3)}</td>
                  <td>{number(item.score_screen_top_quartile_mean, 3)}</td>
                  <td>{number(item.score_yaml, 3)}</td>
                  <td>
                    {item.yaml_artifact
                      ? <a className="text-link" href={`/api/v1/artifacts/${item.yaml_artifact.token}?download=true`}>下载 YAML</a>
                      : "未记录"}
                  </td>
                  <td>{item.selected_for_expansion ? "是" : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

function CandidateDrawer({
  detail,
  metrics,
  onClose,
}: {
  detail: CandidateDetail;
  metrics: MetricPresentation[];
  onClose: () => void;
}) {
  const [structureName, setStructureName] = useState(Object.keys(detail.structures)[0] || "");
  const selectedStructure = detail.structures[structureName];
  const grouped = useMemo(() => {
    const rows = new Map<string, Array<Record<string, unknown>>>();
    for (const item of detail.metrics) {
      const group = String(item.group || "其他指标");
      rows.set(group, [...(rows.get(group) || []), item]);
    }
    return rows;
  }, [detail]);
  return (
    <div className="drawer-backdrop" role="presentation" onMouseDown={onClose}>
      <aside className="candidate-drawer" role="dialog" aria-modal="true" onMouseDown={(event) => event.stopPropagation()}>
        <header>
          <div><p className="section-label">候选详情</p><h2>{detail.candidate_id}</h2><span>{detail.strategy_id}</span></div>
          <button type="button" onClick={onClose} aria-label="关闭候选详情">×</button>
        </header>
        {Object.keys(detail.structures).length > 0 && (
          <section className="candidate-structure">
            <div className="segmented">
              {Object.keys(detail.structures).map((name) => (
                <button className={name === structureName ? "active" : ""} type="button" key={name} onClick={() => setStructureName(name)}>{structureDisplayName(name)}</button>
              ))}
            </div>
            <MolViewer structureUrl={selectedStructure ? `/api/v1/artifacts/${selectedStructure.token}` : undefined} compact />
          </section>
        )}
        <section className="sequence-block">
          <span>设计序列</span>
          <code>{detail.sequence || "当前输出未提供序列"}</code>
        </section>
        {detail.failed_reasons.length > 0 && (
          <section className="failed-reasons">
            <h3>淘汰原因</h3>
            <ul>{detail.failed_reasons.map((reason) => <li key={reason}>{ruleName(reason)}</li>)}</ul>
          </section>
        )}
        {[...grouped.entries()].map(([group, rows]) => (
          <section className="detail-metrics" key={group}>
            <h3>{group}</h3>
            {rows.map((item) => {
              const definition = metrics.find((value) => value.metric_id === item.metric_id);
              return (
                <div key={String(item.metric_id)}>
                  <span><b>{String(item.name)}</b><small>{definition?.source || String(item.source || "")}</small></span>
                  <strong>{number(item.value)} {String(item.unit || "")}</strong>
                </div>
              );
            })}
          </section>
        ))}
        <section className="decision-table">
          <h3>逐条规则</h3>
          {detail.decisions.map((item) => (
            <div key={String(item.rule_id)} className={item.passed ? "passed" : "failed"}>
              <span>{ruleName(String(item.rule_id))}</span>
              <code>{String(item.observed ?? "缺失")} {String(item.operator)} {String(item.threshold)}</code>
              <b>{item.passed ? "通过" : "未通过"}</b>
            </div>
          ))}
        </section>
      </aside>
    </div>
  );
}

function Candidates({
  run,
  metrics,
}: {
  run: Run;
  metrics: MetricPresentation[];
}) {
  const [phase, setPhase] = useState<keyof typeof phaseCopy>("pilot");
  const [page, setPage] = useState(1);
  const [gateStatus, setGateStatus] = useState("");
  const [data, setData] = useState<CandidatePage>();
  const [detail, setDetail] = useState<CandidateDetail>();
  const [loading, setLoading] = useState(false);
  const columns = phase === "full-target"
    ? ["protenix-target-rmsd", "protenix-binder-pose-rmsd", "protenix-pairwise-iptm", "protenix-min-interface-pae", "binder-ptm"]
    : defaultColumns;

  useEffect(() => {
    setLoading(true);
    api.filterCandidates(run.run_key, { phase, page, pageSize: 50, gateStatus })
      .then(setData)
      .finally(() => setLoading(false));
  }, [gateStatus, page, phase, run.run_key]);

  function selectPhase(value: keyof typeof phaseCopy) {
    setPhase(value);
    setPage(1);
    setDetail(undefined);
  }

  async function openCandidate(candidateId: string) {
    setDetail(await api.filterCandidate(run.run_key, candidateId, phase));
  }

  return (
    <div className="filter-section">
      <section className="panel candidate-browser">
        <div className="candidate-toolbar">
          <div className="segmented">
            {(Object.keys(phaseCopy) as Array<keyof typeof phaseCopy>).map((value) => (
              <button type="button" className={phase === value ? "active" : ""} onClick={() => selectPhase(value)} key={value}>{phaseCopy[value]}</button>
            ))}
          </div>
          <label>筛选结论
            <select value={gateStatus} onChange={(event) => { setGateStatus(event.target.value); setPage(1); }}>
              <option value="">全部</option>
              <option value="通过">通过</option>
              <option value="未通过">未通过</option>
            </select>
          </label>
        </div>
        <div className="panel-heading">
          <div><p className="section-label">候选筛选</p><h3>{phaseCopy[phase]}</h3></div>
          <span>{loading ? "正在读取…" : `共 ${data?.total || 0} 个`}</span>
        </div>
        <div className="table-wrap">
          <table className="candidate-table">
            <thead><tr><th>候选</th><th>策略</th><th>结论</th><th>综合得分</th>{columns.map((id) => <th key={id}>{metrics.find((item) => item.metric_id === id)?.name || id}</th>)}<th /></tr></thead>
            <tbody>
              {(data?.items || []).map((item) => (
                <tr key={item.candidate_id}>
                  <td><code>{item.candidate_id}</code></td>
                  <td>{item.strategy_id}</td>
                  <td><span className={item.gate_status === "通过" ? "pass-text" : "fail-text"}>{item.gate_status}</span></td>
                  <td>{number(item.score, 3)}</td>
                  {columns.map((id) => <td key={id}>{number(item.metrics[id])}</td>)}
                  <td><button className="text-button" type="button" onClick={() => openCandidate(item.candidate_id)}>查看详情</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <footer className="pagination">
          <button type="button" disabled={!data || data.page <= 1} onClick={() => setPage((value) => value - 1)}>上一页</button>
          <span>第 {data?.page || 1} / {data?.total_pages || 1} 页</span>
          <button type="button" disabled={!data || data.page >= data.total_pages} onClick={() => setPage((value) => value + 1)}>下一页</button>
        </footer>
      </section>
      {detail && <CandidateDrawer detail={detail} metrics={metrics} onClose={() => setDetail(undefined)} />}
    </div>
  );
}

function EvidenceOverview({
  run,
  overview,
  strategies,
  metrics,
}: {
  run: Run;
  overview: FilterOverview;
  strategies: Strategy[];
  metrics: MetricPresentation[];
}) {
  const [localPass, setLocalPass] = useState<CandidatePage>();
  const [fullTarget, setFullTarget] = useState<CandidatePage>();
  const [detail, setDetail] = useState<CandidateDetail>();
  const [loadError, setLoadError] = useState("");

  useEffect(() => {
    Promise.all([
      api.filterCandidates(run.run_key, {
        phase: "expansion",
        pageSize: 100,
        gateStatus: "通过",
        sortKey: "score",
        sortOrder: "desc",
      }),
      api.filterCandidates(run.run_key, {
        phase: "full-target",
        pageSize: 100,
        sortKey: "protenix-binder-pose-rmsd",
        sortOrder: "asc",
      }),
    ]).then(([nextLocalPass, nextFullTarget]) => {
      setLocalPass(nextLocalPass);
      setFullTarget(nextFullTarget);
    }).catch((value) => {
      setLoadError(value instanceof Error ? value.message : "候选证据读取失败");
    });
  }, [run.run_key]);

  async function openCandidate(candidateId: string, phase: "expansion" | "full-target") {
    setDetail(await api.filterCandidate(run.run_key, candidateId, phase));
  }

  const tierOrder: Record<string, number> = {
    "tier-a": 0,
    "tier-b": 1,
    "tier-c": 2,
    "tier-d": 3,
  };
  const leadingStrategies = [...strategies]
    .sort((left, right) => (
      (tierOrder[left.tier] ?? 99) - (tierOrder[right.tier] ?? 99)
      || right.score_yaml - left.score_yaml
    ))
    .filter((item) => item.tier === "tier-a" || item.tier === "tier-b");
  const protenixIds = new Set((fullTarget?.items || []).map((item) => item.candidate_id));
  const bestPrediction = fullTarget?.items[0];

  return (
    <div className="filter-section evidence-first">
      <section className="evidence-result-header">
        <div>
          <p className="section-label">第5步结果</p>
          <h3>筛选工作已经完成，已有多层结构证据可供审阅</h3>
          <p>
            本次运行完成了 {overview.counts.pilot} 个小规模候选、{overview.counts.expanded} 个扩展候选和
            {" "}{overview.counts.full_target} 个 Protenix 复核。最终停止只表示没有候选达到第6步门槛。
          </p>
        </div>
        <div className="evidence-stop-summary">
          <strong>第6步未解锁</strong>
          <span>程序正常完成 · 科学门槛未通过</span>
        </div>
      </section>

      <StrategyHeatmap strategies={strategies} />

      <section className="strategy-evidence-grid">
        <div className="tier-summary panel">
          <div className="panel-heading">
            <div><p className="section-label">策略分层</p><h3>Tier 分布</h3></div>
            <span>全部 {strategies.length} 个 YAML</span>
          </div>
          <div className="tier-counts">
            {["tier-a", "tier-b", "tier-c", "tier-d"].map((tier) => (
              <article key={tier}>
                <span>{tierName(tier)}</span>
                <strong>{overview.tier_counts[tier] || 0}</strong>
                <small>
                  {tier === "tier-a" ? "至少 2 个最终门候选" : tier === "tier-b" ? "1 个最终门候选" : tier === "tier-c" ? "存在硬门信号" : "未形成可扩展信号"}
                </small>
              </article>
            ))}
          </div>
        </div>
        <div className="leading-strategies panel">
          <div className="panel-heading">
            <div><p className="section-label">优先策略证据</p><h3>等级 A 与等级 B</h3></div>
            <span>均值不填补缺失值</span>
          </div>
          <div className="leading-strategy-list">
            {leadingStrategies.map((strategy) => (
              <article key={strategy.strategy_id}>
                <header>
                  <div>
                    <span>区域 {strategy.region_id} × {strategy.scaffold_id}</span>
                    <strong>{tierName(strategy.tier)}</strong>
                  </div>
                  {strategy.yaml_artifact && (
                    <a href={`/api/v1/artifacts/${strategy.yaml_artifact.token}?download=true`}>
                      下载 YAML
                    </a>
                  )}
                </header>
                <div className="strategy-score-strip">
                  <span>最终门 {strategy.final_gate_pass_count}/{strategy.candidate_count}</span>
                  <span>筛选中位数 {number(strategy.score_screen, 3)}</span>
                  <span>前四分位均值 {number(strategy.score_screen_top_quartile_mean, 3)}</span>
                  <span>策略得分 {number(strategy.score_yaml, 3)}</span>
                </div>
                <dl>
                  {strategy.metric_aggregates.slice(0, 6).map((metric) => (
                    <div key={metric.metric_id}>
                      <dt>{aggregateName(metric.metric_id)}</dt>
                      <dd>{number(metric.mean, 3)} <small>均值 · n={metric.observed_count}</small></dd>
                    </div>
                  ))}
                </dl>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="panel evidence-candidate-panel">
        <div className="panel-heading">
          <div>
            <p className="section-label">初步结构筛选</p>
            <h3>{localPass?.total ?? overview.counts.local_gate_pass} 个候选值得查看结构</h3>
          </div>
          <span>按已有 S_expand_structure 从高到低排列</span>
        </div>
        {loadError && <div className="notice error"><strong>候选证据读取失败</strong><span>{loadError}</span></div>}
        <div className="highlight-candidate-grid">
          {(localPass?.items || []).map((candidate, index) => (
            <button
              type="button"
              key={candidate.candidate_id}
              onClick={() => openCandidate(candidate.candidate_id, "expansion")}
            >
              <header>
                <span>#{String(index + 1).padStart(2, "0")}</span>
                <strong>{candidate.candidate_id}</strong>
                <i className={protenixIds.has(candidate.candidate_id) ? "reviewed" : ""}>
                  {protenixIds.has(candidate.candidate_id) ? "已做 Protenix 复核" : "未进入 Protenix Top 10"}
                </i>
              </header>
              <dl>
                <div><dt>结构得分</dt><dd>{number(candidate.score, 3)}</dd></div>
                <div><dt>结合区域覆盖率</dt><dd>{number(candidate.metrics["hotspot-coverage"], 3)}</dd></div>
                <div><dt>界面 iPTM</dt><dd>{number(candidate.metrics["design-to-target-iptm"], 3)}</dd></div>
                <div><dt>目标 CA RMSD</dt><dd>{number(candidate.metrics["target-ca-rmsd"])} Å</dd></div>
              </dl>
              <span className="candidate-open">查看指标与三维结构 →</span>
            </button>
          ))}
        </div>
      </section>

      <section className="panel protenix-evidence">
        <div className="panel-heading">
          <div>
            <p className="section-label">完整目标复核</p>
            <h3>{fullTarget?.total ?? overview.counts.full_target} 个 Protenix 结果仍然是有效证据</h3>
          </div>
          <span>按观测到的结合位姿 RMSD 从低到高</span>
        </div>
        {bestPrediction && (
          <div className="best-observed">
            <span>当前观测到的最低结合位姿 RMSD</span>
            <strong>{number(bestPrediction.metrics["protenix-binder-pose-rmsd"])} Å</strong>
            <p>{bestPrediction.candidate_id} · 仍未达到通过门槛，不代表胜出候选。</p>
          </div>
        )}
        <div className="table-wrap">
          <table>
            <thead><tr><th>候选</th><th>目标 RMSD</th><th>结合位姿 RMSD</th><th>界面 iPTM</th><th>最小界面 PAE</th><th>结论</th><th /></tr></thead>
            <tbody>
              {(fullTarget?.items || []).map((candidate) => (
                <tr key={candidate.candidate_id}>
                  <td><code>{candidate.candidate_id}</code></td>
                  <td>{number(candidate.metrics["protenix-target-rmsd"])} Å</td>
                  <td><b className="pose-value">{number(candidate.metrics["protenix-binder-pose-rmsd"])} Å</b></td>
                  <td>{number(candidate.metrics["protenix-pairwise-iptm"], 3)}</td>
                  <td>{number(candidate.metrics["protenix-min-interface-pae"])} Å</td>
                  <td><span className="fail-text">{candidate.gate_status}</span></td>
                  <td><button className="text-button" type="button" onClick={() => openCandidate(candidate.candidate_id, "full-target")}>查看结构</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="compact-science-stop">
        <div>
          <p className="section-label">进入第6步的判断</p>
          <h3>{overview.conclusion_title}</h3>
          <p>{overview.conclusion} 上述策略、指标和结构证据仍然保留并可下载。</p>
        </div>
        <span className={`status status-${overview.state}`}>
          <span className="status-mark" />
          {stateCopy[overview.state].label}
        </span>
      </section>

      {detail && (
        <CandidateDrawer
          detail={detail}
          metrics={metrics}
          onClose={() => setDetail(undefined)}
        />
      )}
    </div>
  );
}

function Glossary({ metrics }: { metrics: MetricPresentation[] }) {
  const groups = [...new Set(metrics.map((metric) => metric.group))];
  return (
    <div className="metric-catalog">
      {groups.map((group) => (
        <section className="panel" key={group}>
          <div className="panel-heading"><div><p className="section-label">指标组</p><h3>{group}</h3></div></div>
          <div className="catalog-grid">
            {metrics.filter((metric) => metric.group === group).map((metric) => (
              <article key={metric.metric_id}>
                <div><h4>{metric.name}</h4>{metric.abbreviation && <span>{metric.abbreviation}</span>}</div>
                <p>{metric.definition}</p>
                <dl>
                  <div><dt>来源</dt><dd>{metric.source}</dd></div>
                  <div><dt>判断方向</dt><dd>{metric.direction}</dd></div>
                  <div><dt>用途</dt><dd>{metric.role}</dd></div>
                  <div><dt>当前门槛</dt><dd>{thresholdText(metric)}</dd></div>
                </dl>
              </article>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}

export function StageFive({ stage, run }: { stage: Stage; run: Run }) {
  const [tab, setTab] = useState("evidence");
  const [overview, setOverview] = useState<FilterOverview>();
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [metrics, setMetrics] = useState<MetricPresentation[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([
      api.filterOverview(run.run_key),
      api.filterStrategies(run.run_key),
      api.filterMetrics(run.run_key),
    ]).then(([nextOverview, nextStrategies, nextMetrics]) => {
      setOverview(nextOverview);
      setStrategies(nextStrategies);
      setMetrics(nextMetrics);
    }).catch((value) => setError(value instanceof Error ? value.message : "无法读取筛选结果"));
  }, [run.run_key]);

  if (error) return <div className="notice error"><strong>筛选数据读取失败</strong><span>{error}</span></div>;
  if (!overview) return <div className="loading-block">正在验证并整理第5步结果…</div>;
  return (
    <div className="stage-five">
      <nav className="analysis-tabs" aria-label="筛选分析视图">
        {[
          ["evidence", "筛选证据"],
          ["strategies", "策略比较"],
          ["candidates", "候选筛选"],
          ["metrics", "指标说明"],
          ["conclusion", "结论与原因"],
        ].map(([id, label]) => <button type="button" className={tab === id ? "active" : ""} onClick={() => setTab(id)} key={id}>{label}</button>)}
      </nav>
      {tab === "evidence" && <EvidenceOverview run={run} overview={overview} strategies={strategies} metrics={metrics} />}
      {tab === "conclusion" && <Conclusion overview={overview} onSelect={setTab} />}
      {tab === "strategies" && <Strategies strategies={strategies} />}
      {tab === "candidates" && <Candidates run={run} metrics={metrics} />}
      {tab === "metrics" && <Glossary metrics={metrics} />}
      <p className="science-footnote">筛选规则和阈值来自已冻结的第5步运行记录；本页面不会重新计算或改变本次科学结论。当前步骤状态：{stateCopy[stage.state].label}。</p>
    </div>
  );
}
