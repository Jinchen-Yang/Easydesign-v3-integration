import type { RequestState } from './contracts';

/** Read-only UI projection; native science and Gate state are never rewritten. */
export function latestQueueCancellation(
  projectId: string | undefined,
  requests: Array<RequestState | null | undefined>,
): boolean {
  const latestById = new Map<string, RequestState>();
  for (const request of requests) {
    if (!request || request.project !== projectId) continue;
    const prior = latestById.get(request.id);
    if (!prior || request.updated >= prior.updated) latestById.set(request.id, request);
  }
  const current = [...latestById.values()];
  if (current.some((request) => ['accepted', 'running'].includes(request.state))) return false;
  current.sort((a, b) => b.created - a.created || b.updated - a.updated);
  return current[0]?.result?.code === 'queue_cancelled';
}
