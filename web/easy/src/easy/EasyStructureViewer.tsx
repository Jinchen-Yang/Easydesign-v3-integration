import { useEffect, useRef, useState } from 'react';
import type { AtomSelectionSpec, GLViewer } from '3dmol';
import { RotateCcw, Rotate3D, ZoomIn, ZoomOut } from 'lucide-react';
import type { Artifact, Site } from './product-contracts';
/** Exactly one verified artifact per view. Missing evidence stays visibly unavailable. */
export function EasyStructureViewer({
  artifact,
  roles,
  sites = [],
  selectedSite,
  emptyMessage = 'Structure evidence is not available yet.',
}: {
  artifact: Artifact | null;
  roles: Record<string, string>;
  sites?: Site[];
  selectedSite?: string;
  emptyMessage?: string;
}) {
  const host = useRef<HTMLDivElement>(null),
    viewer = useRef<GLViewer | null>(null),
    framedView = useRef<number[]>([]);
  const [status, setStatus] = useState('loading'),
    [retry, setRetry] = useState(0);
  const [representation, setRepresentation] = useState<'cartoon' | 'sticks'>('cartoon');
  const [chainMode, setChainMode] = useState('all');
  useEffect(() => {
    setChainMode('all');
  }, [artifact?.id]);
  const rolesKey = JSON.stringify(roles),
    sitesKey = JSON.stringify(sites);
  useEffect(() => {
    if (!artifact) {
      setStatus('unavailable');
      return;
    }
    const abort = new AbortController();
    let instance: GLViewer | undefined;
    let observer: ResizeObserver | undefined;
    setStatus('loading');
    void (async () => {
      try {
        const response = await fetch(artifact.url, {
          credentials: 'same-origin',
          signal: abort.signal,
        });
        if (!response.ok) throw new Error('Verified structure is unavailable');
        const data = await response.arrayBuffer();
        const hash = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', data)))
          .map((b) => b.toString(16).padStart(2, '0'))
          .join('');
        if (hash !== artifact.sha256 || data.byteLength !== artifact.size_bytes)
          throw new Error('Structure integrity check failed');
        const mol = await import('3dmol');
        if (abort.signal.aborted || !host.current) return;
        instance = mol.createViewer(host.current, { backgroundColor: '#fafafd', antialias: true });
        instance.addModel(
          new TextDecoder().decode(data),
          artifact.format === 'pdb' ? 'pdb' : 'cif',
          { doAssembly: false },
        );
        if (!instance.selectedAtoms({}).length) throw new Error('No readable atoms');
        // Short peptides / sparse fixtures may have no drawable ribbon. Show their
        // actual atoms even when no bonds can be drawn between isolated Cα atoms.
        const sparse = instance.selectedAtoms({ atom: 'CA' }).length < 20;
        const style = (color: string) => ({
          ...(representation === 'cartoon'
            ? { cartoon: { color } }
            : { stick: { color, radius: 0.15 } }),
          ...(sparse ? { stick: { color, radius: 0.15 }, sphere: { color, radius: 0.45 } } : {}),
        });
        instance.setStyle({}, style('#b9bdc9'));
        for (const [chain, role] of Object.entries(
          JSON.parse(rolesKey) as Record<string, string>,
        )) {
          if (!instance.selectedAtoms({ chain }).length)
            throw new Error('Declared chain missing from structure');
          instance.setStyle(
            { chain },
            style(role === 'focus-target' ? '#6657e8' : role === 'binder' ? '#8070d6' : '#b9bdc9'),
          );
        }
        for (const site of JSON.parse(sitesKey) as Site[]) {
          const selected = site.id === selectedSite;
          const color = selected ? '#8270d4' : '#d5d1ea';
          for (const point of site.coordinates) {
            // Runtime mapping supplies author coordinates, including insertion codes.
            const selection: AtomSelectionSpec = {
              chain: point.author_chain_id,
              resi: Number(point.author_residue_id),
              // PDB parsers retain a blank as " "; mmCIF commonly uses "".
              predicate: (atom) =>
                (atom.icode || '').trim() === (point.insertion_code || '').trim(),
            };
            instance.addStyle(selection, {
              ...(representation === 'cartoon'
                ? { cartoon: { color: selected ? '#6657e8' : '#d5d1ea', thickness: 0.7 } }
                : {}),
              stick: { color, radius: selected ? 0.23 : 0.14 },
              ...(sparse ? { sphere: { color, radius: selected ? 0.65 : 0.45 } } : {}),
            });
          }
        }
        if (chainMode !== 'all') {
          for (const [chain, role] of Object.entries(
            JSON.parse(rolesKey) as Record<string, string>,
          )) {
            if (role !== chainMode) instance.setStyle({ chain }, {});
          }
        }
        instance.zoomTo();
        instance.zoom(Object.values(roles).includes('binder') ? 1.55 : 1.28);
        instance.rotate(20, 'x');
        instance.rotate(-35, 'y');
        framedView.current = instance.getView();
        instance.render();
        viewer.current = instance;
        observer = new ResizeObserver(() => instance?.resize());
        observer.observe(host.current);
        setStatus('ready');
      } catch (error) {
        if (!abort.signal.aborted) {
          instance?.clear();
          setStatus((error as Error).message);
        }
      }
    })();
    return () => {
      abort.abort();
      observer?.disconnect();
      instance?.clear();
      viewer.current = null;
      host.current?.replaceChildren();
    };
  }, [artifact?.id, rolesKey, sitesKey, selectedSite, retry, representation, chainMode]);
  return (
    <section
      className="molecule live-molecule"
      aria-label="Molecular structure"
      data-status={status}
      data-artifact={artifact?.id}
      data-candidate={artifact?.candidate_id || ''}
    >
      <div className="viewer-top">
        <span className="pdb-label" title={artifact?.label}>
          {artifact?.label || 'Target structure'}
        </span>
        <div className="viewer-view-toggle">
          <button
            aria-pressed={representation === 'cartoon'}
            onClick={() => setRepresentation('cartoon')}
          >
            Ribbon
          </button>
          <button
            aria-pressed={representation === 'sticks'}
            onClick={() => setRepresentation('sticks')}
          >
            Atoms
          </button>
        </div>
      </div>
      <div
        ref={host}
        className="molecule-canvas live-canvas"
        aria-label="Interactive structure — drag to rotate, scroll to zoom"
      />
      {status === 'ready' && (
        <>
          <div className="viewer-controls">
            <button
              aria-label="Reset structure view"
              onClick={() => {
                viewer.current?.setView(framedView.current);
                viewer.current?.render();
              }}
            >
              <RotateCcw size={14} />
            </button>
            <button
              aria-label="Zoom in"
              onClick={() => {
                viewer.current?.zoom(1.2);
                viewer.current?.render();
              }}
            >
              <ZoomIn size={14} />
            </button>
            <button
              aria-label="Zoom out"
              onClick={() => {
                viewer.current?.zoom(0.8);
                viewer.current?.render();
              }}
            >
              <ZoomOut size={14} />
            </button>
          </div>
          <span className="rotate-hint">
            <Rotate3D size={12} />
            Drag to explore
          </span>
        </>
      )}
      {status !== 'ready' && (
        <div className="live-viewer-status" role="status">
          {status === 'loading'
            ? 'Loading verified coordinates…'
            : status === 'unavailable'
              ? emptyMessage
              : status}
          {artifact && status !== 'loading' && (
            <button onClick={() => setRetry((r) => r + 1)}>Retry structure</button>
          )}
        </div>
      )}
      <div className="viewer-bottom">
        <label className="chain-picker">
          Show{' '}
          <select
            aria-label="Structure chains"
            value={chainMode}
            onChange={(e) => setChainMode(e.target.value)}
          >
            <option value="all">
              {Object.values(roles).includes('binder')
                ? 'Target + VHH'
                : Object.values(roles).includes('focus-target')
                  ? 'Target + partners'
                  : 'Target'}
            </option>
            {Object.values(roles).includes('binder') && (
              <>
                <option value="target">Target</option>
                <option value="binder">VHH</option>
              </>
            )}
          </select>
        </label>
        <span className="viewer-selection">
          {sites.length
            ? `Site ${sites.find((s) => s.id === selectedSite)?.rank || ''} highlighted`
            : artifact?.candidate_id
              ? Object.values(roles).includes('focus-target')
                ? 'Target chain highlighted'
                : 'Candidate complex'
              : 'Target structure'}
        </span>
      </div>
    </section>
  );
}
