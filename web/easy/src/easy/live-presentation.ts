import type { ProductSnapshot } from './product-contracts';

export interface EasyActivitySummary {
  id: string;
  title: string;
  summary: string;
  status: 'running' | 'completed' | 'waiting';
}

const RUNNING_COPY: Record<string, string> = {
  target: '正在确认目标与结构',
  site: '正在比较结合位点',
  design: '正在整理设计方案',
  pilot: '正在验证候选结构',
  scale: '正在扩展候选验证',
  candidates: '正在整理候选结论',
  handoff: '正在准备最终交付',
};

const READY_COPY: Record<string, string> = {
  target: '目标与结构已整理',
  site: '结合位点已整理',
  design: '设计方案已整理',
  pilot: '候选结构已整理',
  scale: '扩展验证已整理',
  candidates: '候选结论已整理',
  handoff: '最终交付已整理',
};

export function summarizeGoal(goal: string, maximum = 120): string {
  const compact = goal.replace(/\s+/g, ' ').trim();
  const boundary = compact.search(/[。！？!?]|\.(?:\s|$)/);
  const sentence = boundary >= 0 ? compact.slice(0, boundary + 1).trim() : compact;
  return sentence.length <= maximum ? sentence : `${sentence.slice(0, maximum - 1).trim()}…`;
}

export function awaitingDecisionRecovery(snapshot: ProductSnapshot): boolean {
  return snapshot.project.status === 'awaiting_scientist' && snapshot.decision === null;
}

export function summarizeEasyActivity(snapshot: ProductSnapshot): EasyActivitySummary[] {
  const raw = (snapshot.recent_activity || []).filter((item) => item.visible !== false);
  const awaiting = snapshot.project.status === 'awaiting_scientist' || snapshot.decision !== null;
  const completed = ['complete', 'finished'].includes(snapshot.project.status);
  const available = snapshot.project.status === 'available';
  const phase = snapshot.project.phase;
  const reviewComplete = raw.some((item) => {
    const text =
      `${item.type} ${item.title || ''} ${item.summary || item.text || ''}`.toLowerCase();
    const passed = ['complete', 'completed', 'succeeded'].includes(item.status || '');
    return (
      text.includes('independent review ready') ||
      text.includes('independent evidence review was recorded') ||
      (passed && text.includes('judge') && (text.includes('passed') || text.includes('recorded')))
    );
  });
  const rows: EasyActivitySummary[] = [
    {
      id: 'phase-summary',
      title:
        awaiting || completed || available
          ? READY_COPY[phase] || '当前阶段已整理'
          : RUNNING_COPY[phase] || '正在推进当前阶段',
      summary: awaiting
        ? '推荐方案和必要证据已经整理完成。'
        : completed
          ? '当前设计流程已完成。'
          : available
            ? '当前步骤已准备好，系统将继续推进。'
            : '设计助手正在处理当前阶段。',
      status: awaiting || completed || available ? 'completed' : 'running',
    },
  ];
  if (reviewComplete) {
    rows.push({
      id: 'review-summary',
      title: '独立审查已完成',
      summary: '证据与规则检查已经记录。',
      status: 'completed',
    });
  }
  if (awaiting) {
    rows.push({
      id: 'approval-summary',
      title: '等待你批准',
      summary: '请检查推荐方案，然后选择批准或修改。',
      status: 'waiting',
    });
  }
  return rows.slice(-3);
}
