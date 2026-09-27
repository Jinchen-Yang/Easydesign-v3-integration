import { useState } from 'react';
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
}) {
  const [query, setQuery] = useState('');
  const projects = snapshot.projects.filter((project) =>
    `${project.title} ${project.goal}`.toLowerCase().includes(query.trim().toLowerCase()),
  );
  const createTitle = canCreate ? undefined : createDisabledReason;
  return (
    <main className="platform-page" aria-label="Projects">
      <header className="platform-header">
        <span>Research, thoughtfully organized.</span>
        <DemoBadge mode={mode} />
      </header>
      <div className="platform-content">
        <div className="platform-title-row">
          <div>
            <span className="eyebrow">YOUR RESEARCH</span>
            <h1>Projects</h1>
            <p>A space for every question. A clear path to your next candidate.</p>
          </div>
          <button className="primary-button" onClick={onNew} disabled={!canCreate} title={createTitle}>
            <Plus size={16} /> New project
          </button>
        </div>
        {!canCreate && createDisabledReason && (
          <p className="platform-create-note" role="note">{createDisabledReason}</p>
        )}
        {snapshot.projects.length === 0 ? (
          <section className="platform-empty first-project">
            <span className="empty-orbit">
              <FolderOpen size={28} />
            </span>
            <h2>Give your next idea a home.</h2>
            <p>
              Keep your research goal, agent conversation and scientific context together in one
              project.
            </p>
            <button
              className="text-button"
              onClick={onNew}
              disabled={!canCreate}
              title={createTitle}
            >
              Create your first project <ArrowRight size={15} />
            </button>
            <small>
              {!canCreate && createDisabledReason
                ? createDisabledReason
                : mode === 'demo'
                  ? 'Start with the guided lysozyme / VHH demo.'
                  : 'Start with a target and your research goal.'}
            </small>
          </section>
        ) : (
          <>
            <div className="project-list-toolbar">
              <span>
                {snapshot.projects.length} {snapshot.projects.length === 1 ? 'project' : 'projects'}{' '}
                <i /> {mode === 'demo' ? 'Saved on this device' : 'Saved in your workspace'}
              </span>
              <label className="project-search">
                <Search size={15} />
                <input
                  aria-label="Search projects"
                  placeholder="Search projects…"
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
                          title="Delete project"
                          aria-label={`Delete project ${project.title}`}
                          onClick={() => onDelete(project)}
                        >
                          <Trash2 size={16} />
                        </button>
                      )}
                    </div>
                    <span className={`project-status status-${project.status}`}>
                      <i />
                      {labels[project.status]}
                    </span>
                  </div>
                  <h2>{project.title}</h2>
                  <p className="project-card-goal">{project.goal}</p>
                  <div className="project-journey" aria-label={`${project.phase} stage`}>
                    {PHASES.map((phase, index) => (
                      <span
                        title={phase}
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
                    <span>Current stage</span>
                    <strong>{project.phase}</strong>
                  </div>
                  <footer>
                    {onRename && (
                      <button
                        className="icon-button"
                        aria-label={`Rename project ${project.title}`}
                        title="Rename project"
                        onClick={() => onRename(project)}
                      >
                        <Pencil size={15} />
                      </button>
                    )}
                    <button
                      className="text-button"
                      aria-label={`Open project ${project.title}`}
                      onClick={() => onOpen(project.id)}
                    >
                      Open workspace <ArrowRight size={14} />
                    </button>
                  </footer>
                </article>
              ))}
            </div>
            {projects.length === 0 && (
              <div className="platform-empty">
                <Search size={26} />
                <h2>No matching projects</h2>
                <p>Try a different name or research goal.</p>
                <button className="text-button" onClick={() => setQuery('')}>
                  Clear search
                </button>
              </div>
            )}
          </>
        )}
        <p className="platform-footnote">
          Your conversations, decisions and results stay with their project.
        </p>
      </div>
    </main>
  );
}
