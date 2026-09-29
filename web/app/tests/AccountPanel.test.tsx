import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { useEffect, useState } from 'react';
import { HashRouter } from 'react-router-dom';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { AccountPanelProvider } from '../src/shell/AccountPanel';
import { WorkspaceBar } from '../src/shell/WorkspaceBar';
import { I18nProvider, appI18n } from '../src/shell/I18nProvider';
import { SessionProvider, useSession, SESSION_EXPIRED_EVENT } from '../src/shell/SessionProvider';
import { SessionRecoveryModal } from '../src/shell/SessionRecoveryModal';
import type { AccountSession } from '../src/shared/account-client';

const session: AccountSession = {
  user: {id: 'u1', username: 'researcher', display_name: 'Researcher', role: 'user', status: 'active', must_change_password: false},
  csrf_token: 'csrf', invitations: [], scopes: [{id: 's1', name: 'Personal', kind: 'personal', role: 'owner', can_edit: true, can_execute: true}],
};
let mounts = 0;
function Workspace() {
  const {state} = useSession();
  const [draft, setDraft] = useState('');
  useEffect(() => { mounts++; }, []);
  return <><input aria-label="Project draft" value={draft} onChange={e => setDraft(e.target.value)}/>
    {(state.kind === 'authenticated' || state.kind === 'expired') && <WorkspaceBar session={session} scope={session.scopes[0]} view="pro" computeAvailable/>}</>;
}
function setup() {
  const api = {probe: async () => session, login: async () => session, logout: async () => {}};
  return render(<I18nProvider><SessionProvider api={api}><HashRouter><AccountPanelProvider><Workspace/></AccountPanelProvider></HashRouter><SessionRecoveryModal/></SessionProvider></I18nProvider>);
}
beforeEach(async () => {
  mounts = 0;
  localStorage.clear();
  localStorage.setItem('easydesign-easy-locale-v1', 'en');
  await appI18n.changeLanguage('en');
  window.history.replaceState({}, '', '/app/#/projects/project-1?scope=s1&view=pro');
  vi.spyOn(globalThis, 'fetch').mockImplementation(async input => {
    if (String(input).endsWith('/accounts/config')) return Response.json({compute_available: true, registration: 'open'});
    throw new Error(`Unexpected request: ${String(input)}`);
  });
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); });
it('opens settings in place, keeps project inputs and restores focus on close', async () => {
  setup();
  const trigger = await screen.findByRole('button', {name: 'Open account menu'});
  const input = screen.getByRole('textbox', {name: 'Project draft'});
  fireEvent.change(input, {target: {value: 'unsaved hypothesis'}});
  fireEvent.click(trigger);
  fireEvent.click(screen.getByRole('link', {name: 'Team collaboration'}));
  const panel = await screen.findByRole('dialog', {name: 'Account and workspace settings'});
  expect(await within(panel).findByRole('heading', {name: 'Team collaboration', level: 1})).toBeTruthy();
  expect(window.location.hash).toBe('#/projects/project-1?scope=s1&view=pro');
  expect(mounts).toBe(1);
  fireEvent.click(within(panel).getByRole('button', {name: 'Collapse menu'}));
  expect(within(panel).getByRole('button', {name: 'Expand menu'}).getAttribute('aria-expanded')).toBe('false');
  fireEvent.click(within(panel).getByRole('button', {name: 'Close settings'}));
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  expect((input as HTMLInputElement).value).toBe('unsaved hypothesis');
  expect(document.activeElement).toBe(trigger);
});
it('suspends settings for session recovery and returns to the same team input', async () => {
  setup();
  fireEvent.click(await screen.findByRole('button', {name: 'Open account menu'}));
  fireEvent.click(screen.getByRole('link', {name: 'Team collaboration'}));
  const panel = await screen.findByRole('dialog', {name: 'Account and workspace settings'});
  await within(panel).findByRole('heading', {name: 'Team collaboration', level: 1});
  fireEvent.click(within(panel).getByText('Create team', {selector: 'summary'}));
  const name = within(panel).getByRole('textbox', {name: 'Team name'});
  fireEvent.change(name, {target: {value: 'My lab'}});
  act(() => window.dispatchEvent(new CustomEvent(SESSION_EXPIRED_EVENT)));
  await waitFor(() => expect(panel.hasAttribute('open')).toBe(false));
  const recovery = screen.getByRole('dialog');
  fireEvent.change(within(recovery).getByLabelText('Password'), {target: {value: 'password'}});
  fireEvent.click(within(recovery).getByRole('button', {name: 'Sign in'}));
  await waitFor(() => expect(panel.hasAttribute('open')).toBe(true));
  expect((name as HTMLInputElement).value).toBe('My lab');
  expect(mounts).toBe(1);
});
