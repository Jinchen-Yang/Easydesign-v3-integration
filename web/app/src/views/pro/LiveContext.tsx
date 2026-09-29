import { useTranslation } from 'react-i18next';
import { appI18n } from '../../shell/I18nProvider';
import { useEffect, useRef, useState } from 'react';
import {
  ArrowDownToLine,
  Check,
  ChevronLeft,
  ChevronRight,
  Dna,
  Layers,
  Target,
  X,
} from 'lucide-react';
import { DemoBadge } from '../../components/DemoBadge';
import type { WorkflowPhase } from '../../adapters/WorkbenchAdapter';
import type { LiveWorkbenchPort } from '../../adapters/LiveWorkbenchAdapter';
import type { Artifact, Candidate, LiveState, ProductSnapshot } from './contracts';
import { StructureViewer } from './StructureViewer';
import { useInputDraft } from '../../data/useInputDraft';
const show = (v: unknown) =>
  v == null
    ? appI18n.getFixedT(null, 'pro')('Not available')
    : typeof v === 'object'
      ? ''
      : String(v);
// Display priorities only: native thresholds and scientific ranking are untouched.
const prominent = [
  ['bb_rmsd', 'RMSD'],
  ['design_to_target_iptm', 'Interface ipTM'],
  ['bb_rmsd_design', 'Design RMSD'],
  ['design_iptm', 'ipTM'],
  ['interaction_pae', 'Interface PAE'],
  ['delta_sasa_refolded', 'Interface area'],
];
const headlineMetrics = (candidate: Candidate) =>
  prominent
    .flatMap(([id, label]) => {
      const metric = candidate.metrics.find((m) => m.id === id && m.status === 'available');
      return metric ? [{ ...metric, label }] : [];
    })
    .slice(0, 3);
const metricValue = (value: unknown) =>
  typeof value === 'number' ? Number(value.toFixed(3)).toString() : show(value);
export function LiveContext({
  snapshot: v,
  state,
  adapter,
  phase,
  siteId,
  onSite,
  compare,
  onClose,
  revealRequest,
  draftKey,
}: {
  snapshot: ProductSnapshot;
  state: LiveState;
  adapter: LiveWorkbenchPort;
  phase: WorkflowPhase;
  siteId: string;
  onSite: (id: string) => void;
  compare: boolean;
  onClose: () => void;
  revealRequest: number;
  draftKey?: string;
}) {
  const { t } = useTranslation('pro');
  const panel = useRef<HTMLElement>(null),
    scroll = useRef<HTMLDivElement>(null);
  useEffect(() => {
    scroll.current?.scrollTo({ top: 0 });
    if (revealRequest) panel.current?.focus({ preventScroll: true });
  }, [phase, revealRequest]);
  const c = v.scientific_context,
    selected = state.selectedCandidate;
  const candidateView = useInputDraft(
    draftKey ?? null,
    { offset: 0, candidateId: '' },
    {
      valid: (value): value is { offset: number; candidateId: string } => {
        if (!value || typeof value !== 'object') return false;
        const record = value as { offset: number; candidateId: string };
        return (
          Number.isInteger(record.offset) &&
          record.offset >= 0 &&
          typeof record.candidateId === 'string'
        );
      },
    },
  );
  const restoredView = useRef<string | null>(null);
  const [viewError, setViewError] = useState('');
  useEffect(() => {
    if (
      !draftKey ||
      restoredView.current === draftKey ||
      !v.candidates.total ||
      !state.candidates.limit ||
      !state.candidates.items.length
    )
      return;
    restoredView.current = draftKey;
    const saved = candidateView.value;
    if (candidateView.status !== 'local') return;
    let active = true;
    // Restoring a read-only page/selection never changes scientific filtering,
    // submits a Gate or starts computation.
    void (async () => {
      const offset = saved.offset < v.candidates.total ? saved.offset : 0;
      if (offset !== state.candidates.offset) await adapter.candidatePage(offset);
      if (active && saved.candidateId) await adapter.selectCandidate(saved.candidateId);
    })().catch((error: Error) => {
      if (active) setViewError(error.message);
    });
    return () => {
      active = false;
    };
    // Re-run only for a new project or when its first candidate page becomes available.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    draftKey,
    v.candidates.total > 0,
    state.candidates.limit > 0,
    state.candidates.items.length > 0,
    adapter,
  ]);
  const [selectedTargetPreview, setSelectedTargetPreview] = useState('');
  const targetEvidence = c.target || {},
    targetFacts =
      typeof targetEvidence.hard_facts === 'object' && targetEvidence.hard_facts
        ? (targetEvidence.hard_facts as Record<string, unknown>)
        : {},
    targetOptions = Array.isArray(targetEvidence.options)
      ? (targetEvidence.options as Record<string, unknown>[])
      : [],
    targetLabel =
      c.target_id ||
      String(targetFacts.canonical_accession || '') ||
      String(c.target_intent?.target_label || '') ||
      String(c.target_source?.query || '') ||
      t('Your target');
  const defaultTargetPreview = String(
      v.decision?.default_option_id || targetOptions[0]?.option_id || '',
    ),
    defaultTargetOption =
      targetOptions.find((option) => String(option.option_id) === defaultTargetPreview) ||
      targetOptions[0],
    alternativeTargetOptions = targetOptions.filter(
      (option) => String(option.option_id) !== String(defaultTargetOption?.option_id || ''),
    ),
    activeTargetPreview = targetOptions.some(
      (option) => String(option.option_id) === selectedTargetPreview,
    )
      ? selectedTargetPreview
      : defaultTargetPreview,
    targetPreviewOption = targetOptions.find(
      (option) => String(option.option_id) === activeTargetPreview,
    ),
    targetPreviewArtifact = (targetPreviewOption?.preview_artifact as Artifact | undefined) || null,
    targetPreviewPayload =
      typeof targetPreviewOption?.payload === 'object' && targetPreviewOption.payload
        ? (targetPreviewOption.payload as Record<string, unknown>)
        : {},
    targetPreviewChain = String(targetPreviewPayload.chain || ''),
    targetStructureRoles = targetPreviewChain
      ? { [targetPreviewChain]: 'focus-target' }
      : Object.fromEntries((c.chains || []).map((chain) => [chain, 'focus-target']));
  const emptyStructureMessage =
    targetEvidence.decision_kind === 'identity-selection'
      ? t('Approve the verified target identity before structure candidates are prepared.')
      : targetEvidence.decision_kind === 'structure-selection'
        ? t('Select and approve a verified structure candidate to load its coordinates.')
        : v.lifecycle === 'failed'
          ? t(
              'Target research stopped before verified structure evidence was prepared. Retry Target Intelligence to continue.',
            )
          : t('Structure evidence is not available yet.');
  const site = c.sites.find((s) => s.id === siteId) || c.sites[0];
  const entries = state.candidates.items;
  const nativeProgress = ['pilot', 'scale'].includes(phase)
    ? v.jobs.find((job) => job.phase === phase && ['queued', 'running'].includes(job.status))
        ?.progress
    : undefined;
  const select = (candidate: Candidate) => {
    candidateView.setValue({
      offset: state.candidates.offset,
      candidateId: candidate.id,
    });
    void adapter.selectCandidate(candidate.id).catch((error: Error) => setViewError(error.message));
  };
  const page = async (offset: number) => {
    setViewError('');
    try {
      await adapter.candidatePage(offset);
      candidateView.setValue({ offset, candidateId: '' });
    } catch (error) {
      setViewError((error as Error).message);
    }
  };
  const structure = (candidate?: Candidate | null) => (
    <StructureViewer
      artifact={
        candidate
          ? candidate.artifacts.at(-1) || null
          : phase === 'target'
            ? c.structure || targetPreviewArtifact
            : c.structure
      }
      roles={
        candidate
          ? candidate.structure_roles
          : phase === 'target'
            ? targetStructureRoles
            : Object.fromEntries((c.chains || []).map((chain) => [chain, 'target']))
      }
      sites={candidate ? [] : c.sites}
      selectedSite={siteId}
      emptyMessage={!candidate && phase === 'target' ? emptyStructureMessage : undefined}
    />
  );
  const candidateMetrics = selected ? headlineMetrics(selected) : [];
  const metricCards = selected && (
    <div className="candidate-metrics">
      {candidateMetrics.slice(0, 3).map((m) => (
        <div key={m.id}>
          <span>{t(m.label)}</span>
          <strong>
            {metricValue(m.value)} {m.unit}
          </strong>
        </div>
      ))}
    </div>
  );
  const details = (title: string, rows: string[]) =>
    rows.length > 0 && (
      <details className="evidence-details">
        <summary>{title}</summary>
        <ul>
          {rows.map((s, i) => (
            <li key={i}>{s}</li>
          ))}
        </ul>
      </details>
    );
  const campaign = c.campaign,
    completedBatches = Number(campaign?.complete_batches || 0),
    batches = Number(campaign?.planned_batches || 0);
  return (
    <aside
      ref={panel}
      id="scientific-context"
      className={`scientific-context phase-${phase}`}
      aria-label={t('Scientific Context')}
      tabIndex={-1}
      onKeyDown={(e) => {
        if (e.key === 'Escape') onClose();
      }}
    >
      <header className="context-header">
        <div>
          <span className="eyebrow">{t('SCIENTIFIC CONTEXT')}</span>
          <span className="context-phase">{t(phase[0].toUpperCase() + phase.slice(1))}</span>
        </div>
        <DemoBadge mode="live" />
        <button
          className="context-close icon-button"
          aria-label={t('Close scientific context')}
          onClick={onClose}
        >
          <X size={16} />
        </button>
      </header>
      <div className="context-scroll" ref={scroll}>
        {phase === 'goal' && (
          <>
            <div className="context-title">
              <span className="object-icon">
                <Target size={24} />
              </span>
              <h2>{t('A focused research goal')}</h2>
              <p>{v.project.goal}</p>
            </div>
            <div className="definition-list">
              <div>
                <span>{t('Target')}</span>
                <strong>{c.target_id || t('Under review')}</strong>
              </div>
              <div>
                <span>{t('Current step')}</span>
                <strong>{t(v.project.phase[0].toUpperCase() + v.project.phase.slice(1))}</strong>
              </div>
            </div>
            <div className="source-placeholder">
              <Layers size={18} />
              <strong>{t('Your research starts here')}</strong>
              <p>{t('Your goal, source structure and decisions stay with this project.')}</p>
            </div>
          </>
        )}
        {(phase === 'target' || phase === 'site') && (
          <>
            <div className="context-title">
              <div className="title-with-icon">
                <h2>{phase === 'target' ? targetLabel : t('Choose a binding site')}</h2>
                <span className="object-icon small">
                  <Dna size={17} />
                </span>
              </div>
              <p>
                {phase === 'target'
                  ? 'A structural reference for your binder design.'
                  : t('{{count}} candidate sites on your target.', {
                      count: c.sites.length,
                    })}
              </p>
            </div>
            {structure()}
            {phase === 'target' ? (
              <>
                <div className="identity-grid">
                  <div>
                    <span>{t('Target')}</span>
                    <strong>{targetLabel}</strong>
                  </div>
                  <div>
                    <span>{t('Target chain')}</span>
                    <strong>{c.chains?.join(', ') || t('Under review')}</strong>
                  </div>
                  <div>
                    <span>{t('Residues')}</span>
                    <strong>{c.sequence_length || t('Under review')}</strong>
                  </div>
                  <div>
                    <span>{t('Structure')}</span>
                    <strong>
                      {c.structure?.format.toUpperCase() ||
                        (targetOptions.length
                          ? t('{{count}} candidates', {
                              count: targetOptions.length,
                            })
                          : t('Under review'))}
                    </strong>
                  </div>
                </div>
                <div className="definition-list target-source-facts">
                  <div>
                    <span>{t('Organism')}</span>
                    <strong>
                      {String(
                        c.target_intent?.organism ||
                          c.target_source?.organism_taxon_id ||
                          t('Under review'),
                      )}
                    </strong>
                  </div>
                  <div>
                    <span>{t('Evidence state')}</span>
                    <strong>{String(targetEvidence.status || v.lifecycle)}</strong>
                  </div>
                </div>
                {!!targetOptions.length && (
                  <div className="target-structure-options">
                    <div className="section-label">
                      <h3>{t('Automatically selected structure')}</h3>
                      <span>{t('Recommended for this target')}</span>
                    </div>
                    {defaultTargetOption && (
                      <button
                        type="button"
                        className="target-structure-card recommended"
                        aria-label={t('Preview recommended structure {{name}}', {
                          name: String(defaultTargetOption.label || defaultTargetOption.option_id),
                        })}
                        aria-pressed={String(defaultTargetOption.option_id) === activeTargetPreview}
                        disabled={!defaultTargetOption.preview_artifact}
                        onClick={() =>
                          setSelectedTargetPreview(String(defaultTargetOption.option_id))
                        }
                      >
                        <span className="target-structure-badge">
                          {t('Recommended · selected')}
                        </span>
                        <strong>
                          {String(defaultTargetOption.label || defaultTargetOption.option_id)}
                        </strong>
                        <span>
                          {String(defaultTargetOption.description || t('Verified candidate'))}
                        </span>
                      </button>
                    )}
                    <p className="target-selection-note">
                      {t(
                        'The structure and chain are already selected. Approve the target to continue; use Change structure only if you want to replace this recommendation.',
                      )}
                    </p>
                    {!!alternativeTargetOptions.length && (
                      <details className="target-alternatives">
                        <summary>
                          {t('View alternatives ({{count}})', {
                            count: alternativeTargetOptions.length,
                          })}
                        </summary>
                        <p>
                          {t('Previewing an alternative does not change the Gate 1 selection.')}
                        </p>
                        <div className="target-alternative-list">
                          {alternativeTargetOptions.map((candidate) => (
                            <button
                              type="button"
                              className="target-structure-card"
                              key={String(candidate.option_id)}
                              aria-label={t('Preview alternative structure {{name}}', {
                                name: String(candidate.label || candidate.option_id),
                              })}
                              aria-pressed={String(candidate.option_id) === activeTargetPreview}
                              disabled={!candidate.preview_artifact}
                              onClick={() => setSelectedTargetPreview(String(candidate.option_id))}
                            >
                              <strong>{String(candidate.label || candidate.option_id)}</strong>
                              <span>
                                {String(candidate.description || t('Verified candidate'))}
                              </span>
                            </button>
                          ))}
                        </div>
                      </details>
                    )}
                  </div>
                )}
                <div className="quiet-note">
                  <Check size={14} />
                  <p>{t('Review the target and its evidence before moving to site comparison.')}</p>
                </div>
              </>
            ) : (
              <>
                <div className="section-label">
                  <h3>{t('Candidate sites')}</h3>
                  <span>{t('Relative recommendation')}</span>
                </div>
                <div className="site-tabs" role="group" aria-label={t('Candidate sites')}>
                  {c.sites.map((s) => (
                    <button
                      key={s.id}
                      aria-pressed={s.id === site?.id}
                      onClick={() => onSite(s.id)}
                    >
                      <span className={`site-swatch site-${s.rank}`} />
                      {t('Site')} {s.rank}
                      {s.rank === 'A' && <span className="recommend-star">✧</span>}
                    </button>
                  ))}
                </div>
                {site && (
                  <>
                    <div className="selected-site-heading">
                      <strong>
                        {t('Site')} {site.rank}
                      </strong>
                      <span className="recommendation">
                        {!site.selectable
                          ? t('Blocked')
                          : site.rank === 'A'
                            ? t('Recommended')
                            : site.rank === 'B'
                              ? t('Alternative')
                              : t('Exploratory')}
                      </span>
                    </div>
                    <p className="site-rationale">{site.why_ranked}</p>
                    <div className="definition-list">
                      <div>
                        <span>{t('Confidence')}</span>
                        <strong>{site.confidence || t('Not assessed')}</strong>
                      </div>
                      <div>
                        <span>{t('Candidate')}</span>
                        <strong>{site.name}</strong>
                      </div>
                    </div>
                    <div className="residues">
                      <span className="eyebrow">{t('HOTSPOT RESIDUES')}</span>
                      <div>
                        {site.coordinates.length
                          ? site.coordinates.map((r, i) => (
                              <span key={i}>
                                {r.author_chain_id}:{r.author_residue_id}
                                {r.insertion_code || ''}
                              </span>
                            ))
                          : site.design_labels.map((n) => <span key={n}>{n}</span>)}
                      </div>
                    </div>
                    {details(t('Risks'), site.risks)}
                    {details(t('Uncertainties'), site.uncertainty)}
                  </>
                )}
                {compare && (
                  <div className="comparison-table">
                    <h3>{t('Compare candidate sites')}</h3>
                    <table>
                      <thead>
                        <tr>
                          <th>{t('Site')}</th>
                          <th>{t('Confidence')}</th>
                          <th>{t('Recommendation')}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {c.sites.map((s) => (
                          <tr key={s.id} className={s.id === siteId ? 'selected' : ''}>
                            <th>
                              {t('Site')} {s.rank}
                            </th>
                            <td>{s.confidence}</td>
                            <td>{s.why_ranked}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
                {!site && (
                  <p className="scientific-disclaimer">
                    {c.approved_site
                      ? t(
                          'This saved project contains an approved hotspot; the earlier candidate portfolio is unavailable.',
                        )
                      : t('Candidate sites will appear when the research is ready.')}
                  </p>
                )}
              </>
            )}
          </>
        )}
        {phase === 'design' && (
          <>
            <div className="context-title">
              <h2>{t('A deliberate first pilot')}</h2>
              <p>
                {t('{{count}} complementary design approaches.', {
                  count: c.arms.length,
                })}
              </p>
            </div>
            <div className="approved-site">
              <span className="small-check">
                <Check size={13} />
              </span>
              <div>
                <span className="eyebrow">{t('APPROVED SITE')}</span>
                <strong>
                  {c.approved_site?.selected_rank
                    ? t('Site {{name}}', {
                        name: c.approved_site.selected_rank,
                      })
                    : t('See approved hotspot')}
                </strong>
              </div>
              <span>{c.target_id}</span>
            </div>
            <div className="scaffold-card">
              <Dna size={34} strokeWidth={1.2} />
              <span className="eyebrow">{t('BINDER SCAFFOLD')}</span>
              <h3>{t('Design strategy')}</h3>
              <p>{c.design_approved ? t('Approved design') : t('Ready for scientific review')}</p>
            </div>
            <div className="section-label">
              <h3>{t('Design arms')}</h3>
              <span>
                {c.arms.length} {t('arms')}
              </span>
            </div>
            <div className="design-arms">
              {c.arms.map((a, i) => (
                <div key={i}>
                  <span className="arm-number">{String(i + 1).padStart(2, '0')}</span>
                  <div>
                    <strong>{show(a.name || a.arm_id)}</strong>
                    <p>{show(a.hypothesis || a.rationale)}</p>
                  </div>
                </div>
              ))}
            </div>
            <details className="evidence-details">
              <summary>{t('Design files')}</summary>
              {v.artifacts
                .filter((a) => ['yaml', 'yml', 'json'].includes(a.format))
                .map((a) => (
                  <a className="artifact-download" key={a.id} href={a.url} download>
                    <ArrowDownToLine size={14} />
                    {a.label}
                  </a>
                ))}
            </details>
          </>
        )}
        {nativeProgress && (
          <section aria-label={t('Native execution progress')}>
            <div className="context-title">
              <h2>
                {phase === 'pilot' ? t('Pilot') : t('Scale')} {t('computation in progress')}
              </h2>
              <p>
                {nativeProgress.completed} / {nativeProgress.total} {t('candidates collected')}
              </p>
            </div>
            <div
              className="scale-progress"
              role="progressbar"
              aria-label={t('Native candidates collected')}
              aria-valuemin={0}
              aria-valuenow={nativeProgress.completed}
              aria-valuemax={nativeProgress.total || 1}
            >
              <span
                style={{
                  width: `${nativeProgress.total ? Math.min(100, (nativeProgress.completed / nativeProgress.total) * 100) : 0}%`,
                }}
              />
            </div>
            <p>
              {nativeProgress.completed_tasks} / {nativeProgress.total_tasks}{' '}
              {t('strategy tasks complete ·')}{' '}
              {nativeProgress.substage_label || nativeProgress.status}
            </p>
            <p>
              {t(
                'Collected candidates are not native PASS results. Final evidence is still being prepared.',
              )}
            </p>
          </section>
        )}
        {phase === 'scale' && (
          <>
            <div className="context-title">
              <h2>{t('A broader view of the possibilities')}</h2>
              <p>{t('Review progress across the approved design arms.')}</p>
            </div>
            <div className="scale-counter">
              <strong>
                {completedBatches}
                <span> / {batches || '—'}</span>
              </strong>
              <span>{t('batches complete')}</span>
            </div>
            <div
              className="scale-progress"
              role="progressbar"
              aria-label={t('Scale progress')}
              aria-valuenow={completedBatches}
              aria-valuemax={batches || 1}
            >
              <span
                style={{
                  width: `${batches ? (completedBatches / batches) * 100 : 0}%`,
                }}
              />
            </div>
            <div className="batch-list">
              {v.jobs
                .filter((j) => j.phase === 'scale')
                .map((j) => (
                  <div key={j.id} className={j.status === 'succeeded' ? 'complete' : ''}>
                    <span className="batch-icon">
                      <Layers size={15} />
                    </span>
                    <div>
                      <strong>{t(j.status[0].toUpperCase() + j.status.slice(1))}</strong>
                      <span>{j.resumable ? t('Available to resume') : t('Scale batch')}</span>
                    </div>
                  </div>
                ))}
            </div>
            <div className="scale-legend">
              <span>
                <i className="pass" />
                {v.candidates.counts.pass || 0} {t('pass')}
              </span>
              <span>
                <i className="filtered" />
                {v.candidates.counts.fail || 0} {t('filtered')}
              </span>
            </div>
          </>
        )}
        {(phase === 'pilot' || phase === 'candidates') && (
          <>
            <div className="context-title">
              <div className="title-with-icon">
                <h2>
                  {phase === 'pilot'
                    ? t('Small pilot, clear comparison')
                    : v.project.status === 'complete'
                      ? t('Your finalized panel')
                      : t('Your candidates to explore')}
                </h2>
                <span className="count-label">{v.candidates.total}</span>
              </div>
              <p>{t('Compare the evidence and explore each candidate.')}</p>
            </div>
            {!(nativeProgress && v.candidates.total === 0) && (
              <div className="pass-summary">
                <strong>
                  {v.candidates.counts.pass || 0} {t('of')} {v.candidates.total} {t('pass')}
                  <span>
                    {v.candidates.counts.fail || 0} {t('filtered ·')}{' '}
                    {v.candidates.counts.incomplete || 0} {t('incomplete')}
                  </span>
                </strong>
                <div className="pass-segments">
                  {entries.map((ca) => (
                    <span
                      key={ca.id}
                      className={
                        ca.native_status === 'pass'
                          ? 'pass'
                          : ca.native_status === 'fail'
                            ? 'filtered'
                            : 'pending'
                      }
                    />
                  ))}
                </div>
              </div>
            )}
            {selected && (
              <>
                <div className="candidate-view-header">
                  <strong>{selected.backend_id || selected.id}</strong>
                  <span>{selected.panel_role || selected.scaffold}</span>
                  <div>
                    <button
                      aria-label={t('Previous candidate')}
                      onClick={() =>
                        select(
                          entries[
                            (entries.indexOf(selected) - 1 + entries.length) % entries.length
                          ],
                        )
                      }
                    >
                      <ChevronLeft size={15} />
                    </button>
                    <button
                      aria-label={t('Next candidate')}
                      onClick={() =>
                        select(entries[(entries.indexOf(selected) + 1) % entries.length])
                      }
                    >
                      <ChevronRight size={15} />
                    </button>
                  </div>
                </div>
                {structure(selected)}
                {metricCards}
                {selected.sequence && (
                  <div className="sequence-preview">
                    <span>
                      {t('Binder sequence ·')} {selected.sequence.length} aa
                    </span>
                    <code>{selected.sequence}</code>
                  </div>
                )}
                <details className="evidence-details">
                  <summary>{t('All measurements & evidence')}</summary>
                  <table className="metric-table">
                    <tbody>
                      {selected.metrics.map((m) => (
                        <tr key={m.id}>
                          <th>{t(m.label)}</th>
                          <td>
                            {show(m.value)} {m.unit}
                          </td>
                          <td>{m.rule_result || m.status}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {selected.artifacts.map((a) => (
                    <a className="artifact-download" key={a.id} href={a.url} download>
                      {a.label}
                    </a>
                  ))}
                </details>
              </>
            )}
            <div className="section-label">
              <h3>{phase === 'pilot' ? t('Pilot candidates') : t('Candidate panel')}</h3>
              <span>{t('Native evidence')}</span>
            </div>
            <div className="finalists-grid">
              {entries.map((ca) => (
                <div
                  className={`finalist-card ${selected?.id === ca.id ? 'selected' : ''}`}
                  key={ca.id}
                >
                  <button
                    className="candidate-select live-candidate-select"
                    aria-label={t('Select {{name}}', {
                      name: [ca.backend_id || ca.id, ca.scaffold].filter(Boolean).join(' '),
                    })}
                    aria-pressed={selected?.id === ca.id}
                    onClick={() => select(ca)}
                  >
                    <span>
                      <strong>{ca.backend_id || ca.id}</strong>
                      <small>{ca.panel_role || ca.native_status}</small>
                    </span>
                    <code>{ca.scaffold || ca.arm}</code>
                    <span className="candidate-card-extra">
                      {headlineMetrics(ca).map((m) => (
                        <span key={m.id}>
                          {t(m.label)} <b>{metricValue(m.value)}</b>
                        </span>
                      ))}
                    </span>
                  </button>
                </div>
              ))}
            </div>
            {viewError && <p role="alert">{viewError}</p>}
            {state.candidates.total > state.candidates.limit && (
              <div className="live-pager">
                <button
                  disabled={!state.candidates.offset}
                  onClick={() => void page(state.candidates.offset - state.candidates.limit)}
                >
                  {t('Previous')}
                </button>
                <span>
                  {state.candidates.offset + 1}–
                  {Math.min(
                    state.candidates.total,
                    state.candidates.offset + state.candidates.limit,
                  )}
                </span>
                <button
                  disabled={
                    state.candidates.offset + state.candidates.limit >= state.candidates.total
                  }
                  onClick={() => void page(state.candidates.offset + state.candidates.limit)}
                >
                  {t('Next')}
                </button>
              </div>
            )}
          </>
        )}
        {v.project.validation_only && (
          <p className="scientific-disclaimer">
            {t('Validation only · not authorized for experiment')}
          </p>
        )}
        {v.decision?.details_url && (
          <a className="artifact-download" href={v.decision.details_url} download>
            {t('Complete scientific review')}
            <ArrowDownToLine size={13} />
          </a>
        )}
      </div>
    </aside>
  );
}
