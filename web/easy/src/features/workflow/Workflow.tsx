import { Check, Circle, LockKeyhole, ArrowUpRight, FlaskConical } from 'lucide-react';
import type { WorkbenchSnapshot, WorkflowPhase } from '../../adapters/WorkbenchAdapter';
import { labProgress, type LabOrderStep } from '../../domain/labOrder';
export function Workflow({
  snapshot,
  viewedPhase,
  onView,
  onLabOrder,
}: {
  snapshot: WorkbenchSnapshot;
  viewedPhase: WorkflowPhase | 'lab-order';
  onView: (phase: WorkflowPhase) => void;
  onLabOrder: (step?: LabOrderStep) => void;
}) {
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
        <span className="eyebrow">AGENT TASKS</span>
        {snapshot.specialists.map((specialist) => (
          <div className="specialist-row" key={specialist.name}>
            <span className={`specialist-dot ${specialist.status}`} />
            <div>
              <strong>{specialist.name}</strong>
              <small>{specialist.role}</small>
            </div>
            <span className={`activity-state ${specialist.status}`}>
              {specialist.status === 'complete' ? (
                <Check size={12} />
              ) : specialist.status === 'running' ? (
                <span className="tiny-loader" />
              ) : (
                '—'
              )}
            </span>
          </div>
        ))}
      </div>
      <div className="workflow-footer">
        <FlaskConical size={15} />
        <div>
          <strong>A guided research demo</strong>
          <p>
            Simulated results.
            <br />
            Your decisions shape the journey.
          </p>
        </div>
        <ArrowUpRight size={12} />
      </div>
    </aside>
  );
}
