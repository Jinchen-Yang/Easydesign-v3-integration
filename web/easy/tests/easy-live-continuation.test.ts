import { describe, expect, it } from 'vitest';
import { canAutoContinue, shouldOfferManualResume } from '../src/easy/EasyLiveApp';
import type { ProductSnapshot } from '../src/easy/product-contracts';

function snapshot(status: string, stage: string): ProductSnapshot {
  return {
    schema_version: '1',
    mode: 'live',
    revision: 'a'.repeat(64),
    project: {
      id: 'project',
      title: 'Project',
      goal: 'Goal',
      thread_id: 'thread',
      phase: 'pilot',
      status,
      last_activity: 1,
      validation_only: true,
    },
    workflow: [],
    current_action: { id: 'action', stage, message: '', resumable: true },
    specialists: [],
    scientific_context: { structure: null, sites: [], arms: [] },
    jobs: [],
    artifacts: [],
    recent_activity: [],
    tasks: [],
    lifecycle: 'scientific_project',
    event_cursor: 1,
    candidates: { total: 0, counts: {}, url: '/candidates' },
    capabilities: { resume: true, auto_continue: true },
    requests: [],
    lab_order: null,
    connection: 'connected',
    decision: null,
  };
}

describe('Easy live automatic continuation', () => {
  it('reconciles a verified successor worker after the original job was incomplete', () => {
    expect(canAutoContinue(snapshot('incomplete', 'pilot-reconcile'), false)).toBe(true);
  });

  it('does not automatically retry an ordinary incomplete scientific execution', () => {
    expect(canAutoContinue(snapshot('incomplete', 'pilot-operational-evidence'), false)).toBe(
      false,
    );
  });

  it('waits while a continuation request is already active', () => {
    expect(canAutoContinue(snapshot('available', 'pilot-card'), false, 'running')).toBe(false);
  });

  it('never offers a redundant resume button while compute is running', () => {
    const current = snapshot('running', 'pilot-running');
    current.capabilities.auto_continue = false;
    expect(shouldOfferManualResume(current, false)).toBe(false);
    expect(shouldOfferManualResume(snapshot('available', 'pilot-card'), true)).toBe(false);
  });

  it('offers recovery only for a stopped resumable step', () => {
    const current = snapshot('incomplete', 'pilot-operational-evidence');
    current.capabilities.auto_continue = false;
    expect(shouldOfferManualResume(current, false)).toBe(true);
  });
});
