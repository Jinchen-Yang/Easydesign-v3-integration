/**
 * `?next=` return-URL mechanism (execution guide phase 2, pure frontend).
 *
 * When an unauthenticated visitor arrives with a real destination — a shared
 * deep link, or `?next=%23...` handed over by a login boundary — the intent is
 * parked in localStorage and consumed exactly once by the next successful
 * login, so the user lands where they originally wanted to go instead of a
 * generic portal. Only in-app hash routes are accepted; `location.hash`
 * assignment can never navigate off-origin.
 */

const NEXT_URL_KEY = 'easydesign-next-url';

/** A bare root is not a navigational intent; only real destinations count. */
export function isMeaningfulHash(hash: string): boolean {
  const route = hash.replace(/^#/, '');
  return hash.startsWith('#') && route !== '' && route !== '/';
}

export function captureNextUrl(target: string): void {
  if (!target.startsWith('#')) return;
  try {
    localStorage.setItem(NEXT_URL_KEY, target);
  } catch {
    /* Best-effort: without storage the login simply lands on the current route. */
  }
}

export function readNextUrl(): string | null {
  try {
    return localStorage.getItem(NEXT_URL_KEY);
  } catch {
    return null;
  }
}

export function takeNextUrl(): string | null {
  const saved = readNextUrl();
  if (saved !== null) discardNextUrl();
  return saved;
}

export function discardNextUrl(): void {
  try {
    localStorage.removeItem(NEXT_URL_KEY);
  } catch {
    /* Best-effort, same as capture. */
  }
}

/**
 * Park the visitor's intent when the session probe reports guest: an explicit
 * `?next=` hash wins, otherwise the meaningful hash they opened.
 */
export function captureBootIntent(): void {
  const explicit = new URLSearchParams(location.search).get('next');
  if (explicit !== null && explicit.startsWith('#')) {
    captureNextUrl(explicit);
    return;
  }
  if (isMeaningfulHash(location.hash)) captureNextUrl(location.hash);
}
