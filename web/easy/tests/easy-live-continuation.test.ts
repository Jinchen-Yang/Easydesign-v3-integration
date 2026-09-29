import { describe, expect, it } from 'vitest';
import {
  canAutoContinue,
  isProductExecutionActive,
  shouldOfferManualResume,
} from '../src/easy/EasyLiveApp';
import type { ProductSnapshot } from '../src/easy/product-contracts';
import type { Decision, Site } from '../src/easy/product-contracts';
import { optionIdForSite, siteDisplayRank, siteIdForOption } from '../src/easy/site-selection';

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

  it('keeps the interface active after an approval request is accepted by the backend', () => {
    const awaiting = snapshot('awaiting_scientist', 'site-card');
    expect(isProductExecutionActive(awaiting, true)).toBe(true);
    expect(isProductExecutionActive(awaiting, false, 'accepted')).toBe(true);
    expect(isProductExecutionActive(awaiting, false, 'running')).toBe(true);
    expect(isProductExecutionActive(awaiting, false, 'succeeded')).toBe(false);
  });
});

describe('Easy site approval and structure preview mapping', () => {
  const sites: Site[] = [
    { id: 'site-a', rank: 'A', name: 'A', selectable: true, design_labels: [], why_ranked: '', risks: [], uncertainty: [], confidence: 'high', coordinates: [] },
    { id: 'site-b', rank: 'B', name: 'B', selectable: true, design_labels: [], why_ranked: '', risks: [], uncertainty: [], confidence: 'medium', coordinates: [] },
    { id: 'site-c', rank: null, name: 'C', selectable: false, design_labels: [], why_ranked: '', risks: [], uncertainty: [], confidence: 'low', coordinates: [] },
  ];
  const decision = {
    gate: 2,
    default_option_id: 'option-a',
    options: [
      { option_id: 'option-a', rank: 'A' },
      { option_id: 'option-b', rank: 'B' },
      { option_id: 'option-c' },
    ],
  } as Decision;

  it('maps approval choices to their structure previews in both directions', () => {
    expect(siteIdForOption(sites, decision, 'option-b')).toBe('site-b');
    expect(optionIdForSite(sites, decision, 'site-a')).toBe('option-a');
  });

  it('gives an unranked comparison entry a stable display letter without ranking it', () => {
    expect(siteDisplayRank(sites[2], 2)).toBe('C');
    expect(sites[2].rank).toBeNull();
    expect(siteIdForOption(sites, decision, 'option-c')).toBe('site-c');
  });
});
