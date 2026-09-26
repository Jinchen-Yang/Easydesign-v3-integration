import { useEffect, useRef, useState } from 'react';
import {
  ArrowRight,
  ArrowUpRight,
  Atom,
  Check,
  ChevronDown,
  CircleHelp,
  Download,
  FileCheck2,
  FileUp,
  FlaskConical,
  History,
  LoaderCircle,
  Pause,
  Play,
  Plus,
  Save,
  Search,
  SlidersHorizontal,
  Sparkles,
  X,
} from 'lucide-react';
import { loadLocale, saveLocale, translate, type Locale } from './i18n';
import { EasyStageDetails } from './EasyStageDetails';
import { RabbitMascot } from './RabbitMascot';
import { Brand } from '../components/Brand';
import { MolecularViewer } from '../features/viewer/MolecularViewer';
import {
  emptyInput,
  EXAMPLE_GOAL,
  INPUT_TYPES,
  STEPS,
  type EasyAdapter,
  type EasyInput,
  type EasyRun,
  type InputType,
} from './contracts';
import { fileTypes, inputLabel, readInputFile, validateInput } from './inputs';

function download(content: string, name: string) {
  const url = URL.createObjectURL(new Blob([content], { type: 'application/json' }));
  const link = document.createElement('a');
  link.href = url;
  link.download = name;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function date(value: string, locale: Locale) {
  return new Date(value).toLocaleDateString(locale === 'zh' ? 'zh-CN' : 'en-GB', {
    day: 'numeric',
    month: 'short',
  });
}

export function EasyApp({ adapter }: { adapter: EasyAdapter }) {
  const [locale, setLocale] = useState<Locale>(loadLocale);
  const t = (key: string, values?: Record<string, string | number>) =>
    translate(locale, key, values);
  const freshInput = () => ({ ...emptyInput(), goal: t('Design a VHH binder for this target.') });
  useEffect(() => {
    document.documentElement.lang = locale === 'zh' ? 'zh-CN' : 'en';
    document.title = `EasyDesign Easy · ${t('Start a design')}`;
  }, [locale]);
  function changeLanguage(value: Locale) {
    setLocale(value);
    saveLocale(value);
  }

  const [state, setState] = useState(() => adapter.load());
  const [input, setInput] = useState<EasyInput>(
    () =>
      state.runs.find((run) => run.id === state.selectedId && run.status === 'draft')?.input ??
      freshInput(),
  );
  const [draftId, setDraftId] = useState<string | undefined>(
    () => state.runs.find((run) => run.id === state.selectedId && run.status === 'draft')?.id,
  );
  const [advanced, setAdvanced] = useState(false);
  const [error, setError] = useState('');
  const [toast, setToast] = useState('');
  const [uploading, setUploading] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState('all');
  const [candidate, setCandidate] = useState('ED-001');
  const [stageView, setStageView] = useState<{ runId: string; index: number } | null>(null);
  const [help, setHelp] = useState(false);
  const uploadGeneration = useRef(0);
  const fileInput = useRef<HTMLInputElement>(null);
  const helpRef = useRef<HTMLDialogElement>(null);
  const formRef = useRef<HTMLElement>(null);
  const runRef = useRef<HTMLElement>(null);
  const historyRef = useRef<HTMLElement>(null);
  useEffect(() => {
    const unsubscribe = adapter.subscribe(setState);
    setState(adapter.load());
    return () => {
      unsubscribe();
      adapter.dispose();
    };
  }, [adapter]);
  useEffect(() => {
    if (!toast) return;
    const id = setTimeout(() => setToast(''), 3500);
    return () => clearTimeout(id);
  }, [toast]);
  useEffect(() => {
    if (help) helpRef.current?.showModal();
    else helpRef.current?.close();
  }, [help]);
  const selected = state.runs.find((run) => run.id === state.selectedId);
  const active = state.runs.find((run) => run.status === 'running');
  const run = selected?.status !== 'draft' ? selected : undefined;
  const complete = run?.status === 'complete';
  // Browsing a finished stage is local view state, never a run transition.
  const reviewing = !!run && stageView?.runId === run.id && stageView.index < run.step;
  const viewStep = reviewing ? stageView.index : (run?.step ?? 0);
  const showFinalists = complete && viewStep === STEPS.length - 1;
  const showStageDetails = (complete || reviewing) && viewStep < STEPS.length - 1;
  const issue = validateInput(input);
  const type = INPUT_TYPES.find((item) => item.id === input.type)!;
  const fileOnly = ['structure', 'pse', 'bundle'].includes(input.type);
  const filtered = state.runs.filter(
    (item) =>
      (filter === 'all' || item.status === filter) &&
      `${item.name} ${inputLabel(item.input)}`.toLowerCase().includes(query.toLowerCase()),
  );
  function scroll(element: HTMLElement | null) {
    element?.scrollIntoView({
      behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth',
      block: 'start',
    });
  }
  function update(patch: Partial<EasyInput>) {
    setInput((value) => ({ ...value, ...patch }));
    setError('');
  }
  function chooseType(value: InputType) {
    uploadGeneration.current++;
    setUploading(false);
    setDragging(false);
    update({ type: value, text: '', file: null });
    if (fileInput.current) fileInput.current.value = '';
  }
  async function upload(file?: File) {
    if (!file) return;
    const generation = ++uploadGeneration.current;
    setUploading(true);
    setError('');
    try {
      const value = await readInputFile(input.type, file);
      if (generation === uploadGeneration.current) update(value);
    } catch (e) {
      if (generation === uploadGeneration.current) {
        update({ file: null, text: '' });
        setError((e as Error).message);
      }
    } finally {
      if (generation === uploadGeneration.current) setUploading(false);
    }
  }
  function example() {
    setStageView(null);
    uploadGeneration.current++;
    setUploading(false);
    setDraftId(undefined);
    adapter.select(null);
    setInput({ ...freshInput(), text: t(EXAMPLE_GOAL), name: t('Lysozyme · VHH') });
    setError('');
    formRef.current?.querySelector<HTMLTextAreaElement>('textarea')?.focus();
  }
  function newDesign() {
    setStageView(null);
    uploadGeneration.current++;
    setUploading(false);
    setInput(freshInput());
    setDraftId(undefined);
    setError('');
    adapter.select(null);
    scroll(formRef.current);
  }
  function start() {
    if (issue) {
      setError(issue);
      return;
    }
    try {
      adapter.start(input, draftId);
      setStageView(null);
      setDraftId(undefined);
      setCandidate('ED-001');
      setError('');
      setTimeout(() => scroll(runRef.current), 50);
    } catch (e) {
      setError((e as Error).message);
    }
  }
  function open(item: EasyRun) {
    setStageView(null);
    adapter.select(item.id);
    setCandidate('ED-001');
    if (item.status === 'draft') {
      setInput(item.input);
      setDraftId(item.id);
      setError('');
      scroll(formRef.current);
    } else setTimeout(() => scroll(runRef.current), 50);
  }
  function action(fn: () => void) {
    try {
      fn();
    } catch (e) {
      setToast((e as Error).message);
    }
  }
  return (
    <div className="easy-app" lang={locale === 'zh' ? 'zh-CN' : 'en'}>
      <a className="easy-skip" href="#design">
        {t('Skip to design input')}
      </a>
      <header className="easy-header">
        <a className="easy-brand" href="#design" onClick={() => scroll(formRef.current)}>
          <Brand />
          <span className="easy-edition">EASY</span>
        </a>
        <nav aria-label={t('Main navigation')}>
          <a className="easy-nav-current" href="#design" onClick={() => scroll(formRef.current)}>
            {t('Design')}
          </a>
          <a href="#my-designs" onClick={() => scroll(historyRef.current)}>
            {t('My designs')}
          </a>
        </nav>
        <div className="easy-header-end">
          <div className="easy-language" role="group" aria-label={t('Language')}>
            <button
              type="button"
              lang="zh-CN"
              aria-label="中文"
              aria-pressed={locale === 'zh'}
              onClick={() => changeLanguage('zh')}
            >
              中文
            </button>
            <button
              type="button"
              lang="en"
              aria-label={t('English')}
              aria-pressed={locale === 'en'}
              onClick={() => changeLanguage('en')}
            >
              EN
            </button>
          </div>
          <button className="easy-help" aria-label={t('Quick guide')} onClick={() => setHelp(true)}>
            <CircleHelp size={16} />
            <span>{t('Quick guide')}</span>
          </button>
          <a
            className="easy-pro-link"
            href="http://127.0.0.1:13180/#projects"
            target="_blank"
            rel="noreferrer"
          >
            {t('Open Pro')} <ArrowUpRight size={14} />
          </a>
        </div>
      </header>
      <main className="easy-main">
        <section className="easy-intro">
          <h1>
            {locale === 'zh' ? (
              <>
                开始<span>设计</span>
              </>
            ) : (
              <>
                Start a <span>design</span>
              </>
            )}
          </h1>
        </section>
        {state.notice && (
          <p className="easy-notice" role="alert">
            {t(state.notice)}
          </p>
        )}
        <section className="easy-input-card" id="design" ref={formRef} aria-label={t('New design')}>
          <div className="easy-section-top">
            <span className="easy-demo-pill">
              <FlaskConical size={12} /> {t('Demo')}
            </span>
          </div>
          <form
            onSubmit={(event) => {
              event.preventDefault();
              start();
            }}
          >
            <div className="easy-input-row">
              <label className="easy-type-label">
                <span>{t('Input type')}</span>
                <div className="easy-select-wrap">
                  <select
                    aria-label={t('Input type')}
                    value={input.type}
                    onChange={(event) => chooseType(event.target.value as InputType)}
                  >
                    {INPUT_TYPES.map((item) => (
                      <option key={item.id} value={item.id}>
                        {t(item.label)}
                      </option>
                    ))}
                  </select>
                  <ChevronDown size={14} />
                </div>
              </label>
              <div className="easy-input-body">
                {fileOnly ? (
                  <div
                    className={`easy-dropzone ${dragging ? 'is-dragging' : ''}`}
                    onDragOver={(e) => {
                      e.preventDefault();
                      setDragging(true);
                    }}
                    onDragLeave={() => setDragging(false)}
                    onDrop={(e) => {
                      e.preventDefault();
                      setDragging(false);
                      if (e.dataTransfer.files.length > 1)
                        setError('Choose one input file per design.');
                      else void upload(e.dataTransfer.files[0]);
                    }}
                  >
                    <button
                      type="button"
                      onClick={() => fileInput.current?.click()}
                      disabled={uploading}
                    >
                      {input.file ? <FileCheck2 size={23} /> : <FileUp size={23} />}
                      <span>
                        <strong>
                          {uploading
                            ? t('Reading file…')
                            : input.file
                              ? input.file.name
                              : t('Upload or drop a file')}
                        </strong>
                        <small>
                          {input.file
                            ? `${(input.file.size / 1024).toFixed(1)} KB · ${t('Click to replace')}`
                            : t(type.hint)}
                        </small>
                      </span>
                      {input.file && <Check size={16} />}
                    </button>
                  </div>
                ) : (
                  <>
                    <label className="sr-only" htmlFor="easy-target-input">
                      {t(type.label)}
                    </label>
                    {input.type === 'description' || input.type === 'sequence' ? (
                      <textarea
                        id="easy-target-input"
                        className={input.type === 'sequence' ? 'easy-sequence' : ''}
                        maxLength={input.type === 'sequence' ? 22000 : 4000}
                        rows={3}
                        value={input.text}
                        placeholder={
                          input.type === 'description'
                            ? t('e.g. Design a VHH binder against hen egg-white lysozyme…')
                            : t('>my_target\nPaste a protein sequence or FASTA here…')
                        }
                        onChange={(e) => update({ text: e.target.value, file: null })}
                      />
                    ) : (
                      <input
                        id="easy-target-input"
                        maxLength={160}
                        value={input.text}
                        placeholder={
                          input.type === 'pdb-id'
                            ? t('e.g. 1MEL')
                            : input.type === 'uniprot'
                              ? t('e.g. P00698')
                              : t('e.g. Lysozyme or LYZ')
                        }
                        onChange={(e) => update({ text: e.target.value })}
                      />
                    )}
                    {input.type === 'protein-name' && (
                      <label className="easy-species">
                        {t('Organism')}
                        <input
                          placeholder={t('e.g. Gallus gallus')}
                          value={input.species}
                          maxLength={100}
                          onChange={(e) => update({ species: e.target.value })}
                        />
                      </label>
                    )}
                  </>
                )}
                {fileTypes[input.type] && (
                  <input
                    ref={fileInput}
                    type="file"
                    className="sr-only"
                    aria-label={t('Upload {type}', { type: t(type.label) })}
                    accept={fileTypes[input.type]}
                    onChange={(e) => {
                      void upload(e.target.files?.[0]);
                      e.target.value = '';
                    }}
                  />
                )}
                {input.type === 'sequence' && (
                  <div className="easy-input-hint">
                    <button
                      type="button"
                      className="easy-text-button"
                      onClick={() => fileInput.current?.click()}
                    >
                      <FileUp size={13} /> {t('Upload FASTA')}
                    </button>
                  </div>
                )}
              </div>
              <button
                type="submit"
                className="easy-primary easy-start"
                disabled={!!active || uploading || !!issue}
                title={
                  active
                    ? t('Pause the current preview before starting another.')
                    : issue
                      ? t(issue)
                      : undefined
                }
              >
                {t('Start design')} <ArrowRight size={17} />
              </button>
            </div>
            {input.type === 'pse' || input.type === 'bundle' ? (
              <p className="easy-format-note">
                {t('File selection only · Backend validation pending.')}
              </p>
            ) : null}
            {error && (
              <p className="easy-error" role="alert">
                {t(error)}
              </p>
            )}
            {input.text && issue && !error && (
              <p className="easy-validation" role="status">
                {t(issue)}
              </p>
            )}
            <div className="easy-input-actions">
              <div>
                <button className="easy-example" type="button" onClick={example}>
                  <Sparkles size={13} /> {t('Try lysozyme · VHH')} <ArrowUpRight size={12} />
                </button>
                <button
                  className={`easy-options-toggle ${advanced ? 'is-open' : ''}`}
                  type="button"
                  aria-expanded={advanced}
                  aria-controls="easy-options"
                  onClick={() => setAdvanced(!advanced)}
                >
                  <SlidersHorizontal size={14} /> {t('Options')} <ChevronDown size={12} />
                </button>
              </div>
              <button
                className="easy-text-button"
                type="button"
                disabled={uploading || (!input.text.trim() && !input.file)}
                onClick={() =>
                  action(() => {
                    const id = adapter.saveDraft(input, draftId);
                    setDraftId(id);
                    setToast(
                      adapter.load().notice
                        ? 'Draft kept in this tab.'
                        : 'Draft saved on this device.',
                    );
                  })
                }
              >
                <Save size={14} /> {t('Save draft')}
              </button>
            </div>
            {advanced && (
              <div className="easy-options" id="easy-options">
                <label>
                  {t('Design name')}
                  <input
                    placeholder={t('Name your design (optional)')}
                    maxLength={80}
                    value={input.name}
                    onChange={(e) => update({ name: e.target.value })}
                  />
                </label>
                <label>
                  {t('Design goal')}
                  <input
                    maxLength={2000}
                    value={input.goal}
                    onChange={(e) => update({ goal: e.target.value })}
                  />
                </label>
                <p>{t('Demo: VHH · Pilot 8 → Scale 24 → Finalists 6.')}</p>
              </div>
            )}
          </form>
          <div className="easy-demo-note">
            <span /> {t('Fixed lysozyme demo · No compute jobs')}
          </div>
        </section>
        {active && selected?.id !== active.id && (
          <button className="easy-active-notice" onClick={() => open(active)}>
            <LoaderCircle className="easy-spin" size={15} />
            {t('{name} is running', { name: active.name })} <ArrowRight size={15} />
          </button>
        )}
        {run && (
          <section
            className="easy-run"
            ref={runRef}
            aria-label={t('Design progress')}
            id="current-design"
          >
            <div className="easy-run-heading">
              <div>
                <span className="easy-kicker">{run.name}</span>
                <h2>
                  {reviewing
                    ? t(STEPS[viewStep])
                    : complete
                      ? t('6 finalists')
                      : run.status === 'paused'
                        ? t('Paused')
                        : t(STEPS[viewStep])}
                </h2>
              </div>
              <div className="easy-run-actions">
                <span className={`easy-status ${run.status}`}>
                  {complete ? (
                    <Check size={12} />
                  ) : run.status === 'paused' ? (
                    <Pause size={12} />
                  ) : (
                    <LoaderCircle size={12} className="easy-spin" />
                  )}
                  {complete
                    ? t('Completed')
                    : run.status === 'paused'
                      ? t('Paused')
                      : t('In progress')}
                </span>
                {run.status === 'running' && (
                  <button
                    aria-label={t('Pause preview')}
                    className="easy-icon-button"
                    onClick={() => adapter.pause(run.id)}
                  >
                    <Pause size={16} />
                  </button>
                )}
                {run.status === 'paused' && (
                  <button
                    className="easy-outline"
                    onClick={() => action(() => adapter.resume(run.id))}
                  >
                    <Play size={14} /> {t('Resume')}
                  </button>
                )}
              </div>
            </div>
            <div className="easy-steps" aria-label={t('Workflow progress')}>
              {STEPS.map((step, index) => (
                <button
                  type="button"
                  key={step}
                  aria-label={t(step)}
                  disabled={!complete && index > run.step}
                  aria-pressed={viewStep === index}
                  aria-controls="easy-stage-content"
                  className={`${complete || index < run.step ? 'done' : ''} ${!complete && index === run.step ? 'current' : ''}`}
                  aria-current={!complete && index === run.step ? 'step' : undefined}
                  onClick={() => setStageView(index < run.step ? { runId: run.id, index } : null)}
                >
                  <span>{complete || index < run.step ? <Check size={12} /> : index + 1}</span>
                  <b>{t(step)}</b>
                </button>
              ))}
            </div>
            <div
              className="easy-progress-track"
              role="progressbar"
              aria-label={t('Demo stage progress')}
              aria-valuemin={0}
              aria-valuemax={6}
              aria-valuenow={complete ? 6 : run.step}
              aria-valuetext={
                complete
                  ? t('All six demo stages complete')
                  : t('Step {number} of 6: {stage}', {
                      number: run.step + 1,
                      stage: t(STEPS[run.step]),
                    })
              }
            >
              <i style={{ width: `${((complete ? 6 : run.step) / 6) * 100}%` }} />
            </div>
            <div
              id="easy-stage-content"
              className={`easy-run-body ${showFinalists || showStageDetails ? '' : 'is-preview'}`}
              role="region"
              aria-label={t('{stage} details', { stage: t(STEPS[viewStep]) })}
            >
              {showStageDetails && (
                <EasyStageDetails step={viewStep} state={state} locale={locale} />
              )}
              {showFinalists && (
                <div className="easy-results-panel">
                  <div className="easy-result-section-title">
                    <h3>{t('Candidates')}</h3>
                    <span>{t('SIMULATED')}</span>
                  </div>
                  <div className="easy-candidate-head">
                    <span>{t('Candidate')}</span>
                    <span>{t('Interface / confidence')}</span>
                  </div>
                  <div className="easy-candidates" role="group" aria-label={t('Example finalists')}>
                    {state.candidates.map((item) => (
                      <button
                        key={item.id}
                        className={candidate === item.id ? 'selected' : ''}
                        aria-pressed={candidate === item.id}
                        onClick={() => setCandidate(item.id)}
                      >
                        <span className="easy-rank">{item.rank}</span>
                        <strong>{item.id}</strong>
                        <span>
                          {item.interface.toFixed(2)} <small>/ {item.confidence.toFixed(2)}</small>
                        </span>
                        <ArrowUpRight size={13} />
                      </button>
                    ))}
                  </div>
                  <p className="easy-result-note">
                    {t('Example scores · Shared reference structure')}
                  </p>
                  <button
                    className="easy-primary easy-download"
                    onClick={() =>
                      action(() =>
                        download(
                          adapter.exportResult(run.id),
                          `${run.name.replace(/[^a-z0-9_-]+/gi, '-')}-demo-results.json`,
                        ),
                      )
                    }
                  >
                    <Download size={15} /> {t('Download results')}
                  </button>
                </div>
              )}
              <div className="easy-structure-panel">
                <div className="easy-structure-heading">
                  <span>
                    <Atom size={14} /> {t('Structure')}
                  </span>
                  <small>{t('Lysozyme · VHH')}</small>
                </div>
                <MolecularViewer
                  translate={t}
                  reference={state.reference}
                  mode={viewStep >= 3 ? 'complex' : 'target'}
                  sites={viewStep === 1 || viewStep === 2 ? state.review.sites : undefined}
                  selectedSite={
                    viewStep === 1 || viewStep === 2 ? state.review.selectedSite : undefined
                  }
                  candidateId={showFinalists ? candidate : undefined}
                />
                <div className="easy-structure-legend">
                  <span>
                    <i /> {t('Lysozyme')}
                  </span>
                  <span>
                    <i /> VHH
                  </span>
                  <small>{t('1MEL · Reference only')}</small>
                </div>
              </div>
            </div>
            <details className="easy-input-details">
              <summary>
                {t('Input details')} <ChevronDown size={13} />
              </summary>
              <dl>
                <div>
                  <dt>{t('Input')}</dt>
                  <dd>{inputLabel(run.input)}</dd>
                </div>
                {run.input.species && (
                  <div>
                    <dt>{t('Organism')}</dt>
                    <dd>{run.input.species}</dd>
                  </div>
                )}
                <div>
                  <dt>{t('Goal')}</dt>
                  <dd>{run.input.type === 'description' ? run.input.text : run.input.goal}</dd>
                </div>
              </dl>
              {run.input.file && (
                <p>
                  {t(
                    'Only the file name and size are saved, plus a normalized sequence for FASTA. Original file bytes are not retained or uploaded.',
                  )}
                </p>
              )}
            </details>
          </section>
        )}
        <section
          className="easy-history"
          id="my-designs"
          ref={historyRef}
          aria-label={t('My designs')}
        >
          <div className="easy-history-heading">
            <div>
              <h2>
                {t('My designs')} <span>{state.runs.length}</span>
              </h2>
            </div>
            <button className="easy-outline" onClick={newDesign}>
              <Plus size={15} /> {t('New design')}
            </button>
          </div>
          <div className="easy-history-toolbar">
            <div className="easy-filters" aria-label={t('Filter designs')}>
              {[
                ['all', 'All'],
                ['running', 'In progress'],
                ['paused', 'Paused'],
                ['complete', 'Completed'],
                ['draft', 'Drafts'],
              ].map(([value, label]) => (
                <button
                  key={value}
                  aria-pressed={filter === value}
                  onClick={() => setFilter(value)}
                >
                  {t(label)}
                </button>
              ))}
            </div>
            <label className="easy-search">
              <Search size={15} />
              <input
                aria-label={t('Search designs')}
                placeholder={t('Search designs')}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
            </label>
          </div>
          {!filtered.length ? (
            <div className="easy-history-empty">
              <History size={23} />
              <h3>{state.runs.length ? t('No matching designs') : t('No designs yet')}</h3>
            </div>
          ) : (
            <div className="easy-history-table">
              <table>
                <thead>
                  <tr>
                    <th>{t('Design')}</th>
                    <th>{t('Input')}</th>
                    <th>{t('Status')}</th>
                    <th>{t('Updated')}</th>
                    <th>
                      <span className="sr-only">{t('Open')}</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((item) => (
                    <tr key={item.id}>
                      <td>
                        <button className="easy-design-name" onClick={() => open(item)}>
                          {item.status === 'complete' ? (
                            <Check size={16} />
                          ) : item.status === 'draft' ? (
                            <Save size={16} />
                          ) : (
                            <Atom size={16} />
                          )}
                          <span>{item.name}</span>
                        </button>
                      </td>
                      <td>
                        {t(INPUT_TYPES.find((option) => option.id === item.input.type)!.label)}
                      </td>
                      <td>
                        <span className={`easy-status ${item.status}`}>
                          {item.status === 'complete'
                            ? t('Completed')
                            : item.status === 'running'
                              ? t('In progress')
                              : item.status === 'draft'
                                ? t('Draft')
                                : t('Paused')}
                        </span>
                      </td>
                      <td>{date(item.updatedAt, locale)}</td>
                      <td>
                        <button
                          className="easy-icon-button"
                          aria-label={t('Open {name}', { name: item.name })}
                          onClick={() => open(item)}
                        >
                          <ArrowUpRight size={16} />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <div className="easy-history-footer">
            <span>
              <span /> {t('Saved on this device')}
            </span>
          </div>
        </section>
        <footer className="easy-footer">
          <a href="#design" onClick={() => scroll(formRef.current)}>
            {t('Back to top')} <ArrowUpRight size={12} />
          </a>
        </footer>
      </main>
      <RabbitMascot
        locale={locale}
        mood={run?.status === 'running' ? 'running' : complete ? 'complete' : 'idle'}
        stage={run ? STEPS[viewStep] : 'Idle'}
        chatContext={{
          stage: run ? STEPS[viewStep] : 'Idle',
          status: selected?.status ?? 'idle',
          goal: selected
            ? (selected.input.type === 'description'
                ? selected.input.text
                : selected.input.goal
              ).slice(0, 1200)
            : '',
        }}
      />
      {toast && (
        <div className="easy-toast" role="status">
          <Check size={15} />
          {t(toast)}
        </div>
      )}
      <dialog
        ref={helpRef}
        className="easy-guide"
        onCancel={() => setHelp(false)}
        onClick={(event) => {
          if (event.target === event.currentTarget) setHelp(false);
        }}
      >
        <header>
          <span className="easy-kicker">{t('A QUICK INTRODUCTION')}</span>
          <button
            className="easy-icon-button"
            aria-label={t('Close guide')}
            onClick={() => setHelp(false)}
          >
            <X size={18} />
          </button>
        </header>
        <h2>{t('One target. A simpler start.')}</h2>
        {['guide.intake', 'guide.demo', 'guide.files', 'guide.pro'].map((key) => (
          <p key={key}>{t(key)}</p>
        ))}
        <button className="easy-primary" onClick={() => setHelp(false)}>
          {t('Got it')} <ArrowRight size={14} />
        </button>
      </dialog>
    </div>
  );
}
