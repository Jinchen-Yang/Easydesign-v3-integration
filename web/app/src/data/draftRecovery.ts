import { draftsApi, type ProjectDraft } from '../shared/account-client';

/**
 * Draft recovery keeps unsubmitted work alive across a session-expiry overlay.
 *
 * Layering follows the execution guide: the local layer (sessionStorage) always
 * exists, the remote layer (team draft API) mirrors project-creation drafts
 * once they have an identity. Recovery prefers the remote copy because the
 * backend holds the authoritative revision; the local copy covers inputs that
 * were never saved remotely (Gate notes, file references).
 *
 * Namespacing rule: every storage key is prefixed with the owning identity
 * (`easydesign:draft:{accountId}:` or `easydesign:draft:guest:`). Guest drafts
 * never share a namespace with real accounts, and switching accounts purges the
 * previous account's drafts so old work is never restored for a new user.
 */

/** Logical key vocabulary — never store raw project data under other keys. */
export const DRAFT_KEYS = {
  projectCreate: 'draft:project:create',
  projectGate: (projectId: string) => `draft:project:${projectId}:gate`,
  projectFiles: (projectId: string) => `draft:project:${projectId}:files`,
} as const;

const GUEST_IDENTITY = 'guest';
const ENVELOPE_VERSION = 1;

interface DraftEnvelope {
  v: number;
  savedAt: number;
  data: unknown;
}

export interface RecoveredDraft {
  hasLocal: boolean;
  hasRemote: boolean;
  /** Remote payload when one exists (authoritative), otherwise the local copy. */
  data: unknown;
  savedAt: number | null;
}

export interface DraftRecoveryModule {
  /** Identity the namespace currently belongs to: an account id or 'guest'. */
  readonly identity: string;
  saveLocal(key: string, data: unknown): void;
  /** Mirrors a project-creation draft through the backend team-draft API. */
  saveRemote(draft: ProjectDraft): Promise<void>;
  /** Publishes the current remote draft list so recover() can report hasRemote. */
  syncRemote(drafts: ProjectDraft[]): void;
  recover(key: string): RecoveredDraft;
  /** Snapshot of every local draft in the current namespace (for the expired state). */
  recoverAll(): Record<string, unknown>;
  clearLocal(key: string): void;
  clearAll(): void;
  /**
   * Rebinds the namespace. Moving between two account identities purges the
   * previous account's drafts; moving to or from guest never deletes guest
   * drafts — they stay isolated in the guest namespace.
   */
  setIdentity(accountId: string | null): void;
}

/** sessionStorage can be blocked (private modes); degrade to in-memory only. */
function resolveStorage(): Storage {
  try {
    const probe = '__easydesign_draft_probe__';
    window.sessionStorage.setItem(probe, probe);
    window.sessionStorage.removeItem(probe);
    return window.sessionStorage;
  } catch {
    const memory = new Map<string, string>();
    return {
      get length() { return memory.size; },
      clear: () => memory.clear(),
      getItem: (key) => memory.get(key) ?? null,
      key: (index) => [...memory.keys()][index] ?? null,
      removeItem: (key) => { memory.delete(key); },
      setItem: (key, value) => { memory.set(key, value); },
    };
  }
}

function parseEnvelope(raw: string | null): DraftEnvelope | null {
  if (raw === null) return null;
  try {
    const value: unknown = JSON.parse(raw);
    if (
      typeof value !== 'object' || value === null ||
      (value as DraftEnvelope).v !== ENVELOPE_VERSION ||
      typeof (value as DraftEnvelope).savedAt !== 'number'
    ) return null;
    return value as DraftEnvelope;
  } catch {
    return null;
  }
}

export function createDraftRecovery(
  options: { storage?: Storage; transport?: typeof fetch } = {},
): DraftRecoveryModule {
  const storage = options.storage ?? resolveStorage();
  const transport = options.transport;
  const remoteByKey = new Map<string, ProjectDraft>();
  let identity = GUEST_IDENTITY;

  const prefix = () => `easydesign:draft:${identity}`;
  const storageKey = (key: string) => `${prefix()}:${key}`;
  const remoteKey = (draftId: string) => `draft:project:${draftId}`;

  const keysInNamespace = (): string[] => {
    const found: string[] = [];
    for (let index = 0; index < storage.length; index += 1) {
      const key = storage.key(index);
      if (key !== null && key.startsWith(`${prefix()}:`)) found.push(key);
    }
    return found;
  };

  const purgePrefix = (target: string): void => {
    for (let index = storage.length - 1; index >= 0; index -= 1) {
      const key = storage.key(index);
      if (key !== null && key.startsWith(`easydesign:draft:${target}:`)) storage.removeItem(key);
    }
  };

  return {
    get identity() { return identity; },

    saveLocal(key, data) {
      const envelope: DraftEnvelope = { v: ENVELOPE_VERSION, savedAt: Date.now(), data };
      try {
        storage.setItem(storageKey(key), JSON.stringify(envelope));
      } catch {
        /* Quota or blocked storage: recovery stays best-effort, never fatal. */
      }
    },

    async saveRemote(draft) {
      if (!transport) throw new Error('saveRemote requires a scoped transport');
      const saved = await draftsApi.save(transport, draft.payload, draft.id, draft.revision);
      remoteByKey.set(remoteKey(saved.draft.id), saved.draft);
    },

    syncRemote(drafts) {
      remoteByKey.clear();
      for (const draft of drafts) remoteByKey.set(remoteKey(draft.id), draft);
    },

    recover(key) {
      const local = parseEnvelope(storage.getItem(storageKey(key)));
      const remote = remoteByKey.get(key);
      return {
        hasLocal: local !== null,
        hasRemote: remote !== undefined,
        // 远程优先：后端草稿带权威 revision，本地只兜底未保存的输入。
        data: remote !== undefined ? remote.payload : local !== null ? local.data : null,
        savedAt: local !== null ? local.savedAt : remote !== undefined ? remote.updated_at * 1000 : null,
      };
    },

    recoverAll() {
      const recovered: Record<string, unknown> = {};
      for (const fullKey of keysInNamespace()) {
        const envelope = parseEnvelope(storage.getItem(fullKey));
        if (envelope !== null) recovered[fullKey.slice(prefix().length + 1)] = envelope.data;
      }
      return recovered;
    },

    clearLocal(key) {
      storage.removeItem(storageKey(key));
    },

    clearAll() {
      for (const key of keysInNamespace()) storage.removeItem(key);
    },

    setIdentity(accountId) {
      const next = accountId ?? GUEST_IDENTITY;
      if (next === identity) return;
      // 换账号（账号 → 账号）或登出（账号 → 访客）：旧账号草稿必须清空，
      // 绝不让上一位用户的工作恢复到新会话。访客命名空间始终保留。
      if (identity !== GUEST_IDENTITY) purgePrefix(identity);
      identity = next;
      remoteByKey.clear();
    },
  };
}

/** Application-wide instance; SessionProvider receives it by default. */
export const draftRecovery = createDraftRecovery();
