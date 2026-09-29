import fixture from '../../demo/demo-fixture.json';
import reference from '../../demo/structure-reference.json';
import {
  type EasyAdapter,
  type EasyInput,
  type EasyRun,
  type EasySnapshot,
  STEPS,
} from './contracts';
import { inputLabel, isInput, validateInput } from './inputs';
export const EASY_STORAGE_KEY = 'easydesign-easy-preview-v1';
type Persistence = Pick<Storage, 'getItem' | 'setItem'>;

/** Finite demo animation only. No model, scientific API, queue, Gate approval or GPU calls. */
export class EasyDemoAdapter implements EasyAdapter {
  private runs: EasyRun[] = [];
  private selectedId: string | null = null;
  private notice: string | null = null;
  private loaded = false;
  private listeners = new Set<(snapshot: EasySnapshot) => void>();
  private timer?: ReturnType<typeof setTimeout>;
  constructor(
    private storage?: Persistence,
    private stepMs = 1900,
  ) {
    if (!storage)
      this.notice =
        'Browser storage is unavailable. This preview is kept in memory for this tab only.';
  }
  load() {
    if (!this.loaded) {
      this.loaded = true;
      try {
        const raw = this.storage?.getItem(EASY_STORAGE_KEY);
        if (raw) {
          const data = JSON.parse(raw);
          if (data.version !== 1 || !Array.isArray(data.runs) || data.runs.length > 1000)
            throw new Error('Invalid data');
          const ids = new Set<string>();
          for (const run of data.runs) {
            if (
              !run ||
              typeof run.id !== 'string' ||
              ids.has(run.id) ||
              !isInput(run.input) ||
              typeof run.name !== 'string' ||
              run.name.length > 100 ||
              !Number.isFinite(Date.parse(run.createdAt)) ||
              !Number.isFinite(Date.parse(run.updatedAt)) ||
              !['draft', 'running', 'paused', 'complete'].includes(run.status) ||
              !Number.isInteger(run.step) ||
              run.step < 0 ||
              run.step >= STEPS.length ||
              (run.status === 'complete' && run.step !== STEPS.length - 1)
            )
              throw new Error('Invalid run');
            ids.add(run.id);
          }
          this.runs = data.runs;
          if (this.runs.filter((r) => r.status === 'running').length > 1)
            throw new Error('Multiple active demos');
          this.selectedId = ids.has(data.selectedId) ? data.selectedId : null;
        }
      } catch {
        this.runs = [];
        this.selectedId = null;
        this.notice =
          'Saved designs could not be read. This preview is running in memory; the old data has been left untouched.';
        this.storage = undefined;
      }
    }
    this.schedule();
    return this.snapshot();
  }
  private snapshot(): EasySnapshot {
    return {
      mode: 'demo',
      runs: structuredClone(this.runs),
      selectedId: this.selectedId,
      notice: this.notice,
      reference,
      review: {
        sites: fixture.site_options,
        selectedSite: fixture.site_options.find(
          (site) => 'recommended' in site && site.recommended,
        )!.id,
        design: {
          binderType: fixture.design.binder_type,
          scaffold: fixture.design.scaffold,
          arms: fixture.design.arms.map((arm) => ({
            id: arm.id,
            label: arm.label,
            count: arm.pilot_candidates,
          })),
        },
        pilot: {
          total: fixture.pilot.total,
          passed: fixture.pilot.passed,
          filtered: fixture.pilot.failed,
          candidates: fixture.pilot.candidates.map((item) => ({
            ...item,
            status: item.status === 'pass' ? ('pass' as const) : ('filtered' as const),
          })),
        },
        scale: {
          total: fixture.scale.total,
          passed: fixture.scale.passed,
          filtered: fixture.scale.filtered,
          batches: fixture.scale.batches,
          batchSize: fixture.scale.batch_size,
        },
      },
      candidates: fixture.finalists.map(({ sequence_preview, ...candidate }) => ({
        ...candidate,
        status: 'pass' as const,
        sequencePreview: sequence_preview,
        length: 132,
      })),
    };
  }
  subscribe(listener: (state: EasySnapshot) => void) {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  }
  private publish() {
    try {
      this.storage?.setItem(
        EASY_STORAGE_KEY,
        JSON.stringify({ version: 1, runs: this.runs, selectedId: this.selectedId }),
      );
    } catch {
      this.notice =
        'Browser storage is full or unavailable. Keep this tab open; new changes are only in memory.';
    }
    for (const listener of this.listeners) listener(this.snapshot());
  }
  private schedule() {
    if (this.timer || !this.runs.some((run) => run.status === 'running')) return;
    this.timer = setTimeout(() => {
      this.timer = undefined;
      const run = this.runs.find((item) => item.status === 'running');
      if (run) {
        if (run.step === STEPS.length - 1) run.status = 'complete';
        else run.step++;
        run.updatedAt = new Date().toISOString();
        this.publish();
      }
      this.schedule();
    }, this.stepMs);
  }
  private find(id: string) {
    const run = this.runs.find((r) => r.id === id);
    if (!run) throw new Error('This design is unavailable.');
    return run;
  }
  saveDraft(input: EasyInput, existingId?: string) {
    this.load();
    if (!isInput(input)) throw new Error('Invalid input.');
    const old = existingId ? this.find(existingId) : undefined;
    if (old && old.status !== 'draft') throw new Error('Running designs cannot be overwritten.');
    const name =
      input.name.trim() ||
      (input.type === 'description' && /lysozyme/i.test(input.text)
        ? 'Lysozyme · VHH'
        : inputLabel(input).slice(0, 55)) ||
      'Untitled design';
    const now = new Date().toISOString();
    const run: EasyRun = {
      id: old?.id ?? crypto.randomUUID(),
      name,
      input: structuredClone(input),
      createdAt: old?.createdAt ?? now,
      updatedAt: now,
      status: 'draft',
      step: 0,
    };
    if (old) this.runs[this.runs.indexOf(old)] = run;
    else this.runs.unshift(run);
    this.selectedId = run.id;
    this.publish();
    return run.id;
  }
  start(input: EasyInput, draftId?: string) {
    this.load();
    const issue = validateInput(input);
    if (issue) throw new Error(issue);
    if (this.runs.some((run) => run.status === 'running'))
      throw new Error('Pause the current preview before starting another.');
    const id = this.saveDraft(input, draftId);
    this.find(id).status = 'running';
    this.publish();
    this.schedule();
    return id;
  }
  select(id: string | null) {
    if (id) this.find(id);
    this.selectedId = id;
    this.publish();
  }
  pause(id: string) {
    const run = this.find(id);
    if (run.status !== 'running') return;
    clearTimeout(this.timer);
    this.timer = undefined;
    run.status = 'paused';
    run.updatedAt = new Date().toISOString();
    this.publish();
  }
  resume(id: string) {
    if (this.runs.some((run) => run.status === 'running'))
      throw new Error('Another preview is already running.');
    const run = this.find(id);
    if (run.status !== 'paused') throw new Error('This design is not paused.');
    run.status = 'running';
    run.updatedAt = new Date().toISOString();
    this.selectedId = id;
    this.publish();
    this.schedule();
  }
  exportResult(id: string) {
    const run = this.find(id);
    if (run.status !== 'complete') throw new Error('Wait for the preview to finish.');
    return JSON.stringify(
      {
        schema: 'easydesign-easy-demo-v1',
        mode: 'demo',
        input: run.input,
        name: run.name,
        note: 'Simulated lysozyme/VHH results, independent of the supplied input. No scientific computation. Sequence previews are not synthesis-ready. Uploaded file bytes are not included.',
        pilot: 8,
        scale: 24,
        finalists: fixture.finalists,
        structure: {
          pdbId: reference.pdbId,
          role: 'shared reference, not a generated candidate structure',
        },
      },
      null,
      2,
    );
  }
  dispose() {
    clearTimeout(this.timer);
    this.timer = undefined;
    this.listeners.clear();
  }
}
