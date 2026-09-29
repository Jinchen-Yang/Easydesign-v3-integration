import { describe, expect, it } from 'vitest';
import {
  createDraftRecovery, DRAFT_KEYS,
} from '../src/data/draftRecovery';
import type { ProjectDraft } from '../src/shared/account-client';

function memoryStorage(): Storage {
  const map = new Map<string, string>();
  return {
    get length() { return map.size; },
    clear: () => { map.clear(); },
    getItem: (key: string) => map.get(key) ?? null,
    key: (index: number) => [...map.keys()][index] ?? null,
    removeItem: (key: string) => { map.delete(key); },
    setItem: (key: string, value: string) => { map.set(key, value); },
  };
}

function draftFixture(overrides: Partial<ProjectDraft> = {}): ProjectDraft {
  return {
    id: 'd1',
    revision: 2,
    payload: { title: '团队设计', goal: '针对 X 的 VHH', input_id: null },
    state: 'draft',
    created_by: 'u1',
    updated_by: 'u1',
    created_at: 1_700_000_000,
    updated_at: 1_700_000_100,
    start_request_id: null,
    project_id: null,
    ...overrides,
  };
}

function jsonTransport(payload: unknown): typeof fetch {
  return (async () => new Response(JSON.stringify(payload), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })) as typeof fetch;
}

describe('createDraftRecovery 本地层', () => {
  it('saveLocal 后 recover 能读回数据和保存时间', () => {
    const drafts = createDraftRecovery({ storage: memoryStorage() });
    drafts.saveLocal(DRAFT_KEYS.projectCreate, { goal: '针对溶菌酶' });
    const recovered = drafts.recover(DRAFT_KEYS.projectCreate);
    expect(recovered.hasLocal).toBe(true);
    expect(recovered.hasRemote).toBe(false);
    expect(recovered.data).toEqual({ goal: '针对溶菌酶' });
    expect(typeof recovered.savedAt).toBe('number');
  });

  it('未知键 recover 返回空结果而不抛错', () => {
    const drafts = createDraftRecovery({ storage: memoryStorage() });
    const recovered = drafts.recover(DRAFT_KEYS.projectCreate);
    expect(recovered).toEqual({ hasLocal: false, hasRemote: false, data: null, savedAt: null });
  });

  it('clearLocal 只清除指定的草稿', () => {
    const drafts = createDraftRecovery({ storage: memoryStorage() });
    drafts.saveLocal(DRAFT_KEYS.projectCreate, { a: 1 });
    drafts.saveLocal(DRAFT_KEYS.projectGate('p1'), { note: '备注' });
    drafts.clearLocal(DRAFT_KEYS.projectCreate);
    expect(drafts.recover(DRAFT_KEYS.projectCreate).hasLocal).toBe(false);
    expect(drafts.recover(DRAFT_KEYS.projectGate('p1')).hasLocal).toBe(true);
  });

  it('clearAll 清空当前命名空间的全部草稿', () => {
    const drafts = createDraftRecovery({ storage: memoryStorage() });
    drafts.saveLocal(DRAFT_KEYS.projectCreate, { a: 1 });
    drafts.saveLocal(DRAFT_KEYS.projectFiles('p1'), { name: 'x.pdb', size: 10 });
    drafts.clearAll();
    expect(drafts.recover(DRAFT_KEYS.projectCreate).hasLocal).toBe(false);
    expect(drafts.recover(DRAFT_KEYS.projectFiles('p1')).hasLocal).toBe(false);
  });

  it('recoverAll 返回当前命名空间的全部本地草稿', () => {
    const drafts = createDraftRecovery({ storage: memoryStorage() });
    drafts.saveLocal(DRAFT_KEYS.projectCreate, { a: 1 });
    drafts.saveLocal(DRAFT_KEYS.projectGate('p1'), { note: 'n' });
    expect(drafts.recoverAll()).toEqual({
      [DRAFT_KEYS.projectCreate]: { a: 1 },
      [DRAFT_KEYS.projectGate('p1')]: { note: 'n' },
    });
  });

  it('损坏的存储条目被当作不存在处理', () => {
    const storage = memoryStorage();
    storage.setItem('easydesign:draft:guest:draft:project:create', '{not json');
    const drafts = createDraftRecovery({ storage });
    expect(drafts.recover(DRAFT_KEYS.projectCreate).hasLocal).toBe(false);
  });
});

describe('createDraftRecovery 命名空间', () => {
  it('同账号刷新恢复，刷新后换账号清除上一身份的全部 scope 草稿', () => {
    const storage = memoryStorage();
    const first = createDraftRecovery({ storage });
    first.setIdentity('u1');
    const key = DRAFT_KEYS.scoped('s1', 'project', 'p1', 'gate', 'card-revision-1');
    first.saveLocal(key, { instruction: '审阅输入' });
    const reloaded = createDraftRecovery({ storage });
    reloaded.setIdentity('u1');
    expect(reloaded.recover(key).data).toEqual({ instruction: '审阅输入' });
    const switched = createDraftRecovery({ storage });
    switched.setIdentity('u2');
    expect(switched.recover(key).hasLocal).toBe(false);
    switched.setIdentity('u1');
    expect(switched.recover(key).hasLocal).toBe(false);
  });

  it('scope/project/Gate card 逐段编码，分隔符无法拼接成另一草稿键', () => {
    const drafts = createDraftRecovery({ storage: memoryStorage() });
    const key = DRAFT_KEYS.scoped('scope:a', 'p1', 'card:1');
    drafts.saveLocal(key, 'review');
    expect(drafts.recover(DRAFT_KEYS.scoped('scope', 'a:p1', 'card:1')).hasLocal).toBe(false);
    expect(drafts.recover(DRAFT_KEYS.scoped('scope:a', 'p1', 'card:2')).hasLocal).toBe(false);
  });
  it('访客草稿与账号草稿相互隔离，访客数据在登录后仍保留在访客命名空间', () => {
    const storage = memoryStorage();
    const drafts = createDraftRecovery({ storage });
    expect(drafts.identity).toBe('guest');
    drafts.saveLocal(DRAFT_KEYS.projectCreate, { goal: '访客演示输入' });

    drafts.setIdentity('u1');
    expect(drafts.identity).toBe('u1');
    expect(drafts.recover(DRAFT_KEYS.projectCreate).hasLocal).toBe(false);
    drafts.saveLocal(DRAFT_KEYS.projectCreate, { goal: '账号输入' });

    // 回到访客命名空间：账号草稿被清除（登出语义），访客草稿原样保留。
    drafts.setIdentity(null);
    const recovered = drafts.recover(DRAFT_KEYS.projectCreate);
    expect(recovered.hasLocal).toBe(true);
    expect(recovered.data).toEqual({ goal: '访客演示输入' });
  });

  it('换账号时清除旧账号的草稿，绝不恢复给下一位用户', () => {
    const storage = memoryStorage();
    const drafts = createDraftRecovery({ storage });
    drafts.setIdentity('u1');
    drafts.saveLocal(DRAFT_KEYS.projectCreate, { goal: '用户一的机密输入' });
    drafts.saveLocal(DRAFT_KEYS.projectGate('p9'), { note: '审核备注' });

    drafts.setIdentity('u2');
    expect(drafts.recover(DRAFT_KEYS.projectCreate).hasLocal).toBe(false);

    // 即使切回 u1，旧数据也已清除。
    drafts.setIdentity('u1');
    expect(drafts.recover(DRAFT_KEYS.projectCreate).hasLocal).toBe(false);
    expect(drafts.recover(DRAFT_KEYS.projectGate('p9')).hasLocal).toBe(false);
  });
});

describe('createDraftRecovery 远程层', () => {
  it('远程保存的晚到响应不能写入后来登录的账号', async () => {
    let finish!: (value: Response) => void;
    const transport = (() => new Promise<Response>((resolve) => { finish = resolve; })) as typeof fetch;
    const drafts = createDraftRecovery({ storage: memoryStorage(), transport });
    drafts.setIdentity('u1');
    const pending = drafts.saveRemote(draftFixture());
    drafts.setIdentity('u2');
    finish(Response.json({ draft: draftFixture() }));
    await pending;
    expect(drafts.recover('draft:project:d1').hasRemote).toBe(false);
  });
  it('saveRemote 调用团队草稿接口并登记远程副本', async () => {
    const saved = draftFixture({ id: 'd1', revision: 3, payload: { title: 't', goal: 'g' } });
    const drafts = createDraftRecovery({ storage: memoryStorage(), transport: jsonTransport({ draft: saved }) });
    await expect(drafts.saveRemote(draftFixture({ id: 'd1', revision: 2 }))).resolves.toBeUndefined();
    const recovered = drafts.recover('draft:project:d1');
    expect(recovered.hasRemote).toBe(true);
    expect(recovered.data).toEqual(saved.payload);
  });

  it('远程副本优先于本地副本（后端持有权威 revision）', () => {
    const drafts = createDraftRecovery({ storage: memoryStorage() });
    drafts.saveLocal('draft:project:d1', { goal: '本地旧输入' });
    drafts.syncRemote([draftFixture({ id: 'd1', payload: { title: 't', goal: '远程新输入' } })]);
    const recovered = drafts.recover('draft:project:d1');
    expect(recovered.hasLocal).toBe(true);
    expect(recovered.hasRemote).toBe(true);
    expect(recovered.data).toEqual({ title: 't', goal: '远程新输入' });
  });

  it('syncRemote 整体替换远程清单', () => {
    const drafts = createDraftRecovery({ storage: memoryStorage() });
    drafts.syncRemote([draftFixture({ id: 'd1' })]);
    expect(drafts.recover('draft:project:d1').hasRemote).toBe(true);
    drafts.syncRemote([draftFixture({ id: 'd2' })]);
    expect(drafts.recover('draft:project:d1').hasRemote).toBe(false);
    expect(drafts.recover('draft:project:d2').hasRemote).toBe(true);
  });

  it('切换身份时远程清单同步作废', () => {
    const drafts = createDraftRecovery({ storage: memoryStorage() });
    drafts.setIdentity('u1');
    drafts.syncRemote([draftFixture({ id: 'd1' })]);
    drafts.setIdentity('u2');
    expect(drafts.recover('draft:project:d1').hasRemote).toBe(false);
  });

  it('没有 transport 时 saveRemote 明确报错而不是静默成功', async () => {
    const drafts = createDraftRecovery({ storage: memoryStorage() });
    await expect(drafts.saveRemote(draftFixture())).rejects.toThrow('saveRemote requires a scoped transport');
  });
});
