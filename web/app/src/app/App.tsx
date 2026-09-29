import { useEffect, useRef, useState } from 'react';
import {
  ArrowRight,
  ArrowUp,
  Atom,
  ChevronRight,
  FlaskConical,
  PanelLeft,
  PanelRight,
  RotateCcw,
  Sparkles,
  Trash2,
  X,
} from 'lucide-react';
import type {
  WorkbenchAdapter,
  DesignProject,
  WorkbenchEdit,
  WorkbenchSnapshot,
  WorkflowPhase,
} from '../adapters/WorkbenchAdapter';
import { Brand } from '../components/Brand';
import { DemoBadge } from '../components/DemoBadge';
import { Workflow } from '../features/workflow/Workflow';
import { ProjectSidebar, type WorkbenchPage } from '../features/projects/ProjectSidebar';
import { ProjectsPage } from '../features/projects/ProjectsPage';
import { ComputePage } from '../features/compute/ComputePage';
import { useWorkbenchPage } from './navigation';
import { Conversation } from '../features/conversation/Conversation';
import { ScientificContext } from '../features/context/ScientificContext';
import { DecisionBar } from '../features/decisions/DecisionBar';
import { LabOrderPage } from '../features/lab-order/LabOrderPage';
import { createLabOrderDraft, type LabOrderStep } from '../domain/labOrder';

export function Modal({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: React.ReactNode;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    ref.current?.querySelector<HTMLElement>('button,input,textarea')?.focus();
    return () => previous?.focus();
  }, []);
  return (
    <div
      className="modal-scrim"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        ref={ref}
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onKeyDown={(e) => {
          if (e.key === 'Escape') onClose();
          if (e.key === 'Tab') {
            const nodes = [
              ...(ref.current?.querySelectorAll<HTMLElement>(
                'button:not(:disabled), input, textarea, select, a[href]',
              ) ?? []),
            ];
            const first = nodes[0],
              last = nodes.at(-1);
            if (e.shiftKey && document.activeElement === first) {
              e.preventDefault();
              last?.focus();
            } else if (!e.shiftKey && document.activeElement === last) {
              e.preventDefault();
              first?.focus();
            }
          }
        }}
      >
        <header>
          <h2>{title}</h2>
          <button className="icon-button" aria-label="Close dialog" onClick={onClose}>
            <X size={18} />
          </button>
        </header>
        {children}
      </div>
    </div>
  );
}

export function Landing({
  snapshot,
  onStart,
  onResume,
  newDesign,
  focusInput,
  mode = 'demo',
  attachment,
  canStart = true,
}: {
  snapshot: Pick<WorkbenchSnapshot, 'started' | 'completed' | 'phase'> & {
    project: Pick<WorkbenchSnapshot['project'], 'exampleGoal' | 'title'>;
  };
  mode?: 'demo' | 'live';
  attachment?: React.ReactNode;
  canStart?: boolean;
  onStart: (goal: string) => void;
  onResume: () => void;
  newDesign: boolean;
  focusInput: boolean;
}) {
  const [goal, setGoal] = useState(newDesign ? '' : snapshot.project.exampleGoal);
  return (
    <main className="landing">
      <header className="landing-header">
        <span>Research, thoughtfully designed.</span>
        <DemoBadge mode={mode} />
      </header>
      <div className="landing-center">
        <Brand />
        <h1>{newDesign ? 'Start a new design' : 'What would you like to design?'}</h1>
        <p className="landing-subtitle">
          Start with a question. Build a clear path to your next candidate.
        </p>
        <form
          className="goal-composer"
          onSubmit={(e) => {
            e.preventDefault();
            if (canStart && goal.trim()) onStart(goal);
          }}
        >
          <label htmlFor="research-goal" className="sr-only">
            Your research goal
          </label>
          <textarea
            id="research-goal"
            autoFocus={focusInput}
            value={goal}
            maxLength={mode === 'demo' ? 2000 : 1500}
            rows={3}
            onChange={(e) => setGoal(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                if (canStart && goal.trim()) onStart(goal);
              }
            }}
            placeholder="Describe the target, binder and outcome you have in mind…"
          />
          <div>
            <span>
              <Atom size={15} /> Protein design
            </span>
            {attachment}
            <button
              className="landing-submit"
              aria-label="Start design"
              disabled={!canStart || !goal.trim()}
            >
              <ArrowUp size={21} />
            </button>
          </div>
        </form>
        <div className="example-prompts">
          <button onClick={() => setGoal(snapshot.project.exampleGoal)}>
            <FlaskConical size={14} /> Lysozyme · VHH <ArrowRight size={12} />
          </button>
          <button
            onClick={() =>
              setGoal(
                mode === 'demo'
                  ? 'Compare three accessible binding sites on hen egg-white lysozyme with a VHH demo.'
                  : 'Compare three candidate binding sites on hen egg-white lysozyme for VHH design.',
              )
            }
          >
            <Atom size={14} /> Compare binding sites <ArrowRight size={12} />
          </button>
          <button
            onClick={() =>
              setGoal(
                mode === 'demo'
                  ? 'Explore a small two-arm VHH pilot against lysozyme, then review six demo finalists.'
                  : 'Explore a small two-arm VHH pilot against lysozyme, then review the candidate evidence.',
              )
            }
          >
            <Sparkles size={14} /> Explore a small pilot <ArrowRight size={12} />
          </button>
        </div>
        <p className="landing-demo-note">
          {mode === 'demo'
            ? 'A guided lysozyme / VHH demo. Simulated results, real interaction.'
            : 'Describe your goal and optionally attach a target structure to begin.'}
        </p>
        {snapshot.started && (
          <button className="resume-design" onClick={onResume}>
            <span>
              <strong>Continue {snapshot.project.title}</strong>
              <small>
                {snapshot.completed ? 'Panel finalized' : `${snapshot.phase} review`} · Progress
                saved
              </small>
            </span>
            <ArrowRight size={16} />
          </button>
        )}
      </div>
      <footer className="landing-footer">
        <span>
          GOAL <ChevronRight size={10} /> TARGET <ChevronRight size={10} /> SITE{' '}
          <ChevronRight size={10} /> DESIGN <ChevronRight size={10} /> PILOT{' '}
          <ChevronRight size={10} /> SCALE <ChevronRight size={10} /> CANDIDATES
        </span>
        <small>You stay in control at each decision.</small>
      </footer>
    </main>
  );
}

export function App({ adapter }: { adapter: WorkbenchAdapter }) {
  const [snapshot, setSnapshot] = useState<WorkbenchSnapshot>();
  const [screen, setScreen] = useWorkbenchPage();
  const [newDesign, setNewDesign] = useState(false);
  const [projectsOpen, setProjectsOpen] = useState(
    () => window.matchMedia('(min-width: 1101px)').matches,
  );
  const [renamingProject, setRenamingProject] = useState<string | null>(null);
  const [deletingProject, setDeletingProject] = useState<DesignProject | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState('');
  const closeProjectsOnNarrowScreen = () => {
    if (window.matchMedia('(max-width: 1100px)').matches) setProjectsOpen(false);
  };
  // Remount the local composer when starting a fresh draft, even if already on Landing.
  const [draftRevision, setDraftRevision] = useState(0);
  const [viewedPhase, setViewedPhase] = useState<WorkflowPhase | 'lab-order'>('goal');
  const [contextRevealRequest, setContextRevealRequest] = useState(0);
  const contextTrigger = useRef<HTMLElement | null>(null);
  const contextToggle = useRef<HTMLButtonElement>(null);
  const [compare, setCompare] = useState(false),
    [contextOpen, setContextOpen] = useState(false),
    [workflowOpen, setWorkflowOpen] = useState(false);
  const [modal, setModal] = useState<'help' | 'edit' | 'rename' | 'delete' | null>(null),
    [draft, setDraft] = useState(''),
    [error, setError] = useState('');
  useEffect(() => {
    let active = true;
    const unsub = adapter.subscribe((e) => {
      if (active) setSnapshot(e.snapshot);
    });
    adapter
      .load()
      .then((s) => {
        if (active) {
          setSnapshot(s);
        }
      })
      .catch((e: Error) => setError(e.message));
    return () => {
      active = false;
      unsub();
      adapter.dispose();
    };
  }, [adapter]);
  useEffect(() => {
    if (snapshot) {
      setViewedPhase(snapshot.completed && snapshot.labOrder ? 'lab-order' : snapshot.phase);
      setCompare(false);
    }
  }, [snapshot?.phase, snapshot?.project.id, snapshot?.completed]);
  const act = (task: Promise<void>) => {
    setError('');
    void task.catch((e: Error) => setError(e.message));
  };
  const openHome = (freshDraft = false) => {
    setModal(null);
    setContextOpen(false);
    setWorkflowOpen(false);
    setCompare(false);
    setScreen('workspace');
    closeProjectsOnNarrowScreen();
    setNewDesign(freshDraft);
    setDraftRevision((revision) => revision + 1);
  };
  const reset = () => {
    openHome();
    act(adapter.resetDemo());
  };
  const startDesign = (goal: string) => {
    act(
      (async () => {
        // New goals create independent projects; Reset can restart only the selected project.
        if (snapshot?.project.id && !snapshot.started && !newDesign)
          await adapter.sendMessage(goal);
        else await adapter.createProject(goal);
        setNewDesign(false);
        closeProjectsOnNarrowScreen();
        setScreen('workspace');
      })(),
    );
  };
  const focus = (phase: WorkflowPhase) => {
    if (snapshot?.tasks.find((t) => t.id === phase)?.status === 'locked') return;
    contextTrigger.current = document.activeElement as HTMLElement | null;
    setViewedPhase(phase);
    setWorkflowOpen(false);
    setContextOpen(true);
    // Even a second click on the current phase must reveal and focus its context.
    setContextRevealRequest((request) => request + 1);
  };
  const openLabOrder = (step?: LabOrderStep) => {
    if (!snapshot?.completed) return;
    const draft =
      snapshot.labOrder ??
      createLabOrderDraft(
        snapshot.context.finalists.map((candidate) => candidate.id),
        snapshot.context.shortlisted,
      );
    act(
      (async () => {
        await adapter.saveLabOrder({ ...draft, step: step ?? draft.step });
        setViewedPhase('lab-order');
        setWorkflowOpen(false);
        setContextOpen(false);
      })(),
    );
  };
  const closeContext = () => {
    setContextOpen(false);
    const trigger = contextTrigger.current;
    (trigger?.isConnected ? trigger : contextToggle.current)?.focus({ preventScroll: true });
  };
  const edit = (payload: WorkbenchEdit) => {
    if (snapshot) act(adapter.edit(snapshot.decision?.id ?? '', payload));
  };
  const navigate = (page: WorkbenchPage) => {
    setNewDesign(false);
    setModal(null);
    setScreen(page);
    setContextOpen(false);
    setWorkflowOpen(false);
    closeProjectsOnNarrowScreen();
  };
  const selectProject = (id: string) =>
    act(
      (async () => {
        await adapter.selectProject(id);
        const selected = await adapter.load();
        setViewedPhase(selected.completed && selected.labOrder ? 'lab-order' : selected.phase);
        setNewDesign(false);
        setDraftRevision((revision) => revision + 1);
        setWorkflowOpen(false);
        setContextOpen(false);
        setCompare(false);
        setScreen('workspace');
        closeProjectsOnNarrowScreen();
      })(),
    );
  if (!snapshot)
    return (
      <div className="app-loading">
        <Brand />
        <p>{error || 'Opening your research workspace…'}</p>
      </div>
    );
  const inWorkbench = snapshot.started && screen === 'workspace' && !newDesign;
  return (
    <div
      className={`app ${inWorkbench ? 'in-workbench' : ''} ${projectsOpen ? 'projects-expanded' : ''}`}
    >
      <ProjectSidebar
        expanded={projectsOpen}
        page={screen}
        onToggle={() => setProjectsOpen((open) => !open)}
        onClose={() => setProjectsOpen(false)}
        onNavigate={navigate}
        onHelp={() => setModal('help')}
      />
      {screen === 'projects' ? (
        <ProjectsPage
          snapshot={snapshot}
          onNew={() => openHome(true)}
          onOpen={selectProject}
          onRename={(project) => {
            setRenamingProject(project.id);
            setDraft(project.title);
            setModal('rename');
          }}
          onDelete={(project) => {
            setDeletingProject(project);
            setDeleteError('');
            setModal('delete');
          }}
        />
      ) : screen === 'compute' ? (
        <ComputePage snapshot={snapshot} onOpen={selectProject} />
      ) : !inWorkbench ? (
        <Landing
          key={draftRevision}
          snapshot={snapshot}
          newDesign={newDesign}
          focusInput={draftRevision > 0}
          onStart={startDesign}
          onResume={() => {
            setViewedPhase(snapshot.completed && snapshot.labOrder ? 'lab-order' : snapshot.phase);
            setNewDesign(false);
            setScreen('workspace');
          }}
        />
      ) : (
        <div className="workspace">
          <header className="workspace-header">
            <button
              className="mobile-workflow icon-button"
              aria-label="Toggle workflow"
              onClick={() => setWorkflowOpen(!workflowOpen)}
            >
              <PanelLeft size={18} />
            </button>
            <div className="project-breadcrumb">
              <span>Agent Workspace</span>
              <ChevronRight size={13} />
              <select
                aria-label="Current project"
                value={snapshot.project.id ?? ''}
                onChange={(e) => selectProject(e.target.value)}
              >
                {snapshot.projects.map((project) => (
                  <option key={project.id} value={project.id}>
                    {project.title}
                  </option>
                ))}
              </select>
            </div>
            <span className="save-indicator">
              <span /> {snapshot.busy ? 'Demo running' : 'Local demo'}
            </span>
            <div className="header-actions">
              <DemoBadge />
              <button className="header-button" onClick={() => act(adapter.replayDemo())}>
                <RotateCcw size={13} /> Replay demo
              </button>
              <button className="header-button reset-button" onClick={reset}>
                Reset
              </button>
              {viewedPhase !== 'lab-order' && (
                <button
                  ref={contextToggle}
                  className="mobile-context icon-button"
                  aria-label="Open scientific context"
                  aria-controls="scientific-context"
                  aria-expanded={contextOpen}
                  onClick={() => (contextOpen ? closeContext() : focus(viewedPhase))}
                >
                  <PanelRight size={17} />
                </button>
              )}
            </div>
          </header>
          <div
            className={`workbench-grid ${contextOpen ? 'context-open' : ''} ${workflowOpen ? 'workflow-open' : ''}`}
          >
            <Workflow
              snapshot={snapshot}
              viewedPhase={viewedPhase}
              onView={focus}
              onLabOrder={openLabOrder}
            />
            {viewedPhase === 'lab-order' && snapshot.labOrder ? (
              <LabOrderPage
                key={`lab:${snapshot.project.id}`}
                draft={snapshot.labOrder}
                candidates={snapshot.context.finalists}
                onChange={(draft) => act(adapter.saveLabOrder(draft))}
              />
            ) : (
              <div className="research-main">
                <Conversation
                  key={`conversation:${snapshot.project.id}`}
                  snapshot={snapshot}
                  viewedPhase={viewedPhase === 'lab-order' ? snapshot.phase : viewedPhase}
                  onFocus={focus}
                  onSend={(text) => {
                    setViewedPhase(snapshot.phase);
                    act(adapter.sendMessage(text));
                  }}
                  onSkip={() => act(adapter.skipAnimation())}
                />
                <ScientificContext
                  key={`context:${snapshot.project.id}`}
                  snapshot={snapshot}
                  phase={viewedPhase === 'lab-order' ? snapshot.phase : viewedPhase}
                  revealRequest={contextRevealRequest}
                  compare={compare}
                  onEdit={edit}
                  onClose={closeContext}
                />
                <DecisionBar
                  snapshot={snapshot}
                  onApprove={() => {
                    setViewedPhase(snapshot.phase);
                    act(adapter.approve(snapshot.decision!.id));
                  }}
                  onCompare={() => {
                    setCompare(!compare);
                    focus(snapshot.phase);
                  }}
                  onEdit={() => {
                    setDraft(
                      snapshot.phase === 'site'
                        ? snapshot.context.selectedSite
                        : snapshot.context.scaffold,
                    );
                    setModal('edit');
                  }}
                  onRevise={() => edit({ type: 'revise-pilot' })}
                  onReplay={() => act(adapter.replayDemo())}
                  onLabOrder={() => openLabOrder()}
                />
              </div>
            )}
          </div>
        </div>
      )}
      {(error || snapshot.notice) && (
        <div className="toast" role="alert">
          <span>{error || snapshot.notice}</span>
          {error && (
            <button aria-label="Dismiss message" onClick={() => setError('')}>
              <X size={14} />
            </button>
          )}
        </div>
      )}
      {modal === 'delete' && deletingProject && (
        <Modal
          title="Delete project?"
          onClose={() => {
            if (!deleting) setModal(null);
          }}
        >
          <p>
            Delete <strong>{deletingProject.title}</strong> from this device? Its conversation, demo
            results and lab draft will be removed. This cannot be undone.
          </p>
          <p className="delete-scope">Server files and running GPU jobs are unaffected.</p>
          {deleteError && <p role="alert">{deleteError}</p>}
          <div className="modal-actions">
            <button className="secondary-button" disabled={deleting} onClick={() => setModal(null)}>
              Cancel
            </button>
            <button
              className="primary-button delete-confirm"
              disabled={deleting}
              onClick={async () => {
                setDeleting(true);
                try {
                  await adapter.deleteProject(deletingProject.id);
                  setModal(null);
                  setDeletingProject(null);
                } catch (e) {
                  setDeleteError(e instanceof Error ? e.message : 'Could not delete project.');
                } finally {
                  setDeleting(false);
                }
              }}
            >
              <Trash2 size={15} />
              {deleting ? 'Deleting…' : 'Delete project'}
            </button>
          </div>
        </Modal>
      )}
      {modal === 'rename' && (
        <Modal title="Rename project" onClose={() => setModal(null)}>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (renamingProject && draft.trim()) {
                act(adapter.renameProject(renamingProject, draft));
                setModal(null);
              }
            }}
          >
            <label className="form-label">
              Project name
              <input
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                maxLength={80}
                required
              />
            </label>
            <div className="modal-actions">
              <button type="button" className="secondary-button" onClick={() => setModal(null)}>
                Cancel
              </button>
              <button className="primary-button" disabled={!draft.trim()}>
                Save name <ArrowRight size={14} />
              </button>
            </div>
          </form>
        </Modal>
      )}
      {modal === 'help' && (
        <Modal title="A clear path through protein design" onClose={() => setModal(null)}>
          <p>
            EasyDesign helps you move from a research goal to a candidate panel, with a scientist
            conversation and the relevant context side by side.
          </p>
          <div className="modal-demo">
            <DemoBadge />
            <p>
              This standalone prototype uses fixed lysozyme/VHH data: 8 pilot candidates, 24 in
              scale, and 6 finalists. No model or scientific job is called. Compute & Queue can
              separately display read-only live GPU metrics when configured.
            </p>
          </div>
          <p>
            The molecule is the public PDB 1MEL reference. Site scores, candidate scores and
            outcomes are simulated. Conversation shows concise research summaries and tool events
            only.
          </p>
          <button className="primary-button" onClick={() => navigate('workspace')}>
            Explore the workbench <ArrowRight size={14} />
          </button>
        </Modal>
      )}
      {modal === 'edit' && (
        <Modal
          title={snapshot.phase === 'site' ? 'Choose a demo site' : 'Edit the design plan'}
          onClose={() => setModal(null)}
        >
          <p>
            {snapshot.phase === 'site'
              ? 'Select the site you want both design arms to explore. Residue groups are fixed demo fixtures.'
              : 'Give your scaffold a useful label. The demo keeps two arms and a fixed 4 + 4 candidate budget.'}
          </p>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              edit(
                snapshot.phase === 'site'
                  ? { type: 'site', siteId: draft }
                  : { type: 'scaffold', scaffold: draft },
              );
              setModal(null);
            }}
          >
            {snapshot.phase === 'site' ? (
              <fieldset className="edit-sites">
                <legend className="sr-only">Demo site</legend>
                {snapshot.context.sites.map((s) => (
                  <label key={s.id}>
                    <input
                      type="radio"
                      name="site"
                      value={s.id}
                      checked={draft === s.id}
                      onChange={() => setDraft(s.id)}
                    />
                    <strong>{s.label}</strong>
                    <span>{s.residues.join(' · ')}</span>
                    {s.recommended && <small>Recommended</small>}
                  </label>
                ))}
              </fieldset>
            ) : (
              <label className="form-label">
                Scaffold label
                <input
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  maxLength={100}
                  required
                />
              </label>
            )}
            <div className="modal-actions">
              <button type="button" className="secondary-button" onClick={() => setModal(null)}>
                Cancel
              </button>
              <button className="primary-button" disabled={!draft.trim()}>
                Save changes <ArrowRight size={14} />
              </button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
}
