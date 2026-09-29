import type { EasyInput } from './contracts';
import { sequence, validateInput } from './inputs';
import { appI18n } from '../../shell/I18nProvider';

const easyT = (key: string): string => appI18n.t(key, { ns: 'easy' });

export const MAX_PRODUCT_GOAL = 4000;

export interface ProductSource {
  pdb_id?: string;
  uniprot?: string;
}

export function productSource(input: EasyInput): ProductSource | undefined {
  if (input.type === 'pdb-id') return { pdb_id: input.text.trim() };
  if (input.type === 'uniprot') return { uniprot: input.text.trim().toUpperCase() };
  return undefined;
}

/** Keep the complete submitted intent. Never silently truncate an identifier or sequence. */
export function productGoal(input: EasyInput): string {
  if (input.type === 'description') return input.text.trim();
  const source =
    input.type === 'sequence'
      ? `${input.file?.name || 'pasted sequence'} (${sequence(input.text).length} residues)`
      : input.file?.name || input.text.trim();
  const organism = input.species.trim() ? ` Organism: ${input.species.trim()}.` : '';
  return `${input.goal.trim()} Input ${input.type}: ${source}.${organism}`;
}

export function validateLiveInput(input: EasyInput): string | null {
  if (input.type === 'sequence' && input.file && !/\.(fasta|fa|faa)$/i.test(input.file.name))
    return easyT('Upload a FASTA file, or paste the sequence directly.');
  if (input.type === 'pdb-id' && /^pdb_/i.test(input.text.trim()))
    return easyT('The current native backend supports only four-character PDB IDs; for extended PDB IDs, upload a structure file instead.');
  if (input.type === 'uniprot' && input.text.includes('-'))
    return easyT('The current native backend supports only canonical UniProt accessions; for isoforms, upload the corresponding structure file instead.');
  return (
    validateInput(input) ||
    (productGoal(input).length > MAX_PRODUCT_GOAL
      ? easyT('The complete design goal must not exceed 4,000 characters; shorten it before submitting — the system never truncates goals.')
      : null)
  );
}
