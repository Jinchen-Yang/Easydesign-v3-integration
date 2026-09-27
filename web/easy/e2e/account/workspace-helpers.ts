import type {Page} from '@playwright/test';
import {
  emptyPage, injectAccountMode, jsonResponse, sessionFor, usage,
  workbenchSnapshot,
} from './fixtures';

export function installWorkspaceRoutes(page: Page) {
  // Match the document regardless of query string (?scope=...).
  void page.route(url => url.pathname === '/easy/', async route => injectAccountMode(route));
  void page.route('**/api/v1/**', async route => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const reply = (body: unknown, status = 200) => jsonResponse(route, body, status);
    if (path === '/api/v1/accounts/config')
      return reply({mode: 'multi-user', registration: 'admin-review', setup_required: false, compute_available: true});
    if (path === '/api/v1/accounts/me') return reply(sessionFor('bob'));
    if (path === '/api/v1/scopes/team-1/usage') return reply(usage('team-1'));
    if (path.endsWith('/projects') && request.method() === 'GET')
      return reply({items: [workbenchSnapshot().project], total: 1, offset: 0, limit: 5});
    if (path.endsWith('/workbench') && request.method() === 'GET') return reply(workbenchSnapshot());
    if (path.endsWith('/candidates') && request.method() === 'GET') return reply(emptyPage);
    if (path === '/api/v1/scopes/team-1/rabbit/chat' && request.method() === 'GET')
      return reply({configured: false});
    return reply({error: {code: 'not_found', message: `fixture miss ${path}`}}, 404);
  });
}
