import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { emptyInput, EXAMPLE_GOAL, INPUT_TYPES } from '../../src/easy/contracts';
import { readInputFile, sequence, validateInput } from '../../src/easy/inputs';
import { EASY_STORAGE_KEY, EasyDemoAdapter } from '../../src/easy/EasyDemoAdapter';
class MemoryStorage {
  data = new Map<string, string>();
  getItem(key: string) {
    return this.data.get(key) ?? null;
  }
  setItem(key: string, value: string) {
    this.data.set(key, value);
  }
}
const example = () => ({ ...emptyInput(), text: EXAMPLE_GOAL });
beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());
describe('Easy intake', () => {
  it('covers eight modes, explicit organism, identifiers and goals', () => {
    expect(INPUT_TYPES).toHaveLength(8);
    expect(validateInput(example())).toBeNull();
    expect(validateInput({ ...emptyInput(), type: 'protein-name', text: 'LYZ' })).toContain(
      'organism',
    );
    expect(
      validateInput({
        ...emptyInput(),
        type: 'protein-name',
        text: 'LYZ',
        species: 'Gallus gallus',
      }),
    ).toBeNull();
    for (const value of ['P00698', 'A0A024RBG1', 'P12345-2'])
      expect(validateInput({ ...emptyInput(), type: 'uniprot', text: value })).toBeNull();
    expect(validateInput({ ...emptyInput(), type: 'uniprot', text: 'lysozyme' })).toContain(
      'valid',
    );
    expect(validateInput({ ...emptyInput(), type: 'pdb-id', text: '1MEL' })).toBeNull();
    expect(
      validateInput({ ...emptyInput(), type: 'pdb-id', text: '1MEL; command' }),
    ).not.toBeNull();
    expect(validateInput({ ...emptyInput(), type: 'pdb-id', text: '1MEL', goal: '' })).toContain(
      'goal',
    );
  });
  it('normalizes one canonical sequence and rejects multiple or ambiguous FASTA records', () => {
    expect(sequence('>target\n acde\nFGHIK')).toBe('ACDEFGHIK');
    for (const text of ['', '>a\nACDE\n>b\nACDE', '>target\nACDX', 'ACD*'])
      expect(() => sequence(text)).toThrow();
  });
  it('checks structure/FASTA/bundle contents but never executes PSE', async () => {
    const file = (name: string, text: string) => new File([text], name);
    expect((await readInputFile('sequence', file('a.fasta', '>target\nACDEFGHIK'))).text).toBe(
      'ACDEFGHIK',
    );
    expect(
      (await readInputFile('structure', file('a.pdb', 'ATOM      1  CA  GLY A   1'))).file?.name,
    ).toBe('a.pdb');
    expect(
      (await readInputFile('structure', file('a.cif', 'data_x\n_atom_site.Cartn_x 0'))).text,
    ).toBe('');
    await expect(readInputFile('structure', file('a.pdb', 'not coordinates'))).rejects.toThrow(
      'coordinate',
    );
    await expect(readInputFile('structure', file('a.exe', 'ATOM  '))).rejects.toThrow('type');
    await expect(readInputFile('bundle', file('a.json', '{}'))).rejects.toThrow('target_id');
    expect((await readInputFile('bundle', file('a.json', '{"target_id":"lysozyme"}'))).text).toBe(
      '',
    );
    expect((await readInputFile('pse', file('a.pse', 'opaque binary'))).text).toBe('');
    await expect(readInputFile('pse', file('a.pse', ''))).rejects.toThrow('non-empty');
  });
});
describe('isolated Easy demo lifecycle', () => {
  it('completes 8 / 24 / 6 automatically without network calls or Pro data writes', async () => {
    const fetch = vi.spyOn(globalThis, 'fetch');
    const storage = new MemoryStorage();
    storage.setItem('easydesign-workbench-projects-v1', 'original-pro-data');
    const adapter = new EasyDemoAdapter(storage, 20);
    const id = adapter.start(example());
    expect(() => adapter.start(example())).toThrow('Pause');
    await vi.advanceTimersByTimeAsync(150);
    const state = adapter.load();
    expect(state.runs[0].status).toBe('complete');
    expect(state.candidates).toHaveLength(6);
    const result = JSON.parse(adapter.exportResult(id));
    expect(result.pilot).toBe(8);
    expect(result.scale).toBe(24);
    expect(result.finalists).toHaveLength(6);
    expect(result.mode).toBe('demo');
    expect(storage.getItem('easydesign-workbench-projects-v1')).toBe('original-pro-data');
    expect(fetch).not.toHaveBeenCalled();
    fetch.mockRestore();
    adapter.dispose();
  });
  it('persists pause, draft edits, restart and independent runs', async () => {
    const storage = new MemoryStorage();
    const adapter = new EasyDemoAdapter(storage, 20);
    const id = adapter.start(example());
    await vi.advanceTimersByTimeAsync(25);
    adapter.pause(id);
    const step = adapter.load().runs[0].step;
    await vi.advanceTimersByTimeAsync(300);
    expect(adapter.load().runs[0].step).toBe(step);
    adapter.dispose();
    const restored = new EasyDemoAdapter(storage, 20);
    expect(restored.load().runs[0].status).toBe('paused');
    const draft = restored.saveDraft({
      ...emptyInput(),
      type: 'pdb-id',
      text: '1MEL',
      name: 'Other input',
    });
    restored.saveDraft(
      { ...emptyInput(), type: 'pdb-id', text: '1UBQ', name: 'Updated draft' },
      draft,
    );
    expect(restored.load().runs).toHaveLength(2);
    restored.resume(id);
    await vi.advanceTimersByTimeAsync(150);
    expect(restored.load().runs.find((r) => r.id === id)?.input.text).toBe(EXAMPLE_GOAL);
    expect(restored.load().runs.find((r) => r.id === draft)?.input.text).toBe('1UBQ');
    restored.dispose();
  });
  it('resumes a running preview after reload, preserves corrupt saved bytes, handles quota', async () => {
    const storage = new MemoryStorage();
    const a = new EasyDemoAdapter(storage, 20);
    a.start(example());
    await vi.advanceTimersByTimeAsync(30);
    a.dispose();
    const b = new EasyDemoAdapter(storage, 20);
    b.load();
    await vi.advanceTimersByTimeAsync(150);
    expect(b.load().runs[0].status).toBe('complete');
    b.dispose();
    storage.setItem(EASY_STORAGE_KEY, 'broken');
    const c = new EasyDemoAdapter(storage, 20);
    expect(c.load().notice).toContain('left untouched');
    c.start(example());
    expect(storage.getItem(EASY_STORAGE_KEY)).toBe('broken');
    c.dispose();
    const broken = {
      getItem: () => null,
      setItem: () => {
        throw new Error('quota');
      },
    };
    const d = new EasyDemoAdapter(broken, 20);
    d.start(example());
    expect(d.load().notice).toContain('memory');
    d.dispose();
  });
});
