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
  access?: {
    stage_number: number;
    access: "configure" | "running" | "view-only" | "not-reached";
    locked_by_stage?: number;
    locked_at?: string;
    reason: string;
    allowed_actions: string[];
  };
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

export interface ProjectDraft {
  project_id: string;
  target_id: string;
  input_type: string;
  status: "draft";
  configured_through_stage: number;
  updated_at: string;
  config_sha256: string;
  session_id?: string;
}

export interface ProjectResponse {
  projects: Project[];
  drafts: ProjectDraft[];
  editable_projects: string[];
}

export interface DesignSession {
  schema_version: "0.1";
  session_id: string;
  project_id: string;
  design_mode: "full-workflow" | "stepwise" | "developer-smoke";
  execution_mode: "unattended" | "review-gated";
  current_stage: number;
  status: string;
  config_revisions: Array<{
    revision: number;
    stage_number: number;
    relative_path: string;
    sha256: string;
    created_at: string;
  }>;
  run_lineage: string[];
  created_at: string;
  updated_at: string;
}

export interface StageFormDefinition {
  schema_version: "0.1";
  stage_number: number;
  title: string;
  defaults: Record<string, unknown>;
  presentation: {
    description: string;
    action_label: string;
    facts: Array<{
      label: string;
      value: string | number | boolean;
      note?: string;
    }>;
  };
}

export interface UiJobRecord {
  job_id: string;
  status: string;
  run_key?: string;
  run_id?: string;
  error?: string;
  stage_number?: number;
}

export interface ProjectCatalogEntry {
  project_id: string;
  category: "project-run" | "archived-project-run" | "developer-smoke-run";
  run_count: number;
  paths: string[];
}

export interface RegionEditorResidue {
  label_seq_id: number;
  amino_acid: string;
  sequence_index: number;
  auth_chain_id: string;
  auth_residue_id: string;
  insertion_code?: string;
  reference_position?: number;
  source_color?: string;
  current_region?: "A" | "B" | "C";
}

export interface RegionEditorProjection {
  run_key: string;
  target_id: string;
  target_structure_sha256: string;
  residue_mapping_sha256: string;
  structure: Artifact;
  source_annotation_status: string;
  current_region_source?: string;
  residues: RegionEditorResidue[];
}

export type AssistantProviderId = "deepseek" | "zhipu-glm";

export interface AssistantProviderStatus {
  provider: AssistantProviderId;
  configured: boolean;
  model?: string;
  base_url?: string;
  api_key_masked?: string;
}

export interface AssistantServiceStatus {
  available: boolean;
  service_name: "EasyDesign 结构助手";
  detail: string;
}

export interface ViewerAction {
  action:
    | "representation"
    | "color"
    | "background"
    | "focus"
    | "orient"
    | "center"
    | "label"
    | "unlabel"
    | "select"
    | "deselect";
  target: string;
  value?: string;
}

export interface RegionEditOperation {
  operation: "add" | "remove" | "toggle" | "replace" | "clear";
  region_id: "A" | "B" | "C";
  numbering: "label" | "auth" | "sequence" | "uniprot";
  chain?: string;
  residues: string[];
}

export interface ScientificAnalysisPlan {
  methods: Array<"sasa" | "scannet">;
  requires_confirmation: true;
  reason: string;
}

export interface PmlEditProposal {
  assistant_message: string;
  summary: string;
  conversation_title: string;
  pml: string;
}

export interface ViewControlOperation {
  action: "undo-last-view-action" | "reset-default-view";
}

export interface AssistantProposal {
  proposal_id: string;
  kind: "pml-edit" | "viewer-actions" | "region-edit" | "analysis-plan" | "view-control" | "explanation";
  explanation: string;
  pml_edit?: PmlEditProposal;
  viewer_actions: ViewerAction[];
  region_operations: RegionEditOperation[];
  analysis_plan?: ScientificAnalysisPlan;
  view_control?: ViewControlOperation;
}

export interface InteractionMessage {
  message_id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
  provider?: AssistantProviderId;
  model?: string;
  request_id?: string;
  version_id?: string;
  proposal?: AssistantProposal;
}

export interface SceneVersion {
  version_id: string;
  revision: number;
  parent_version_id?: string;
  base_version_id?: string;
  actor: "human" | "ai" | "viewer" | "system";
  source: string;
  summary: string;
  pml: string;
  sha256: string;
  created_at: string;
}

export interface ReferenceStructure {
  object_id: string;
  role: "target" | "reference";
  object_name: string;
  filename: string;
  file_format: string;
  sha256: string;
  source: string;
  created_at: string;
}

export interface PmlRevision {
  revision: number;
  pml: string;
  source: "viewer" | "assistant" | "expert-console";
  created_at: string;
}

export interface StructureInteractionSession {
  schema_version: "0.1" | "0.2" | "0.3";
  session_id: string;
  project_id: string;
  run_key: string;
  stage_number: 1 | 2;
  target_structure_sha256: string;
  residue_mapping_sha256: string;
  selected_provider?: AssistantProviderId;
  messages: InteractionMessage[];
  pml_revisions: PmlRevision[];
  view_state_revisions?: Array<{
    revision: number;
    actions: ViewerAction[];
    source: "viewer" | "assistant";
    created_at: string;
  }>;
  scene_versions?: SceneVersion[];
  active_scene_version_id?: string;
  reference_structures?: ReferenceStructure[];
  current_regions: Partial<Record<"A" | "B" | "C", number[]>>;
  created_at: string;
  updated_at: string;
}

export interface SelfTestRecord {
  schema_version: "0.1";
  self_test_id: string;
  mode: "deterministic-seven-stage" | "real-backend-micro";
  status: string;
  engineering_status: string;
  backend_status: string;
  scientific_status: string;
  stage_statuses: Record<string, string>;
  run_key?: string;
  run_relative_path?: string;
  current_stage: number;
  next_stage?: number;
  active_job_id?: string;
  config_relative_path?: string;
  fixture_asset_id?: string;
  environment: Record<string, string>;
  created_at: string;
  updated_at: string;
  message: string;
}

export interface RuntimeInstallItem {
  environment_id?: string;
  asset_id?: string;
  status: string;
  license?: string;
  license_confirmation_required?: boolean;
  destination?: string;
  current?: Record<string, unknown>;
}

export interface SetupJob {
  job_id: string;
  status: string;
  pid?: number;
  started_at: string;
  completed_at?: string;
  minimal: boolean;
  component?: string;
  accepted_license_ids: string[];
  return_code?: number;
  stdout_relative_path: string;
  stderr_relative_path: string;
  error?: string;
}

export interface InstallStatus {
  workspace: string;
  plan: {
    disk: {
      free_bytes: number;
      incremental_peak_bytes: number;
      reserve_bytes: number;
      sufficient: boolean;
    };
  };
  component_plans: Record<string, {
    component?: string;
    disk: {
      free_bytes: number;
      incremental_peak_bytes: number;
      reserve_bytes: number;
      sufficient: boolean;
    };
  }>;
  environments: RuntimeInstallItem[];
  assets: RuntimeInstallItem[];
  jobs: SetupJob[];
  quarantine: {
    path: string;
    entries: number;
  };
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

export interface TaskExecution {
  task_id: string;
  strategy_id: string;
  status: string;
  requested_candidates: number;
  collected_candidates: number;
  attempt_count: number;
  retry_count: number;
  last_device?: number;
  latest_heartbeat_at?: string;
  heartbeat_elapsed_seconds?: number;
  heartbeat_message?: string;
}

export interface DeviceExecution {
  device: number;
  current_task_id?: string;
  current_strategy_id?: string;
  assigned_task_count: number;
  succeeded_task_count: number;
  attempt_count: number;
  failed_attempt_count: number;
  collected_candidates: number;
  busy_seconds: number;
  latest_heartbeat_at?: string;
  heartbeat_elapsed_seconds?: number;
  heartbeat_message?: string;
  tasks: TaskExecution[];
}

export interface RemoteExecutor {
  executor_id: string;
  label: string;
}

export interface RemoteJob {
  executor_id: string;
  job_id: string;
  project_id: string;
  run_id: string;
  submitted_at: string;
  active_unit_name: string;
  resume_count: number;
}

export interface ExecutionProgress {
  stage_number: number;
  stage_id: string;
  status: string;
  updated_at: string;
  total_tasks: number;
  pending_tasks: number;
  waiting_tasks: number;
  running_tasks: number;
  succeeded_tasks: number;
  failed_tasks: number;
  planned_candidates: number;
  collected_candidates: number;
  elapsed_seconds: number;
  throughput_candidates_per_hour?: number;
  estimated_remaining_seconds?: number;
  device_history_status: string;
  devices: DeviceExecution[];
  strategies?: Array<{
    strategy_id: string;
    task_count: number;
    succeeded_task_count: number;
    failed_task_count: number;
    requested_candidates: number;
    collected_candidates: number;
  }>;
  recent_events: Array<Record<string, unknown>>;
  recent_errors: string[];
}

export interface FilterOverview {
  run_key: string;
  state: StageState;
  advisory_validation: boolean;
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
  score_screen_top_quartile_mean: number;
  score_yaml: number;
  selected_for_expansion: boolean;
  promotion_rank?: number;
  advisory_status?: "advisory-supported" | "advisory-warning";
  diagnostic_warning_count: number;
  diagnostic_candidate_count?: number;
  diagnostic_local_gate_pass_count?: number;
  diagnostic_full_target_count?: number;
  diagnostic_full_target_pass_count?: number;
  configuration: Record<string, unknown>;
  metric_aggregates: Array<{
    metric_id: string;
    observed_count: number;
    missing_count: number;
    mean?: number;
    median?: number;
    minimum?: number;
    maximum?: number;
  }>;
  yaml_artifact?: Artifact;
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
  subscribe?: (
    subject: unknown,
    handler: (event: any) => void,
  ) => { unsubscribe?: () => void };
  plugin: {
    behaviors?: {
      interaction?: {
        click?: unknown;
      };
    };
    managers: {
      camera: { reset: () => void };
      structure?: {
        hierarchy?: {
          current?: {
            structures?: unknown[];
          };
        };
      };
    };
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
      lib?: {
        structure?: {
          StructureElement?: {
            Loci?: {
              is: (value: unknown) => boolean;
              forEachLocation: (
                value: unknown,
                callback: (location: unknown) => void,
              ) => void;
            };
          };
          StructureProperties?: {
            chain?: {
              label_asym_id: (location: unknown) => string;
            };
            residue?: {
              label_seq_id: (location: unknown) => number;
            };
          };
        };
      };
    };
  }
}
