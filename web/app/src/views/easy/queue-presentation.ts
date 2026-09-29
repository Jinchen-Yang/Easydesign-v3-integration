import type { ProductSnapshot, Project, RequestState } from './product-contracts';
import { appI18n } from '../../shell/I18nProvider';

const easyT = (key: string): string => appI18n.t(key, { ns: 'easy' });

function currentRequests(
  projectId: string | undefined,
  requests: Array<RequestState | null | undefined>,
): RequestState[] {
  const latestById = new Map<string, RequestState>();
  for (const request of requests) {
    if (!request || request.project !== projectId) continue;
    const prior = latestById.get(request.id);
    if (!prior || request.updated >= prior.updated) latestById.set(request.id, request);
  }
  return [...latestById.values()];
}

/** Read-only UI projection; native science and Gate state are never rewritten. */
export function latestQueueCancellation(
  projectId: string | undefined,
  requests: Array<RequestState | null | undefined>,
): boolean {
  const current = currentRequests(projectId, requests);
  if (current.some((request) => ['accepted', 'running'].includes(request.state))) return false;
  current.sort((a, b) => b.created - a.created || b.updated - a.updated);
  return current[0]?.result?.code === 'queue_cancelled';
}

type ListProject = Pick<Project, 'id' | 'status'>;
type ListSnapshot = Pick<ProductSnapshot, 'requests' | 'jobs' | 'decision'> & {
  project: ListProject;
};

/** A project container marked running is not proof of a running computation. */
export function projectListStatus(
  project: ListProject,
  snapshot: ListSnapshot | null,
  pendingRequest?: RequestState | null,
): string {
  if (snapshot?.project.id === project.id) {
    if (snapshot.decision) return snapshot.project.status;
    // A same-version POST acknowledgement may omit the server's queue projection.
    // Only equal state+version may prefer the snapshot; a newly accepted action
    // must not be hidden by an equally timestamped terminal snapshot.
    const pending = snapshot.requests.some(
      (request) =>
        request.project === project.id &&
        request.id === pendingRequest?.id &&
        request.updated === pendingRequest.updated &&
        request.state === pendingRequest.state,
    )
      ? undefined
      : pendingRequest;
    const requests = currentRequests(project.id, [...snapshot.requests, pending]);
    if (
      snapshot.jobs.some((job) =>
        ['queued', 'running', 'dispatching', 'drain-requested'].includes(job.status),
      )
    )
      return snapshot.project.status;
    const active = requests.filter((request) => ['accepted', 'running'].includes(request.state));
    if (active.length)
      return active.every((request) => request.result?.queue?.state === 'queued')
        ? easyT('Queuing')
        : snapshot.project.status;
    if (
      latestQueueCancellation(project.id, snapshot.requests) &&
      latestQueueCancellation(project.id, requests)
    )
      return easyT('Queue cancelled');
  }
  return project.status === 'running' ? easyT('Open to view execution status') : project.status;
}
