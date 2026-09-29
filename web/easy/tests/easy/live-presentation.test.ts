import { describe, expect, it } from 'vitest';
import {
  awaitingDecisionRecovery,
  shouldShowGateRiskDisclosure,
  summarizeEasyDesignPlan,
  summarizeEasyActivity,
  summarizeGoal,
} from '../../src/easy/live-presentation';
import type { ProductSnapshot } from '../../src/easy/product-contracts';

function snapshot(): ProductSnapshot {
  return {
    schema_version: '1',
    mode: 'live',
    revision: 'a'.repeat(64),
    project: {
      id: 'easy-project',
      title: 'Easy project',
      goal: 'Design an NK2R VHH.',
      phase: 'design',
      status: 'awaiting_scientist',
      thread_id: 'thread',
      last_activity: 9,
      validation_only: false,
    },
    workflow: [],
    current_action: { id: 'action', stage: 'scientist-gate', message: '', resumable: false },
    specialists: [],
    scientific_context: { structure: null, sites: [], arms: [] },
    decision: {
      id: 'card',
      gate: 3,
      type: 'design',
      question: 'Approve this design?',
      default_option_id: 'approve',
      options: [{ option_id: 'approve', eligible: true, actions: ['approve'] }],
      warnings: [],
      limitations: [],
      action_summary: 'Approve or revise.',
      revision_targets: ['design'],
      review_status: 'SUPPORTED',
      required_fields: {},
      summary: {},
    },
    jobs: [],
    artifacts: [],
    recent_activity: [
      {
        id: 1,
        type: 'judge.completed',
        title: 'Independent review ready',
        summary: 'The independent evidence review was recorded for the current Gate.',
        status: 'completed',
      },
      {
        id: 2,
        type: 'gate.awaiting',
        title: 'Scientist Gate',
        summary: 'The reviewed decision is awaiting explicit Scientist authority.',
        status: 'running',
      },
    ],
    tasks: [],
    lifecycle: 'scientific_project',
    event_cursor: 9,
    candidates: { total: 0, counts: {}, url: '/candidates' },
    capabilities: { decide: true },
    requests: [],
    lab_order: null,
    connection: 'connected',
  };
}

describe('Easy live presentation', () => {
  it('shows one compact goal sentence rather than the complete prompt', () => {
    expect(
      summarizeGoal(
        '请为人源 NK2R 设计胞外 VHH。请在每个 Scientist Gate 等待确认，并运行很多后续步骤。',
      ),
    ).toBe('请为人源 NK2R 设计胞外 VHH。');
    expect(summarizeGoal('x'.repeat(200))).toHaveLength(120);
  });

  it('groups raw Judge and Runtime events into three user-facing stages', () => {
    expect(summarizeEasyActivity(snapshot())).toEqual([
      expect.objectContaining({ title: '设计方案已整理', status: 'completed' }),
      expect.objectContaining({ title: '独立审查已完成', status: 'completed' }),
      expect.objectContaining({ title: '等待你批准', status: 'waiting' }),
    ]);
  });

  it('never presents an awaiting-scientist snapshot without a card as agent work', () => {
    const value = snapshot();
    value.decision = null;
    expect(awaitingDecisionRecovery(value)).toBe(true);
    value.project.status = 'running';
    expect(awaitingDecisionRecovery(value)).toBe(false);
  });

  it('keeps risk and limitation lists out of every compact Easy approval card', () => {
    expect(shouldShowGateRiskDisclosure(1, 4, 6)).toBe(false);
    expect(shouldShowGateRiskDisclosure(2, 4, 6)).toBe(false);
    expect(shouldShowGateRiskDisclosure(3, 12, 8)).toBe(false);
    expect(shouldShowGateRiskDisclosure(5, 2, 1)).toBe(false);
    expect(shouldShowGateRiskDisclosure(3, 0, 0)).toBe(false);
  });

  it('summarizes the approved site, design arms, and scaffold YAML counts', () => {
    const value = snapshot();
    value.scientific_context.approved_site = {
      selected_candidate_id: 'site-a',
      selected_rank: 'A',
      hotspots: {},
    };
    value.scientific_context.arms = [{ arm_id: 'arm-1' }, { arm_id: 'arm-2' }];
    value.artifacts = [
      ...['7eow', '7xl0', '8coh'].map((scaffold) => ({
        id: `one-${scaffold}`,
        label: `arm-1-scaffold-${scaffold}`,
        url: `/one/${scaffold}`,
        format: 'yaml',
        sha256: scaffold.padEnd(64, '0'),
        size_bytes: 1,
        role: 'scientific-evidence',
        candidate_id: null,
      })),
      ...['7eow', '7xl0'].map((scaffold) => ({
        id: `two-${scaffold}`,
        label: `arm-2-scaffold-${scaffold}`,
        url: `/two/${scaffold}`,
        format: 'yaml',
        sha256: scaffold.padEnd(64, '1'),
        size_bytes: 1,
        role: 'scientific-evidence',
        candidate_id: null,
      })),
    ];
    expect(summarizeEasyDesignPlan(value)).toEqual({
      siteLabel: '位点 A',
      planCount: 2,
      plans: [
        { id: 'arm-1', label: '方案 1', scaffoldCount: 3 },
        { id: 'arm-2', label: '方案 2', scaffoldCount: 2 },
      ],
      yamlCount: 5,
    });
  });

  it('does not present an available continuation as active model work', () => {
    const value = snapshot();
    value.decision = null;
    value.project.status = 'available';
    expect(summarizeEasyActivity(value)[0]).toMatchObject({
      title: '设计方案已整理',
      status: 'completed',
    });
  });
});
