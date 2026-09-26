import type { Candidate, SiteOption, StructureReference } from '../adapters/WorkbenchAdapter';

export const INPUT_TYPES = [
  {
    id: 'description',
    label: 'Description',
    hint: 'Describe your target and what you want to design.',
  },
  {
    id: 'protein-name',
    label: 'Protein / Gene name',
    hint: 'A protein or gene name, with its organism.',
  },
  { id: 'uniprot', label: 'UniProt ID', hint: 'Enter a UniProt accession, for example P00698.' },
  { id: 'pdb-id', label: 'PDB ID', hint: 'Enter a PDB identifier, for example 1MEL.' },
  { id: 'structure', label: 'Structure file', hint: 'PDB or mmCIF · Up to 2 MB' },
  {
    id: 'sequence',
    label: 'Sequence / FASTA',
    hint: 'One protein sequence · Paste or upload a FASTA file.',
  },
  {
    id: 'pse',
    label: 'PyMOL session',
    hint: 'PSE · Up to 2 MB',
  },
  {
    id: 'bundle',
    label: 'Existing target',
    hint: 'Target Bundle JSON · Up to 2 MB',
  },
] as const;
export type InputType = (typeof INPUT_TYPES)[number]['id'];
export interface EasyInput {
  type: InputType;
  text: string;
  species: string;
  name: string;
  goal: string;
  file: { name: string; size: number } | null;
}
export const emptyInput = (): EasyInput => ({
  type: 'description',
  text: '',
  species: '',
  name: '',
  goal: 'Design a VHH binder for this target.',
  file: null,
});
export const EXAMPLE_GOAL =
  'Design a VHH binder against hen egg-white lysozyme and prioritize a compact, accessible epitope.';
export const STEPS = ['Target', 'Site', 'Design', 'Pilot', 'Scale', 'Candidates'] as const;
export type RunStatus = 'draft' | 'running' | 'paused' | 'complete';
export interface EasyRun {
  id: string;
  name: string;
  input: EasyInput;
  createdAt: string;
  updatedAt: string;
  status: RunStatus;
  step: number;
}
export interface EasyReview {
  sites: SiteOption[];
  selectedSite: string;
  design: {
    binderType: string;
    scaffold: string;
    arms: { id: string; label: string; count: number }[];
  };
  pilot: {
    total: number;
    passed: number;
    filtered: number;
    candidates: Pick<Candidate, 'id' | 'status' | 'interface' | 'confidence'>[];
  };
  scale: { total: number; passed: number; filtered: number; batches: number; batchSize: number };
}
export interface EasySnapshot {
  mode: 'demo';
  runs: EasyRun[];
  selectedId: string | null;
  notice: string | null;
  reference: StructureReference;
  candidates: Candidate[];
  review: EasyReview;
}
/** A product port, not a scientific scheduler. Live support must preserve native Gate authority. */
export interface EasyAdapter {
  load(): EasySnapshot;
  subscribe(listener: (snapshot: EasySnapshot) => void): () => void;
  saveDraft(input: EasyInput, existingId?: string): string;
  start(input: EasyInput, draftId?: string): string;
  select(id: string | null): void;
  pause(id: string): void;
  resume(id: string): void;
  exportResult(id: string): string;
  dispose(): void;
}
