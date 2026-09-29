import { LiveProductStore, type LiveProductPort } from '../data/LiveProductStore';
import type { ProductLabOrderDraft } from '../data/product-contracts';
export { ApiError } from '../data/LiveProductStore';

export interface LiveWorkbenchPort extends LiveProductPort {
  applyLabOrder(
    action: 'save' | 'quote' | 'submit',
    draft?: ProductLabOrderDraft,
    acknowledgement?: 'SIMULATED_ORDER_ONLY',
  ): Promise<void>;
}

/** Pro uses the full server projection; scheduling and commands belong to the store. */
export class LiveWorkbenchAdapter extends LiveProductStore implements LiveWorkbenchPort {
  async applyLabOrder(
    action: 'save' | 'quote' | 'submit',
    draft?: ProductLabOrderDraft,
    acknowledgement?: 'SIMULATED_ORDER_ONLY',
  ) {
    await this.performLabOrder(action, draft, acknowledgement);
  }
}
