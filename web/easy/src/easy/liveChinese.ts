import type { Decision, GateOption } from './product-contracts';

const STAGE_NAMES = [
  '靶点确认',
  '位点选择',
  '方案设计',
  '小规模验证',
  '扩大验证',
  '候选分子',
] as const;

const PHASE_NAMES: Record<string, string> = {
  target: STAGE_NAMES[0],
  site: STAGE_NAMES[1],
  design: STAGE_NAMES[2],
  pilot: STAGE_NAMES[3],
  scale: STAGE_NAMES[4],
  candidates: STAGE_NAMES[5],
  handoff: STAGE_NAMES[5],
};

const STATUS_NAMES: Record<string, string> = {
  awaiting_scientist: '等待审批',
  available: '可以继续',
  running: '正在运行',
  accepted: '正在处理',
  complete: '已完成',
  completed: '已完成',
  finished: '已完成',
  incomplete: '需要处理',
  failed: '运行失败',
  paused: '已暂停',
  waiting: '等待中',
};

const CONNECTION_NAMES: Record<string, string> = {
  loading: '正在连接',
  connected: '已连接',
  reconnecting: '正在重新连接',
  'authentication-required': '需要验证',
};

const GATE_TITLES: Record<number, string> = {
  1: '确认靶点和参考结构',
  2: '选择并批准结合位点',
  3: '批准设计方案和小规模验证计划',
  4: '决定是否进入扩大验证',
  5: '确认最终候选方案',
};

const GATE_INTROS: Record<number, string> = {
  1: '系统已推荐与目标匹配的结构和链，请确认后继续。',
  2: '请比较候选位点；默认选中系统推荐项，也可以自行选择。',
  3: '请确认设计约束和小规模验证计划。',
  4: '请根据小规模验证结果决定是否进入扩大验证。',
  5: '请确认最终候选及其排序，完成本轮设计。',
};

const LIVE_SCIENTIFIC_TERMS: ReadonlyArray<[RegExp, string]> = [
  [
    /region-A-has-2-spatial-components;user-members-preserved/gi,
    '位点 A 包含两个空间组分；已保留用户指定残基',
  ],
  [/approach_validation\s+not-performed/gi, '尚未进行接近路径验证'],
  [/region-A-has-2-spatial-components/gi, '位点 A 包含两个空间组分'],
  [/user-members-preserved/gi, '已保留用户指定残基'],
  [/\bGate\s*([1-5])\b/gi, '第 $1 关'],
  [/\binverse[ -]?fold(?:ing)?\b/gi, '逆向折叠'],
  [/\bnative[ -]?filter(?:ing)?\b/gi, '原生筛选'],
  [/\bTarget\b/gi, '靶点'],
  [/\bSites?\b/gi, '位点'],
  [/\bDesign\b/gi, '设计方案'],
  [/\bPilot\b/gi, '小规模验证'],
  [/\bScale\b/gi, '扩大验证'],
  [/\bCandidates?\b/gi, '候选分子'],
  [/\bScientist\b/gi, '科学家'],
  [/\bAgents?\b/gi, '设计助手'],
  [/\bhotspots?\b/gi, '热点残基'],
  [/\bscaffolds?\b/gi, '骨架'],
  [/\bbinders?\b/gi, '结合分子'],
  [/\bprimary\b/gi, '主候选'],
  [/\bbackups?\b/gi, '备选'],
  [/\boverride\b/gi, '越权批准'],
  [/\bavoid\b/gi, '应避免'],
  [/\bINCONCLUSIVE\b/g, '结论不确定'],
  [/\bnot-performed\b/gi, '尚未执行'],
];

/**
 * Scientific localization may intentionally preserve acronyms and named tools.
 * Normalize only product workflow vocabulary so live approvals remain concise
 * Chinese without rewriting VHH, PDB, UniProt, YAML, AFO or BoltzGen.
 */
export function normalizeLiveScientificChinese(value: string): string {
  return LIVE_SCIENTIFIC_TERMS.reduce(
    (localized, [pattern, replacement]) => localized.replace(pattern, replacement),
    value,
  );
}

export function liveStageName(stage: string | number): string {
  if (typeof stage === 'number') return STAGE_NAMES[stage] || '研究阶段';
  return PHASE_NAMES[stage.toLowerCase()] || '研究阶段';
}

export function liveStatusName(status: string): string {
  return STATUS_NAMES[status.toLowerCase()] || '处理中';
}

export function liveConnectionName(connection: string): string {
  return CONNECTION_NAMES[connection.toLowerCase()] || '连接状态未知';
}

export function liveActionName(stage: string): string {
  const value = stage.toLowerCase();
  if (value.includes('complete') || value.includes('finished')) return '当前阶段已完成';
  if (value.includes('reconcile')) return '正在核对已完成的运行记录';
  if (value.includes('scientist') || value.includes('gate')) return '等待科学家审批';
  if (value.includes('target')) return '正在整理靶点和结构信息';
  if (value.includes('site')) return '正在比较候选结合位点';
  if (value.includes('design') || value.includes('binder')) return '正在整理设计方案';
  if (value.includes('pilot')) return '正在执行小规模验证';
  if (value.includes('scale')) return '正在执行扩大验证';
  if (value.includes('candidate') || value.includes('handoff')) return '正在整理最终候选';
  return '正在处理当前步骤';
}

export function gateTitle(gate: number): string {
  return GATE_TITLES[gate] || '确认当前科学决策';
}

export function gateIntro(gate: number): string {
  return GATE_INTROS[gate] || '请检查当前建议和风险后作出决定。';
}

const GATE4_OPTIONS: Record<string, { label: string; description: string }> = {
  PROMOTE_TO_SCALE: {
    label: '进入扩大验证',
    description: '按已审查的策略和候选分配开展扩大验证。',
  },
  RUN_ANOTHER_PILOT: {
    label: '再进行一轮小规模验证',
    description: '制定新的小规模验证计划；再次获得你的明确批准后才会运行。',
  },
  REVISE_DESIGN: {
    label: '修改设计方案',
    description: '返回方案设计，根据本轮诊断修改设计约束与策略。',
  },
  REVISE_SITE: {
    label: '重新选择结合位点',
    description: '返回位点选择，同时保留已经验证的靶点证据。',
  },
  STOP: {
    label: '停止本次设计',
    description: '停止后续计算，并保留全部已有结果和审计记录。',
  },
};

const GATE5_OPTIONS: Record<string, { label: string; description: string }> = {
  'wet-lab-panel': {
    label: '确认最终候选并生成交接方案',
    description: '确认主候选与备选列表，生成模拟下单所需的交接信息；不会授权真实实验或采购。',
  },
  'revise-final-selection': {
    label: '调整最终候选',
    description: '返回候选筛选，根据现有证据调整主候选、备选及其排序。',
  },
  stop: {
    label: '停止并保留结果',
    description: '停止本次设计，不生成实验交接方案，并保留全部已有结果。',
  },
};

function gate4ScaleDescription(decision: Decision): string | null {
  const interpretation = decision.summary?.proposed_interpretation;
  if (!interpretation || typeof interpretation !== 'object') return null;
  const value = interpretation as Record<string, unknown>;
  const strategies = Array.isArray(value.selected_strategy_ids)
    ? value.selected_strategy_ids.filter((item): item is string => typeof item === 'string')
    : [];
  const requested =
    typeof value.requested_scale_candidates === 'number' ? value.requested_scale_candidates : null;
  const allocations =
    value.production_strategy_allocations &&
    typeof value.production_strategy_allocations === 'object'
      ? (value.production_strategy_allocations as Record<string, unknown>)
      : {};
  if (!strategies.length || requested === null) return null;
  const allocationText = strategies
    .map((strategy) => {
      const scaffold = strategy.includes('-scaffold-')
        ? strategy.split('-scaffold-').pop()!.toUpperCase()
        : strategy;
      const count = allocations[strategy];
      return typeof count === 'number' ? `骨架 ${scaffold}：${count} 个` : `骨架 ${scaffold}`;
    })
    .join('；');
  return `将小规模验证支持的 ${strategies.length} 条策略进入扩大验证，共 ${requested} 个候选（${allocationText}）。`;
}

export function gateOptionFallback(
  decision: Decision,
  option: GateOption,
  index: number,
): { label: string; description: string } {
  const recommended = option.option_id === decision.default_option_id ? '（推荐）' : '';
  const blocked = option.eligible ? '' : '当前不可选择';
  if (decision.gate === 1)
    return {
      label: `推荐靶点结构${recommended}`,
      description: blocked || '结构和目标链已完成一致性检查。',
    };
  if (decision.gate === 2)
    return {
      label: `位点 ${option.rank || String.fromCharCode(65 + index)}${recommended}`,
      description: blocked || '正在整理该位点的科学依据。',
    };
  if (decision.gate === 3)
    return {
      label: `设计方案${recommended}`,
      description: blocked,
    };
  if (decision.gate === 4) {
    const copy = GATE4_OPTIONS[option.option_id] || {
      label: `后续路径 ${index + 1}`,
      description: '按当前小规模验证证据选择后续路径。',
    };
    const description =
      option.option_id === 'PROMOTE_TO_SCALE'
        ? gate4ScaleDescription(decision) || copy.description
        : copy.description;
    return {
      label: `${copy.label}${recommended}`,
      description: blocked ? `当前不可选择：${description}` : description,
    };
  }
  if (decision.gate === 5) {
    const copy = GATE5_OPTIONS[option.option_id] || {
      label: `候选处理路径 ${index + 1}`,
      description: '根据候选排序和证据选择后续处理方式。',
    };
    return {
      label: `${copy.label}${recommended}`,
      description: blocked ? `当前不可选择：${copy.description}` : copy.description,
    };
  }
  return { label: `方案 ${index + 1}${recommended}`, description: blocked || '正在整理科学依据。' };
}

export function liveInputTypeName(id: string): string {
  return (
    {
      description: '自然语言描述',
      'protein-name': '蛋白质或基因名称',
      uniprot: 'UniProt 编号',
      'pdb-id': 'PDB 编号',
      structure: '结构文件',
      sequence: '序列或 FASTA',
    }[id] || '输入'
  );
}
