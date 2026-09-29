import { act, cleanup, fireEvent, render, renderHook, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { DRAFT_KEYS, draftRecovery } from '../src/data/draftRecovery';
import { useInputDraft } from '../src/data/useInputDraft';
import { GateReview } from '../src/views/pro/GateReview';
import { Conversation } from '../src/features/conversation/Conversation';
import { Landing } from '../src/app/App';
import { EasyLiveApp } from '../src/views/easy/EasyLiveApp';
import type { EasyProductPort } from '../src/views/easy/EasyProductAdapter';
import { LiveLabOrderPage } from '../src/features/lab-order/LiveLabOrderPage';
import { I18nProvider, appI18n } from '../src/shell/I18nProvider';
import { SessionProvider, SESSION_EXPIRED_EVENT, useSession, type SessionContextValue } from '../src/shell/SessionProvider';
import type { Decision, ProductLabOrder, ProductLabOrderRequirements } from '../src/data/product-contracts';
import type { AccountSession } from '../src/shared/account-client';

const session: AccountSession = {
  user: { id: 'draft-owner', username: 'draft-user', display_name: 'Draft user', role: 'user', status: 'active', must_change_password: false },
  csrf_token: 'token', invitations: [],
  scopes: [{ id: 's1', kind: 'personal', name: 'Personal', role: 'owner', can_edit: true, can_execute: true }],
};
const decision: Decision = {
  id: 'immutable-card-revision-1', gate: 2, type: 'site-hotspot', question: 'Review candidate site',
  default_option_id: 'site1', options: [{ option_id: 'site1', label: 'Site 1', description: 'Evidence', eligible: true, actions: ['revise', 'override', 'approve'] }],
  warnings: [], limitations: [], action_summary: 'Review', revision_targets: ['site-hotspot'],
  review_status: 'SUPPORTED', required_fields: { revise: ['instruction'], override: ['reason', 'acknowledgement'] }, summary: {},
};

beforeEach(async () => {
  sessionStorage.clear(); localStorage.clear();
  draftRecovery.setIdentity(session.user.id);
  localStorage.setItem('easydesign-easy-locale-v1', 'en');
  await appI18n.changeLanguage('en');
});
afterEach(cleanup);

describe('local input drafts', () => {
  it('scope changes and Gate revisions have independent values; an old success cannot clear new input', () => {
    const view = renderHook(({ scope, card }) => useInputDraft(DRAFT_KEYS.scoped(scope, 'p1', 'gate', card), ''), {
      initialProps: { scope: 's1', card: 'c1' },
    });
    act(() => view.result.current.setValue('Scope one review'));
    const completeOldRequest = view.result.current.complete;
    act(() => view.result.current.setValue('Newer edit while awaiting a response'));
    act(() => completeOldRequest('submitted'));
    expect(view.result.current.status).toBe('local');
    expect(view.result.current.value).toBe('Newer edit while awaiting a response');
    view.rerender({ scope: 's2', card: 'c1' });
    expect(view.result.current.value).toBe('');
    act(() => view.result.current.setValue('Scope two review'));
    view.rerender({ scope: 's1', card: 'c2' });
    expect(view.result.current.value).toBe('');
    view.rerender({ scope: 's1', card: 'c1' });
    expect(view.result.current.value).toBe('Newer edit while awaiting a response');
    act(() => view.result.current.complete('submitted'));
    expect(draftRecovery.recover(DRAFT_KEYS.scoped('s1', 'p1', 'gate', 'c1')).hasLocal).toBe(false);
    expect(draftRecovery.recover(DRAFT_KEYS.scoped('s2', 'p1', 'gate', 'c1')).data).toBe('Scope two review');
  });

  it('changing account prevents a mounted old input callback from writing into the new identity', () => {
    const view = renderHook(() => useInputDraft(DRAFT_KEYS.scoped('s1', 'create'), ''));
    act(() => view.result.current.setValue('Private old-account input'));
    const oldCallback = view.result.current.setValue;
    draftRecovery.setIdentity('new-account');
    act(() => oldCallback('Late old-account update'));
    view.rerender();
    expect(view.result.current.value).toBe('');
    expect(draftRecovery.recoverAll()).toEqual({});
  });
});

describe('Gate input and actual session recovery', () => {
  it('401 preserves inputs; same-account re-login restores without resubmitting; only explicit success clears', async () => {
    const machine: { current: SessionContextValue | null } = { current: null };
    const key = DRAFT_KEYS.scoped('s1', 'project', 'p1', 'gate', decision.id);
    const submit = vi.fn(async (): Promise<void> => {
      window.dispatchEvent(new CustomEvent(SESSION_EXPIRED_EVENT, { detail: { session } }));
      throw new Error('Session expired');
    });
    function Harness() {
      machine.current = useSession();
      return <GateReview decision={decision} draftKey={key} busy={machine.current.state.kind !== 'authenticated'} onSelect={() => {}} onSubmit={submit} />;
    }
    render(<I18nProvider><SessionProvider api={{ probe: async () => session, login: async () => session, logout: async () => {} }}>
      <Harness />
    </SessionProvider></I18nProvider>);
    await waitFor(() => expect(machine.current?.state.kind).toBe('authenticated'));
    fireEvent.change(screen.getByLabelText('Scientist instruction'), { target: { value: 'Recheck the solvent-exposed epitope.' } });
    fireEvent.click(screen.getByRole('button', { name: /Submit /i }));
    await waitFor(() => expect(machine.current?.state.kind).toBe('expired'));
    expect(draftRecovery.recover(key).hasLocal).toBe(true);
    await act(async () => { await machine.current!.recoverSession('secret'); });
    expect((screen.getByLabelText('Scientist instruction') as HTMLInputElement).value).toBe('Recheck the solvent-exposed epitope.');
    expect(submit).toHaveBeenCalledTimes(1);
    submit.mockImplementation(async () => {});
    fireEvent.click(screen.getByRole('button', { name: /Submit /i }));
    await waitFor(() => expect(draftRecovery.recover(key).hasLocal).toBe(false));
    expect(submit).toHaveBeenCalledTimes(2);
  });

  it('Gate override acknowledgement restores only for the same card, scope and account', async () => {
    const key = DRAFT_KEYS.scoped('s1', 'project', 'p1', 'gate', decision.id);
    const props = { decision, draftKey: key, busy: false, onSelect: vi.fn(), onSubmit: vi.fn(async (): Promise<void> => {}) };
    const view = render(<I18nProvider><GateReview {...props} /></I18nProvider>);
    fireEvent.change(screen.getByLabelText('Decision action'), { target: { value: 'override' } });
    fireEvent.change(screen.getByLabelText('Reason'), { target: { value: 'Reason supplied by the researcher' } });
    fireEvent.change(screen.getByLabelText('Acknowledgement'), { target: { value: 'I acknowledge the limitations' } });
    view.unmount();
    const restored = render(<I18nProvider><GateReview {...props} /></I18nProvider>);
    expect((screen.getByLabelText('Reason') as HTMLInputElement).value).toBe('Reason supplied by the researcher');
    expect((screen.getByLabelText('Acknowledgement') as HTMLInputElement).value).toBe('I acknowledge the limitations');
    expect(props.onSubmit).not.toHaveBeenCalled();
    restored.rerender(<I18nProvider><GateReview {...props} decision={{ ...decision, id: 'new-card' }} draftKey={DRAFT_KEYS.scoped('s1', 'project', 'p1', 'gate', 'new-card')} /></I18nProvider>);
    expect((screen.getByLabelText('Scientist instruction') as HTMLInputElement).value).toBe('');
    expect(props.onSubmit).not.toHaveBeenCalled();
  });
});

it('conversation failure preserves a remountable draft, and success clears it', async () => {
  const key = DRAFT_KEYS.scoped('s1', 'project', 'p1', 'conversation');
  const send = vi.fn(async (): Promise<void> => { throw new Error('offline'); });
  const props = { snapshot: { messages: [], phase: 'target' as const, busy: false, completed: false }, viewedPhase: 'target' as const,
    mode: 'live' as const, draftKey: key, onFocus: () => {}, onSkip: () => {}, onSend: send };
  const view = render(<I18nProvider><Conversation {...props} /></I18nProvider>);
  fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Explain the target evidence' } });
  fireEvent.click(screen.getByRole('button', { name: 'Send message' }));
  await waitFor(() => expect(send).toHaveBeenCalledTimes(1));
  view.unmount();
  render(<I18nProvider><Conversation {...props} /></I18nProvider>);
  expect((screen.getByRole('textbox') as HTMLInputElement).value).toBe('Explain the target evidence');
  send.mockImplementation(async () => {});
  fireEvent.click(screen.getByRole('button', { name: 'Send message' }));
  await waitFor(() => expect(draftRecovery.recover(key).hasLocal).toBe(false));
  expect((screen.getByRole('textbox') as HTMLInputElement).value).toBe('');
});

it('Pro creation failure retains the research goal through remount; no implicit resubmit', async () => {
  const key = DRAFT_KEYS.scoped('s1', 'pro', 'create', 'goal');
  const start = vi.fn(async (): Promise<void> => { throw new Error('offline'); });
  const props = { snapshot: { started: false, completed: false, phase: 'goal' as const, project: { exampleGoal: 'Example', title: 'Project' } },
    mode: 'live' as const, newDesign: true, focusInput: false, draftKey: key, onStart: start, onResume: () => {} };
  const view = render(<I18nProvider><Landing {...props} /></I18nProvider>);
  fireEvent.change(screen.getByRole('textbox'), { target: { value: 'A researcher-entered design goal' } });
  fireEvent.click(screen.getByRole('button', { name: 'Start design' }));
  await waitFor(() => expect(start).toHaveBeenCalledTimes(1));
  view.unmount();
  render(<I18nProvider><Landing {...props} /></I18nProvider>);
  expect((screen.getByRole('textbox') as HTMLInputElement).value).toBe('A researcher-entered design goal');
  expect(start).toHaveBeenCalledTimes(1);
});

it('restored Easy file metadata requires re-selection and cannot start a scientific request', async () => {
  const key = DRAFT_KEYS.scoped('s1', 'easy', 'create');
  draftRecovery.saveLocal(key, { type: 'structure', name: 'Example', text: '', species: '', goal: 'Design a VHH', file: { name: 'target.pdb', size: 124 } });
  const create = vi.fn();
  const adapter = {
    load: async () => ({ connection: 'connected', projects: { items: [], total: 0, offset: 0 }, candidates: { items: [], total: 0, offset: 0 },
      snapshot: null, selectedProject: null, selectedCandidate: null, pendingRequest: null, pending: false, error: null }),
    subscribe: () => () => {}, dispose: () => {}, createTypedProject: create,
  } as unknown as EasyProductPort;
  render(<I18nProvider><EasyLiveApp adapter={adapter} access={session.scopes[0]} /></I18nProvider>);
  expect(await screen.findByText(/Attachment target.pdb \(124 bytes\) must be selected again/)).toBeTruthy();
  const start = screen.getByRole('button', { name: 'Start design' }) as HTMLButtonElement;
  expect(start.disabled).toBe(true);
  fireEvent.click(start);
  expect(create).not.toHaveBeenCalled();
  expect(draftRecovery.recover(key).hasLocal).toBe(true);
});

it('Lab Order local changes remain distinct from server-saved draft, failed save retains them', async () => {
  const requirements: ProductLabOrderRequirements = { format: 'VHH', amount: '1 mg', host: 'E. coli', buffer: 'PBS', profile: 'simulation-lab',
    preferred_date: '', purchase_order: '', sds_purity: '', sec_purity: '', endotoxin: '', concentration: '', notes: '' };
  const order: ProductLabOrder = { schema_version: '1', mode: 'simulation', provider: 'mock-lab-v1', project_id: 'p1',
    handoff_sha256: 'synthetic-sha', handoff_status: 'complete', ordering_status: 'draft', revision: 'revision1',
    candidates: [{ id: 'c1', selection_class: 'selected', selection_rank: 1, sequence_length: 12, sequence_ready: true, sequence_sha256: 'synthetic-sequence-sha' }],
    draft: { schema_version: '1', candidate_ids: ['c1'], requirements, reviewed: true }, quote: null, receipt: null,
    capabilities: { save: true, quote: true, submit: false, real_order: false }, disclaimer: 'Simulation only' };
  const key = DRAFT_KEYS.scoped('s1', 'project', 'p1', 'lab-order');
  const apply = vi.fn(async (): Promise<void> => { throw new Error('Network unavailable'); });
  const props = { order, draftKey: key, busy: false, error: '', onApply: apply };
  const view = render(<I18nProvider><LiveLabOrderPage {...props} /></I18nProvider>);
  fireEvent.change(screen.getByLabelText('Amount per sample'), { target: { value: '2 mg' } });
  expect((screen.getByRole('button', { name: /Generate mock quote/ }) as HTMLButtonElement).disabled).toBe(true);
  fireEvent.click(screen.getByRole('button', { name: 'Save simulation draft' }));
  expect(await screen.findByRole('alert')).toHaveProperty('textContent', 'Network unavailable');
  expect(draftRecovery.recover(`${key}:revision1`).hasLocal).toBe(true);
  view.unmount();
  render(<I18nProvider><LiveLabOrderPage {...props} /></I18nProvider>);
  expect((screen.getByLabelText('Amount per sample') as HTMLInputElement).value).toBe('2 mg');
  apply.mockImplementation(async () => {});
  fireEvent.click(screen.getByRole('button', { name: 'Save simulation draft' }));
  await waitFor(() => expect(draftRecovery.recover(`${key}:revision1`).hasLocal).toBe(false));
  expect(screen.getByText('Saved to the server; not submitted for execution.')).toBeTruthy();
  expect(apply).toHaveBeenCalledTimes(2);
});
