/** Local request preparation only. No provider order, price or production state. */
export const LAB_STEPS = ['samples', 'requirements', 'review'] as const;
export type LabOrderStep = (typeof LAB_STEPS)[number];
export interface LabRequirements {
  format: '' | 'VHH' | 'VHH-Fc';
  amount: string;
  host: string;
  buffer: string;
  profile: '' | 'demo-lab';
  preferredDate: string;
  purchaseOrder: string;
  sdsPurity: string;
  secPurity: string;
  endotoxin: string;
  concentration: string;
  notes: string;
}
export interface LabOrderDraft {
  version: 1;
  step: LabOrderStep;
  candidateIds: string[];
  requirements: LabRequirements;
  reviewed: boolean;
}
export function createLabOrderDraft(
  finalistIds: string[],
  shortlisted: string[] = [],
): LabOrderDraft {
  const selected = finalistIds.filter((id) => shortlisted.includes(id));
  return {
    version: 1,
    step: 'samples',
    candidateIds: selected.length ? selected : [...finalistIds],
    requirements: {
      format: '',
      amount: '',
      host: '',
      buffer: '',
      profile: '',
      preferredDate: '',
      purchaseOrder: '',
      sdsPurity: '',
      secPurity: '',
      endotoxin: '',
      concentration: '',
      notes: '',
    },
    reviewed: false,
  };
}
export function isLabOrderDraft(value: unknown, finalistIds: string[]): value is LabOrderDraft {
  if (!value || typeof value !== 'object') return false;
  const d = value as LabOrderDraft;
  if (
    d.version !== 1 ||
    !LAB_STEPS.includes(d.step) ||
    typeof d.reviewed !== 'boolean' ||
    !Array.isArray(d.candidateIds) ||
    d.candidateIds.length > finalistIds.length ||
    new Set(d.candidateIds).size !== d.candidateIds.length ||
    !d.candidateIds.every((id) => finalistIds.includes(id))
  )
    return false;
  const r = d.requirements;
  if (
    !r ||
    typeof r !== 'object' ||
    !['', 'VHH', 'VHH-Fc'].includes(r.format) ||
    !['', 'demo-lab'].includes(r.profile)
  )
    return false;
  return (
    Object.keys(createLabOrderDraft([]).requirements).every((key) => {
      const text = r[key as keyof LabRequirements];
      return typeof text === 'string' && text.length <= (key === 'notes' ? 2000 : 160);
    }) &&
    (!r.preferredDate || /^\d{4}-\d{2}-\d{2}$/.test(r.preferredDate))
  );
}
export function labProgress(draft: LabOrderDraft) {
  const samples = draft.candidateIds.length > 0;
  const r = draft.requirements;
  const requirements = Boolean(samples && r.format && r.amount.trim() && r.profile);
  return { samples, requirements, review: requirements && draft.reviewed };
}
