import { webcrypto, createHash } from 'node:crypto';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { I18nProvider, appI18n, LANGUAGE_KEY } from '../src/shell/I18nProvider';
import { EasyStructureViewer } from '../src/views/easy/EasyStructureViewer';
import { StructureViewer } from '../src/views/pro/StructureViewer';
import type { Artifact, Site } from '../src/data/product-contracts';

const mol = vi.hoisted(() => {
  const atoms = [
    { chain: 'A', resi: 42, icode: ' ', atom: 'CA' },
    { chain: 'A', resi: 42, icode: 'B', atom: 'CA' },
    { chain: 'B', resi: 1, icode: '', atom: 'CA' },
  ];
  const viewer = {
    addModel: vi.fn(),
    selectedAtoms: vi.fn((selection: { chain?: string; atom?: string } = {}) =>
      atoms.filter(
        (atom) =>
          (!selection.chain || selection.chain === atom.chain) &&
          (!selection.atom || selection.atom === atom.atom),
      ),
    ),
    zoomTo: vi.fn(),
    zoom: vi.fn(),
    rotate: vi.fn(),
    getView: vi.fn(() => [1, 2, 3]),
    setView: vi.fn(),
    render: vi.fn(),
    resize: vi.fn(),
    clear: vi.fn(),
    setStyle: vi.fn(),
    addStyle: vi.fn(),
  };
  return { viewer, createViewer: vi.fn(() => viewer) };
});
vi.mock('3dmol', () => ({ createViewer: mol.createViewer }));
const text = 'ATOM      1  CA  ALA A  42      11.000  10.000  12.000  1.00 20.00           C\n';
const bytes = new TextEncoder().encode(text);
const hash = createHash('sha256').update(bytes).digest('hex');
let identity = 0;
function artifact(): Artifact {
  const id = `structure-${++identity}`;
  return {
    id,
    label: 'Verified target',
    url: `/api/v1/scopes/s1/artifacts/${id}`,
    format: 'pdb',
    sha256: hash,
    size_bytes: bytes.byteLength,
    role: 'target',
    candidate_id: null,
  };
}
function site(id: string, code = ''): Site {
  return {
    id,
    rank: id,
    name: `Site ${id}`,
    selectable: true,
    design_labels: [42],
    why_ranked: '',
    risks: [],
    uncertainty: [],
    confidence: 'reviewed',
    coordinates: [{ author_chain_id: 'A', author_residue_id: '42', insertion_code: code }],
  };
}
beforeEach(async () => {
  vi.clearAllMocks();
  vi.stubGlobal('crypto', webcrypto);
  vi.stubGlobal(
    'ResizeObserver',
    class {
      observe() {}
      disconnect() {}
    },
  );
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => new Response(bytes)),
  );
  localStorage.setItem(LANGUAGE_KEY, 'en');
  await appI18n.changeLanguage('en');
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('shared manifest-verified structure viewer', () => {
  it('uses one implementation for both views and keeps parsing/camera stable across selection changes', async () => {
    expect(EasyStructureViewer).toBe(StructureViewer);
    const evidence = artifact();
    const props = {
      artifact: evidence,
      roles: { A: 'focus-target', B: 'binder' },
      sites: [site('A'), site('B', 'B')],
      selectedSite: 'A',
    };
    const { rerender } = render(
      <I18nProvider>
        <EasyStructureViewer {...props} />
      </I18nProvider>,
    );
    await waitFor(() =>
      expect(screen.getByRole('region', { name: 'Molecular structure' }).dataset.status).toBe(
        'ready',
      ),
    );
    expect(fetch).toHaveBeenCalledWith(
      evidence.url,
      expect.objectContaining({ credentials: 'same-origin' }),
    );
    expect(mol.viewer.addModel).toHaveBeenCalledWith(text, 'pdb', { doAssembly: false });
    fireEvent.click(screen.getByRole('button', { name: /^Atoms$/ }));
    rerender(
      <I18nProvider>
        <StructureViewer {...props} selectedSite="B" />
      </I18nProvider>,
    );
    await waitFor(() => expect(screen.getByText('Site B highlighted')).toBeTruthy());
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(mol.createViewer).toHaveBeenCalledTimes(1);
    expect(mol.viewer.addModel).toHaveBeenCalledTimes(1);
    expect(mol.viewer.zoomTo).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole('button', { name: 'Reset structure view' }));
    expect(mol.viewer.setView).toHaveBeenCalledWith([1, 2, 3]);
  });

  it('respects author insertion codes and draws the selected overlapping site last', async () => {
    render(
      <I18nProvider>
        <StructureViewer
          artifact={artifact()}
          roles={{ A: 'focus-target', B: 'binder' }}
          sites={[site('A'), site('B', 'B')]}
          selectedSite="A"
        />
      </I18nProvider>,
    );
    await waitFor(() => expect(mol.viewer.addStyle).toHaveBeenCalled());
    const [selection, style] = mol.viewer.addStyle.mock.calls.at(-1)!;
    expect(selection).toMatchObject({ chain: 'A', resi: 42 });
    expect(selection.predicate({ icode: ' ' })).toBe(true);
    expect(selection.predicate({ icode: '' })).toBe(true);
    expect(selection.predicate({ icode: 'B' })).toBe(false);
    expect(style.stick.color).toBe('#8270d4');
    fireEvent.change(screen.getByRole('combobox', { name: 'Structure chains' }), {
      target: { value: 'target' },
    });
    expect(mol.viewer.setStyle).toHaveBeenLastCalledWith({ chain: 'B' }, {});
    expect(mol.viewer.setStyle.mock.calls).not.toContainEqual([{ chain: 'A' }, {}]);
  });

  it('reuses verified bytes between views but revalidates a changed size contract', async () => {
    const evidence = artifact();
    const first = render(
      <I18nProvider>
        <EasyStructureViewer artifact={evidence} roles={{ A: 'target' }} />
      </I18nProvider>,
    );
    await waitFor(() => expect(mol.createViewer).toHaveBeenCalledTimes(1));
    first.unmount();
    const second = render(
      <I18nProvider>
        <StructureViewer artifact={evidence} roles={{ A: 'target' }} />
      </I18nProvider>,
    );
    await waitFor(() => expect(mol.createViewer).toHaveBeenCalledTimes(2));
    expect(fetch).toHaveBeenCalledTimes(1);
    second.rerender(
      <I18nProvider>
        <StructureViewer
          artifact={{ ...evidence, size_bytes: evidence.size_bytes + 1 }}
          roles={{ A: 'target' }}
        />
      </I18nProvider>,
    );
    await screen.findByText('Structure integrity check failed');
    expect(fetch).toHaveBeenCalledTimes(2);
    expect(mol.createViewer).toHaveBeenCalledTimes(2);
  });

  it('shows unavailable or corrupt evidence without guessing a fallback structure URL', async () => {
    const evidence = artifact();
    const { rerender } = render(
      <I18nProvider>
        <StructureViewer
          artifact={{ ...evidence, sha256: '0'.repeat(64) }}
          roles={{ A: 'target' }}
        />
      </I18nProvider>,
    );
    await screen.findByText('Structure integrity check failed');
    expect(mol.createViewer).not.toHaveBeenCalled();
    expect(fetch).toHaveBeenCalledTimes(1);
    rerender(
      <I18nProvider>
        <StructureViewer artifact={null} roles={{}} />
      </I18nProvider>,
    );
    await screen.findByText('Structure evidence is not available yet.');
    expect(fetch).toHaveBeenCalledTimes(1);
  });
});
