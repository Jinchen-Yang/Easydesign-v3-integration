import { useEffect, useState } from 'react';
import type { WorkbenchPage } from '../features/projects/ProjectSidebar';

const readPage = (): WorkbenchPage => {
  const page = window.location.hash.slice(1);
  return page === 'workspace' || page === 'compute' ? page : 'projects';
};

/** Three local destinations, with native browser Back/Forward and reload support. */
export function useWorkbenchPage() {
  const [page, setPage] = useState(readPage);
  useEffect(() => {
    const update = () => setPage(readPage());
    window.addEventListener('hashchange', update);
    return () => window.removeEventListener('hashchange', update);
  }, []);
  const navigate = (next: WorkbenchPage) => {
    setPage(next);
    if (window.location.hash !== `#${next}`) window.location.hash = next;
  };
  return [page, navigate] as const;
}
