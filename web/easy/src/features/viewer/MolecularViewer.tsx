import { useEffect, useRef, useState } from 'react';
import { Atom, RotateCcw, Rotate3D, ZoomIn, ZoomOut } from 'lucide-react';
import type { GLViewer } from '3dmol';
import type { SiteOption, StructureReference } from '../../adapters/WorkbenchAdapter';

const identity = (text: string) => text;

export interface MolecularViewerProps {
  translate?: (text: string) => string;
  reference: StructureReference;
  mode: 'target' | 'complex';
  sites?: SiteOption[];
  selectedSite?: string;
  candidateId?: string;
}
export function residueNumbers(ranges: string[]): number[] {
  return ranges.flatMap((range) => {
    const [a, b = a] = range.split('-').map(Number);
    return Array.from({ length: Math.max(0, b - a + 1) }, (_, i) => a + i);
  });
}
async function loadStructure(
  localUrl: string,
  remoteUrl: string,
  signal: AbortSignal,
): Promise<string> {
  for (const url of [localUrl, remoteUrl]) {
    try {
      const response = await fetch(url, {
        signal: AbortSignal.any([signal, AbortSignal.timeout(4500)]),
      });
      if (!response.ok) throw new Error('Structure unavailable');
      const data = await response.text();
      if (!data.includes('\nATOM ')) throw new Error('Invalid structure file');
      return data;
    } catch (error) {
      if (signal.aborted) throw error;
    }
  }
  throw new Error('The reference structure could not be loaded.');
}

/** All molecular rendering and network access stay within this component. */
export function MolecularViewer({
  translate: t = identity,
  reference,
  mode,
  sites = [],
  selectedSite,
  candidateId,
}: MolecularViewerProps) {
  const element = useRef<HTMLDivElement>(null);
  const viewer = useRef<GLViewer | null>(null);
  const baseView = useRef<number[]>([]);
  const framedView = useRef<number[]>([]);
  const [status, setStatus] = useState<'loading' | 'ready' | 'fallback'>('loading');
  const [retry, setRetry] = useState(0);
  const [chainMode, setChainMode] = useState<'target' | 'complex' | 'binder'>(mode);
  const [style, setStyle] = useState<'cartoon' | 'sticks'>('cartoon');
  useEffect(() => {
    setChainMode(mode);
  }, [mode]);
  useEffect(() => {
    const controller = new AbortController();
    let instance: GLViewer | undefined;
    let observer: ResizeObserver | undefined;
    setStatus('loading');
    async function boot() {
      try {
        const [mol, data] = await Promise.all([
          import('3dmol'),
          loadStructure(reference.localUrl, reference.sourceUrl, controller.signal),
        ]);
        if (controller.signal.aborted || !element.current) return;
        instance = mol.createViewer(element.current, {
          backgroundColor: '#fafafd',
          antialias: true,
        });
        instance.addModel(data, 'pdb');
        if (
          !instance.selectedAtoms({ chain: reference.targetChain }).length ||
          !instance.selectedAtoms({ chain: reference.binderChain }).length
        )
          throw new Error('Reference chain unavailable');
        instance.setStyle({}, { cartoon: { color: '#b9bdc9' } });
        instance.zoomTo();
        instance.rotate(20, 'x');
        instance.rotate(-35, 'y');
        baseView.current = instance.getView();
        viewer.current = instance;
        observer = new ResizeObserver(() => {
          instance?.resize();
        });
        observer.observe(element.current);
        setStatus('ready');
      } catch {
        if (!controller.signal.aborted) {
          instance?.clear();
          viewer.current = null;
          setStatus('fallback');
        }
      }
    }
    void boot();
    return () => {
      controller.abort();
      observer?.disconnect();
      instance?.clear();
      viewer.current = null;
      element.current?.replaceChildren();
    };
  }, [
    reference.localUrl,
    reference.sourceUrl,
    reference.targetChain,
    reference.binderChain,
    retry,
  ]);

  useEffect(() => {
    const v = viewer.current;
    if (!v || status !== 'ready') return;
    v.setView(baseView.current);
    v.setStyle({}, {});
    const target = { chain: reference.targetChain },
      binder = { chain: reference.binderChain };
    const renderStyle = (color: string) =>
      style === 'cartoon'
        ? { cartoon: { color, thickness: 0.6 } }
        : { stick: { color, radius: 0.12 } };
    if (chainMode !== 'binder') v.setStyle(target, renderStyle('#b8bdcb'));
    if (chainMode !== 'target') v.setStyle(binder, renderStyle('#8274cf'));
    if (chainMode !== 'binder') {
      for (const site of sites) {
        const selected = selectedSite === site.id;
        v.setStyle(
          { ...target, resi: residueNumbers(site.residues) },
          {
            cartoon: { color: selected ? '#6657e8' : '#d5d1ea', thickness: 0.7 },
            ...(selected ? { stick: { color: '#8270d4', radius: 0.18 } } : {}),
          },
        );
      }
    }
    v.zoomTo(
      chainMode === 'target' ? target : chainMode === 'binder' ? binder : { or: [target, binder] },
    );
    v.zoom(chainMode === 'target' ? 1.28 : 1.55);
    if (candidateId) v.rotate((Number(candidateId.split('-')[1]) - 1) * 16, 'y');
    v.render();
    framedView.current = v.getView();
  }, [
    status,
    chainMode,
    selectedSite,
    candidateId,
    sites,
    reference.targetChain,
    reference.binderChain,
    style,
  ]);

  return (
    <section
      className="molecule"
      aria-label={t('Molecular structure')}
      data-status={status}
      data-selection={selectedSite ? `Site ${selectedSite}` : candidateId || chainMode}
      data-chain-mode={chainMode}
    >
      <div className="viewer-top">
        <span className="pdb-label">
          {reference.pdbId}
          <span>{t('REFERENCE')}</span>
        </span>
        <div className="viewer-view-toggle">
          <button aria-pressed={style === 'cartoon'} onClick={() => setStyle('cartoon')}>
            {t('Ribbon')}
          </button>
          <button aria-pressed={style === 'sticks'} onClick={() => setStyle('sticks')}>
            {t('Atoms')}
          </button>
        </div>
      </div>
      <div
        className={`molecule-canvas ${status !== 'ready' ? 'not-ready' : ''}`}
        ref={element}
        aria-label={t('Interactive 1MEL structure — drag to rotate, scroll to zoom')}
      />
      {status === 'loading' && (
        <div className="viewer-state">
          <Atom className="slow-spin" size={32} />
          <strong>{t('Opening the reference structure')}</strong>
          <span>{t('The demo can continue while it loads.')}</span>
        </div>
      )}
      {status === 'fallback' && (
        <div className="viewer-state">
          <Atom size={36} />
          <strong>{t('Structure preview unavailable')}</strong>
          <span>{t('You can still compare sites and complete the demo.')}</span>
          <button className="text-button" onClick={() => setRetry((n) => n + 1)}>
            {t('Try loading again')}
          </button>
        </div>
      )}
      {status === 'ready' && (
        <>
          <div className="viewer-controls">
            <button
              title={t('Reset structure view')}
              aria-label={t('Reset structure view')}
              onClick={() => {
                viewer.current?.setView(framedView.current);
                viewer.current?.render();
              }}
            >
              <RotateCcw size={14} />
            </button>
            <button
              title={t('Zoom in')}
              aria-label={t('Zoom in')}
              onClick={() => {
                viewer.current?.zoom(1.2);
                viewer.current?.render();
              }}
            >
              <ZoomIn size={14} />
            </button>
            <button
              title={t('Zoom out')}
              aria-label={t('Zoom out')}
              onClick={() => {
                viewer.current?.zoom(0.8);
                viewer.current?.render();
              }}
            >
              <ZoomOut size={14} />
            </button>
          </div>
          <span className="rotate-hint">
            <Rotate3D size={12} /> {t('Drag to explore')}
          </span>
        </>
      )}
      <div className="viewer-bottom">
        <label className="chain-picker">
          {t('Show')}{' '}
          <select
            aria-label={t('Structure chains')}
            value={chainMode}
            onChange={(e) => setChainMode(e.target.value as typeof chainMode)}
          >
            <option value="target">
              {t('Target')} · {reference.targetChain}
            </option>
            <option value="complex">{t('Target + VHH')}</option>
            <option value="binder">VHH · {reference.binderChain}</option>
          </select>
        </label>
        <span className="viewer-selection">
          {selectedSite
            ? t('Site {site} highlighted').replace('{site}', selectedSite)
            : candidateId
              ? `${candidateId} · ${t('reference')}`
              : t('Target structure')}
        </span>
      </div>
    </section>
  );
}
