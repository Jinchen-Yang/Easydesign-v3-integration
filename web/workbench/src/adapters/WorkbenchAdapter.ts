/** Product contract. Components never read fixture files or DSH internals. */
import type { LabOrderDraft } from '../domain/labOrder';
export const PHASES = ['goal', 'target', 'site', 'design', 'pilot', 'scale', 'candidates'] as const;
export type WorkflowPhase = (typeof PHASES)[number];
export type WorkflowStatus = 'complete' | 'current' | 'locked' | 'approval';
export type ActivityStatus = 'waiting' | 'running' | 'complete';
export interface WorkflowTask {
  id: WorkflowPhase;
  label: string;
  status: WorkflowStatus;
  subtasks: { label: string; status: ActivityStatus }[];
}
export interface ConversationItem {
  id: string;
  phase: WorkflowPhase;
  kind: 'user' | 'summary' | 'tool' | 'note';
  title?: string;
  text: string;
  detail?: string;
  focus?: WorkflowPhase;
}
export interface Specialist {
  name: string;
  role: string;
  status: ActivityStatus;
}
export interface SiteOption {
  id: string;
  label: string;
  residues: string[];
  accessibility: number;
  geometry: number;
  evidence: number;
  recommended?: boolean;
}
export interface Candidate {
  id: string;
  rank?: number;
  status: 'pass' | 'filtered';
  interface: number;
  confidence: number;
  clash?: number;
  developability?: number;
  sequencePreview: string;
  length: number;
}
export interface StructureReference {
  pdbId: string;
  sourceUrl: string;
  localUrl: string;
  targetName: string;
  uniprot: string;
  targetChain: string;
  targetLabelChain?: string | null;
  binderChain: string;
  targetSequence: string;
  binderSequence: string;
}
export interface ScientificContext {
  phase: WorkflowPhase;
  structure: StructureReference;
  sites: SiteOption[];
  selectedSite: string;
  approvedSite?: string;
  scaffold: string;
  arms: { id: string; label: string; count: number }[];
  pilotCandidates: Candidate[];
  finalists: Candidate[];
  selectedCandidate: string;
  shortlisted: string[];
  scale: {
    total: number;
    batches: number;
    batchSize: number;
    completedBatches: number;
    passed: number;
    filtered: number;
  };
}
export interface DecisionState {
  id: string;
  phase: WorkflowPhase;
  title: string;
  description: string;
  label: string;
}
export interface DesignProject {
  id: string;
  title: string;
  goal: string;
  phase: WorkflowPhase;
  status: 'not-started' | 'running' | 'paused' | 'review' | 'complete';
}
export interface WorkbenchSnapshot {
  version: 1;
  started: boolean;
  completed: boolean;
  busy: boolean;
  phase: WorkflowPhase;
  project: { id: string | null; title: string; goal: string; exampleGoal: string; badge: string };
  projects: DesignProject[];
  compute: {
    connection: 'demo-only';
    runs: {
      id: string;
      projectId: string;
      projectTitle: string;
      phase: 'pilot' | 'scale';
      status: 'running' | 'paused' | 'complete';
      prepared: number;
      total: number;
    }[];
  };
  tasks: WorkflowTask[];
  messages: ConversationItem[];
  specialists: Specialist[];
  context: ScientificContext;
  decision?: DecisionState;
  mode: 'demo';
  labOrder: LabOrderDraft | null;
  notice?: string;
}
export interface WorkbenchEvent {
  type: 'snapshot';
  snapshot: WorkbenchSnapshot;
}
export type WorkbenchEdit =
  | { type: 'site'; siteId: string }
  | { type: 'candidate'; candidateId: string }
  | { type: 'shortlist'; candidateId: string }
  | { type: 'scaffold'; scaffold: string }
  | { type: 'revise-pilot' };
export interface WorkbenchAdapter {
  load(): Promise<WorkbenchSnapshot>;
  subscribe(cb: (event: WorkbenchEvent) => void): () => void;
  sendMessage(text: string): Promise<void>;
  createProject(goal: string): Promise<void>;
  selectProject(projectId: string): Promise<void>;
  renameProject(projectId: string, title: string): Promise<void>;
  deleteProject(projectId: string): Promise<void>;
  approve(decisionId: string): Promise<void>;
  edit(decisionId: string, payload: WorkbenchEdit): Promise<void>;
  saveLabOrder(draft: LabOrderDraft): Promise<void>;
  resetDemo(): Promise<void>;
  replayDemo(): Promise<void>;
  skipAnimation(): Promise<void>;
  dispose(): void;
}
