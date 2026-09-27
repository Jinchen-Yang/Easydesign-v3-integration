import type {Route} from '@playwright/test';

/**
 * Synthetic multi-user fixtures for browser acceptance only. No real accounts,
 * tokens or science: every value here is a conspicuous placeholder that merely
 * exercises the real UI contract (scopes, CSRF headers, revisions, errors).
 */
export interface FixtureUser {
  id: string;
  username: string;
  display_name: string;
  role: 'admin' | 'user';
  status: 'pending' | 'active' | 'suspended' | 'rejected';
  must_change_password: boolean;
}

export const users: Record<string, FixtureUser> = {
  alice: {id: 'user-a', username: 'alice', display_name: 'Alice Lead', role: 'user', status: 'active', must_change_password: false},
  bob: {id: 'user-b', username: 'bob', display_name: 'Bob Member', role: 'user', status: 'active', must_change_password: false},
  root: {id: 'user-root', username: 'root', display_name: 'Platform Admin', role: 'admin', status: 'active', must_change_password: false},
  carol: {id: 'user-c', username: 'carol', display_name: 'Carol Pending', role: 'user', status: 'pending', must_change_password: false},
};

export const personalScope = (user: FixtureUser) => ({
  id: user.id, kind: 'personal', name: `${user.display_name} 的个人工作区`, role: 'owner', can_edit: true, can_execute: true,
});

export const teamScope = (role: 'admin' | 'member') => ({
  id: 'team-1', kind: 'team', name: 'Antibody Crew', role, can_edit: true, can_execute: role === 'admin',
});

export const observerScope = (id: string, name: string) => ({
  id, kind: name.includes('团队') ? 'team' : 'personal', name, role: 'observer', can_edit: false, can_execute: false,
});

export function sessionFor(username: string) {
  const user = users[username]!;
  const scopes = username === 'root'
    ? [personalScope(user)]
    : [personalScope(user), teamScope(username === 'alice' ? 'admin' : 'member')];
  return {user, csrf_token: `csrf-${username}-synthetic`, scopes, invitations: []};
}

const jsonResponse = (route: Route, body: unknown, status = 200) =>
  route.fulfill({json: body, status});
export {jsonResponse};

export interface DraftRecord {
  id: string;
  revision: number;
  payload: {title: string; goal: string};
  state: 'draft' | 'starting' | 'started';
  created_by: string;
  updated_by: string;
  created_at: number;
  updated_at: number;
  start_request_id: string | null;
  project_id: string | null;
}

export function freshDrafts(): DraftRecord[] {
  const now = Date.now() / 1000 - 600;
  return [{
    id: 'draft-1', revision: 2, payload: {title: 'Lysozyme VHH', goal: 'Design a VHH binder against HEWL.'},
    state: 'draft', created_by: users.alice.id, updated_by: users.bob.id,
    created_at: now, updated_at: now + 60, start_request_id: null, project_id: null,
  }];
}

export const FINAL_DESIGN_RULE_FIXTURE = 'Per-person cumulative final-design allowance. The unit is one candidate in '
  + 'the published, checksum-verified Scale global candidate pool of a Gate-4 approved production campaign; '
  + 'scientifically negative candidates count as delivered. Pilot pools never count; Gate-5 panel revisions '
  + 'never add final designs.';

export const finalDesignEntry = (overrides: Partial<{
  id: string; scope_id: string; subject_id: string; amount: number; delivered: number | null;
  state: 'reserved' | 'settled' | 'released'; reason: string | null;
}> = {}) => ({
  id: overrides.id || 'fdr-synthetic-0001',
  scope_id: overrides.scope_id || 'team-1',
  project_id: 'workbench-synthetic',
  request_id: 'req-synthetic-approve-1',
  authority_key: 'a'.repeat(64),
  subject_id: overrides.subject_id || users.alice.id,
  amount: overrides.amount ?? 12,
  delivered: overrides.delivered === undefined ? null : overrides.delivered,
  state: overrides.state || 'reserved',
  campaign_sha256: null,
  reason: overrides.reason === undefined ? null : overrides.reason,
  created_at: Date.now() / 1000 - 300,
  updated_at: Date.now() / 1000 - 60,
});

export const usage = (scopeId: string, finalDesigns?: {
  allowance?: number | null; reserved?: number; delivered?: number;
}) => {
  const allowance = finalDesigns?.allowance === undefined ? 30 : finalDesigns.allowance;
  const reserved = finalDesigns?.reserved ?? 12;
  const delivered = finalDesigns?.delivered ?? 8;
  const remaining = allowance === null ? null : allowance - reserved - delivered;
  return {
    scope: {...(scopeId === 'team-1' ? teamScope('admin') : personalScope(users.bob)), id: scopeId},
    limits: {
      max_active_jobs: 2, max_active_chats: 4, max_gpu_devices: 2, max_upload_bytes: 52428800,
      max_stored_upload_bytes: 104857600, max_candidates_per_job: 24,
      final_designs_allowance: 30, pilot_stage_budget: 30, scale_stage_budget: 30,
    },
    stored_upload_bytes: 8388608,
    admissions: [
      {id: 'adm-1', scope_id: scopeId, request_id: 'req-synthetic-0001', actor_id: users.alice.id, kind: 'scientific',
        state: 'running', gpu_slots: 1, max_candidates: 24, devices: [0], created_at: Date.now() / 1000 - 300,
        updated_at: Date.now() / 1000 - 60, reason: null},
      {id: 'adm-2', scope_id: scopeId, request_id: 'req-synthetic-0002', actor_id: users.bob.id, kind: 'conversation',
        state: 'released', gpu_slots: 0, max_candidates: 0, devices: [], created_at: Date.now() / 1000 - 900,
        updated_at: Date.now() / 1000 - 800, reason: null},
    ],
    // Personal scope blocks carry the caller's own cumulative balance; team scope
    // blocks carry only the team-local aggregate (never member balances).
    final_designs: scopeId === 'team-1'
      ? {
        kind: 'team' as const,
        scope_id: 'team-1',
        reserved: 12,
        delivered: 8,
        rule: FINAL_DESIGN_RULE_FIXTURE,
        entries: [
          finalDesignEntry({state: 'settled', delivered: 8}),
          finalDesignEntry({id: 'fdr-synthetic-0002', amount: 4, state: 'reserved', reason: 'resumable_batches'}),
        ],
      }
      : {
        kind: 'personal' as const,
        subject_id: scopeId,
        allowance,
        reserved,
        delivered,
        remaining,
        rule: FINAL_DESIGN_RULE_FIXTURE,
        entries: [finalDesignEntry({scope_id: 'team-1', state: 'settled', delivered: 8})],
      },
  };
};

export const workbenchSnapshot = () => ({
  schema_version: '1', mode: 'live', revision: 'f'.repeat(64),
  project: {
    id: 'proj-1', title: 'Synthetic team project', goal: 'Fixture goal', thread_id: 'thread-1',
    phase: 'site', status: 'awaiting_scientist', last_activity: 5, validation_only: true,
  },
  workflow: [{id: 'site', label: 'Site', status: 'awaiting_scientist', gate: 2}],
  current_action: {id: 'action-1', stage: 'site-review', message: 'Scientist decides', resumable: false},
  specialists: [],
  scientific_context: {structure: null, sites: [], arms: []},
  decision: {
    id: 'card-1', gate: 2, type: 'site-hotspot', question: '选择候选位点',
    default_option_id: 'site-A', warnings: [], limitations: [], action_summary: 'Review sites',
    revision_targets: ['site'], review_status: null, required_fields: {},
    summary: {}, details_url: '/api/v1/projects/proj-1/review',
    options: [
      {option_id: 'site-A', label: 'Site A', eligible: true, actions: ['approve', 'revise'], rank: 'A'},
      {option_id: 'site-B', label: 'Site B', eligible: true, actions: ['approve', 'revise'], rank: 'B'},
    ],
  },
  jobs: [], artifacts: [],
  recent_activity: [{
    id: 1, type: 'specialist.completed', title: 'Site review completed',
    summary: 'Synthetic site evidence recorded', role: 'site', status: 'complete', phase: 'site',
  }],
  tasks: [], lifecycle: 'scientific_project',
  event_cursor: 9, candidates: {total: 0, counts: {}, url: '/api/v1/projects/proj-1/candidates'},
  capabilities: {decide: true}, requests: [], lab_order: null, connection: 'connected',
});

export const emptyPage = {items: [], total: 0, offset: 0, limit: 20};

export async function injectAccountMode(route: Route): Promise<void> {
  const response = await route.fetch();
  const html = (await response.text()).replace(
    '</head>', '<meta name="easydesign-identity-mode" content="accounts" /></head>',
  );
  await route.fulfill({response, body: html});
}
