import { expect, it } from 'vitest';
import { latestQueueCancellation, projectListStatus } from '../src/easy/queue-presentation';
import type { RequestState } from '../src/easy/product-contracts';

const cancelled: RequestState = {
  id: 'old',
  project: 'p1',
  state: 'failed',
  result: { code: 'queue_cancelled' },
  created: 1,
  updated: 5,
};
it('projects only the latest cancellation in the current project', () => {
  expect(latestQueueCancellation('p1', [cancelled])).toBe(true);
  expect(latestQueueCancellation('other', [cancelled])).toBe(false);
  expect(
    latestQueueCancellation('p1', [
      cancelled,
      { ...cancelled, id: 'new', state: 'succeeded', result: null, created: 2, updated: 6 },
    ]),
  ).toBe(false);
});
it('never masks a new active request with an older cancellation', () => {
  expect(
    latestQueueCancellation('p1', [
      cancelled,
      { ...cancelled, id: 'new', state: 'running', result: null, created: 2, updated: 4 },
    ]),
  ).toBe(false);
});
it('refresh supersedes an outdated in-memory state for the same request', () => {
  expect(
    latestQueueCancellation('p1', [
      { ...cancelled, state: 'accepted', result: null, updated: 1 },
      cancelled,
    ]),
  ).toBe(true);
  expect(
    latestQueueCancellation('p1', [
      cancelled,
      { ...cancelled, state: 'running', result: null, updated: 6 },
    ]),
  ).toBe(false);
});

it('shows the cancelled current design consistently in its list row', () => {
  const project = { id: 'p1', status: 'running' };
  expect(
    projectListStatus(project, {
      project,
      requests: [cancelled],
      jobs: [],
      decision: null,
    }),
  ).toBe('排队已取消');
});

it('does not infer execution from a running container without its fresh snapshot', () => {
  const project = { id: 'p1', status: 'running' };
  expect(projectListStatus(project, null)).toBe('打开查看执行状态');
  expect(
    projectListStatus(project, {
      project: { id: 'other', status: 'running' },
      requests: [cancelled],
      jobs: [],
      decision: null,
    }),
  ).toBe('打开查看执行状态');
  expect(projectListStatus({ ...project, status: 'complete' }, null)).toBe('complete');
});

it.each(['accepted', 'running'])(
  'keeps a fresh %s request ahead of an old cancellation',
  (state) => {
    const project = { id: 'p1', status: 'running' };
    expect(
      projectListStatus(project, {
        project,
        requests: [
          cancelled,
          { ...cancelled, id: 'new', state, result: null, created: 2, updated: 6 },
        ],
        jobs: [],
        decision: null,
      }),
    ).toBe('running');
  },
);

it.each(['queued', 'running', 'dispatching', 'drain-requested'])(
  'never masks a native %s job with a cancelled request',
  (status) => {
    const project = { id: 'p1', status: 'running' };
    expect(
      projectListStatus(project, {
        project,
        requests: [cancelled],
        decision: null,
        jobs: [
          { id: 'native-job', phase: 'pilot', status, resumable: false, validation_only: false },
        ],
      }),
    ).toBe('running');
  },
);

it('preserves a live Scientist Gate instead of labelling the project cancelled', () => {
  const project = { id: 'p1', status: 'awaiting_scientist' };
  expect(
    projectListStatus(project, {
      project,
      requests: [cancelled],
      jobs: [],
      decision: {
        id: 'gate-1',
        gate: 1,
        type: 'target',
        question: 'Approve target?',
        default_option_id: 'target',
        options: [],
        warnings: [],
        limitations: [],
        action_summary: 'Review target',
        revision_targets: [],
        review_status: null,
        required_fields: {},
        summary: {},
      },
    }),
  ).toBe('awaiting_scientist');
});

it('does not let an old snapshot cancellation hide a newly accepted action', () => {
  const project = { id: 'p1', status: 'running' };
  expect(
    projectListStatus(
      project,
      {
        project,
        requests: [cancelled],
        jobs: [],
        decision: null,
      },
      { ...cancelled, id: 'new', state: 'accepted', result: null, created: 2, updated: 6 },
    ),
  ).toBe('running');
});

it('requires cancellation in the snapshot, not only a remembered pending response', () => {
  const project = { id: 'p1', status: 'running' };
  expect(
    projectListStatus(
      project,
      {
        project,
        requests: [],
        jobs: [],
        decision: null,
      },
      cancelled,
    ),
  ).toBe('打开查看执行状态');
});

it('uses the newest observation of the same request and ignores other projects', () => {
  const project = { id: 'p1', status: 'running' };
  const snapshot = { project, requests: [cancelled], jobs: [], decision: null };
  expect(
    projectListStatus(project, snapshot, {
      ...cancelled,
      state: 'accepted',
      result: null,
      updated: 1,
    }),
  ).toBe('排队已取消');
  expect(
    projectListStatus(project, snapshot, {
      ...cancelled,
      project: 'other',
      state: 'running',
      result: null,
      updated: 7,
    }),
  ).toBe('排队已取消');
  expect(
    projectListStatus(project, snapshot, {
      ...cancelled,
      id: 'new',
      state: 'succeeded',
      result: null,
      created: 2,
      updated: 7,
    }),
  ).toBe('打开查看执行状态');
});

it('does not mutate the native project or request facts', () => {
  const project = Object.freeze({ id: 'p1', status: 'running' });
  const request = Object.freeze({ ...cancelled });
  const snapshot = Object.freeze({ project, requests: [request], jobs: [], decision: null });
  expect(projectListStatus(project, snapshot)).toBe('排队已取消');
  expect(project.status).toBe('running');
  expect(request.state).toBe('failed');
});

const queued: RequestState = {
  ...cancelled,
  id: 'new-queued',
  state: 'accepted',
  created: 2,
  updated: 6,
  result: {
    queue: { state: 'queued', position: 1, reason: 'waiting_for_resources', cancellable: true },
  },
};

it('labels an explicitly queued active request as queued, not running or cancelled', () => {
  const project = { id: 'p1', status: 'running' };
  expect(
    projectListStatus(project, {
      project,
      requests: [cancelled, queued],
      jobs: [],
      decision: null,
    }),
  ).toBe('排队中');
});

it('uses the snapshot queue projection over the same-version plain POST acknowledgement', () => {
  const project = { id: 'p1', status: 'running' };
  expect(
    projectListStatus(
      project,
      {
        project,
        requests: [cancelled, queued],
        jobs: [],
        decision: null,
      },
      { ...queued, result: null },
    ),
  ).toBe('排队中');
});

it('respects the resource queue projection even when the request journal says running', () => {
  const project = { id: 'p1', status: 'running' };
  expect(
    projectListStatus(project, {
      project,
      requests: [{ ...queued, state: 'running' }],
      jobs: [],
      decision: null,
    }),
  ).toBe('排队中');
});

it('does not call a mixed queued and executing request set queued', () => {
  const project = { id: 'p1', status: 'running' };
  expect(
    projectListStatus(project, {
      project,
      requests: [cancelled, queued, { ...queued, id: 'executing', state: 'running', result: null }],
      jobs: [],
      decision: null,
    }),
  ).toBe('running');
});

it('protects native execution and does not guess worker-starting is resource waiting', () => {
  const project = { id: 'p1', status: 'running' };
  expect(
    projectListStatus(project, {
      project,
      requests: [cancelled, queued],
      decision: null,
      jobs: [
        {
          id: 'native',
          phase: 'pilot',
          status: 'running',
          resumable: false,
          validation_only: false,
        },
      ],
    }),
  ).toBe('running');
  expect(
    projectListStatus(project, {
      project,
      jobs: [],
      decision: null,
      requests: [
        {
          ...queued,
          result: {
            queue: {
              state: 'starting',
              position: null,
              reason: 'worker_starting',
              cancellable: false,
            },
          },
        },
      ],
    }),
  ).toBe('running');
});

it('never resolves equally timestamped active-vs-terminal conflict into cancellation', () => {
  const project = { id: 'p1', status: 'running' };
  const active = { ...cancelled, state: 'accepted', result: null };
  expect(
    projectListStatus(
      project,
      {
        project,
        requests: [cancelled],
        jobs: [],
        decision: null,
      },
      active,
    ),
  ).toBe('running');
  expect(
    projectListStatus(
      project,
      {
        project,
        requests: [active],
        jobs: [],
        decision: null,
      },
      cancelled,
    ),
  ).toBe('打开查看执行状态');
});
