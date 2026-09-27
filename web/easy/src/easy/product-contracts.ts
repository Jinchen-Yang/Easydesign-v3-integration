/** Product API v1. No Agent objects, model prose parsing, or filesystem paths. */
export type GateAction = 'approve' | 'revise' | 'reject' | 'override';
export interface Artifact {
  id: string;
  label: string;
  url: string;
  format: string;
  sha256: string;
  size_bytes: number;
  role: string;
  candidate_id: string | null;
}
export interface Metric {
  id: string;
  label: string;
  value: number | string | boolean | null;
  unit: string | null;
  direction: 'lower' | 'higher' | 'context';
  status: string;
  rule_result: string | null;
  threshold: number | null;
  profile_id: string | null;
  source: string | null;
}
export interface Candidate {
  id: string;
  arm: string;
  backend_id: string | null;
  scaffold: string | null;
  native_status: string;
  evaluable: boolean;
  competition_eligible: boolean;
  independent_prediction: string;
  sequence: string | null;
  sequence_sha256: string;
  metrics: Metric[];
  artifacts: Artifact[];
  panel_role: string | null;
  failure_reason: string | null;
  lineage: Record<string, unknown>;
  structure_roles: Record<string, string>;
}
export interface Project {
  id: string;
  title: string;
  goal: string;
  thread_id: string | null;
  phase: string;
  status: string;
  last_activity: number;
  validation_only: boolean;
  notice?: string;
}
export interface GateOption {
  option_id: string;
  label?: string;
  description?: string;
  eligible: boolean;
  actions: GateAction[];
  rank?: string;
  priority?: string;
  design_labels?: number[];
  major_risks?: string[];
  uncertainty?: string[];
  confidence?: string;
  [key: string]: unknown;
}
export interface Decision {
  id: string;
  gate: number;
  type: string;
  question: string;
  default_option_id: string;
  options: GateOption[];
  warnings: string[];
  limitations: string[];
  action_summary: string;
  revision_targets: string[];
  review_status: string | null;
  required_fields: Record<string, string[]>;
  summary: Record<string, unknown>;
  details_url?: string;
  summary_is_excerpt?: boolean;
}
export interface Site {
  id: string;
  rank: string;
  name: string;
  selectable: boolean;
  design_labels: number[];
  why_ranked: string;
  risks: string[];
  uncertainty: string[];
  confidence: string;
  coordinates: {
    author_chain_id: string;
    author_residue_id: string;
    insertion_code?: string;
    [key: string]: unknown;
  }[];
}
export interface RequestState {
  kind?: string;
  id: string;
  project: string;
  state: string;
  result: { message?: string; code?: string; status?: string } | null;
  created: number;
  updated: number;
}
export interface ProductSnapshot {
  schema_version: '1';
  mode: 'live';
  revision: string;
  project: Project;
  workflow: {
    id: string;
    label: string;
    status: string;
    gate: number | null;
    subtasks?: { label: string; status: 'waiting' | 'running' | 'complete' }[];
  }[];
  current_action: { id: string; stage: string; message: string; resumable: boolean };
  specialists: { role: string; status: string; description?: string }[];
  scientific_context: {
    target?: Record<string, unknown>;
    target_intent?: Record<string, unknown>;
    target_source?: Record<string, unknown>;
    target_id?: string;
    sequence_length?: number;
    chains?: string[];
    structure: Artifact | null;
    sites: Site[];
    approved_site?: {
      selected_candidate_id: string | null;
      selected_rank: string | null;
      hotspots: Record<string, unknown>;
    };
    arms: Record<string, unknown>[];
    design_approved?: boolean;
    campaign?: Record<string, unknown>;
    panel?: Record<string, unknown>;
  };
  decision: Decision | null;
  jobs: {
    id: string;
    phase: string;
    status: string;
    resumable: boolean;
    validation_only: boolean;
    progress?: {
      stage_id: string;
      status: string;
      completed: number;
      total: number;
      completed_tasks: number;
      total_tasks: number;
      running_tasks: number;
      estimated_remaining_seconds: number | null;
      substage: string | null;
      substage_label: string | null;
      substage_completed: number | null;
      substage_total: number | null;
      pipeline_step: number | null;
      pipeline_steps: number | null;
    };
  }[];
  artifacts: Artifact[];
  conversation?: {
    id: string;
    kind: 'user' | 'summary' | 'note';
    text: string;
    phase: string;
    retry_request_id?: string;
  }[];
  recent_activity: {
    id: number;
    visible?: boolean;
    type: string;
    text?: string;
    summary?: string;
    title?: string;
    role?: string | null;
    specialist?: string | null;
    tool?: string | null;
    status?: string | null;
    task_id?: string | null;
    phase?: string;
    progress?: { completed?: number; total?: number; label?: string };
  }[];
  tasks: {
    id: number;
    type: string;
    task_id: string;
    title?: string;
    summary?: string;
    status?: string | null;
    specialist?: string | null;
    role?: string | null;
    phase?: string;
    progress?: { completed?: number; total?: number; label?: string };
  }[];
  lifecycle: string;
  event_cursor: number;
  candidates: { total: number; counts: Record<string, number>; url: string };
  capabilities: Record<string, boolean>;
  requests: RequestState[];
  lab_order: LabOrderView | null;
  connection: string;
}
export interface Page<T> {
  items: T[];
  total: number;
  offset: number;
  limit: number;
  revision?: string;
}
export interface LiveState {
  connection: 'loading' | 'connected' | 'reconnecting' | 'authentication-required';
  projects: Page<Project>;
  snapshot: ProductSnapshot | null;
  candidates: Page<Candidate>;
  selectedCandidate: Candidate | null;
  selectedProject: string | null;
  pending: boolean;
  error: string | null;
  pendingRequest: RequestState | null;
}
export interface GateInput {
  action: GateAction;
  selected_option_id: string;
  instruction?: string;
  revision_target?: string;
  acknowledgement?: string;
  reason?: string;
}

export interface LabOrderCandidate {
  id: string;
  selection_class: string;
  selection_rank: number;
  sequence_length: number;
  sequence_sha256: string;
  sequence_ready: boolean;
}

export interface LabOrderView {
  schema_version: '1';
  mode: 'simulation';
  provider: 'mock-lab-v1';
  project_id: string;
  handoff_sha256: string;
  handoff_status: string;
  ordering_status: string;
  revision: string;
  candidates: LabOrderCandidate[];
  draft: Record<string, unknown> | null;
  quote: Record<string, unknown> | null;
  receipt: Record<string, unknown> | null;
  capabilities: { save: boolean; quote: boolean; submit: boolean; real_order: false };
  disclaimer: string;
}

export interface LabOrderDraftInput {
  schema_version: '1';
  candidate_ids: string[];
  requirements: {
    format: 'VHH' | 'VHH-Fc';
    amount: string;
    host: string;
    buffer: string;
    profile: 'simulation-lab';
    preferred_date: string;
    purchase_order: string;
    sds_purity: string;
    sec_purity: string;
    endotoxin: string;
    concentration: string;
    notes: string;
  };
  reviewed: true;
}
