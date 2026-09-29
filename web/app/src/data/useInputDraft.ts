import { useRef, useState, type SetStateAction } from 'react';
import { draftRecovery, type DraftRecoveryModule } from './draftRecovery';

export type InputDraftStatus = 'empty' | 'local' | 'saved' | 'submitted';

/** Input recovery only. Restoring a value never sends a request. */
export function useInputDraft<T>(
  key: string | null,
  initial: T | (() => T),
  options: { drafts?: DraftRecoveryModule; valid?: (value: unknown) => value is T; serialize?: (value: T) => unknown } = {},
) {
  const drafts = options.drafts ?? draftRecovery;
  const identity = drafts.identity;
  const initialize = () => {
    const fallback = typeof initial === 'function' ? (initial as () => T)() : initial;
    const saved = key ? drafts.recover(key) : null;
    const valid = saved?.hasLocal && (options.valid ? options.valid(saved.data) : typeof saved.data === typeof fallback);
    return {
      key, identity,
      value: valid ? saved!.data as T : fallback,
      status: (valid ? 'local' : 'empty') as InputDraftStatus,
    };
  };
  const [stored, setStored] = useState(initialize);
  const current = stored.key === key && stored.identity === identity ? stored : initialize();
  if (current !== stored) setStored(current);
  const latest = useRef(current);
  latest.current = current;
  const setValue = (update: SetStateAction<T>) => {
    const prior = latest.current;
    if (prior.key !== key || prior.identity !== identity || drafts.identity !== identity) return;
    const value = typeof update === 'function' ? (update as (old: T) => T)(prior.value) : update;
    const next = { ...prior, value, status: 'local' as const };
    latest.current = next;
    // Synchronous persistence also captures input when a 401 is dispatched in
    // the same turn, before React has had a chance to run an effect.
    if (key) drafts.saveLocal(key, options.serialize ? options.serialize(value) : value);
    setStored(next);
  };
  const complete = (status: 'saved' | 'submitted', nextValue?: T) => {
    const prior = latest.current;
    // A late success must never erase a newer edit or another account/scope.
    if (drafts.identity !== identity) return;
    if (key) {
      const persisted = drafts.recover(key);
      const submitted = options.serialize ? options.serialize(current.value) : current.value;
      if (persisted.hasLocal && JSON.stringify(persisted.data) === JSON.stringify(submitted)) drafts.clearLocal(key);
    }
    // A successful request can advance the server revision (and thus the UI
    // key) before its Promise resolves. Clear only that old submitted copy;
    // never replace the input already displayed for the new revision.
    if (prior.key !== key || prior.identity !== identity || prior.value !== current.value) return;
    const next = { ...prior, value: nextValue === undefined ? prior.value : nextValue, status };
    latest.current = next;
    setStored(next);
  };
  return { value: current.value, setValue, status: current.status, complete };
}
