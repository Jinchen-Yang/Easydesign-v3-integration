import { useTranslation } from 'react-i18next';
import { useEffect, useRef } from 'react';
import {
  ArrowUpRight,
  Check,
  ChevronLeft,
  ChevronRight,
  Dna,
  Layers,
  Star,
  Target,
  X,
} from 'lucide-react';
import type {
  Candidate,
  WorkbenchEdit,
  WorkbenchSnapshot,
  WorkflowPhase,
} from '../../adapters/WorkbenchAdapter';
import { DemoBadge } from '../../components/DemoBadge';
import { MolecularViewer } from '../viewer/MolecularViewer';

const percent = (n: number) => `${Math.round(n * 100)}%`;
function Sequence({
  sequence,
  label = 'REFERENCE SEQUENCE',
}: {
  sequence: string;
  label?: string;
}) {
  const { t } = useTranslation('pro');
  return (
    <div className="sequence">
      <div>
        <span className="eyebrow">{t(label)}</span>
        <span>{sequence.length} aa</span>
      </div>
      <code title={sequence}>{sequence}</code>
    </div>
  );
}
function MetricRow({ label, value }: { label: string; value: number }) {
  const { t } = useTranslation('pro');
  return (
    <div className="metric-row">
      <span>{t(label)}</span>
      <span className="metric-track">
        <span style={{ width: percent(value) }} />
      </span>
      <strong>{value.toFixed(2)}</strong>
    </div>
  );
}
function CandidateMetrics({ candidate }: { candidate: Candidate }) {
  const { t } = useTranslation('pro');
  return (
    <div className="candidate-metrics">
      <div>
        <span>{t('Interface')}</span>
        <strong>{candidate.interface.toFixed(2)}</strong>
      </div>
      <div>
        <span>{t('Confidence')}</span>
        <strong>{candidate.confidence.toFixed(2)}</strong>
      </div>
      <div>
        <span>{candidate.clash === undefined ? t('Developability') : t('Clash')}</span>
        <strong>{(candidate.clash ?? candidate.developability ?? 0).toFixed(2)}</strong>
      </div>
    </div>
  );
}

export function ScientificContext({
  snapshot,
  phase,
  revealRequest,
  compare,
  onEdit,
  onClose,
}: {
  snapshot: WorkbenchSnapshot;
  phase: WorkflowPhase;
  revealRequest: number;
  compare: boolean;
  onEdit: (edit: WorkbenchEdit) => void;
  onClose: () => void;
}) {
  const { t } = useTranslation('pro');
  const panel = useRef<HTMLElement>(null);
  const scroll = useRef<HTMLDivElement>(null);
  const previousRequest = useRef(revealRequest);
  useEffect(() => {
    scroll.current?.scrollTo({ top: 0, behavior: 'instant' });
    if (previousRequest.current !== revealRequest) {
      panel.current?.focus({ preventScroll: true });
      previousRequest.current = revealRequest;
    }
  }, [phase, revealRequest]);
  const c = snapshot.context,
    site = c.sites.find((s) => s.id === c.selectedSite)!;
  const candidates = phase === 'pilot' ? c.pilotCandidates : c.finalists;
  const selected =
    candidates.find((candidate) => candidate.id === c.selectedCandidate) ?? candidates[0];
  const currentBusy = phase === snapshot.phase && snapshot.busy;
  const canSelectSite = phase === snapshot.phase && !snapshot.busy && !snapshot.completed;
  const selectCandidate = (candidateId: string) => onEdit({ type: 'candidate', candidateId });
  return (
    <aside
      ref={panel}
      id="scientific-context"
      className={`scientific-context phase-${phase}`}
      aria-label={t('Scientific Context')}
      tabIndex={-1}
      onKeyDown={(event) => {
        if (event.key === 'Escape' && window.matchMedia('(max-width: 1180px)').matches) {
          event.preventDefault();
          onClose();
        }
      }}
    >
      <header className="context-header">
        <div>
          <span className="eyebrow">{t('SCIENTIFIC CONTEXT')}</span>
          <span className="context-phase">{t(phase.charAt(0).toUpperCase() + phase.slice(1))}</span>
        </div>
        <DemoBadge />
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
              <p>{snapshot.project.goal}</p>
            </div>
            <div className="definition-list">
              <div>
                <span>{t('Target')}</span>
                <strong>{t('Lysozyme')}</strong>
              </div>
              <div>
                <span>{t('Binder type')}</span>
                <strong>VHH</strong>
              </div>
              <div>
                <span>{t('Objective')}</span>
                <strong>{t('Accessible epitope')}</strong>
              </div>
              <div>
                <span>{t('Mode')}</span>
                <strong>{t('UI Demo Fixture')}</strong>
              </div>
            </div>
            <div className="source-placeholder">
              <Layers size={18} />
              <strong>{t('Your research starts here')}</strong>
              <p>
                {t(
                  'This demo includes a public structure reference. Uploaded sources will be supported in a future version.',
                )}
              </p>
            </div>
          </>
        )}
        {(phase === 'target' || phase === 'site') && (
          <>
            <div className="context-title">
              <div className="title-with-icon">
                <h2>
                  {phase === 'target' ? t('Hen egg-white lysozyme') : t('Choose a binding site')}
                </h2>
                <span className="object-icon small">
                  <Dna size={17} />
                </span>
              </div>
              <p>
                {phase === 'target'
                  ? 'A compact reference for your VHH design.'
                  : t('Three demo sites on the same target surface.')}
              </p>
            </div>
            <MolecularViewer
              reference={c.structure}
              mode="target"
              sites={phase === 'site' ? c.sites : undefined}
              selectedSite={phase === 'site' ? c.selectedSite : undefined}
            />
            {phase === 'target' ? (
              <>
                <div className="identity-grid">
                  <div>
                    <span>{t('PDB reference')}</span>
                    <a href="https://www.rcsb.org/structure/1MEL" target="_blank" rel="noreferrer">
                      1MEL <ArrowUpRight size={12} />
                    </a>
                  </div>
                  <div>
                    <span>UniProt</span>
                    <a
                      href="https://www.uniprot.org/uniprotkb/P00698/entry"
                      target="_blank"
                      rel="noreferrer"
                    >
                      P00698 <ArrowUpRight size={12} />
                    </a>
                  </div>
                  <div>
                    <span>{t('Target chain')}</span>
                    <strong>
                      {c.structure.targetChain} <small>{t('author · C label')}</small>
                    </strong>
                  </div>
                  <div>
                    <span>{t('Reference')}</span>
                    <strong>{t('Lysozyme / VHH')}</strong>
                  </div>
                </div>
                <Sequence sequence={c.structure.targetSequence} />
                <div className="quiet-note">
                  <Check size={14} />
                  <p>
                    {t(
                      'Reference identity is available. Your approval moves the demo to site comparison.',
                    )}
                  </p>
                </div>
              </>
            ) : (
              <>
                <div className="section-label">
                  <h3>{t('Candidate sites')}</h3>
                  <span className="simulated-label">{t('Simulated scores')}</span>
                </div>
                <div className="site-tabs" role="group" aria-label={t('Candidate sites')}>
                  {c.sites.map((s) => (
                    <button
                      key={s.id}
                      aria-pressed={s.id === c.selectedSite}
                      disabled={!canSelectSite}
                      onClick={() => onEdit({ type: 'site', siteId: s.id })}
                    >
                      <span className={`site-swatch site-${s.id}`} />
                      {s.label}
                      {s.recommended && <span className="recommend-star">✧</span>}
                    </button>
                  ))}
                </div>
                <div className="selected-site-heading">
                  <strong>{site.label}</strong>
                  {site.recommended && <span className="recommendation">{t('Recommended')}</span>}
                </div>
                <div className="site-metrics">
                  <MetricRow label={t('Accessibility')} value={site.accessibility} />
                  <MetricRow label={t('Geometry')} value={site.geometry} />
                  <MetricRow label={t('Evidence')} value={site.evidence} />
                </div>
                <div className="residues">
                  <span className="eyebrow">{t('DEMO RESIDUES')}</span>
                  <div>
                    {site.residues.map((r) => (
                      <span key={r}>
                        {c.structure.targetChain}:{r}
                      </span>
                    ))}
                  </div>
                </div>
                {compare && (
                  <div className="comparison-table">
                    <h3>{t('Compare all three sites')}</h3>
                    <table>
                      <thead>
                        <tr>
                          <th>{t('Site')}</th>
                          <th>{t('Access.')}</th>
                          <th>{t('Geometry')}</th>
                          <th>{t('Evidence')}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {c.sites.map((s) => (
                          <tr key={s.id} className={s.id === c.selectedSite ? 'selected' : ''}>
                            <th>{s.label}</th>
                            <td>{s.accessibility.toFixed(2)}</td>
                            <td>{s.geometry.toFixed(2)}</td>
                            <td>{s.evidence.toFixed(2)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
                <p className="scientific-disclaimer">
                  {t('Residue groups and scores are demo fixtures, not validated epitopes.')}
                </p>
              </>
            )}
          </>
        )}
        {phase === 'design' && (
          <>
            <div className="context-title">
              <h2>{t('A deliberate first pilot')}</h2>
              <p>{t('One scaffold. Two complementary approaches.')}</p>
            </div>
            <div className="approved-site">
              <span className="small-check">
                <Check size={13} />
              </span>
              <div>
                <span className="eyebrow">{t('APPROVED SITE')}</span>
                <strong>
                  {t('Site')} {c.approvedSite ?? c.selectedSite}
                </strong>
              </div>
              <span>{t('Lysozyme')}</span>
            </div>
            <div className="scaffold-card">
              <Dna size={34} strokeWidth={1.2} />
              <span className="eyebrow">{t('BINDER SCAFFOLD')}</span>
              <h3>{c.scaffold}</h3>
              <p>{t('Single-domain antibody · VHH')}</p>
              <DemoBadge short />
            </div>
            <div className="section-label">
              <h3>{t('Design arms')}</h3>
              <span>{t('8 candidates total')}</span>
            </div>
            <div className="design-arms">
              {c.arms.map((a, i) => (
                <div key={a.id}>
                  <span className="arm-number">0{i + 1}</span>
                  <div>
                    <strong>{a.label}</strong>
                    <p>
                      {i === 0
                        ? t('Concentrate on the selected hotspot.')
                        : t('Explore the surrounding interface.')}
                    </p>
                  </div>
                  <span className="arm-budget">
                    {a.count}
                    <small>{t('candidates')}</small>
                  </span>
                </div>
              ))}
            </div>
            <div className="budget-strip">
              <span>{t('Pilot budget')}</span>
              <strong>
                4 + 4 <span>=</span> 8
              </strong>
            </div>
            <p className="scientific-disclaimer">
              {t('This plan plays a simulated pilot. It does not submit a compute job.')}
            </p>
          </>
        )}
        {phase === 'pilot' && (
          <>
            <div className="context-title">
              <div className="title-with-icon">
                <h2>{t('Small pilot, clear comparison')}</h2>
                <span className="count-label">8</span>
              </div>
              <p>{t('Two arms · eight simulated candidates')}</p>
            </div>
            <div className="pass-summary">
              <strong>
                {currentBusy ? t('Reviewing') : t('6 of 8 pass')}
                <span>
                  {currentBusy
                    ? t('Preparing the fixed pilot results')
                    : t('2 filtered · 75% demo pass rate')}
                </span>
              </strong>
              <div className="pass-segments" aria-label={t('6 passing and 2 filtered')}>
                {c.pilotCandidates.map((candidate) => (
                  <span key={candidate.id} className={currentBusy ? 'pending' : candidate.status} />
                ))}
              </div>
            </div>
            <div className="pilot-grid" aria-label={t('Pilot candidates')}>
              {c.pilotCandidates.map((candidate) => (
                <button
                  key={candidate.id}
                  data-testid="pilot-candidate"
                  onClick={() => selectCandidate(candidate.id)}
                  aria-pressed={selected.id === candidate.id}
                >
                  <strong>{candidate.id}</strong>
                  <span className={`result-status ${candidate.status}`}>
                    {currentBusy
                      ? t('Pending')
                      : candidate.status === 'pass'
                        ? t('Pass')
                        : t('Filtered')}
                  </span>
                </button>
              ))}
            </div>
            <div className="section-label">
              <h3>
                {selected.id} <span>{t('reference view')}</span>
              </h3>
              <span className="simulated-label">{t('Demo fixture')}</span>
            </div>
            <MolecularViewer reference={c.structure} mode="complex" candidateId={selected.id} />
            <CandidateMetrics candidate={selected} />
            <div className="length-row">
              <span>{t('Reference residues shown')}</span>
              <strong>{selected.length} aa</strong>
            </div>
            <p className="scientific-disclaimer">
              {t(
                'Scores and outcomes are simulated. All candidates share the 1MEL reference complex.',
              )}
            </p>
          </>
        )}
        {phase === 'scale' && (
          <>
            <div className="context-title">
              <h2>{t('A broader view of the possibilities')}</h2>
              <p>{t('Three small batches. A fixed, focused scope.')}</p>
            </div>
            <div className="scale-counter">
              <strong>
                {c.scale.completedBatches * 8}
                <span> / 24</span>
              </strong>
              <span>{t('simulated candidates reviewed')}</span>
            </div>
            <div
              className="scale-progress"
              role="progressbar"
              aria-label={t('Scale progress')}
              aria-valuenow={c.scale.completedBatches * 8}
              aria-valuemin={0}
              aria-valuemax={24}
            >
              <span style={{ width: `${(c.scale.completedBatches / 3) * 100}%` }} />
            </div>
            <div className="batch-list">
              {Array.from({ length: 3 }, (_, i) => (
                <div key={i} className={i < c.scale.completedBatches ? 'complete' : ''}>
                  <span className="batch-icon">
                    {i < c.scale.completedBatches ? <Check size={15} /> : <Layers size={15} />}
                  </span>
                  <div>
                    <strong>
                      {t('Batch')} {i + 1}
                    </strong>
                    <span>{t('8 candidates')}</span>
                  </div>
                  <span>
                    {i < c.scale.completedBatches
                      ? '6 pass · 2 filtered'
                      : i === c.scale.completedBatches
                        ? t('In review')
                        : t('Waiting')}
                  </span>
                </div>
              ))}
            </div>
            <div className="section-label">
              <h3>{t('Candidate distribution')}</h3>
              <span className="simulated-label">{t('Simulated')}</span>
            </div>
            <div className="scale-dots">
              {Array.from({ length: 24 }, (_, i) => (
                <span
                  key={i}
                  title={t('Demo candidate {{number}}', { number: i + 1 })}
                  className={
                    i < c.scale.completedBatches * 8 ? (i % 8 < 6 ? 'pass' : 'filtered') : 'pending'
                  }
                >
                  {String(i + 1).padStart(2, '0')}
                </span>
              ))}
            </div>
            <div className="scale-legend">
              <span>
                <i className="pass" />
                {c.scale.completedBatches * 6} {t('pass')}
              </span>
              <span>
                <i className="filtered" />
                {c.scale.completedBatches * 2} {t('filtered')}
              </span>
            </div>
            <p className="scientific-disclaimer">
              {t('All 24 outcomes are deterministic UI fixtures.')}
            </p>
          </>
        )}
        {phase === 'candidates' && (
          <>
            <div className="context-title">
              <div className="title-with-icon">
                <h2>
                  {snapshot.completed ? t('Your finalized panel') : t('Six finalists to explore')}
                </h2>
                <span className="count-label">6</span>
              </div>
              <p>
                {snapshot.completed
                  ? 'A complete demo journey, ready to revisit.'
                  : t('Compare the panel and star your favorites.')}
              </p>
            </div>
            <div className="candidate-view-header">
              <strong>{selected.id}</strong>
              <span>{t('Shared 1MEL reference')}</span>
              <div>
                <button
                  aria-label={t('Previous candidate')}
                  onClick={() =>
                    selectCandidate(candidates[(candidates.indexOf(selected) + 5) % 6].id)
                  }
                >
                  <ChevronLeft size={15} />
                </button>
                <button
                  aria-label={t('Next candidate')}
                  onClick={() =>
                    selectCandidate(candidates[(candidates.indexOf(selected) + 1) % 6].id)
                  }
                >
                  <ChevronRight size={15} />
                </button>
              </div>
            </div>
            <MolecularViewer reference={c.structure} mode="complex" candidateId={selected.id} />
            <CandidateMetrics candidate={selected} />
            <div className="sequence-preview">
              <span>{t('Demo sequence preview')}</span>
              <code>{selected.sequencePreview}</code>
            </div>
            <div className="section-label">
              <h3>{t('Finalist panel')}</h3>
              <span className="simulated-label">{t('Simulated metrics')}</span>
            </div>
            <div className="finalists-grid">
              {c.finalists.map((candidate) => (
                <div
                  className={`finalist-card ${selected.id === candidate.id ? 'selected' : ''}`}
                  key={candidate.id}
                  data-testid="finalist-card"
                >
                  <button
                    className="candidate-select"
                    aria-label={t('Select {{name}}', { name: candidate.id })}
                    aria-pressed={selected.id === candidate.id}
                    onClick={() => selectCandidate(candidate.id)}
                  >
                    <span>
                      <strong>{candidate.id}</strong>
                      <small>#{candidate.rank}</small>
                    </span>
                    <code>{candidate.sequencePreview}</code>
                    <span className="candidate-card-extra">
                      <span title={t('Simulated interface score')}>
                        {t('Int.')}
                        <b>{candidate.interface.toFixed(2)}</b>
                      </span>
                      <span title={t('Simulated confidence score')}>
                        {t('Conf.')}
                        <b>{candidate.confidence.toFixed(2)}</b>
                      </span>
                      <span title={t('Simulated developability score')}>
                        {t('Dev.')}
                        <b>{candidate.developability?.toFixed(2)}</b>
                      </span>
                    </span>
                  </button>
                  <button
                    className="star-button"
                    aria-label={t('Star {{name}}', { name: candidate.id })}
                    aria-pressed={c.shortlisted.includes(candidate.id)}
                    onClick={() => onEdit({ type: 'shortlist', candidateId: candidate.id })}
                  >
                    <Star
                      size={13}
                      fill={c.shortlisted.includes(candidate.id) ? 'currentColor' : 'none'}
                    />
                  </button>
                </div>
              ))}
            </div>
            {compare && (
              <div className="comparison-table">
                <h3>{t('Panel comparison · Demo')}</h3>
                <table>
                  <thead>
                    <tr>
                      <th>{t('Candidate')}</th>
                      <th>{t('Interface')}</th>
                      <th>{t('Conf.')}</th>
                      <th>{t('Develop.')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {c.finalists.map((x) => (
                      <tr key={x.id}>
                        <th>{x.id}</th>
                        <td>{x.interface.toFixed(2)}</td>
                        <td>{x.confidence.toFixed(2)}</td>
                        <td>{x.developability?.toFixed(2)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <p className="scientific-disclaimer">
              {t(
                'Demo candidates, not generated proteins. The 1MEL complex is a shared visualization placeholder.',
              )}
            </p>
          </>
        )}
      </div>
    </aside>
  );
}
