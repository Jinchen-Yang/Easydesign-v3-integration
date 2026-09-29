import { useRef } from 'react';
import { CircleHelp, FolderOpen, Sparkles, Cpu, PanelLeftClose, PanelLeftOpen } from 'lucide-react';
import { Brand } from '../../components/Brand';
export type WorkbenchPage = 'projects' | 'workspace' | 'compute';
const destinations = [
  { id: 'projects', label: 'Projects', icon: FolderOpen },
  { id: 'workspace', label: 'Agent Workspace', icon: Sparkles },
  { id: 'compute', label: 'Compute & Queue', icon: Cpu },
] as const;

export function ProjectSidebar({
  expanded,
  mode = 'demo',
  page,
  onToggle,
  onClose,
  onNavigate,
  onHelp,
}: {
  mode?: 'demo' | 'live';
  expanded: boolean;
  page: WorkbenchPage;
  onToggle: () => void;
  onClose: () => void;
  onNavigate: (page: WorkbenchPage) => void;
  onHelp: () => void;
}) {
  const panel = useRef<HTMLElement>(null);
  const toggle = useRef<HTMLButtonElement>(null);
  const close = () => {
    onClose();
    toggle.current?.focus();
  };
  return (
    <>
      {expanded && (
        <button
          className="project-sidebar-backdrop"
          aria-label="Close project sidebar"
          tabIndex={-1}
          onClick={close}
        />
      )}
      <aside
        ref={panel}
        className={`app-rail project-rail ${expanded ? 'expanded' : ''}`}
        aria-label="App navigation"
        onKeyDown={(e) => {
          if (expanded && e.key === 'Escape') {
            e.preventDefault();
            close();
          }
          if (expanded && e.key === 'Tab' && window.matchMedia('(max-width: 1100px)').matches) {
            const items = [
              ...(panel.current?.querySelectorAll<HTMLButtonElement>('button:not(:disabled)') ??
                []),
            ];
            const first = items[0],
              last = items.at(-1);
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
        <div className="project-rail-header">
          <button
            className="rail-brand"
            aria-label="EasyDesign home"
            onClick={() => onNavigate('projects')}
          >
            <Brand compact={!expanded} />
          </button>
          <button
            ref={toggle}
            className="project-sidebar-toggle"
            aria-expanded={expanded}
            aria-controls="platform-navigation"
            aria-label={expanded ? 'Collapse project sidebar' : 'Expand project sidebar'}
            title={expanded ? 'Collapse project sidebar' : 'Expand project sidebar'}
            onClick={onToggle}
          >
            {expanded ? <PanelLeftClose size={19} /> : <PanelLeftOpen size={19} />}
          </button>
        </div>
        <nav className="rail-group" id="platform-navigation" aria-label="Main navigation">
          {destinations.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              aria-label={label}
              title={label}
              className={page === id ? 'active' : ''}
              aria-current={page === id ? 'page' : undefined}
              onClick={() => onNavigate(id)}
            >
              <Icon size={19} />
              {expanded && <span>{label}</span>}
            </button>
          ))}
        </nav>
        <div className="rail-bottom">
          {expanded && (
            <p className="project-storage-note">
              {mode === 'demo'
                ? 'Demo projects · Saved on this device'
                : 'Research projects · Saved in your workspace'}
            </p>
          )}
          <button
            aria-label={mode === 'demo' ? 'About this demo' : 'About EasyDesign'}
            title={mode === 'demo' ? 'About this demo' : 'About EasyDesign'}
            onClick={onHelp}
          >
            <CircleHelp size={19} />
            {expanded && <span>{mode === 'demo' ? 'About this demo' : 'About EasyDesign'}</span>}
          </button>
          <div className="researcher-profile">
            <span className="user-avatar" title="Local researcher">
              R
            </span>
            {expanded && (
              <span>
                Research workspace<small>{mode === 'demo' ? 'Local demo' : 'Live workspace'}</small>
              </span>
            )}
          </div>
        </div>
      </aside>
    </>
  );
}
