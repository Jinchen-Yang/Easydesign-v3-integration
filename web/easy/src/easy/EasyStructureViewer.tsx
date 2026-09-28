import { useEffect, useRef, useState } from 'react';
import type { AtomSelectionSpec, GLViewer } from '3dmol';
import { RotateCcw, Rotate3D, ZoomIn, ZoomOut } from 'lucide-react';
import type { Artifact, Site } from './product-contracts';

const verifiedStructureCache = new Map<string, ArrayBuffer>();

function cacheStructure(sha256: string, data: ArrayBuffer) {
  verifiedStructureCache.delete(sha256);
  verifiedStructureCache.set(sha256, data);
  while (verifiedStructureCache.size > 8)
    verifiedStructureCache.delete(verifiedStructureCache.keys().next().value as string);
}

/** Exactly one verified artifact per view. Missing evidence stays visibly unavailable. */
export function EasyStructureViewer({
  artifact,
  roles,
  sites = [],
  selectedSite,
  emptyMessage = '暂时没有可显示的结构证据。',
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
    [retry, setRetry] = useState(0),
    [modelVersion, setModelVersion] = useState(0);
  const [representation, setRepresentation] = useState<'cartoon' | 'sticks'>('cartoon');
  const [chainMode, setChainMode] = useState('all');
  useEffect(() => {
    setChainMode('all');
  }, [artifact?.id]);
  const rolesKey = JSON.stringify(roles),
    sitesKey = JSON.stringify(sites);

  // Artifact loading, integrity verification and parsing are tied only to the
  // artifact. Site/representation controls are deliberately handled below so
  // changing a highlight never downloads or reparses the same structure.
  useEffect(() => {
    if (!artifact) {
      viewer.current?.clear();
      viewer.current = null;
      host.current?.replaceChildren();
      setStatus('unavailable');
      return;
    }
    const abort = new AbortController();
    let instance: GLViewer | undefined;
    let observer: ResizeObserver | undefined;
    setStatus('loading');
    void (async () => {
      try {
        let data = verifiedStructureCache.get(artifact.sha256);
        if (!data) {
          const response = await fetch(artifact.url, {
            credentials: 'same-origin',
            signal: abort.signal,
          });
          if (!response.ok) throw new Error('Verified structure is unavailable');
          data = await response.arrayBuffer();
          const hash = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', data)))
            .map((b) => b.toString(16).padStart(2, '0'))
            .join('');
          if (hash !== artifact.sha256 || data.byteLength !== artifact.size_bytes)
            throw new Error('Structure integrity check failed');
          cacheStructure(artifact.sha256, data);
        }
        const mol = await import('3dmol');
        if (abort.signal.aborted || !host.current) return;
        host.current.replaceChildren();
        instance = mol.createViewer(host.current, { backgroundColor: '#fafafd', antialias: true });
        instance.addModel(
          new TextDecoder().decode(data),
          artifact.format === 'pdb' ? 'pdb' : 'cif',
          { doAssembly: false },
        );
        if (!instance.selectedAtoms({}).length) throw new Error('No readable atoms');
        instance.zoomTo();
        instance.zoom(Object.values(roles).includes('binder') ? 1.55 : 1.28);
        instance.rotate(20, 'x');
        instance.rotate(-35, 'y');
        framedView.current = instance.getView();
        instance.render();
        viewer.current = instance;
        observer = new ResizeObserver(() => instance?.resize());
        observer.observe(host.current);
        setModelVersion((value) => value + 1);
        setStatus('ready');
      } catch {
        if (!abort.signal.aborted) {
          instance?.clear();
          setStatus('error');
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
  }, [artifact?.id, artifact?.sha256, artifact?.url, retry]);

  useEffect(() => {
    const instance = viewer.current;
    if (!instance || status !== 'ready') return;
    try {
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
      for (const [chain, role] of Object.entries(JSON.parse(rolesKey) as Record<string, string>)) {
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
          const selection: AtomSelectionSpec = {
            chain: point.author_chain_id,
            resi: Number(point.author_residue_id),
            predicate: (atom) => (atom.icode || '').trim() === (point.insertion_code || '').trim(),
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
      instance.render();
    } catch {
      setStatus('error');
    }
  }, [chainMode, modelVersion, representation, rolesKey, selectedSite, sitesKey, status]);
  return (
    <section
      className="molecule live-molecule"
      aria-label="分子结构"
      data-status={status}
      data-artifact={artifact?.id}
      data-candidate={artifact?.candidate_id || ''}
    >
      <div className="viewer-top">
        <div className="viewer-view-toggle">
          <button
            aria-pressed={representation === 'cartoon'}
            onClick={() => setRepresentation('cartoon')}
          >
            带状
          </button>
          <button
            aria-pressed={representation === 'sticks'}
            onClick={() => setRepresentation('sticks')}
          >
            原子
          </button>
        </div>
      </div>
      <div
        ref={host}
        className="molecule-canvas live-canvas"
        aria-label="交互式结构：拖动旋转，滚轮缩放"
      />
      {status === 'ready' && (
        <>
          <div className="viewer-controls">
            <button
              aria-label="重置结构视角"
              onClick={() => {
                viewer.current?.setView(framedView.current);
                viewer.current?.render();
              }}
            >
              <RotateCcw size={14} />
            </button>
            <button
              aria-label="放大"
              onClick={() => {
                viewer.current?.zoom(1.2);
                viewer.current?.render();
              }}
            >
              <ZoomIn size={14} />
            </button>
            <button
              aria-label="缩小"
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
            拖动查看
          </span>
        </>
      )}
      {status !== 'ready' && (
        <div className="live-viewer-status" role="status">
          {status === 'loading'
            ? '正在加载已验证坐标…'
            : status === 'unavailable'
              ? emptyMessage
              : '结构暂时不可用。'}
          {artifact && status !== 'loading' && (
            <button onClick={() => setRetry((r) => r + 1)}>重新加载结构</button>
          )}
        </div>
      )}
      <div className="viewer-bottom">
        <label className="chain-picker">
          显示{' '}
          <select
            aria-label="结构链"
            value={chainMode}
            onChange={(e) => setChainMode(e.target.value)}
          >
            <option value="all">
              {Object.values(roles).includes('binder')
                ? '靶点 + VHH'
                : Object.values(roles).includes('focus-target')
                  ? '靶点 + 互作链'
                  : '靶点'}
            </option>
            {Object.values(roles).includes('binder') && (
              <>
                <option value="target">靶点</option>
                <option value="binder">VHH</option>
              </>
            )}
          </select>
        </label>
        <span className="viewer-selection">
          {sites.length
            ? `已高亮位点 ${sites.find((s) => s.id === selectedSite)?.rank || ''}`
            : artifact?.candidate_id
              ? Object.values(roles).includes('focus-target')
                ? '已高亮靶点链'
                : '候选复合物'
              : '靶点结构'}
        </span>
      </div>
    </section>
  );
}
