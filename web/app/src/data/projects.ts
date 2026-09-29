import { scopedTransport, type AccountSession, type AccountScope } from '../shared/account-client';

export interface ProjectListItem {
  id: string;
  title?: string;
  status?: string;
  updated_at?: number;
  surface?: string;
}

/**
 * Scoped project listing for the home page. Straight fetch + JSON here;
 * TanStack Query handles caching/dedup at the call site.
 */
export async function fetchProjects(
  session: AccountSession,
  scope: AccountScope,
  surface: 'easy' | 'professional' = 'easy',
): Promise<ProjectListItem[]> {
  const transport = scopedTransport(session, scope);
  const response = await transport(`/api/v1/projects?surface=${surface}`, { credentials: 'same-origin' });
  const value: unknown = await response.json().catch(() => null);
  if (!response.ok) throw new Error((value as { error?: { message?: string } } | null)?.error?.message ?? '项目列表暂时无法加载');
  const items = (value as { items?: ProjectListItem[] } | null)?.items;
  return Array.isArray(items) ? items : [];
}
