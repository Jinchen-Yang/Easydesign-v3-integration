import type {Page, Route} from '@playwright/test';
import {
  freshDrafts, jsonResponse, sessionFor, usage, users, type DraftRecord,
} from './fixtures';

/** In-memory synthetic account/draft state; resets per test. */
export function installAccountRoutes(page: Page) {
  let current: string | null = null;
  let drafts: DraftRecord[] = freshDrafts();
  let staleOnce = false;
  const approved: Record<string, string> = {};

  const reply = (route: Route, body: unknown, status = 200) => jsonResponse(route, body, status);
  const actor = () => users[(current || 'bob') as keyof typeof users]!;

  page.on('close', () => { current = null; });

  void page.route('**/api/v1/**', async route => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const post = request.method() === 'POST' ? await safeJson(request) : undefined;

    if (path === '/api/v1/accounts/config' && request.method() === 'GET')
      return reply(route, {mode: 'multi-user', registration: 'admin-review', setup_required: false, compute_available: true});
    if (path === '/api/v1/accounts/register' && post)
      return reply(route, {status: 'pending-review'}, 201);
    if (path === '/api/v1/accounts/login' && post) {
      const username = String(post.username);
      if (!(username in users) || users[username as keyof typeof users]!.status !== 'active')
        return reply(route, {error: {code: 'invalid_credentials', message: '用户名或密码不正确'}}, 401);
      current = username;
      return reply(route, {user: users[current as keyof typeof users]!.username, status: 'ok'});
    }
    if (path === '/api/v1/accounts/logout') { current = null; return reply(route, {status: 'logged-out'}); }
    if (path === '/api/v1/accounts/me') {
      if (!current) return reply(route, {error: {code: 'session_required', message: '请先登录'}}, 401);
      return reply(route, sessionFor(current));
    }
    if (path === '/api/v1/teams/team-1' && request.method() === 'GET') {
      if (!current) return reply(route, {error: {code: 'session_required', message: '请先登录'}}, 401);
      return reply(route, {
        team: {
          id: 'team-1', name: 'Antibody Crew', status: 'active',
          members: [
            {user_id: users.alice.id, username: 'alice', display_name: 'Alice Lead', role: 'admin', status: 'active', account_status: 'active'},
            {user_id: users.bob.id, username: 'bob', display_name: 'Bob Member', role: 'member', status: 'active', account_status: 'active'},
          ],
        },
      });
    }
    if (path === '/api/v1/scopes/team-1/drafts' && request.method() === 'GET')
      return reply(route, {drafts});
    if (path === '/api/v1/scopes/team-1/drafts' && request.method() === 'POST') {
      drafts.unshift({
        id: 'draft-new', revision: 1, payload: {title: String(post?.title), goal: String(post?.goal)},
        state: 'draft', created_by: actor().id, updated_by: actor().id,
        created_at: Date.now() / 1000, updated_at: Date.now() / 1000, start_request_id: null, project_id: null,
      });
      return reply(route, {draft: drafts[0]}, 200);
    }
    if (path === '/api/v1/scopes/team-1/drafts/draft-1' && request.method() === 'POST') {
      const draft = drafts.find(item => item.id === 'draft-1')!;
      if (staleOnce) {
        staleOnce = false;
        draft.revision += 1; // Another member saved first.
        return reply(route, {error: {code: 'stale_draft', message: '草稿已被其他成员更新，请重新加载'}}, 409);
      }
      if (post?.revision !== draft.revision)
        return reply(route, {error: {code: 'stale_draft', message: '草稿已被其他成员更新，请重新加载'}}, 409);
      draft.revision += 1;
      draft.payload = {title: String(post?.title), goal: String(post?.goal)};
      draft.updated_by = actor().id;
      return reply(route, {draft});
    }
    if (path === '/api/v1/scopes/team-1/drafts/draft-1/start' && request.method() === 'POST') {
      const draft = drafts.find(item => item.id === 'draft-1')!;
      if (post?.revision !== draft.revision)
        return reply(route, {error: {code: 'stale_draft', message: '启动前草稿已更新，请重新审阅'}}, 409);
      draft.state = 'started';
      draft.start_request_id = String(post?.request_id);
      draft.project_id = 'proj-new';
      return reply(route, {project: {id: 'proj-new'}, request: {id: 'req-1', state: 'accepted'}}, 202);
    }
    if (path === '/api/v1/scopes/team-1/usage' && request.method() === 'GET')
      return reply(route, usage('team-1'));
    if (path === '/api/v1/admin/users' && request.method() === 'GET') {
      if (!current || actor().role !== 'admin')
        return reply(route, {error: {code: 'admin_required', message: '需要系统管理员'}}, 403);
      return reply(route, {users: Object.values(users).map(user => ({...user, status: approved[user.username] || user.status}))});
    }
    if (path === '/api/v1/admin/teams' && request.method() === 'GET')
      return reply(route, {teams: [{id: 'team-1', name: 'Antibody Crew', status: 'active'}]});
    if (path === '/api/v1/admin/audit' && request.method() === 'GET')
      return reply(route, {events: [{seq: 1, actor_id: users.bob.id, action: 'session.login', scope_id: null, target_id: null, created_at: Date.now() / 1000 - 60}]});
    if (/^\/api\/v1\/quotas\/(user-[a-z]|team-1)$/.test(path) && request.method() === 'GET')
      return reply(route, {limits: {
        max_active_jobs: 1, max_active_chats: 2, max_gpu_devices: 1,
        max_upload_bytes: 32 * 1024 ** 2, max_stored_upload_bytes: 10 * 1024 ** 3,
        max_candidates_per_job: 24,
      }});
    if (/^\/api\/v1\/admin\/quotas\//.test(path) && request.method() === 'POST') {
      const value = post as Record<string, number> | undefined;
      if (!value || Object.values(value).some(entry => !Number.isInteger(entry)))
        return reply(route, {error: {code: 'invalid_request', message: '请求字段不正确'}}, 400);
      return reply(route, {limits: value});
    }
    if (/^\/api\/v1\/admin\/users\/user-c$/.test(path) && request.method() === 'POST') {
      approved['carol'] = String(post?.status);
      return reply(route, {user: {...users.carol, status: String(post?.status)}});
    }
    return reply(route, {error: {code: 'not_found', message: `fixture miss ${path}`}}, 404);
  });

  return {
    armStaleOnce: () => { staleOnce = true; },
    drafts: () => drafts,
  };
}

async function safeJson(request: {postDataJSON(): Promise<unknown>}): Promise<Record<string, unknown> | undefined> {
  try {
    const value = (await request.postDataJSON()) as unknown;
    return value && typeof value === 'object' ? (value as Record<string, unknown>) : undefined;
  } catch {
    return undefined;
  }
}

export async function login(page: Page, username: string) {
  await page.goto('/easy/account/');
  await page.getByLabel('用户名').fill(username);
  await page.getByLabel('密码', {exact: true}).fill('synthetic-password-12');
  await page.getByRole('button', {name: '登录', exact: true}).click();
}

export {};
