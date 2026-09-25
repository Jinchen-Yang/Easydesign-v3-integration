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
import { DemoBadge } from '../components/DemoBadge';
import type { WorkflowPhase } from '../adapters/WorkbenchAdapter';
import type { LiveWorkbenchPort } from '../adapters/LiveWorkbenchAdapter';
import type { Artifact, Candidate, LiveState, ProductSnapshot } from './contracts';
import { StructureViewer } from './StructureViewer';
const show = (v: unknown) => (v == null ? 'Not available' : typeof v === 'object' ? '' : String(v));
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
}) {
  const panel = useRef<HTMLElement>(null),
    scroll = useRef<HTMLDivElement>(null);
  useEffect(() => {
    scroll.current?.scrollTo({ top: 0 });
    if (revealRequest) panel.current?.focus({ preventScroll: true });
  }, [phase, revealRequest]);
  const c = v.scientific_context,
    selected = state.selectedCandidate;
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
      'Your target';
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
      ? 'Approve the verified target identity before structure candidates are prepared.'
      : targetEvidence.decision_kind === 'structure-selection'
        ? 'Select and approve a verified structure candidate to load its coordinates.'
        : v.lifecycle === 'failed'
          ? 'Target research stopped before verified structure evidence was prepared. Retry Target Intelligence to continue.'
          : 'Structure evidence is not available yet.';
  const site = c.sites.find((s) => s.id === siteId) || c.sites[0];
  const entries = state.candidates.items;
  const select = (candidate: Candidate) => void adapter.selectCandidate(candidate.id);
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
          <span>{m.label}</span>
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
      aria-label="Scientific Context"
      tabIndex={-1}
      onKeyDown={(e) => {
        if (e.key === 'Escape') onClose();
      }}
    >
      <header className="context-header">
        <div>
          <span className="eyebrow">SCIENTIFIC CONTEXT</span>
          <span className="context-phase">{phase[0].toUpperCase() + phase.slice(1)}</span>
        </div>
        <DemoBadge mode="live" />
        <button
          className="context-close icon-button"
          aria-label="Close scientific context"
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
              <h2>A focused research goal</h2>
              <p>{v.project.goal}</p>
            </div>
            <div className="definition-list">
              <div>
                <span>Target</span>
                <strong>{c.target_id || 'Under review'}</strong>
              </div>
              <div>
                <span>Current step</span>
                <strong>{v.project.phase}</strong>
              </div>
            </div>
            <div className="source-placeholder">
              <Layers size={18} />
              <strong>Your research starts here</strong>
              <p>Your goal, source structure and decisions stay with this project.</p>
            </div>
          </>
        )}
        {(phase === 'target' || phase === 'site') && (
          <>
            <div className="context-title">
              <div className="title-with-icon">
                <h2>{phase === 'target' ? targetLabel : 'Choose a binding site'}</h2>
                <span className="object-icon small">
                  <Dna size={17} />
                </span>
              </div>
              <p>
                {phase === 'target'
                  ? 'A structural reference for your binder design.'
                  : `${c.sites.length} candidate sites on your target.`}
              </p>
            </div>
            {structure()}
            {phase === 'target' ? (
              <>
                <div className="identity-grid">
                  <div>
                    <span>Target</span>
                    <strong>{targetLabel}</strong>
                  </div>
                  <div>
                    <span>Target chain</span>
                    <strong>{c.chains?.join(', ') || 'Under review'}</strong>
                  </div>
                  <div>
                    <span>Residues</span>
                    <strong>{c.sequence_length || 'Under review'}</strong>
                  </div>
                  <div>
                    <span>Structure</span>
                    <strong>
                      {c.structure?.format.toUpperCase() ||
                        (targetOptions.length
                          ? `${targetOptions.length} candidates`
                          : 'Under review')}
                    </strong>
                  </div>
                </div>
                <div className="definition-list target-source-facts">
                  <div>
                    <span>Organism</span>
                    <strong>
                      {String(
                        c.target_intent?.organism ||
                          c.target_source?.organism_taxon_id ||
                          'Under review',
                      )}
                    </strong>
                  </div>
                  <div>
                    <span>Evidence state</span>
                    <strong>{String(targetEvidence.status || v.lifecycle)}</strong>
                  </div>
                </div>
                {!!targetOptions.length && (
                  <div className="target-structure-options">
                    <div className="section-label">
                      <h3>Automatically selected structure</h3>
                      <span>Recommended for this target</span>
                    </div>
                    {defaultTargetOption && (
                      <button
                        type="button"
                        className="target-structure-card recommended"
                        aria-label={`Preview recommended structure ${String(defaultTargetOption.label || defaultTargetOption.option_id)}`}
                        aria-pressed={String(defaultTargetOption.option_id) === activeTargetPreview}
                        disabled={!defaultTargetOption.preview_artifact}
                        onClick={() =>
                          setSelectedTargetPreview(String(defaultTargetOption.option_id))
                        }
                      >
                        <span className="target-structure-badge">Recommended · selected</span>
                        <strong>
                          {String(defaultTargetOption.label || defaultTargetOption.option_id)}
                        </strong>
                        <span>
                          {String(defaultTargetOption.description || 'Verified candidate')}
                        </span>
                      </button>
                    )}
                    <p className="target-selection-note">
                      The structure and chain are already selected. Approve the target to continue;
                      use Change structure only if you want to replace this recommendation.
                    </p>
                    {!!alternativeTargetOptions.length && (
                      <details className="target-alternatives">
                        <summary>View alternatives ({alternativeTargetOptions.length})</summary>
                        <p>Previewing an alternative does not change the Gate 1 selection.</p>
                        <div className="target-alternative-list">
                          {alternativeTargetOptions.map((candidate) => (
                            <button
                              type="button"
                              className="target-structure-card"
                              key={String(candidate.option_id)}
                              aria-label={`Preview alternative structure ${String(candidate.label || candidate.option_id)}`}
                              aria-pressed={String(candidate.option_id) === activeTargetPreview}
                              disabled={!candidate.preview_artifact}
                              onClick={() => setSelectedTargetPreview(String(candidate.option_id))}
                            >
                              <strong>{String(candidate.label || candidate.option_id)}</strong>
                              <span>{String(candidate.description || 'Verified candidate')}</span>
                            </button>
                          ))}
                        </div>
                      </details>
                    )}
                  </div>
                )}
                <div className="quiet-note">
                  <Check size={14} />
                  <p>Review the target and its evidence before moving to site comparison.</p>
                </div>
              </>
            ) : (
              <>
                <div className="section-label">
                  <h3>Candidate sites</h3>
                  <span>Relative recommendation</span>
                </div>
                <div className="site-tabs" role="group" aria-label="Candidate sites">
                  {c.sites.map((s) => (
                    <button
                      key={s.id}
                      aria-pressed={s.id === site?.id}
                      onClick={() => onSite(s.id)}
                    >
                      <span className={`site-swatch site-${s.rank}`} />
                      Site {s.rank}
                      {s.rank === 'A' && <span className="recommend-star">✧</span>}
                    </button>
                  ))}
                </div>
                {site && (
                  <>
                    <div className="selected-site-heading">
                      <strong>Site {site.rank}</strong>
                      <span className="recommendation">
                        {!site.selectable
                          ? 'Blocked'
                          : site.rank === 'A'
                            ? 'Recommended'
                            : site.rank === 'B'
                              ? 'Alternative'
                              : 'Exploratory'}
                      </span>
                    </div>
                    <p className="site-rationale">{site.why_ranked}</p>
                    <div className="definition-list">
                      <div>
                        <span>Confidence</span>
                        <strong>{site.confidence || 'Not assessed'}</strong>
                      </div>
                      <div>
                        <span>Candidate</span>
                        <strong>{site.name}</strong>
                      </div>
                    </div>
                    <div className="residues">
                      <span className="eyebrow">HOTSPOT RESIDUES</span>
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
                    {details('Risks', site.risks)}
                    {details('Uncertainties', site.uncertainty)}
                  </>
                )}
                {compare && (
                  <div className="comparison-table">
                    <h3>Compare candidate sites</h3>
                    <table>
                      <thead>
                        <tr>
                          <th>Site</th>
                          <th>Confidence</th>
                          <th>Recommendation</th>
                        </tr>
                      </thead>
                      <tbody>
                        {c.sites.map((s) => (
                          <tr key={s.id} className={s.id === siteId ? 'selected' : ''}>
                            <th>Site {s.rank}</th>
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
                      ? 'This saved project contains an approved hotspot; the earlier candidate portfolio is unavailable.'
                      : 'Candidate sites will appear when the research is ready.'}
                  </p>
                )}
              </>
            )}
          </>
        )}
        {phase === 'design' && (
          <>
            <div className="context-title">
              <h2>A deliberate first pilot</h2>
              <p>
                {c.arms.length} complementary design{' '}
                {c.arms.length === 1 ? 'approach' : 'approaches'}.
              </p>
            </div>
            <div className="approved-site">
              <span className="small-check">
                <Check size={13} />
              </span>
              <div>
                <span className="eyebrow">APPROVED SITE</span>
                <strong>
                  {c.approved_site?.selected_rank
                    ? `Site ${c.approved_site.selected_rank}`
                    : 'See approved hotspot'}
                </strong>
              </div>
              <span>{c.target_id}</span>
            </div>
            <div className="scaffold-card">
              <Dna size={34} strokeWidth={1.2} />
              <span className="eyebrow">BINDER SCAFFOLD</span>
              <h3>Design strategy</h3>
              <p>{c.design_approved ? 'Approved design' : 'Ready for scientific review'}</p>
            </div>
            <div className="section-label">
              <h3>Design arms</h3>
              <span>{c.arms.length} arms</span>
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
              <summary>Design files</summary>
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
        {phase === 'scale' && (
          <>
            <div className="context-title">
              <h2>A broader view of the possibilities</h2>
              <p>Review progress across the approved design arms.</p>
            </div>
            <div className="scale-counter">
              <strong>
                {completedBatches}
                <span> / {batches || '—'}</span>
              </strong>
              <span>batches complete</span>
            </div>
            <div
              className="scale-progress"
              role="progressbar"
              aria-label="Scale progress"
              aria-valuenow={completedBatches}
              aria-valuemax={batches || 1}
            >
              <span style={{ width: `${batches ? (completedBatches / batches) * 100 : 0}%` }} />
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
                      <strong>{j.status}</strong>
                      <span>{j.resumable ? 'Available to resume' : 'Scale batch'}</span>
                    </div>
                  </div>
                ))}
            </div>
            <div className="scale-legend">
              <span>
                <i className="pass" />
                {v.candidates.counts.pass || 0} pass
              </span>
              <span>
                <i className="filtered" />
                {v.candidates.counts.fail || 0} filtered
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
                    ? 'Small pilot, clear comparison'
                    : v.project.status === 'complete'
                      ? 'Your finalized panel'
                      : 'Your candidates to explore'}
                </h2>
                <span className="count-label">{v.candidates.total}</span>
              </div>
              <p>Compare the evidence and explore each candidate.</p>
            </div>
            <div className="pass-summary">
              <strong>
                {v.candidates.counts.pass || 0} of {v.candidates.total} pass
                <span>
                  {v.candidates.counts.fail || 0} filtered · {v.candidates.counts.incomplete || 0}{' '}
                  incomplete
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
            {selected && (
              <>
                <div className="candidate-view-header">
                  <strong>{selected.backend_id || selected.id}</strong>
                  <span>{selected.panel_role || selected.scaffold}</span>
                  <div>
                    <button
                      aria-label="Previous candidate"
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
                      aria-label="Next candidate"
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
                    <span>Binder sequence · {selected.sequence.length} aa</span>
                    <code>{selected.sequence}</code>
                  </div>
                )}
                <details className="evidence-details">
                  <summary>All measurements & evidence</summary>
                  <table className="metric-table">
                    <tbody>
                      {selected.metrics.map((m) => (
                        <tr key={m.id}>
                          <th>{m.label}</th>
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
              <h3>{phase === 'pilot' ? 'Pilot candidates' : 'Candidate panel'}</h3>
              <span>Native evidence</span>
            </div>
            <div className="finalists-grid">
              {entries.map((ca) => (
                <div
                  className={`finalist-card ${selected?.id === ca.id ? 'selected' : ''}`}
                  key={ca.id}
                >
                  <button
                    className="candidate-select live-candidate-select"
                    aria-label={`Select ${ca.backend_id || ca.id} ${ca.scaffold || ''}`}
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
                          {m.label} <b>{metricValue(m.value)}</b>
                        </span>
                      ))}
                    </span>
                  </button>
                </div>
              ))}
            </div>
            {state.candidates.total > state.candidates.limit && (
              <div className="live-pager">
                <button
                  disabled={!state.candidates.offset}
                  onClick={() =>
                    void adapter.candidatePage(state.candidates.offset - state.candidates.limit)
                  }
                >
                  Previous
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
                  onClick={() =>
                    void adapter.candidatePage(state.candidates.offset + state.candidates.limit)
                  }
                >
                  Next
                </button>
              </div>
            )}
          </>
        )}
        {v.project.validation_only && (
          <p className="scientific-disclaimer">Validation only · not authorized for experiment</p>
        )}
        {v.decision?.details_url && (
          <a className="artifact-download" href={v.decision.details_url} download>
            Complete scientific review <ArrowDownToLine size={13} />
          </a>
        )}
      </div>
    </aside>
  );
}
