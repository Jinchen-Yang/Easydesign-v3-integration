import type { AccountScope, AccountSession } from '../shared/account-client';

/**
 * The 401 bridge between the scoped transport and the session state machine.
 * Lives in its own module so `account-client.ts` can dispatch without a
 * runtime import cycle with `SessionProvider.tsx` (which imports the client).
 */

export const SESSION_EXPIRED_EVENT = 'easydesign:session-expired';

export interface SessionExpiredDetail {
  session: AccountSession;
  scope?: AccountScope;
}

export function dispatchSessionExpired(detail: SessionExpiredDetail): void {
  window.dispatchEvent(new CustomEvent(SESSION_EXPIRED_EVENT, { detail }));
}

/** A denied operation is permission refresh, never an automatic sign-out. */
export const SESSION_PERMISSIONS_EVENT = 'easydesign:session-permissions';
export interface SessionPermissionsDetail extends SessionExpiredDetail {
  scope: AccountScope;
  status: 403 | 404;
  code: string;
}
const permissionCodes = new Set([
  'forbidden',
  'team_admin_required',
  'read_only_scope',
  'unauthorized',
  'password_change_required',
  'csrf_failed',
]);
export function needsPermissionRefresh(status: number, code: string): boolean {
  // Scope membership is deliberately concealed as not_found by AccountStore.scope().
  return (status === 403 && permissionCodes.has(code)) || (status === 404 && code === 'not_found');
}
export function dispatchSessionPermissions(detail: SessionPermissionsDetail): void {
  window.dispatchEvent(new CustomEvent(SESSION_PERMISSIONS_EVENT, { detail }));
}
