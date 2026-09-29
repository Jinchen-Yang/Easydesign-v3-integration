import {cleanup, fireEvent, render, screen, waitFor, act} from '@testing-library/react';
import {afterEach, beforeAll, expect, it, vi} from 'vitest';
import {RabbitChat} from '../src/views/easy/RabbitChat';
import {AccountTransportContext} from '../src/views/easy/AccountTransportContext';
import {loadAppNamespaces} from '../src/shell/I18nProvider';
import type {AccountScope} from '../src/shared/account-client';

const scope: AccountScope = {id:'personal-test',name:'Personal',kind:'personal',role:'owner',can_edit:true,can_execute:true};
const props = {open:true,locale:'en' as const,context:{stage:'Idle' as const,status:'idle' as const,goal:''},style:{},onClose:vi.fn(),onSettings:vi.fn(),onActivity:vi.fn()};
beforeAll(async () => { await loadAppNamespaces(['easy']); });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
function view(transport: typeof fetch) {
  return <AccountTransportContext.Provider value={{transport,scope}}><RabbitChat {...props}/></AccountTransportContext.Provider>;
}

it('guides demo visitors to a workspace without calling an unscoped endpoint', () => {
  const fetcher = vi.fn(); vi.stubGlobal('fetch', fetcher);
  render(<RabbitChat {...props}/>);
  expect(screen.getByRole('link', {name:'Sign in / choose a workspace'}).getAttribute('href')).toBe('#/account');
  expect(screen.queryByText('Chat is not connected yet.')).toBeNull();
  expect((screen.getByRole('textbox') as HTMLTextAreaElement).disabled).toBe(true);
  fireEvent.submit(screen.getByRole('textbox').closest('form')!);
  expect(fetcher).not.toHaveBeenCalled();
});

it.each([404, 503])('does not misreport HTTP %s as missing configuration, and can retry', async status => {
  const transport = vi.fn<typeof fetch>()
    .mockResolvedValueOnce(Response.json({error:{code:'not_found'}}, {status}))
    .mockResolvedValueOnce(Response.json({configured:true}));
  render(view(transport));
  await screen.findByText('Could not check the chat connection. Please try again.');
  expect(screen.queryByText('Chat is not connected yet.')).toBeNull();
  expect((screen.getByRole('textbox') as HTMLTextAreaElement).disabled).toBe(true);
  fireEvent.click(screen.getByRole('button', {name:'Retry connection'}));
  await waitFor(() => expect((screen.getByRole('textbox') as HTMLTextAreaElement).disabled).toBe(false));
  expect(transport).toHaveBeenCalledTimes(2);
});

it('reports authentication separately from configuration', async () => {
  const transport = vi.fn<typeof fetch>().mockResolvedValue(Response.json({error:{code:'unauthorized'}}, {status:401}));
  render(view(transport));
  await screen.findByText(/The session or workspace permission changed/);
  expect(screen.queryByText('Chat is not connected yet.')).toBeNull();
});

it('only reports not configured when the server explicitly says false', async () => {
  const transport = vi.fn<typeof fetch>().mockResolvedValue(Response.json({configured:false}));
  render(view(transport));
  await screen.findByText('Chat is not connected yet.');
  expect((screen.getByRole('textbox') as HTMLTextAreaElement).disabled).toBe(true);
});

it('ignores an old status response after the workspace transport changes', async () => {
  let finishOld!: (response: Response) => void;
  const old = vi.fn<typeof fetch>(() => new Promise(resolve => { finishOld = resolve; }));
  const current = vi.fn<typeof fetch>().mockResolvedValue(Response.json({configured:true}));
  const rendered = render(view(old));
  rendered.rerender(view(current));
  await waitFor(() => expect((screen.getByRole('textbox') as HTMLTextAreaElement).disabled).toBe(false));
  await act(async () => { finishOld(Response.json({configured:false})); });
  expect(screen.queryByText('Chat is not connected yet.')).toBeNull();
  expect((screen.getByRole('textbox') as HTMLTextAreaElement).disabled).toBe(false);
});
