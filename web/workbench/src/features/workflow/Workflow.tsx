import { Check, Circle, LockKeyhole, ArrowUpRight, FlaskConical } from 'lucide-react';
import type { WorkbenchSnapshot, WorkflowPhase } from '../../adapters/WorkbenchAdapter';
import { labProgress, type LabOrderStep } from '../../domain/labOrder';
export function Workflow({
  snapshot,
  mode = 'demo',
  viewedPhase,
  onView,
  onLabOrder,
  agentTasks = [],
  onOpenTasks,
}: {
  mode?: 'demo' | 'live';
  snapshot: Pick<WorkbenchSnapshot, 'tasks' | 'completed' | 'specialists'> &
    Partial<Pick<WorkbenchSnapshot, 'labOrder'>>;
  viewedPhase: WorkflowPhase | 'lab-order';
  onView: (phase: WorkflowPhase) => void;
  onLabOrder: (step?: LabOrderStep) => void;
  agentTasks?: { id: string; title: string; detail: string; status: string }[];
  onOpenTasks?: () => void;
}) {
  const finishedTasks = agentTasks.filter((task) =>
    ['complete', 'completed'].includes(task.status),
  ).length;
  return (
    <aside className="workflow" aria-label="Workflow">
      <div className="workflow-top">
        <span className="eyebrow">WORKFLOW</span>
        <span className="workflow-count">
          {snapshot.completed ? '7' : snapshot.tasks.filter((x) => x.status === 'complete').length}{' '}
          / 8
        </span>
      </div>
      <nav>
        {snapshot.tasks.map((task, i) => (
          <div
            key={task.id}
            className={`workflow-step ${task.id === viewedPhase ? 'viewed' : ''} ${task.status}`}
          >
            <button
              onClick={() => onView(task.id)}
              disabled={task.status === 'locked'}
              aria-current={task.id === viewedPhase ? 'step' : undefined}
              data-testid={`phase-${task.id}`}
            >
              <span className="step-indicator">
                {task.status === 'complete' ? (
                  <Check size={13} />
                ) : task.status === 'locked' ? (
                  <span>{i + 1}</span>
                ) : (
                  <span className="current-dot" />
                )}
              </span>
              <span>{task.label}</span>
              {task.status === 'approval' && (
                <span className="approval-dot" title="Ready for your review" />
              )}
              {task.status === 'locked' && <LockKeyhole className="step-lock" size={11} />}
            </button>
            {task.id === viewedPhase && (
              <div className="subtasks">
                {task.subtasks.map((sub) => (
                  <div key={sub.label} className={sub.status}>
                    {sub.status === 'complete' ? (
                      <Check size={11} />
                    ) : sub.status === 'running' ? (
                      <span className="tiny-loader" />
                    ) : (
                      <Circle size={8} />
                    )}
                    <span>{sub.label}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}
        <div
          className={`workflow-step lab-workflow-step ${viewedPhase === 'lab-order' ? 'viewed' : ''} ${snapshot.completed ? '' : 'locked'}`}
        >
          <button
            onClick={() => onLabOrder()}
            disabled={!snapshot.completed}
            aria-current={viewedPhase === 'lab-order' ? 'step' : undefined}
            data-testid="phase-lab-order"
          >
            <span className="step-indicator" aria-label="Pending submission">
              <Check size={13} />
            </span>
            <span>Lab Order</span>
            {!snapshot.completed && <LockKeyhole className="step-lock" size={11} />}
          </button>
          {viewedPhase === 'lab-order' && snapshot.labOrder && (
            <nav className="lab-subtasks" aria-label="Lab order steps">
              {(['samples', 'requirements', 'review'] as const).map((step, index) => {
                const complete = labProgress(snapshot.labOrder!)[step];
                return (
                  <button
                    key={step}
                    onClick={() => onLabOrder(step)}
                    aria-current={snapshot.labOrder!.step === step ? 'step' : undefined}
                  >
                    <span
                      className={`lab-step-check ${complete ? 'done' : ''}`}
                      aria-label={complete ? 'Complete' : 'Pending'}
                    >
                      <Check size={12} />
                    </span>
                    {['Samples', 'Specs', 'Review'][index]}
                  </button>
                );
              })}
            </nav>
          )}
        </div>
      </nav>
      <div className="agent-tasks">
        <div className="agent-task-heading">
          <span className="eyebrow">AGENT TASKS</span>
          <span>
            {finishedTasks}/{agentTasks.length}
          </span>
        </div>
        {(agentTasks.length
          ? agentTasks.slice(0, 3)
          : snapshot.specialists.map((specialist) => ({
              id: specialist.name,
              title: specialist.name,
              detail: specialist.role,
              status: specialist.status,
            }))
        ).map((task) => (
          <div className="specialist-row" key={task.id}>
            <span className={`specialist-dot ${task.status}`} />
            <div>
              <strong>{task.title}</strong>
              <small>{task.detail}</small>
            </div>
            <span className={`activity-state ${task.status}`}>
              {['complete', 'completed'].includes(task.status) ? (
                <Check size={12} />
              ) : ['running', 'retrying'].includes(task.status) ? (
                <span className="tiny-loader" />
              ) : (
                '—'
              )}
            </span>
          </div>
        ))}
        {!!agentTasks.length && (
          <button className="view-agent-tasks" type="button" onClick={onOpenTasks}>
            View all tasks <ArrowUpRight size={12} />
          </button>
        )}
      </div>
      <div className="workflow-footer">
        <FlaskConical size={15} />
        <div>
          <strong>
            {mode === 'demo' ? 'A guided research demo' : 'A guided research workspace'}
          </strong>
          <p>
            {mode === 'demo' ? 'Simulated results.' : 'Evidence, clearly explained.'}
            <br />
            Your decisions shape the journey.
          </p>
        </div>
        <ArrowUpRight size={12} />
      </div>
    </aside>
  );
}
