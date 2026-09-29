import type { EasyInput } from './contracts';
import { sequence, validateInput } from './inputs';

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
    return '请上传 FASTA 文件，或直接粘贴序列。';
  if (input.type === 'pdb-id' && /^pdb_/i.test(input.text.trim()))
    return '当前原生后端仅支持四位 PDB ID；扩展 PDB ID 请改用结构文件上传。';
  if (input.type === 'uniprot' && input.text.includes('-'))
    return '当前原生后端仅支持 canonical UniProt accession；isoform 请改用对应结构文件上传。';
  return (
    validateInput(input) ||
    (productGoal(input).length > MAX_PRODUCT_GOAL
      ? '完整设计目标不能超过 4,000 个字符，请缩短后再提交；系统不会截断目标。'
      : null)
  );
}
