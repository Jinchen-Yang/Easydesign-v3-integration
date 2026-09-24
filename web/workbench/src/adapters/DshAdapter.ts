import type {
  WorkbenchAdapter,
  WorkbenchEdit,
  WorkbenchEvent,
  WorkbenchSnapshot,
  WorkflowPhase,
} from './WorkbenchAdapter';
import type { LabOrderDraft } from '../domain/labOrder';

export const DSH_PHASE_MAPPING: Record<WorkflowPhase, string> = {
  goal: 'prepare',
  target: 'prepare',
  site: 'prepare',
  design: 'strategize',
  pilot: 'pilot',
  scale: 'scale',
  candidates: 'select',
};

/** Deliberately unavailable. Future integration must supply structured server events.
 * Never infer stage/approval authority from assistant prose or simulate DSH success.
 */
export class DshAdapter implements WorkbenchAdapter {
  async load(): Promise<WorkbenchSnapshot> {
    throw new Error('DSH integration is not configured. Use the standalone demo.');
  }
  subscribe(_cb: (event: WorkbenchEvent) => void): () => void {
    return () => {};
  }
  async sendMessage(_text: string): Promise<void> {
    throw new Error('DSH integration is not configured.');
  }
  async createProject(_goal: string): Promise<void> {
    throw new Error('DSH project transport is not configured.');
  }
  async selectProject(_projectId: string): Promise<void> {
    throw new Error('DSH project transport is not configured.');
  }
  async renameProject(_projectId: string, _title: string): Promise<void> {
    throw new Error('DSH project transport is not configured.');
  }
  async deleteProject(_projectId: string): Promise<void> {
    throw new Error('DSH project deletion is not configured.');
  }
  async approve(_id: string): Promise<void> {
    throw new Error('DSH approval transport is not configured.');
  }
  async edit(_id: string, _payload: WorkbenchEdit): Promise<void> {
    throw new Error('DSH integration is not configured.');
  }
  async resetDemo(): Promise<void> {
    throw new Error('Demo controls are not available in DSH mode.');
  }
  async saveLabOrder(_draft: LabOrderDraft): Promise<void> {
    throw new Error('Lab ordering is not configured.');
  }
  async replayDemo(): Promise<void> {
    throw new Error('Demo controls are not available in DSH mode.');
  }
  async skipAnimation(): Promise<void> {
    throw new Error('Demo controls are not available in DSH mode.');
  }
  dispose(): void {}
}
