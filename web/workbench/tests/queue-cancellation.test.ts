import { expect, it } from 'vitest';
import { latestQueueCancellation } from '../src/live/queue-presentation';
import type { RequestState } from '../src/live/contracts';

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
