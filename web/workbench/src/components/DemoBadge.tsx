import { FlaskConical } from 'lucide-react';
export function DemoBadge({ short = false }: { short?: boolean }) {
  return (
    <span className="demo-badge">
      <FlaskConical size={12} />
      {short ? 'Demo' : 'Demo fixture'}
    </span>
  );
}
