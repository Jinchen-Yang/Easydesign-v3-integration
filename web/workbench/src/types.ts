export type StageState =
  | "draft"
  | "validating"
  | "ready"
  | "queued"
  | "running"
  | "awaiting-human-approval"
  | "succeeded"
  | "scientific-stop"
  | "operational-failed"
  | "not-reached"
  | "simulated-preview";

export interface Artifact {
  artifact_id: string;
  role: string;
  file_format: string;
  size_bytes: number;
  sha256: string;
  token: string;
}

export interface Stage {
  stage_number: number;
  stage_id: string;
  title: string;
  state: StageState;
  capability: { status: string; summary: string };
  summary: string;
  evidence_status: string;
  selected_attempt_id?: string;
  started_at?: string;
  completed_at?: string;
  highlights: Record<string, unknown>;
  tables: Record<string, Array<Record<string, unknown>>>;
  artifacts: Artifact[];
}

export interface Run {
  run_key: string;
  project_id: string;
  run_id: string;
  status: string;
  evidence_status: string;
  workflow_state?: string;
  created_at: string;
  updated_at: string;
  completed_at?: string;
  code_version: string;
  code_commit?: string;
  profile_id?: string;
  integrity_status: string;
  stages: Stage[];
}

export interface Project {
  project_id: string;
  run_count: number;
  latest_run?: Run;
  runs: Run[];
}

export interface ProjectResponse {
  projects: Project[];
  editable_projects: string[];
}

export interface ReplayFrame {
  frame_id: string;
  label: string;
  stage_number?: number;
  state: StageState;
  description: string;
}

export interface Replay {
  replay_id: string;
  source_run_key: string;
  source_manifest_sha256: string;
  banner: string;
  frames: ReplayFrame[];
}

export interface FilterOverview {
  run_key: string;
  state: StageState;
  conclusion_title: string;
  conclusion: string;
  next_actions: string[];
  counts: Record<string, number>;
  tier_counts: Record<string, number>;
  step_chain: Array<{ id: string; label: string; count: number }>;
  failed_rule_counts: Record<string, number>;
}

export interface Strategy {
  strategy_id: string;
  region_id: string;
  scaffold_id: string;
  candidate_count: number;
  unique_sequence_count: number;
  hard_pass_count: number;
  final_gate_pass_count: number;
  final_gate_pass_rate: number;
  tier: string;
  score_screen: number;
  score_yaml: number;
  selected_for_expansion: boolean;
}

export interface CandidateListItem {
  candidate_id: string;
  phase: string;
  strategy_id: string;
  sequence_length?: number;
  gate_status: string;
  score?: number;
  metrics: Record<string, number | string | boolean | null>;
  failed_rules: string[];
}

export interface CandidatePage {
  phase: string;
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
  items: CandidateListItem[];
}

export interface CandidateDetail {
  candidate_id: string;
  phase: string;
  strategy_id: string;
  sequence?: string;
  gate_status: string;
  score?: number;
  metrics: Array<Record<string, unknown>>;
  decisions: Array<Record<string, unknown>>;
  failed_reasons: string[];
  backend_metrics: Record<string, number | string | boolean | null>;
  structures: Record<string, Artifact>;
}

export interface MetricPresentation {
  metric_id: string;
  name: string;
  abbreviation?: string;
  group: string;
  definition: string;
  unit?: string;
  source: string;
  direction: string;
  role: string;
  missing_value_policy: string;
  operator?: string;
  threshold?: number | string | boolean;
}

export interface MolstarViewer {
  plugin: {
    managers: { camera: { reset: () => void } };
    dispose?: () => void;
  };
  dispose?: () => void;
}

declare global {
  interface Window {
    molstar?: {
      Viewer: {
        create: (element: string, options: Record<string, unknown>) => Promise<MolstarViewer>;
      };
      PluginExtensions: {
        mvs: {
          createBuilder: () => any;
          loadMVS: (
            plugin: MolstarViewer["plugin"],
            state: unknown,
            options: Record<string, unknown>,
          ) => Promise<void>;
        };
      };
    };
  }
}
