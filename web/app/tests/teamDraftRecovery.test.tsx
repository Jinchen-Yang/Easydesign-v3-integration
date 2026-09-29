import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { HashRouter } from 'react-router-dom';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { AccountApp } from '../src/views/account/AccountApp';
import { I18nProvider, LANGUAGE_KEY, appI18n } from '../src/shell/I18nProvider';
import { SessionProvider, SESSION_EXPIRED_EVENT, useSession, type SessionContextValue } from '../src/shell/SessionProvider';
import type { AccountSession, ProjectDraft } from '../src/shared/account-client';

const session: AccountSession = {
  user: { id: 'u1', username: 'researcher', display_name: 'Researcher', role: 'user', status: 'active', must_change_password: false },
  csrf_token: 'token', invitations: [],
  scopes: ['team1', 'team2'].map(id => ({ id, name: id, kind: 'team', role: 'owner', can_edit: true, can_execute: true })),
};
const savedDraft = (): ProjectDraft => ({ id: 'd1', revision: 1, payload: { title: 'Saved title', goal: 'Saved research goal' },
  state: 'draft', created_by: 'u1', updated_by: 'u1', created_at: 1, updated_at: 1, start_request_id: null, project_id: null });

beforeEach(async () => {
  localStorage.clear(); sessionStorage.clear(); localStorage.setItem(LANGUAGE_KEY, 'en');
  await appI18n.changeLanguage('en');
  window.history.replaceState({}, '', '/#/account?section=teams');
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

function mount(options: { conflict?: boolean; team2?: () => Promise<Response> } = {}) {
  let draft = savedDraft();
  const writes: unknown[] = [];
  const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = String(input);
    if (url.endsWith('/accounts/config')) return Response.json({ mode: 'multi-user', registration: 'open', setup_required: false, compute_available: true });
    if (url.endsWith('/teams/team1')) return Response.json({ team: { id: 'team1', name: 'Team one', status: 'active', members: [] } });
    if (url.endsWith('/teams/team2')) return options.team2 ? options.team2() : Response.json({ team: { id: 'team2', name: 'Team two', status: 'active', members: [] } });
    if (url.includes('/drafts') && init?.method === 'POST') {
      writes.push(JSON.parse(String(init.body)));
      if (options.conflict) {
        draft = { ...draft, revision: 2, payload: { title: 'Colleague title', goal: 'Colleague research goal' } };
        return Response.json({ error: { code: 'stale_draft', message: 'Another member saved a newer revision.' } }, { status: 409 });
      }
      return Response.json({ draft });
    }
    if (url.includes('/scopes/team1/drafts')) return Response.json({ drafts: [draft] });
    if (url.includes('/scopes/team2/drafts')) return Response.json({ drafts: [] });
    throw new Error(`Unexpected request ${url}`);
  });
  const machine: { current: SessionContextValue | null } = { current: null };
  function Capture() { machine.current = useSession(); return null; }
  render(<I18nProvider><SessionProvider api={{ probe: async () => ({ ...session }), login: async () => ({ ...session, csrf_token: 'new-token' }), logout: async () => {} }}>
    <HashRouter><Capture/><AccountApp/></HashRouter>
  </SessionProvider></I18nProvider>);
  return { machine, writes, fetchMock, setDraft: (next: ProjectDraft) => { draft = next; } };
}

it('team creation form survives permission refresh and same-account expiry recovery', async () => {
  const { machine } = mount();
  const panel = await screen.findByRole('region', { name: 'Team project drafts' });
  fireEvent.click(within(panel).getByRole('button', { name: 'New draft' }));
  fireEvent.change(within(panel).getByLabelText('Title'), { target: { value: 'Unsubmitted title' } });
  fireEvent.change(within(panel).getByLabelText('Research goal'), { target: { value: 'Unsubmitted research goal' } });
  await act(async () => { await machine.current!.refreshSession(); });
  expect((within(panel).getByLabelText('Title') as HTMLInputElement).value).toBe('Unsubmitted title');
  act(() => window.dispatchEvent(new CustomEvent(SESSION_EXPIRED_EVENT, { detail: { session } })));
  await act(async () => { await machine.current!.recoverSession('password'); });
  expect((within(panel).getByLabelText('Research goal') as HTMLTextAreaElement).value).toBe('Unsubmitted research goal');
});

it('a save conflict retains input and its original revision until explicitly loading the newer version', async () => {
  const { writes } = mount({ conflict: true });
  const panel = await screen.findByRole('region', { name: 'Team project drafts' });
  fireEvent.click(await within(panel).findByRole('button', { name: 'Edit' }));
  fireEvent.change(within(panel).getByLabelText('Research goal'), { target: { value: 'My unsaved research goal' } });
  fireEvent.click(within(panel).getByRole('button', { name: 'Save new version' }));
  await within(panel).findByText('Another member saved a newer revision.');
  await within(panel).findByText('Colleague title');
  expect((within(panel).getByLabelText('Research goal') as HTMLTextAreaElement).value).toBe('My unsaved research goal');
  expect((within(panel).getByRole('button', { name: 'Save new version' }) as HTMLButtonElement).disabled).toBe(true);
  expect(writes).toHaveLength(1);
  expect(writes[0]).toMatchObject({ revision: 1 });
  fireEvent.click(within(panel).getByRole('button', { name: 'Discard my edits and load the latest saved version' }));
  expect((within(panel).getByLabelText('Research goal') as HTMLTextAreaElement).value).toBe('Colleague research goal');
  expect((within(panel).getByRole('button', { name: 'Save new version' }) as HTMLButtonElement).disabled).toBe(false);
});

it('a permission refresh cannot silently upgrade the revision underneath an open editor', async () => {
  const { machine, setDraft, writes } = mount();
  const panel = await screen.findByRole('region', { name: 'Team project drafts' });
  fireEvent.click(await within(panel).findByRole('button', { name: 'Edit' }));
  fireEvent.change(within(panel).getByLabelText('Research goal'), { target: { value: 'My edit based on revision one' } });
  setDraft({ ...savedDraft(), revision: 2, payload: { title: 'Other saved version', goal: 'Someone else changed the goal' } });
  await act(async () => { await machine.current!.refreshSession(); });
  await within(panel).findByText('Other saved version');
  expect((within(panel).getByLabelText('Research goal') as HTMLTextAreaElement).value).toBe('My edit based on revision one');
  expect((within(panel).getByRole('button', { name: 'Save new version' }) as HTMLButtonElement).disabled).toBe(true);
  expect(writes).toHaveLength(0);
});

it('switching teams hides the old team actions and drafts while the new team loads', async () => {
  let finish!: (value: Response) => void;
  const { fetchMock } = mount({ team2: () => new Promise(resolve => { finish = resolve; }) });
  await screen.findByRole('button', { name: 'Edit' });
  fireEvent.change(screen.getByLabelText('Select team'), { target: { value: 'team2' } });
  expect(screen.queryByText('Team one')).toBeNull();
  expect(screen.queryByRole('button', { name: 'Edit' })).toBeNull();
  await waitFor(() => expect(fetchMock).toHaveBeenCalledWith('/api/v1/teams/team2', expect.anything()));
  await act(async () => { finish(Response.json({ team: { id: 'team2', name: 'Team two', status: 'active', members: [] } })); });
  expect(await screen.findByText('Team two')).toBeTruthy();
  expect(screen.queryByText('Saved title')).toBeNull();
});
