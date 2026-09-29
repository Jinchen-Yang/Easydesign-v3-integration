import { useTranslation } from 'react-i18next';
import { useInputDraft } from '../../data/useInputDraft';
import { ArrowRight, FolderOpen, Pencil, Plus, Search, Trash2 } from 'lucide-react';
import {
  PHASES,
  type DesignProject,
  type WorkbenchSnapshot,
} from '../../adapters/WorkbenchAdapter';
import { DemoBadge } from '../../components/DemoBadge';

const labels: Record<DesignProject['status'], string> = {
  'not-started': 'Not started',
  running: 'In progress',
  paused: 'Paused',
  review: 'Ready for review',
  complete: 'Completed',
};

export function ProjectsPage({
  snapshot,
  mode = 'demo',
  onNew,
  onOpen,
  onRename,
  onDelete,
  canCreate = true,
  createDisabledReason,
  draftKey,
}: {
  mode?: 'demo' | 'live';
  snapshot: Pick<WorkbenchSnapshot, 'projects'>;
  onNew: () => void;
  onOpen: (id: string) => void;
  onRename?: (project: DesignProject) => void;
  onDelete?: (project: DesignProject) => void;
  /**
   * Mirror of the backend creation right for affordance gating only. When
   * false, creation controls render disabled with the reason instead of a
   * no-op callback; the server remains the authority.
   */
  canCreate?: boolean;
  createDisabledReason?: string;
  draftKey?: string;
}) {
  const { t } = useTranslation('pro');
  const { value: query, setValue: setQuery } = useInputDraft(draftKey ?? null, '');
  const projects = snapshot.projects.filter((project) =>
    `${project.title} ${project.goal}`.toLowerCase().includes(query.trim().toLowerCase()),
  );
  const createTitle = canCreate ? undefined : createDisabledReason;
  return (
    <main className="platform-page" aria-label={t('Projects')}>
      <header className="platform-header">
        <span>{t('Research, thoughtfully organized.')}</span>
        <DemoBadge mode={mode} />
      </header>
      <div className="platform-content">
        <div className="platform-title-row">
          <div>
            <span className="eyebrow">{t('YOUR RESEARCH')}</span>
            <h1>{t('Projects')}</h1>
            <p>{t('A space for every question. A clear path to your next candidate.')}</p>
          </div>
          <button
            className="primary-button"
            onClick={onNew}
            disabled={!canCreate}
            title={createTitle}
          >
            <Plus size={16} /> {t('New project')}
          </button>
        </div>
        {!canCreate && createDisabledReason && (
          <p className="platform-create-note" role="note">
            {createDisabledReason}
          </p>
        )}
        {snapshot.projects.length === 0 ? (
          <section className="platform-empty first-project">
            <span className="empty-orbit">
              <FolderOpen size={28} />
            </span>
            <h2>{t('Give your next idea a home.')}</h2>
            <p>
              {t(
                'Keep your research goal, agent conversation and scientific context together in one project.',
              )}
            </p>
            <button
              className="text-button"
              onClick={onNew}
              disabled={!canCreate}
              title={createTitle}
            >
              {t('Create your first project')}
              <ArrowRight size={15} />
            </button>
            <small>
              {!canCreate && createDisabledReason
                ? createDisabledReason
                : mode === 'demo'
                  ? t('Start with the guided lysozyme / VHH demo.')
                  : t('Start with a target and your research goal.')}
            </small>
          </section>
        ) : (
          <>
            <div className="project-list-toolbar">
              <span>
                {t(snapshot.projects.length === 1 ? '{{count}} project' : '{{count}} projects', {
                  count: snapshot.projects.length,
                })}{' '}
                <i /> {mode === 'demo' ? t('Saved on this device') : t('Saved in your workspace')}
              </span>
              <label className="project-search">
                <Search size={15} />
                <input
                  aria-label={t('Search projects')}
                  placeholder={t('Search projects…')}
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                />
              </label>
            </div>
            <div className="project-card-grid">
              {projects.map((project) => (
                <article className="project-card" data-testid="design-project" key={project.id}>
                  <div className="project-card-top">
                    <div className="project-card-tools">
                      <span className="project-folder">
                        <FolderOpen size={20} />
                      </span>
                      {onDelete && (
                        <button
                          className="icon-button project-delete"
                          title={t('Delete project')}
                          aria-label={t('Delete project {{name}}', {
                            name: project.title,
                          })}
                          onClick={() => onDelete(project)}
                        >
                          <Trash2 size={16} />
                        </button>
                      )}
                    </div>
                    <span className={`project-status status-${project.status}`}>
                      <i />
                      {t(labels[project.status])}
                    </span>
                  </div>
                  <h2>{project.title}</h2>
                  <p className="project-card-goal">{project.goal}</p>
                  <div
                    className="project-journey"
                    aria-label={t('{{phase}} stage', {
                      phase: t(project.phase[0].toUpperCase() + project.phase.slice(1)),
                    })}
                  >
                    {PHASES.map((phase, index) => (
                      <span
                        title={t(phase[0].toUpperCase() + phase.slice(1))}
                        key={phase}
                        className={
                          project.status === 'complete' || index <= PHASES.indexOf(project.phase)
                            ? 'reached'
                            : ''
                        }
                      />
                    ))}
                  </div>
                  <div className="project-card-stage">
                    <span>{t('Current stage')}</span>
                    <strong>{t(project.phase[0].toUpperCase() + project.phase.slice(1))}</strong>
                  </div>
                  <footer>
                    {onRename && (
                      <button
                        className="icon-button"
                        aria-label={t('Rename project {{name}}', {
                          name: project.title,
                        })}
                        title={t('Rename project')}
                        onClick={() => onRename(project)}
                      >
                        <Pencil size={15} />
                      </button>
                    )}
                    <button
                      className="text-button"
                      aria-label={t('Open project {{name}}', {
                        name: project.title,
                      })}
                      onClick={() => onOpen(project.id)}
                    >
                      {t('Open workspace')}
                      <ArrowRight size={14} />
                    </button>
                  </footer>
                </article>
              ))}
            </div>
            {projects.length === 0 && (
              <div className="platform-empty">
                <Search size={26} />
                <h2>{t('No matching projects')}</h2>
                <p>{t('Try a different name or research goal.')}</p>
                <button className="text-button" onClick={() => setQuery('')}>
                  {t('Clear search')}
                </button>
              </div>
            )}
          </>
        )}
        <p className="platform-footnote">
          {t('Your conversations, decisions and results stay with their project.')}
        </p>
      </div>
    </main>
  );
}
