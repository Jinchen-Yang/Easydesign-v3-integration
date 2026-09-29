import { act, cleanup, render } from '@testing-library/react';
import { useEffect } from 'react';
import { HashRouter, Route, Routes, useParams, useSearchParams, useNavigate } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { bindRouterNavigate, writeProjectRoute } from '../src/views/easy/routeParams';

/**
 * 验收点：路由桥写入后，路由器读到的是新项目。
 * HashRouter 只监听 popstate；writeProjectRoute 必须通过绑定的
 * navigate(replace) 让路由器同步，而不是 replaceState + hashchange。
 */

afterEach(cleanup);

beforeEach(() => {
  window.history.pushState({}, '', '/');
});

function BindProbe() {
  const navigate = useNavigate();
  useEffect(() => bindRouterNavigate(navigate), [navigate]);
  return null;
}

function RouteProbe({ report }: { report: (value: { id: string | undefined; view: string | null; scope: string | null }) => void }) {
  const { id } = useParams();
  const [params] = useSearchParams();
  useEffect(() => { report({ id, view: params.get('view'), scope: params.get('scope') }); });
  return null;
}

describe('路由桥与路由器同步', () => {
  it('writeProjectRoute 后路由器读到新项目与保留的 scope/view', async () => {
    const seen: Array<{ id: string | undefined; view: string | null; scope: string | null }> = [];
    window.location.hash = '#/projects/p1?scope=s1&view=easy';
    render(
      <HashRouter>
        <BindProbe />
        <Routes>
          <Route path="/projects" element={<RouteProbe report={(v) => { seen.push(v); }} />} />
          <Route path="/projects/:id" element={<RouteProbe report={(v) => { seen.push(v); }} />} />
        </Routes>
      </HashRouter>,
    );
    await act(async () => {});
    expect(seen.at(-1)).toMatchObject({ id: 'p1', view: 'easy', scope: 's1' });

    await act(async () => { writeProjectRoute('p2'); });
    expect(window.location.hash).toBe('#/projects/p2?scope=s1&view=easy');
    expect(seen.at(-1)).toMatchObject({ id: 'p2', view: 'easy', scope: 's1' });

    // 清空项目（新建设计）回落到 /projects，scope/view 仍在。
    await act(async () => { writeProjectRoute(null); });
    expect(window.location.hash).toBe('#/projects?scope=s1&view=easy');
    expect(seen.at(-1)).toMatchObject({ id: undefined, view: 'easy', scope: 's1' });
  });

  it('未绑定路由器时退化为 replaceState + popstate，地址仍然正确', () => {
    window.location.hash = '#/projects/p1?scope=s1&view=pro';
    window.dispatchEvent(new PopStateEvent('popstate')); // 让初始 hash 被读取（无路由器也无妨）
    writeProjectRoute('p9');
    expect(window.location.hash).toBe('#/projects/p9?scope=s1&view=pro');
  });
});
