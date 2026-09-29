import {cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {afterEach, beforeEach, expect, it, vi} from 'vitest';
import {AppShell} from '../src/shell/AppShell';
import {LANGUAGE_KEY} from '../src/shell/I18nProvider';

beforeEach(() => {
  localStorage.clear();
  window.history.replaceState({}, '', '/app/#/account');
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

it.each(['zh', 'en'])('blocks mismatched registration and exposes credential semantics (%s)', async locale => {
  localStorage.setItem(LANGUAGE_KEY, locale);
  const registrations: unknown[] = [];
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url.endsWith('/accounts/config')) return Response.json({setup_required: false, registration: 'open'});
    if (url.endsWith('/accounts/register')) {
      registrations.push(JSON.parse(String(init?.body)));
      return Response.json({status: 'registered'}, {status: 201});
    }
    return Response.json({error: {code: 'unauthorized'}}, {status: 401});
  }));
  const text = locale === 'zh' ? {
    username: '用户名', password: '密码', confirm: '确认密码',
    register: '没有账号？立即注册', create: '创建账号',
    mismatch: '两次密码不一致，请输入相同的密码。',
    loginHeading: '登录 EasyDesign',
  } : {
    username: 'Username', password: 'Password', confirm: 'Confirm password',
    register: 'No account? Create one', create: 'Create account',
    mismatch: 'Passwords do not match. Please enter the same password twice.',
    loginHeading: 'Sign in to EasyDesign',
  };
  render(<AppShell/>);
  await screen.findByRole('heading', {name: text.loginHeading});
  expect(screen.getByLabelText(text.username).getAttribute('autocomplete')).toBe('username');
  expect(screen.getByLabelText(text.username).getAttribute('name')).toBe('username');
  expect(screen.getByLabelText(text.password).getAttribute('autocomplete')).toBe('current-password');
  fireEvent.click(screen.getByRole('button', {name: text.register}));
  const password = screen.getByLabelText(text.password) as HTMLInputElement;
  const confirmation = screen.getByLabelText(text.confirm) as HTMLInputElement;
  expect(password.autocomplete).toBe('new-password');
  expect(confirmation.autocomplete).toBe('new-password');
  expect(confirmation.required).toBe(true);
  fireEvent.change(screen.getByLabelText(text.username), {target: {value: 'registration-check'}});
  fireEvent.change(password, {target: {value: 'a-valid-password-123'}});
  expect((screen.getByRole('button', {name: text.create}) as HTMLButtonElement).disabled).toBe(true);
  fireEvent.change(confirmation, {target: {value: 'a-different-password'}});
  expect(screen.getByRole('alert').textContent).toBe(text.mismatch);
  expect((screen.getByRole('button', {name: text.create}) as HTMLButtonElement).disabled).toBe(true);
  // Even bypassing the disabled button must not issue a registration request.
  fireEvent.submit(password.form!);
  expect(registrations).toEqual([]);
  expect(document.activeElement).toBe(confirmation);
  fireEvent.change(confirmation, {target: {value: 'a-valid-password-123'}});
  expect(screen.queryByRole('alert')).toBeNull();
  expect((screen.getByRole('button', {name: text.create}) as HTMLButtonElement).disabled).toBe(false);
  // Editing the original after matching must also invalidate confirmation.
  fireEvent.change(password, {target: {value: 'a-valid-password-124'}});
  fireEvent.submit(password.form!);
  expect(registrations).toEqual([]);
  fireEvent.change(confirmation, {target: {value: 'a-valid-password-124'}});
  fireEvent.submit(password.form!);
  await waitFor(() => expect(registrations).toEqual([{
    username: 'registration-check', password: 'a-valid-password-124', display_name: 'registration-check',
  }]));
  await screen.findByRole('heading', {name: text.loginHeading});
  expect((screen.getByLabelText(text.password) as HTMLInputElement).value).toBe('');
  fireEvent.click(screen.getByRole('button', {name: text.register}));
  expect((screen.getByLabelText(text.confirm) as HTMLInputElement).value).toBe('');
});
