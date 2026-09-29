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
