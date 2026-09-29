/**
 * Easy/Pro 视图与新 Hash Router 的参数桥。
 *
 * 统一应用里路由参数挂在 hash 上（`#/projects/:id?scope=…&view=…`）；
 * 旧界面把 `?project=`/`?scope=` 放在 location.search 上。这里的读取方
 * 同时接受两种来源（兼容期外部链接），写入方只产出新路由。写入用
 * history.replaceState 保持"切换项目不留历史"的旧行为，随后手动派发
 * hashchange 让 HashRouter 同步读址。
 */

export function hashQuery(): URLSearchParams {
  return new URLSearchParams(location.hash.split('?')[1] ?? '');
}

/** 项目 ID：优先路由段（#/projects/:id），其次哈希 query，最后旧 search query。 */
export function readProjectRoute(): string | null {
  const pathMatch = /#\/projects\/([^/?]+)/.exec(location.hash);
  if (pathMatch) return decodeURIComponent(pathMatch[1]);
  return hashQuery().get('project') ?? new URLSearchParams(location.search).get('project');
}

export type WorkspaceView = 'easy' | 'pro';

export function workspaceHref(scope: string, view: WorkspaceView, project?: string | null): string {
  const params = new URLSearchParams({ scope, view });
  return project
    ? `#/projects/${encodeURIComponent(project)}?${params}`
    : `#/projects?${params}`;
}

function currentScopeParam(): string | null {
  return hashQuery().get('scope') ?? new URLSearchParams(location.search).get('scope');
}

function currentViewParam(): WorkspaceView {
  return hashQuery().get('view') === 'pro' ? 'pro' : 'easy';
}

/** 把当前地址规范化为 `#/projects/:id?scope&view`（project 为空则回 `#/projects`）。 */
export function writeProjectRoute(project: string | null): void {
  const search = new URLSearchParams(location.search);
  search.delete('project');
  search.delete('token');
  const searchPart = search.size ? `?${search}` : '';
  const query = new URLSearchParams();
  const scope = currentScopeParam();
  if (scope) query.set('scope', scope);
  query.set('view', currentViewParam());
  const hash = project
    ? `#/projects/${encodeURIComponent(project)}?${query}`
    : `#/projects?${query}`;
  history.replaceState({}, '', `${location.pathname}${searchPart}${hash}`);
  // replaceState 不触发 hashchange；手动通知 Router 重读地址。
  window.dispatchEvent(new HashChangeEvent('hashchange'));
}

/** 清掉地址上的旧单机 token / 旧 project 参数（迁移期一次性清理）。 */
export function stripLegacySearch(): void {
  const search = new URLSearchParams(location.search);
  if (!search.has('token') && !search.has('project')) return;
  search.delete('token');
  search.delete('project');
  const searchPart = search.size ? `?${search}` : '';
  history.replaceState({}, '', `${location.pathname}${searchPart}${location.hash}`);
}
