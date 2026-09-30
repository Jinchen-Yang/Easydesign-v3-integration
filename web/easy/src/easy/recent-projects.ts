export type RecentProjectOpens = Record<string, number>;

const STORAGE_KEY = 'easydesign.easy.recent-project-opens.v1';
const MAX_PROJECTS = 100;

export function loadRecentProjectOpens(
  storage: Pick<Storage, 'getItem'> | null = typeof window === 'undefined'
    ? null
    : window.localStorage,
): RecentProjectOpens {
  if (!storage) return {};
  try {
    const value: unknown = JSON.parse(storage.getItem(STORAGE_KEY) || '{}');
    if (!value || typeof value !== 'object' || Array.isArray(value)) return {};
    const opened: RecentProjectOpens = {};
    for (const [project, timestamp] of Object.entries(value)) {
      if (
        project.length > 0 &&
        project.length <= 256 &&
        typeof timestamp === 'number' &&
        Number.isFinite(timestamp) &&
        timestamp > 0 &&
        timestamp <= 8640000000000000
      )
        opened[project] = timestamp;
    }
    return opened;
  } catch {
    return {};
  }
}

export function rememberProjectOpen(
  current: RecentProjectOpens,
  project: string,
  openedAt = Date.now(),
  storage: Pick<Storage, 'setItem'> | null = typeof window === 'undefined'
    ? null
    : window.localStorage,
): RecentProjectOpens {
  const next = Object.fromEntries(
    Object.entries({ ...current, [project]: openedAt })
      .sort((left, right) => right[1] - left[1])
      .slice(0, MAX_PROJECTS),
  );
  try {
    storage?.setItem(STORAGE_KEY, JSON.stringify(next));
  } catch {
    // Private browsing and storage quotas must not prevent opening a project.
  }
  return next;
}

export function formatProjectOpenTime(timestamp: number): string {
  const value = new Date(timestamp);
  const pad = (part: number) => String(part).padStart(2, '0');
  return `${value.getFullYear()}-${pad(value.getMonth() + 1)}-${pad(value.getDate())} ${pad(
    value.getHours(),
  )}:${pad(value.getMinutes())}`;
}
