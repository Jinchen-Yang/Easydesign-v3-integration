import {
  createContext, useCallback, useContext, useEffect, useMemo, useReducer, useRef,
  type ReactNode,
} from 'react';
import {
  AccountApiError, accountApi, notifySessionChange, subscribeSessionBroadcast,
  type AccountScope, type AccountSession,
} from '../shared/account-client';
import { draftRecovery, type DraftRecoveryModule } from '../data/draftRecovery';
import { SESSION_EXPIRED_EVENT, type SessionExpiredDetail } from '../shared/sessionEvents';
import { appI18n } from './I18nProvider';

const commonT = (key: string): string => appI18n.t(key, { ns: 'common' });
import { captureBootIntent, discardNextUrl, takeNextUrl } from './nextUrl';

export { SESSION_EXPIRED_EVENT };

/**
 * Session state machine (execution guide §2.1).
 *
 * Transitions:
 *   init → checking
 *   checking → guest | authenticated | network-error
 *   guest → [登录成功] → authenticated
 *   authenticated → [401 事件] → expired（记录路径 + 收集草稿）
 *   authenticated → [主动登出] → guest
 *   expired → [重新登录同账号] → authenticated（恢复路径）
 *   expired → [重新登录不同账号] → guest（清除数据）→ 登录后 authenticated
 *   expired → [取消恢复] → guest
 *   network-error → [重试成功] → authenticated
 *   network-error → [放弃] → guest
 *
 * The machine never redirects the page. A 401 only moves the state to
 * `expired`; recovery overlays and navigation stay a UI concern.
 */

export type SessionState =
  | { kind: 'guest' }
  | { kind: 'checking' }
  | { kind: 'authenticated'; session: AccountSession; scope: AccountScope }
  | {
      kind: 'expired';
      previousSession: AccountSession;
      recoverableData: Record<string, unknown>;
    }
  | { kind: 'network-error'; retry: () => void };

export type SessionEvent =
  | { type: 'probe-start' }
  | { type: 'probe-authenticated'; session: AccountSession; scope: AccountScope }
  | { type: 'probe-guest' }
  | { type: 'probe-network-error'; retry: () => void }
  | { type: 'login-authenticated'; session: AccountSession; scope: AccountScope }
  | { type: 'session-expired'; recoverableData: Record<string, unknown> }
  | { type: 'switch-account' }
  | { type: 'recovery-dismissed' }
  | { type: 'signed-out' };

export function reduceSession(state: SessionState, event: SessionEvent): SessionState {
  switch (event.type) {
    case 'probe-start':
      return { kind: 'checking' };
    case 'probe-authenticated':
      return state.kind === 'checking' || state.kind === 'network-error'
        ? { kind: 'authenticated', session: event.session, scope: event.scope }
        : state;
    case 'probe-guest':
      return state.kind === 'checking' ? { kind: 'guest' } : state;
    case 'probe-network-error':
      return state.kind === 'checking' ? { kind: 'network-error', retry: event.retry } : state;
    case 'login-authenticated':
      return state.kind === 'guest' ||
        state.kind === 'checking' ||
        state.kind === 'network-error' ||
        state.kind === 'expired'
        ? { kind: 'authenticated', session: event.session, scope: event.scope }
        : state;
    case 'session-expired':
      return state.kind === 'authenticated'
        ? {
            kind: 'expired',
            previousSession: state.session,
            recoverableData: event.recoverableData,
          }
        : state;
    case 'switch-account':
      return state.kind === 'expired' ? { kind: 'guest' } : state;
    case 'recovery-dismissed':
      return state.kind === 'expired' || state.kind === 'network-error' ? { kind: 'guest' } : state;
    case 'signed-out':
      return state.kind === 'authenticated' || state.kind === 'expired' ? { kind: 'guest' } : state;
  }
}

/** Fired by the scoped transport on any 401; see shell/sessionEvents.ts. */

const RECOVERY_PATH_KEY = 'easydesign-recovery-path';

function saveRecoveryPath(): void {
  try {
    localStorage.setItem(RECOVERY_PATH_KEY, location.hash);
  } catch {
    /* Path restoration is best-effort; the workspace still renders fresh. */
  }
}

function takeRecoveryPath(): string | null {
  try {
    const saved = localStorage.getItem(RECOVERY_PATH_KEY);
    localStorage.removeItem(RECOVERY_PATH_KEY);
    return saved;
  } catch {
    return null;
  }
}

function hashQueryParameter(name: string): string | null {
  const query = location.hash.split('?')[1] ?? '';
  return new URLSearchParams(query).get(name);
}

/**
 * Scope resolution mirrors the legacy surfaces: an explicit `?scope=` wins
 * (hash query first, then search), then the first known scope, and only as a
 * last resort a usage fetch for the personal scope id.
 */
export function resolveScope(session: AccountSession): Promise<AccountScope> {
  const requested = hashQueryParameter('scope') ?? new URLSearchParams(location.search).get('scope');
  const known = requested === null ? undefined : session.scopes.find((scope) => scope.id === requested);
  if (known !== undefined) return Promise.resolve(known);
  const first = session.scopes[0];
  if (first !== undefined) return Promise.resolve(first);
  return accountApi<{ scope: AccountScope }>(
    `/scopes/${encodeURIComponent(session.user.id)}/usage`, session,
  ).then((usage) => usage.scope);
}

export interface SessionApi {
  probe(): Promise<AccountSession>;
  login(username: string, password: string): Promise<AccountSession>;
  logout(session: AccountSession): Promise<void>;
}

export const defaultSessionApi: SessionApi = {
  probe: () => accountApi<AccountSession>('/accounts/me'),
  login: (username, password) => accountApi<AccountSession>('/accounts/login', null, { username, password }),
  logout: (session) => accountApi('/accounts/logout', session, {}),
};

export interface SessionContextValue {
  state: SessionState;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  /** Same-account re-login from the expired state; restores the interrupted route. */
  recoverSession: (password: string) => Promise<void>;
  /** Gives up recovery (expired) or retries later (network-error) and lands as guest. */
  dismissRecovery: () => void;
}

const SessionContext = createContext<SessionContextValue | null>(null);

interface SessionProviderProps {
  children?: ReactNode;
  drafts?: DraftRecoveryModule;
  api?: SessionApi;
}

export function SessionProvider({ children, drafts = draftRecovery, api = defaultSessionApi }: SessionProviderProps) {
  const [state, dispatch] = useReducer(reduceSession, { kind: 'checking' });
  const stateRef = useRef(state);
  stateRef.current = state;

  const probe = useCallback(async (): Promise<void> => {
    dispatch({ type: 'probe-start' });
    try {
      const session = await api.probe();
      const scope = await resolveScope(session);
      drafts.setIdentity(session.user.id);
      dispatch({ type: 'probe-authenticated', session, scope });
      // An already-signed-in visitor has no pending login intent; drop any
      // stale target so a later login is not thrown back to an old route.
      discardNextUrl();
    } catch (error) {
      if (error instanceof AccountApiError && error.status === 401) {
        // Park the deep link this guest actually opened (?next= or the hash)
        // so the next successful login returns them to it.
        captureBootIntent();
        dispatch({ type: 'probe-guest' });
        return;
      }
      dispatch({ type: 'probe-network-error', retry: () => { void probe(); } });
    }
    // probe is stable per api/drafts identity; retries capture the same closure.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [api, drafts]);

  useEffect(() => { void probe(); }, [probe]);

  useEffect(() => {
    // 其他标签页登出/换号：重新探测，本标签页跟随（不再整页跳转）。
    return subscribeSessionBroadcast(() => { void probe(); });
  }, [probe]);

  useEffect(() => {
    const handleExpired = (event: Event): void => {
      // Detail is informational; the authoritative previous session comes from
      // the current state so a stale event can never forge an identity.
      const current = stateRef.current;
      if (current.kind !== 'authenticated') return;
      if (event instanceof CustomEvent) {
        const detail = event.detail as Partial<SessionExpiredDetail> | undefined;
        if (detail?.session !== undefined && detail.session.user.id !== current.session.user.id) return;
      }
      saveRecoveryPath();
      dispatch({ type: 'session-expired', recoverableData: drafts.recoverAll() });
    };
    window.addEventListener(SESSION_EXPIRED_EVENT, handleExpired);
    return () => window.removeEventListener(SESSION_EXPIRED_EVENT, handleExpired);
  }, [drafts]);

  const login = useCallback(async (username: string, password: string): Promise<void> => {
    const current = stateRef.current;
    const recovering = current.kind === 'expired' && username === current.previousSession.user.username;
    if (current.kind === 'expired' && !recovering) {
      // 换账号：清除旧账号草稿、作废属于上一位用户的回跳路径并回落访客态。
      drafts.clearAll();
      takeRecoveryPath();
      dispatch({ type: 'switch-account' });
    }
    const session = await api.login(username, password);
    const scope = await resolveScope(session);
    drafts.setIdentity(session.user.id);
    // Same-account recovery returns to the interrupted route; a fresh guest
    // login consumes the parked `?next=` intent (if any) instead.
    const restorePath = recovering ? takeRecoveryPath() : takeNextUrl();
    dispatch({ type: 'login-authenticated', session, scope });
    if (restorePath) location.hash = restorePath;
  }, [api, drafts]);

  const recoverSession = useCallback(async (password: string): Promise<void> => {
    const current = stateRef.current;
    if (current.kind !== 'expired') {
      throw new AccountApiError('invalid_state', commonT('There is no session pending recovery'), 409);
    }
    const session = await api.login(current.previousSession.user.username, password);
    const scope = await resolveScope(session);
    drafts.setIdentity(session.user.id);
    const restorePath = takeRecoveryPath();
    dispatch({ type: 'login-authenticated', session, scope });
    if (restorePath) location.hash = restorePath;
  }, [api, drafts]);

  const logout = useCallback(async (): Promise<void> => {
    const current = stateRef.current;
    if (current.kind !== 'authenticated' && current.kind !== 'expired') return;
    const session = current.kind === 'authenticated' ? current.session : current.previousSession;
    try {
      await api.logout(session);
    } catch {
      /* 会话可能已被服务端吊销；本地登出必须照常完成。 */
    }
    drafts.clearAll();
    drafts.setIdentity(null);
    notifySessionChange();
    dispatch({ type: 'signed-out' });
  }, [api, drafts]);

  const dismissRecovery = useCallback((): void => {
    // 放弃恢复时作废回跳路径：它属于已过期的那个会话，不该影响之后的登录。
    takeRecoveryPath();
    dispatch({ type: 'recovery-dismissed' });
  }, []);

  const value = useMemo<SessionContextValue>(
    () => ({ state, login, logout, recoverSession, dismissRecovery }),
    [state, login, logout, recoverSession, dismissRecovery],
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionContextValue {
  const value = useContext(SessionContext);
  if (value === null) throw new Error('useSession must be used inside <SessionProvider>');
  return value;
}
