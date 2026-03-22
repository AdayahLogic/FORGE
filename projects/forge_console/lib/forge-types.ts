export type CommandResult<T> = {
  status: "ok" | "error";
  message: string;
  payload: T;
};

export type ForgeProjectRow = {
  project_key: string;
  project_name: string;
  description: string;
  workspace_type: string;
  dispatch_status: string;
  governance_status: string;
  enforcement_status: string;
  lifecycle_status: string;
  queue_status: string;
  current_package_id: string;
  current_package_path: string;
  latest_evaluation_status: string;
  latest_local_analysis_status: string;
  executor_health: string;
};

export type ForgeOverviewSnapshot = {
  generated_at: string;
  studio_name: string;
  overview: {
    studio_health: string;
    aegis_posture: Record<string, unknown>;
    queue_counts: Record<string, number>;
    package_counts: Record<string, number>;
    evaluation_counts: {
      pending: number;
      completed: number;
      blocked: number;
      error: number;
      bands: Record<string, Record<string, number>>;
    };
    local_analysis_counts: {
      pending: number;
      completed: number;
      blocked: number;
      error: number;
      confidence_bands: Record<string, number>;
      next_actions: Record<string, number>;
    };
    project_count: number;
    executor_health: Record<string, unknown>;
  };
  projects: ForgeProjectRow[];
  approval_center: {
    approval_summary: Record<string, unknown>;
    approval_lifecycle: Record<string, unknown>;
    allowed_actions: string[];
    surface_mode: string;
  };
  raw: {
    dashboard_summary: Record<string, unknown>;
  };
};

export type PackageQueueRow = {
  package_id: string;
  created_at: string;
  package_status: string;
  review_status: string;
  runtime_target_id: string;
  decision_status: string;
  eligibility_status: string;
  release_status: string;
  handoff_status: string;
  execution_status: string;
  evaluation_status: string;
  failure_class: string;
  recovery_status: string;
  retry_policy_status: string;
  retry_authorized: boolean;
  idempotency_status: string;
  duplicate_success_blocked: boolean;
  rollback_repair_status: string;
  integrity_status: string;
  failure_risk_band: string;
  local_analysis_status: string;
  suggested_next_action: string;
};

export type PackageDetailSnapshot = {
  package_id: string;
  project_key: string;
  project_path: string;
  review_header: Record<string, unknown>;
  sections: Record<string, unknown>;
  evaluation: Record<string, unknown>;
  local_analysis: Record<string, unknown>;
  package_json: Record<string, unknown>;
  timeline: Array<Record<string, unknown>>;
};

export type ProjectSnapshot = {
  project_key: string;
  project_name: string;
  project_path: string;
  project_meta: Record<string, unknown>;
  project_summary: Record<string, unknown>;
  project_state: Record<string, unknown>;
  latest_session: Record<string, unknown>;
  system_health: Record<string, unknown>;
  package_queue: {
    project_key: string;
    project_path: string;
    count: number;
    pending_count: number;
    packages: PackageQueueRow[];
  };
  current_package: PackageDetailSnapshot | null;
  approval_summary: Record<string, unknown>;
  degraded_sources: string[];
};

export type ApprovalCenterState = {
  lastActionStatus: "idle" | "submitting" | "success" | "error";
  lastActionMessage: string;
  requiredConfirmationPhrase: string;
};

export type ControlDraft = {
  action: string;
  confirmationText: string;
  confirmed: boolean;
  submitting: boolean;
};

export type DataFreshness = "idle" | "loading" | "ready" | "stale" | "error";

export type SurfaceMode = "read_only" | "supervised_control";

export type ForgeUiState = {
  selectedProjectKey: string;
  selectedPackageId: string;
  boardFilters: {
    showOnlyRisk: boolean;
    includeCompleted: boolean;
  };
  detailDrawerOpen: boolean;
  overviewSnapshot: ForgeOverviewSnapshot | null;
  projectSnapshot: ProjectSnapshot | null;
  packageQueue: PackageQueueRow[];
  packageDetail: PackageDetailSnapshot | null;
  approvalCenterState: ApprovalCenterState;
  controlDraft: ControlDraft;
  dataFreshness: DataFreshness;
  surfaceMode: SurfaceMode;
  degradedSources: string[];
};
