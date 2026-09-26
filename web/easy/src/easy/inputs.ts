import { INPUT_TYPES, type EasyInput, type InputType } from './contracts';
const AMINO = /^[ACDEFGHIKLMNPQRSTVWY]+$/i;
const UNIPROT =
  /^(?:[OPQ][0-9][A-Z0-9]{3}[0-9]|[A-NR-Z][0-9](?:[A-Z][A-Z0-9]{2}[0-9]){1,2})(?:-[1-9][0-9]*)?$/i;
export const MAX_FILE_BYTES = 2 * 1024 * 1024;
export const fileTypes: Partial<Record<InputType, string>> = {
  structure: '.pdb,.cif,.mmcif',
  sequence: '.fasta,.fa,.faa,.txt',
  pse: '.pse',
  bundle: '.json',
};
export function sequence(text: string): string {
  const lines = text.trim().split(/\r?\n/);
  const headers = lines.filter((line) => line.startsWith('>'));
  if (headers.length > 1) throw new Error('Use one protein sequence per design.');
  if (headers.length && !lines[0].startsWith('>'))
    throw new Error('The FASTA header must be the first line.');
  const value = lines
    .filter((line) => !line.startsWith('>'))
    .join('')
    .replace(/\s/g, '')
    .toUpperCase();
  if (!value || !AMINO.test(value))
    throw new Error('Use the 20 standard amino acids only; ambiguous residues are not supported.');
  if (value.length > 20000)
    throw new Error('Use a sequence of at most 20,000 residues in this preview.');
  return value;
}
export function validateInput(input: EasyInput): string | null {
  if (!INPUT_TYPES.some((option) => option.id === input.type)) return 'Choose an input type.';
  if (input.name.length > 80) return 'Keep the design name under 80 characters.';
  if (input.goal.length > 2000) return 'Keep the design goal under 2,000 characters.';
  if (input.type !== 'description' && !input.goal.trim()) return 'Add a design goal in Options.';
  const text = input.text.trim();
  if (input.type === 'description')
    return text.length < 12
      ? 'Describe a target and a design goal (at least 12 characters).'
      : text.length > 4000
        ? 'Keep your description under 4,000 characters.'
        : null;
  if (input.type === 'protein-name')
    return !text
      ? 'Enter a protein or gene name.'
      : !input.species.trim()
        ? 'Add an organism to identify the right target.'
        : null;
  if (input.type === 'uniprot')
    return UNIPROT.test(text) ? null : 'Enter a valid UniProt accession, such as P00698.';
  if (input.type === 'pdb-id')
    return /^(?:[1-9][A-Z0-9]{3}|pdb_[a-z0-9]{8})$/i.test(text)
      ? null
      : 'Enter a PDB identifier, such as 1MEL.';
  if (input.type === 'sequence') {
    try {
      sequence(text);
      return null;
    } catch (e) {
      return (e as Error).message;
    }
  }
  if (!input.file) return 'Choose a file to continue.';
  if (input.file.size <= 0 || input.file.size > MAX_FILE_BYTES)
    return 'Choose a non-empty file smaller than 2 MB.';
  if (input.type === 'structure')
    return /\.(pdb|cif|mmcif)$/i.test(input.file.name) ? null : 'Choose a PDB or mmCIF file.';
  if (input.type === 'pse')
    return /\.pse$/i.test(input.file.name) ? null : 'Choose a PyMOL .pse session.';
  return /\.json$/i.test(input.file.name) ? null : 'Choose a Target Bundle JSON file.';
}
/** Lightweight intake only; never executes PSE or treats uploaded metadata as verified science. */
export async function readInputFile(
  type: InputType,
  file: File,
): Promise<Pick<EasyInput, 'file' | 'text'>> {
  if (!file.size || file.size > MAX_FILE_BYTES)
    throw new Error('Choose a non-empty file smaller than 2 MB.');
  const allowed = fileTypes[type]?.split(',');
  if (!allowed?.some((extension) => file.name.toLowerCase().endsWith(extension)))
    throw new Error('This file does not match the selected input type.');
  let text = '';
  if (type !== 'pse') {
    const contents = await file.text();
    if (type === 'sequence') text = sequence(contents);
    if (type === 'structure') {
      const pdb = /\.pdb$/i.test(file.name);
      if (pdb ? !/^(ATOM  |HETATM)/m.test(contents) : !/_atom_site\./.test(contents))
        throw new Error('No coordinate records found. Choose a PDB or mmCIF structure.');
    }
    if (type === 'bundle') {
      let value: unknown;
      try {
        value = JSON.parse(contents);
      } catch {
        throw new Error('This file is not valid JSON.');
      }
      if (
        !value ||
        typeof value !== 'object' ||
        typeof (value as Record<string, unknown>).target_id !== 'string'
      )
        throw new Error('Choose an EasyDesign Target Bundle with a target_id.');
    }
  }
  return { file: { name: file.name, size: file.size }, text };
}
export function inputLabel(input: EasyInput) {
  return (
    input.file?.name ||
    input.text.trim().replace(/\s+/g, ' ') ||
    INPUT_TYPES.find((type) => type.id === input.type)!.label
  );
}
export function isInput(value: unknown): value is EasyInput {
  if (!value || typeof value !== 'object') return false;
  const input = value as EasyInput;
  return (
    INPUT_TYPES.some((item) => item.id === input.type) &&
    ['text', 'species', 'name', 'goal'].every(
      (key) => typeof input[key as 'text'] === 'string' && input[key as 'text'].length <= 25000,
    ) &&
    (input.file === null ||
      (typeof input.file?.name === 'string' &&
        input.file.name.length <= 300 &&
        Number.isFinite(input.file.size) &&
        input.file.size > 0 &&
        input.file.size <= MAX_FILE_BYTES))
  );
}
