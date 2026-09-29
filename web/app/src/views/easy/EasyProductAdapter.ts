import { LiveProductStore, type LiveProductPort } from '../../data/LiveProductStore';
import type {
  ProductTargetInput,
  ProductLabOrder,
  ProductLabOrderDraft,
} from '../../data/product-contracts';
import type { EasyInput } from './contracts';
import { sequence } from './inputs';
import { appI18n } from '../../shell/I18nProvider';
const commonT = (key: string): string => appI18n.t(key, { ns: 'common' });
export { ApiError } from '../../data/LiveProductStore';

export interface EasyProductPort extends LiveProductPort {
  createTypedProject(
    title: string,
    goal: string,
    input: EasyInput,
    file?: File | null,
  ): Promise<void>;
  labOrder(): Promise<ProductLabOrder>;
  saveLabOrder(draft: ProductLabOrderDraft): Promise<ProductLabOrder>;
  quoteLabOrder(): Promise<ProductLabOrder>;
  submitLabOrder(): Promise<ProductLabOrder>;
}

/** Easy input encoding and compact server projection over the shared live state. */
export class EasyProductAdapter extends LiveProductStore implements EasyProductPort {
  constructor(transport: typeof fetch = (input, init) => fetch(input, init), interval = 2000) {
    super(transport, interval, { surface: 'easy', projectLimit: 5, candidateView: 'summary' });
  }
  async createTypedProject(title: string, goal: string, input: EasyInput, file?: File | null) {
    if (this.state.pending) return;
    let target_input: ProductTargetInput;
    if (input.type === 'description') {
      target_input = { kind: 'description', description: input.text.trim() };
    } else if (input.type === 'protein-name') {
      target_input = {
        kind: 'protein-name',
        name: input.text.trim(),
        organism: input.species.trim(),
      };
    } else if (input.type === 'uniprot') {
      target_input = { kind: 'uniprot', accession: input.text.trim().toUpperCase() };
    } else if (input.type === 'pdb-id') {
      target_input = { kind: 'pdb-id', pdb_id: input.text.trim().toUpperCase() };
    } else if (input.type === 'structure' || input.type === 'sequence') {
      const upload =
        input.type === 'structure'
          ? file
          : file ||
            new Blob([`>easy-ui-target\n${sequence(input.text)}\n`], {
              type: 'text/plain;charset=utf-8',
            });
      if (!upload)
        throw new Error(commonT('Choose a target structure before starting the design.'));
      const filename =
        input.type === 'structure' ? file!.name : file?.name || 'easy-ui-target.fasta';
      const artifact = await this.api<{ id: string }>(
        '/inputs?filename=' + encodeURIComponent(filename),
        { method: 'POST', body: upload },
      );
      target_input = { kind: input.type, artifact_id: artifact.id };
    } else {
      throw new Error(commonT('This input type is not supported by the live backend.'));
    }
    await this.command('/projects', { title, goal, surface: 'easy', target_input });
  }

  saveLabOrder(draft: ProductLabOrderDraft) {
    return this.performLabOrder('save', draft);
  }
  quoteLabOrder() {
    return this.performLabOrder('quote');
  }
  submitLabOrder() {
    return this.performLabOrder('submit', undefined, 'SIMULATED_ORDER_ONLY');
  }
}
