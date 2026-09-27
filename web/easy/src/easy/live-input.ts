import type { EasyInput } from './contracts';
import { validateInput } from './inputs';

export const MAX_PRODUCT_GOAL = 1500;

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
  const source = input.file?.name || input.text.trim();
  const organism = input.species.trim() ? ` Organism: ${input.species.trim()}.` : '';
  return `${input.goal.trim()} Input ${input.type}: ${source}.${organism}`;
}

export function validateLiveInput(input: EasyInput): string | null {
  if (input.type === 'sequence')
    return '当前科学 Agent 尚未接入 Sequence / FASTA 输入；请使用 UniProt ID 或上传对应结构，系统不会猜测或替换你的序列。';
  if (input.type === 'pdb-id' && /^pdb_/i.test(input.text.trim()))
    return '当前原生后端仅支持四位 PDB ID；扩展 PDB ID 请改用结构文件上传。';
  if (input.type === 'uniprot' && input.text.includes('-'))
    return '当前原生后端仅支持 canonical UniProt accession；isoform 请改用对应结构文件上传。';
  return (
    validateInput(input) ||
    (productGoal(input).length > MAX_PRODUCT_GOAL
      ? '完整设计输入不能超过 1,500 个字符，请缩短输入后再提交；系统不会截断目标或序列。'
      : null)
  );
}
