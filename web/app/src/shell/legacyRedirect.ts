/**
 * 旧链接规范化（执行指南 §2.3）：旧界面把目的地放在 location.search
 * （/easy/?scope=x&project=y、/?project=y、/account/）。在壳挂载前执行，
 * 会话探测的 next 捕获与路由器看到的都是最终 hash。已在应用路由内或
 * 带登录回跳参数（?next=）时不动作。
 */
export function applyLegacyRedirect(
  replace: (url: string) => void = (url) => { location.replace(url); },
): void {
  if (location.hash && location.hash !== '#/' && location.hash !== '#') return;
  const params = new URLSearchParams(location.search);
  if (params.has('next')) return;
  const path = location.pathname.replace(/\/+$/, '') || '/';
  const scope = params.get('scope');
  const project = params.get('project');
  // 旧 '/' 根路径就是 Pro 工作台：无 view 参数时按来源面缺省。
  const view = params.get('view') ?? (path === '/' ? 'pro' : 'easy');
  if (path === '/account') {
    replace('#/account');
    return;
  }
  if (path === '/easy' && project) {
    replace(`#/projects/${encodeURIComponent(project)}?scope=${encodeURIComponent(scope ?? '')}&view=easy`);
    return;
  }
  if ((path === '/' || path === '/app') && project) {
    replace(`#/projects/${encodeURIComponent(project)}?scope=${encodeURIComponent(scope ?? '')}&view=${view}`);
    return;
  }
  if (scope) {
    replace(`#/?scope=${encodeURIComponent(scope)}`);
  }
}
