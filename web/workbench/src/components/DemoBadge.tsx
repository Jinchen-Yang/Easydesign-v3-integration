import { FlaskConical } from 'lucide-react';
export function DemoBadge({
  short = false,
  mode = 'demo',
}: {
  short?: boolean;
  mode?: 'demo' | 'live';
}) {
  return (
    <span className="demo-badge">
      <FlaskConical size={12} />
      {mode === 'live' ? 'Live workspace' : short ? 'Demo' : 'Demo fixture'}
    </span>
  );
}
