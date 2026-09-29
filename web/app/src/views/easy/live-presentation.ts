import type { ProductSnapshot } from './product-contracts';
import { appI18n } from '../../shell/I18nProvider';

const easyT = (key: string): string => appI18n.t(key, { ns: 'easy' });

export interface EasyActivitySummary {
  id: string;
  title: string;
  summary: string;
  status: 'running' | 'completed' | 'waiting';
}

const RUNNING_COPY: Record<string, string> = {
  target: 'Confirming the target and structure',
  site: 'Comparing binding sites',
  design: 'Preparing the design plan',
  pilot: 'Validating candidate structures',
  scale: 'Expanding candidate validation',
  candidates: 'Preparing candidate conclusions',
  handoff: 'Preparing the final handoff',
};

const READY_COPY: Record<string, string> = {
  target: 'Target and structure ready',
  site: 'Binding sites ready',
  design: 'Design plan ready',
  pilot: 'Candidate structures ready',
  scale: 'Expanded validation ready',
  candidates: 'Candidate conclusions ready',
  handoff: 'Final handoff ready',
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
  const blocked = ['blocked', 'incomplete'].includes(snapshot.project.status);
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
      title: easyT(
        blocked && !awaiting
          ? 'The current execution is incomplete'
          : awaiting || completed || available
            ? READY_COPY[phase] || 'Current stage ready'
            : RUNNING_COPY[phase] || 'Advancing the current stage',
      ),
      summary: easyT(
        awaiting
          ? 'The recommended plan and required evidence are ready.'
          : completed
            ? 'The current design flow is complete.'
            : blocked
              ? 'The current execution has stopped; evidence and recovery state are retained.'
              : available
                ? 'The current step is ready; the system will continue.'
                : 'The science Agent is working on the current stage.',
      ),
      status:
        blocked && !awaiting
          ? 'waiting'
          : awaiting || completed || available
            ? 'completed'
            : 'running',
    },
  ];
  if (reviewComplete) {
    rows.push({
      id: 'review-summary',
      title: easyT('Independent review complete'),
      summary: easyT('Evidence and rule checks have been recorded.'),
      status: 'completed',
    });
  }
  if (awaiting) {
    rows.push({
      id: 'approval-summary',
      title: easyT('Waiting for your approval'),
      summary: easyT('Review the recommended plan, then choose approve or revise.'),
      status: 'waiting',
    });
  }
  return rows.slice(-3);
}
