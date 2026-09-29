import { useTranslation } from 'react-i18next';
import { useState } from 'react';
import { ArrowRight, Layers } from 'lucide-react';
import type { WorkbenchSnapshot } from '../../adapters/WorkbenchAdapter';
import { LiveResources } from './LiveResources';

export function ComputePage({
  snapshot,
  onOpen,
}: {
  snapshot: WorkbenchSnapshot;
  onOpen: (projectId: string) => void;
}) {
  const { t } = useTranslation('pro');
  const [projectId, setProjectId] = useState('all');
  const [status, setStatus] = useState('all');
  const runs = snapshot.compute.runs.filter(
    (run) =>
      (projectId === 'all' || run.projectId === projectId) &&
      (status === 'all' || run.status === status),
  );
  return (
    <main className="platform-page" aria-label={t('Compute & Queue')}>
      <header className="platform-header">
        <span>{t('A clear view of the work in progress.')}</span>
      </header>
      <div className="platform-content">
        <div className="platform-title-row">
          <div>
            <span className="eyebrow">{t('RESOURCES & ACTIVITY')}</span>
            <h1>{t('Compute & Queue')}</h1>
            <p>{t("Live resources and your project's activity, in one place.")}</p>
          </div>
        </div>
        <LiveResources />
        <div className="run-section-heading">
          <div>
            <h2>{t('Demo runs')}</h2>
            <p>
              {t(
                'Simulated Pilot and Scale activity from your projects. No GPU jobs are submitted.',
              )}
            </p>
          </div>
          <span className="count-label">{snapshot.compute.runs.length}</span>
        </div>
        <div className="run-filters">
          <label>
            {t('Project')}
            <select
              aria-label={t('Filter runs by project')}
              value={projectId}
              onChange={(e) => setProjectId(e.target.value)}
            >
              <option value="all">{t('All projects')}</option>
              {snapshot.projects.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.title}
                </option>
              ))}
            </select>
          </label>
          <label>
            {t('Status')}
            <select
              aria-label={t('Filter runs by status')}
              value={status}
              onChange={(e) => setStatus(e.target.value)}
            >
              <option value="all">{t('All statuses')}</option>
              <option value="running">{t('In progress')}</option>
              <option value="paused">{t('Paused')}</option>
              <option value="complete">{t('Completed')}</option>
            </select>
          </label>
        </div>
        {runs.length ? (
          <div className="runs-table-wrap">
            <table className="runs-table">
              <thead>
                <tr>
                  <th>{t('Run / project')}</th>
                  <th>{t('Status')}</th>
                  <th>{t('Demo results')}</th>
                  <th>
                    <span className="sr-only">{t('Open')}</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {runs.map((run) => (
                  <tr key={run.id} data-testid="demo-run">
                    <td>
                      <strong>
                        {run.phase === 'pilot' ? t('Pilot exploration') : t('Scale exploration')}
                      </strong>
                      <span>{run.projectTitle}</span>
                    </td>
                    <td>
                      <span className={`project-status status-${run.status}`}>
                        <i />
                        {run.status === 'complete'
                          ? t('Completed')
                          : run.status === 'paused'
                            ? t('Paused')
                            : t('In progress')}
                      </span>
                    </td>
                    <td>
                      <strong>
                        {run.prepared} / {run.total}
                      </strong>
                      <span>{t('simulated candidates')}</span>
                    </td>
                    <td>
                      <button
                        className="icon-button"
                        title={t('Open project workspace')}
                        aria-label={t('Open {{phase}} project {{name}}', {
                          phase: t(run.phase === 'pilot' ? 'Pilot' : 'Scale'),
                          name: run.projectTitle,
                        })}
                        onClick={() => onOpen(run.projectId)}
                      >
                        <ArrowRight size={17} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="platform-empty queue-empty">
            <Layers size={27} />
            <h2>
              {snapshot.compute.runs.length
                ? t('No runs match these filters')
                : t('Room for your next run')}
            </h2>
            <p>
              {snapshot.compute.runs.length
                ? t('Choose another project or status to see more activity.')
                : t(
                    'Once you approve a design in Agent Workspace, its simulated pilot will appear here.',
                  )}
            </p>
            {snapshot.compute.runs.length > 0 && (
              <button
                className="text-button"
                onClick={() => {
                  setProjectId('all');
                  setStatus('all');
                }}
              >
                {t('Clear filters')}
              </button>
            )}
          </div>
        )}
        <p className="platform-footnote">
          {t(
            "Demo activity reflects each project's current replay. Approvals remain in Agent Workspace.",
          )}
        </p>
      </div>
    </main>
  );
}
