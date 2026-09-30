// Value import from a leaf module: sessionEvents type-imports this file, so
// the cycle stays type-only and erases at runtime.
import {
  dispatchSessionExpired,
  dispatchSessionPermissions,
  needsPermissionRefresh,
} from "./sessionEvents";
import { appI18n } from "../shell/I18nProvider";

const commonT = (key: string): string => appI18n.t(key, { ns: "common" });

export interface AccountUser {
  id: string;
  username: string;
  display_name: string;
  role: "admin" | "user";
  status: "pending" | "active" | "suspended" | "rejected";
  must_change_password: boolean;
}

export interface AccountScope {
  id: string;
  kind: "personal" | "team";
  name: string;
  role: "owner" | "admin" | "member" | "observer";
  can_edit: boolean;
  can_execute: boolean;
}

export interface Invitation {
  id: string;
  team_id: string;
  team_name: string;
  role: "admin" | "member";
}

export interface AccountSession {
  user: AccountUser;
  csrf_token: string;
  scopes: AccountScope[];
  invitations: Invitation[];
}

export interface QuotaLimits {
  max_active_jobs: number;
  max_active_chats: number;
  max_gpu_devices: number;
  max_upload_bytes: number;
  max_stored_upload_bytes: number;
  /** Per-execution candidate ceiling — not the cumulative final-design balance. */
  max_candidates_per_job: number;
  /** Personal cumulative final-design allowance; null = unrestricted. */
  final_designs_allowance: number | null;
  /** Stage budget frozen into NEW projects of this scope; null = native default. */
  pilot_stage_budget: number | null;
  /** Stage budget frozen into NEW projects of this scope; null = native default. */
  scale_stage_budget: number | null;
}

export class AccountApiError extends Error {
  constructor(
    public code: string,
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

export interface AccountConfig {
  mode: string;
  registration: string;
  setup_required: boolean;
  /** False when the service runs without a scientific launcher (accounts-only). */
  compute_available: boolean;
}

export function fetchAccountConfig(): Promise<AccountConfig> {
  return accountApi<AccountConfig>("/accounts/config");
}

export function accountMode(): boolean {
  return (
    document
      .querySelector('meta[name="easydesign-identity-mode"]')
      ?.getAttribute("content") === "accounts"
  );
}

export async function accountApi<T>(
  path: string,
  session?: AccountSession | null,
  body?: unknown,
): Promise<T> {
  const headers: Record<string, string> = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (session) headers["X-CSRF-Token"] = session.csrf_token;
  let response: Response;
  try {
    response = await fetch("/api/v1" + path, {
      method: body === undefined ? "GET" : "POST",
      credentials: "same-origin",
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: AbortSignal.timeout(30_000),
    });
  } catch {
    throw new AccountApiError(
      "network_error",
      commonT("Network error; please try again later"),
      0,
    );
  }
  // A proxy or partial outage can return HTML/text; never leak a parse crash as the error.
  if (response.status === 401 && session) dispatchSessionExpired({ session });
  const value: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = value as {
      error?: { code?: string; message?: string };
    } | null;
    throw new AccountApiError(
      detail?.error?.code || "request_failed",
      detail?.error?.message ||
        commonT("The request could not be completed for now"),
      response.status,
    );
  }
  return value as T;
}

export function workspaceUrl(
  scope: string,
  surface: "easy" | "professional" = "easy",
): string {
  return `${surface === "easy" ? "/easy/" : "/"}?scope=${encodeURIComponent(scope)}`;
}

export function accountLoginUrl(): string {
  return "/account/";
}

export async function currentAccountScope(
  session: AccountSession,
): Promise<AccountScope> {
  const id =
    new URLSearchParams(location.search).get("scope") || session.user.id;
  const known = session.scopes.find((item) => item.id === id);
  if (known) return known;
  return (
    await accountApi<{ scope: AccountScope }>(
      `/scopes/${encodeURIComponent(id)}/usage`,
      session,
    )
  ).scope;
}

export function scopedProductPath(scope: string, path: string): string {
  if (path.startsWith("/api/v1/scopes/")) return path;
  if (path.startsWith("/api/v1/"))
    return (
      `/api/v1/scopes/${encodeURIComponent(scope)}` +
      path.slice("/api/v1".length)
    );
  if (path === "/api/rabbit/localize")
    return `/api/v1/scopes/${encodeURIComponent(scope)}/rabbit/localize`;
  if (path === "/api/rabbit/chat")
    return `/api/v1/scopes/${encodeURIComponent(scope)}/rabbit/chat`;
  return path;
}

/**
 * Scope declared product link fields for href use. The server rewrites keys named
 * `url`, but fields such as `decision.details_url` can still point at the
 * unscoped API, which an account session cannot call; keep them usable here and
 * never silently fall back to an unscoped endpoint.
 */
export function scopeProductUrl(
  scope: string,
  url: string | null | undefined,
): string | undefined {
  return typeof url === "string" && url.startsWith("/api/v1/")
    ? scopedProductPath(scope, url)
    : url || undefined;
}

/** Project a product snapshot's decision link fields into the caller's scope. */
export function scopeDecisionLinks<
  T extends { decision?: { details_url?: string } | null },
>(snapshot: T, scope: string): T {
  const url = snapshot.decision?.details_url;
  if (!url || !url.startsWith("/api/v1/")) return snapshot;
  return {
    ...snapshot,
    decision: {
      ...snapshot.decision!,
      details_url: scopedProductPath(scope, url),
    },
  };
}

export interface SurfaceAccess {
  can_edit: boolean;
  can_execute: boolean;
  role: string;
}

export interface SurfaceRights {
  canEdit: boolean;
  canExecute: boolean;
  /** Team members may discuss and co-edit; read-only observers may not. */
  canDiscuss: boolean;
  readOnly: boolean;
}

/**
 * Mirror of the backend scope rights for UI gating only. The server remains the
 * authority; these flags just keep controls that cannot succeed disabled.
 * `compute` reflects the account config: without a scientific launcher the
 * backend refuses admissions, so no surface may offer execution or project
 * conversation, while co-editing (rename, drafts) stays available.
 */
export function surfaceRights(
  access?: SurfaceAccess | null,
  compute = true,
): SurfaceRights {
  const canEdit = access?.can_edit ?? true;
  const canExecute = (access?.can_execute ?? true) && compute;
  return {
    canEdit,
    canExecute,
    canDiscuss: canEdit && compute,
    readOnly: !canEdit,
  };
}

export interface SessionRef {
  current: AccountSession | null;
}

/**
 * Like scopedTransport, but the session is read from a ref at request time, so
 * one transport — and the adapter built on it, with its idempotency
 * request-id tables — survives a same-account re-login during expiry recovery.
 */
async function observeScopedPermissions(
  response: Response,
  session: AccountSession,
  scope: AccountScope,
) {
  if (response.status !== 403 && response.status !== 404) return;
  const value = await response
    .clone()
    .json()
    .catch(() => null);
  const code = value?.error?.code;
  if (typeof code === "string" && needsPermissionRefresh(response.status, code))
    dispatchSessionPermissions({
      session,
      scope,
      status: response.status,
      code,
    });
}

export function scopedTransportFromRef(
  ref: SessionRef,
  scope: AccountScope,
): typeof fetch {
  const owner = ref.current?.user.id;
  return async (input, init) => {
    const session = ref.current;
    if (typeof input !== "string" || session === null) {
      throw new Error(
        "Scoped requests require a relative URL and a live session",
      );
    }
    if (session.user.id !== owner)
      throw new AccountApiError(
        "identity_changed",
        commonT("The active account changed. Reopen this workspace."),
        409,
      );
    const headers = new Headers(init?.headers);
    headers.set("X-CSRF-Token", session.csrf_token);
    const response = await fetch(scopedProductPath(scope.id, input), {
      ...init,
      headers,
      credentials: "same-origin",
    });
    if (response.status === 401) {
      notifySessionChange();
      dispatchSessionExpired({ session, scope });
    }
    await observeScopedPermissions(response, session, scope);
    return response;
  };
}

export function scopedTransport(
  session: AccountSession,
  scope: AccountScope,
): typeof fetch {
  // Capture this session/scope. An old tab must not act using a newly signed-in user's CSRF token.
  return async (input, init) => {
    if (typeof input !== "string")
      throw new Error("Scoped requests require a relative product URL");
    const headers = new Headers(init?.headers);
    headers.set("X-CSRF-Token", session.csrf_token);
    const response = await fetch(scopedProductPath(scope.id, input), {
      ...init,
      headers,
      credentials: "same-origin",
    });
    if (response.status === 401) {
      // 旧界面（/easy/、/account/ 兼容期）仍靠广播自行跳转；本应用不再
      // location.replace —— 只发事件，由 SessionProvider 切到 expired 状态
      // 并浮出恢复遮罩，页面与未保存输入原地保留。
      notifySessionChange();
      dispatchSessionExpired({ session, scope });
    }
    await observeScopedPermissions(response, session, scope);
    return response;
  };
}

// BroadcastChannel delivers to other channel objects even within the same page.
// Tag every broadcast with its originating page so a page never reacts to its
// own login/logout and redirects itself away from the surface it just opened.
const PAGE_ID = crypto.randomUUID();

export function notifySessionChange(): void {
  const channel = new BroadcastChannel("easydesign-account-session");
  channel.postMessage({ type: "session-changed", origin: PAGE_ID });
  channel.close();
}

/**
 * 订阅**其他标签页**的会话变化（登录/登出）。新应用不做整页跳转，由
 * SessionProvider 收到通知后重新探测，多标签页保持同一真相。
 */
export function subscribeSessionBroadcast(handler: () => void): () => void {
  const channel = new BroadcastChannel("easydesign-account-session");
  channel.onmessage = (event: MessageEvent) => {
    const data = event.data as { origin?: string } | null;
    if (data?.origin && data.origin !== PAGE_ID) handler();
  };
  return () => {
    channel.close();
  };
}

export function watchSessionChanges(): () => void {
  const channel = new BroadcastChannel("easydesign-account-session");
  channel.onmessage = (event: MessageEvent) => {
    const data = event.data as { origin?: string } | null;
    if (data?.origin && data.origin !== PAGE_ID)
      location.replace(accountLoginUrl());
  };
  const restore = (event: PageTransitionEvent) => {
    if (event.persisted) location.reload();
  };
  window.addEventListener("pageshow", restore);
  return () => {
    channel.close();
    window.removeEventListener("pageshow", restore);
  };
}

export interface ProjectDraft {
  id: string;
  revision: number;
  payload: {
    title: string;
    goal: string;
    input_id?: string | null;
    surface?: string;
  };
  state: "draft" | "starting" | "started";
  created_by: string;
  updated_by: string;
  created_at: number;
  updated_at: number;
  start_request_id: string | null;
  project_id: string | null;
}

export interface ResourceAdmission {
  id: string;
  scope_id: string;
  request_id: string;
  actor_id: string;
  kind: "scientific" | "conversation";
  state: string;
  gpu_slots: number;
  max_candidates: number;
  devices: number[];
  created_at: number;
  updated_at: number;
  reason: string | null;
}

/** One Gate-4 campaign charge against a person's final-design allowance. */
export interface FinalDesignEntry {
  id: string;
  scope_id: string;
  project_id: string;
  request_id: string;
  /** Gate-4 card id — the canonical approval identity. */
  authority_key: string;
  /** The billed person (original approver). */
  subject_id: string;
  amount: number;
  delivered: number | null;
  state: "reserved" | "settled" | "released";
  campaign_sha256: string | null;
  reason: string | null;
  created_at: number;
  updated_at: number;
}

/** The caller's own cumulative balance (personal scope usage block). */
export interface FinalDesignsPersonal {
  kind: "personal";
  subject_id: string;
  allowance: number | null;
  reserved: number;
  delivered: number;
  remaining: number | null;
  rule: string;
  entries: FinalDesignEntry[];
}

/** Team-local aggregate only; never other members' personal balances. */
export interface FinalDesignsTeam {
  kind: "team";
  scope_id: string;
  reserved: number;
  delivered: number;
  rule: string;
  entries: FinalDesignEntry[];
}

export type FinalDesignsBlock = FinalDesignsPersonal | FinalDesignsTeam;

export interface ScopeUsage {
  scope: AccountScope;
  limits: QuotaLimits;
  stored_upload_bytes: number;
  admissions: ResourceAdmission[];
  final_designs: FinalDesignsBlock;
}

/** Site-wide final-design aggregates for the platform admin console. */
export interface FinalDesignsSubjectSummary {
  subject_id: string;
  username: string | null;
  display_name: string | null;
  allowance: number | null;
  reserved: number;
  delivered: number;
  remaining: number | null;
}

export interface FinalDesignsOverview {
  rule: string;
  entries: FinalDesignEntry[];
  subjects: FinalDesignsSubjectSummary[];
}

export function fetchFinalDesignsOverview(
  session: AccountSession,
): Promise<FinalDesignsOverview> {
  return accountApi<FinalDesignsOverview>("/admin/final-designs", session);
}

async function scopedApi<T>(
  transport: typeof fetch,
  path: string,
  body?: unknown,
): Promise<T> {
  const response = await transport(path, {
    method: body === undefined ? "GET" : "POST",
    ...(body === undefined
      ? {}
      : {
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        }),
    credentials: "same-origin",
    signal: AbortSignal.timeout(30_000),
  });
  const value: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = value as {
      error?: { code?: string; message?: string };
    } | null;
    throw new AccountApiError(
      detail?.error?.code || "request_failed",
      detail?.error?.message ||
        commonT("The operation could not be completed for now"),
      response.status,
    );
  }
  return value as T;
}

/** Team collaboration drafts: saving never starts science; starting claims a revision. */
export const draftsApi = {
  list: (transport: typeof fetch) =>
    scopedApi<{ drafts: ProjectDraft[] }>(transport, "/api/v1/drafts"),
  save: (
    transport: typeof fetch,
    draft: { title: string; goal: string; input_id?: string | null },
    identity?: string,
    expectedRevision?: number,
  ) =>
    scopedApi<{ draft: ProjectDraft }>(
      transport,
      identity
        ? `/api/v1/drafts/${encodeURIComponent(identity)}`
        : "/api/v1/drafts",
      { ...draft, ...(identity ? { revision: expectedRevision } : {}) },
    ),
  start: (transport: typeof fetch, identity: string, revision: number) =>
    scopedApi<{
      draft?: ProjectDraft;
      project?: { id: string };
    }>(transport, `/api/v1/drafts/${encodeURIComponent(identity)}/start`, {
      revision,
      request_id: crypto.randomUUID(),
    }),
};

export function fetchScopeUsage(
  session: AccountSession,
  scopeId: string,
): Promise<ScopeUsage> {
  return accountApi<ScopeUsage>(
    `/scopes/${encodeURIComponent(scopeId)}/usage`,
    session,
  );
}
