export type CommandResult<T> = {
  status: "ok" | "error";
  message: string;
  payload: T;
};

export type ForgeSystemStatus = {
  backend_reachable: boolean;
  status: "online" | "offline";
  label: string;
  reason: string;
};

export type ForgeWorkflowActivity = {
  current_phase: "planning" | "routing" | "execution" | "review";
  phase_label: string;
  last_action: string;
  current_project: string;
  active_package_id: string;
  package_status: string;
  package_created_at: string;
};

export type ForgeLifecycleTransition = {
  stage_id: string;
  stage_label: string;
  state: string;
  detail: string;
  occurred_at: string;
};

export type ForgeExecutionFeedback = {
  package_created: boolean;
  package_created_at: string;
  package_status: string;
  status_summary: string;
  active_transition: string;
  lifecycle_transitions: ForgeLifecycleTransition[];
};

export type ForgeDeliverySummary = {
  delivery_status: string;
  delivery_summary_title: string;
  delivery_summary_text: string;
  delivered_artifact_types: string[];
  delivered_artifact_labels: string[];
  delivered_artifact_count: number;
  delivery_progress_state:
    | "no_delivery_summary"
    | "delivery_summary_ready"
    | "delivery_in_progress"
    | "client_safe_packaging_ready"
    | "internal_review_required"
    | string;
  client_ready_notes: string;
  internal_details_redacted: boolean;
  packaging_reason: string;
  authority_trace?: Record<string, unknown>;
  governance_trace?: Record<string, unknown>;
};

export type ForgeEstimatedCost = {
  cost_estimate: number;
  cost_unit: "usd_estimated" | string;
  cost_source: "model_execution" | "runtime_execution" | "composed_operation" | string;
  cost_breakdown: {
    model: string;
    estimated_tokens: number;
    estimated_cost: number;
  };
};

export type ForgeBudgetCaps = {
  session_budget_cap: number;
  project_budget_cap: number;
  operation_budget_cap: number;
  kill_switch_enabled: boolean;
};

export type ForgeBudgetControl = {
  budget_caps: ForgeBudgetCaps;
  budget_status:
    | "within_budget"
    | "approaching_cap"
    | "cap_exceeded"
    | "kill_switch_triggered";
  budget_scope: "operation" | "project" | "session";
  budget_cap: number;
  current_estimated_cost: number;
  remaining_estimated_budget: number;
  kill_switch_active: boolean;
  budget_reason: string;
};

export type ForgeModelLane =
  | "low_cost_lane"
  | "balanced_lane"
  | "high_reasoning_lane"
  | "governed_high_sensitivity_lane"
  | "";

export type ForgeModelRoutingOutcome =
  | "route_low_cost"
  | "route_balanced"
  | "route_high_reasoning"
  | "route_governed_high_sensitivity"
  | "route_blocked_by_budget"
  | "route_deferred_for_review";

export type ForgeModelRoutingPolicy = {
  task_type: string;
  task_complexity: string;
  task_risk_level: string;
  cost_sensitivity: string;
  budget_status: string;
  selected_model_lane: ForgeModelLane;
  routing_reason: string;
  routing_status: string;
  routing_outcome: ForgeModelRoutingOutcome | string;
  budget_aware_note: string;
  authority_trace: Record<string, unknown>;
  governance_trace: Record<string, unknown>;
};

export type ForgeConstraintSections = {
  scope_boundaries: string[];
  risk_notes: string[];
  runtime_preferences: string[];
  output_expectations: string[];
  review_expectations: string[];
};

export type ForgeRequestedArtifactsDraft = {
  selected: string[];
  custom: string[];
};

export type ForgeLeadQualificationDraft = {
  budget_band: string;
  urgency: string;
  problem_clarity: string;
  decision_readiness: string;
  fit_notes: string;
};

export type ForgeLeadQualificationSummary = {
  qualification_status:
    | "underqualified"
    | "needs_more_info"
    | "qualified"
    | "high_priority";
  qualification_signals: {
    budget_band: string;
    urgency: string;
    problem_clarity: string;
    decision_readiness: string;
  };
  missing_qualification_fields: string[];
  lead_readiness_level: string;
  qualification_reasoning_summary: string;
};

export type ForgeRevenueOfferStatus =
  | "no_offer_yet"
  | "offer_needs_more_info"
  | "offer_ready"
  | "high_touch_review_recommended";

export type ForgeRevenueOfferSummary = {
  offer_status: ForgeRevenueOfferStatus;
  recommended_service_type: string;
  recommended_package_tier: string;
  estimated_complexity_band: string;
  pricing_direction: string;
  offer_reasoning_summary: string;
  offer_constraints_or_notes: string[];
};

export type ForgeRevenueResponseStatus =
  | "no_response"
  | "needs_more_info"
  | "response_ready"
  | "high_touch_required";

export type ForgeRevenueResponseSummary = {
  response_status: ForgeRevenueResponseStatus;
  response_tone: "professional" | "friendly" | "consultative";
  response_message: string;
  response_summary: string;
  response_constraints: string[];
};

export type ForgeRevenueConversionStatus =
  | "conversion_not_ready"
  | "conversion_needs_review"
  | "conversion_ready"
  | "high_touch_conversion_required";

export type ForgeRevenueConversionSummary = {
  conversion_status: ForgeRevenueConversionStatus;
  proposed_project_type: string;
  proposed_project_name: string;
  proposed_scope_summary: string;
  proposed_constraints: string[];
  conversion_reasoning_summary: string;
  conversion_notes: string[];
};

export type ForgeRequestedArtifactDetail = {
  artifact_id: string;
  label: string;
  source: "catalog" | "custom";
};

export type ForgeAutonomyModeDetail = {
  mode: string;
  label: string;
  summary: string;
  operator_posture: string;
};

export type ForgeLeadIntakeProfile = {
  contact_name: string;
  contact_email: string;
  company_name: string;
  contact_channel: string;
  lead_source: string;
  problem_summary: string;
  requested_outcome: string;
  budget_context: string;
  urgency_context: string;
};

export type ForgeCompositionStatus = {
  is_complete: boolean;
  missing_fields: string[];
  warning_count: number;
  stale_preview: boolean;
};

export type ForgeAttachmentRecord = {
  attachment_id: string;
  project_id: string;
  package_id: string;
  request_id: string;
  linked_context: {
    project_id: string;
    package_id: string;
    request_id: string;
  };
  file_name: string;
  file_type: string;
  file_size_bytes: number;
  source: string;
  purpose: string;
  uploaded_at: string;
  trust_level: string;
  allowed_consumers: string[];
  extracted_summary: string;
  status: string;
  classification: string;
  status_reason: string;
  raw_storage_path: string;
  governance_trace: {
    origin: string;
    surface: string;
    classification_reason: string;
    classifier_version: string;
    routing_authority: string;
    execution_authority: string;
    notes: string[];
  };
};

export type ForgeReviewAttachmentRecord = ForgeAttachmentRecord & {
  review_relevance: string;
  review_ready: boolean;
};

export type ForgeReviewCenterSnapshot = {
  package_id: string;
  approval_ready_context: {
    review_status: string;
    sealed: boolean;
    seal_reason: string;
    approval_id_refs: string[];
    requires_human_approval: boolean;
    decision_status: string;
    release_status: string;
    review_checklist: string[];
  };
  returned_artifacts: Array<{
    artifact_type: string;
    summary: string;
    status: string;
    source: string;
  }>;
  patch_context: {
    patch_summary: string;
    changed_files: string[];
    candidate_paths: string[];
    requested_outputs: string[];
  };
  test_results: {
    execution_result_status: string;
    exit_code?: number | null;
    log_ref: string;
    integrity_status: string;
    evaluation_quality_band: string;
    suggested_next_action: string;
  };
  execution_feedback: ForgeExecutionFeedback;
  model_routing_policy?: ForgeModelRoutingPolicy;
  evaluation_summary: Record<string, unknown>;
  local_analysis_summary: Record<string, unknown>;
  related_attachments: ForgeReviewAttachmentRecord[];
  delivery_summary?: ForgeDeliverySummary;
  client_safe_delivery_summary?: ForgeDeliverySummary;
};

export type ForgeIntakePreview = {
  request_id: string;
  request_kind: string;
  intake_mode: "development" | "revenue_lead";
  objective: string;
  project_context: string;
  constraints: string[];
  structured_constraints: ForgeConstraintSections;
  lead_intake_profile: ForgeLeadIntakeProfile;
  requested_artifacts: string[];
  requested_artifact_details: ForgeRequestedArtifactDetail[];
  autonomy_mode: string;
  autonomy_mode_detail: ForgeAutonomyModeDetail;
  composition_status: ForgeCompositionStatus;
  linked_attachments: Array<{
    attachment_id: string;
    file_name: string;
    status: string;
    classification: string;
    allowed_for_request_preview: boolean;
    extracted_summary: string;
  }>;
  readiness: string;
  warnings: string[];
  qualification_summary: ForgeLeadQualificationSummary | null;
  offer_summary: ForgeRevenueOfferSummary | null;
  response_summary: ForgeRevenueResponseSummary | null;
  conversion_summary: ForgeRevenueConversionSummary | null;
  cost_tracking: ForgeEstimatedCost;
  budget_caps: ForgeBudgetCaps;
  budget_control: ForgeBudgetControl;
  budget_status: ForgeBudgetControl["budget_status"];
  budget_scope: ForgeBudgetControl["budget_scope"];
  budget_cap: number;
  current_estimated_cost: number;
  remaining_estimated_budget: number;
  kill_switch_active: boolean;
  budget_reason: string;
  model_routing_policy: ForgeModelRoutingPolicy;
  package_preview: {
    creation_mode: string;
    package_creation_allowed: boolean;
    governance_required: boolean;
    routing_authority: string;
    execution_authority: string;
    routing_status?: string;
    budget_aware_routing_note?: string;
    attachment_input_count: number;
    attachment_preview_count: number;
    summary: string;
  };
};

export type ForgeIntakeWorkspace = {
  project_key: string;
  project_path: string;
  draft_seed: {
    request_kind: string;
    objective: string;
    project_context: string;
    constraints: string[];
    structured_constraints: ForgeConstraintSections;
    requested_artifacts: string[];
    requested_artifacts_draft: ForgeRequestedArtifactsDraft;
    lead_qualification: ForgeLeadQualificationDraft;
    autonomy_mode: string;
    linked_attachment_ids: string[];
    lead_intake_profile: ForgeLeadIntakeProfile;
  };
  attachments: ForgeAttachmentRecord[];
  governance_notes: {
    routing_authority: string;
    execution_authority: string;
    request_status: string;
    allowed_actions: string[];
    blocked_use_cases: string[];
  };
  preview: ForgeIntakePreview;
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
  estimated_cost_total_usd?: number;
  budget_status?: ForgeBudgetControl["budget_status"];
  budget_scope?: ForgeBudgetControl["budget_scope"];
  budget_cap?: number;
  current_estimated_cost?: number;
  remaining_estimated_budget?: number;
  kill_switch_active?: boolean;
  selected_model_lane?: ForgeModelLane;
  routing_status?: string;
  routing_reason?: string;
};

export type ForgeClientProjectRow = {
  project_key: string;
  project_name: string;
  description: string;
  client_status: string;
  current_phase: string;
  progress_percent: number;
  progress_label: string;
  safe_summary: string;
  delivery_summary: ForgeDeliverySummary;
};

export type ForgeClientMilestone = {
  milestone_id: string;
  title: string;
  status: "pending" | "in_progress" | "ready_for_review" | "complete";
  summary: string;
  target_label: string;
};

export type ForgeClientDeliverable = {
  deliverable_id: string;
  title: string;
  status: "pending" | "in_progress" | "ready_for_review" | "complete" | "approved";
  summary: string;
  safe_to_share: boolean;
  approved_at: string;
};

export type ForgeClientAttachment = {
  attachment_id: string;
  file_name: string;
  purpose: string;
  status: string;
  summary: string;
  uploaded_at: string;
};

export type ForgeClientTimelineEvent = {
  event_id: string;
  label: string;
  status: "pending" | "in_progress" | "ready_for_review" | "complete" | "approved";
  summary: string;
  occurred_at: string;
};

export type ForgeClientProjectSnapshot = {
  project_key: string;
  project_name: string;
  description: string;
  client_status: string;
  current_phase: string;
  progress_percent: number;
  progress_label: string;
  safe_summary: string;
  delivery_summary: ForgeDeliverySummary;
  milestones: ForgeClientMilestone[];
  deliverables: ForgeClientDeliverable[];
  approved_attachments: ForgeClientAttachment[];
  timeline: ForgeClientTimelineEvent[];
};

export type ForgeClientViewSnapshot = {
  generated_at: string;
  surface_mode: "client_safe";
  selected_project_key: string;
  projects: ForgeClientProjectRow[];
  project: ForgeClientProjectSnapshot | null;
};

export type ForgeOverviewSnapshot = {
  generated_at: string;
  studio_name: string;
  overview: {
    system_status: ForgeSystemStatus;
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
    cost_visibility?: {
      estimated_cost_total_usd: number;
      project_estimated_cost_usd: Record<string, number>;
      operation_count_total: number;
      label: string;
    };
    budget_visibility?: {
      label: string;
      budget_status: ForgeBudgetControl["budget_status"];
      budget_scope: ForgeBudgetControl["budget_scope"];
      budget_cap: number;
      current_estimated_cost: number;
      remaining_estimated_budget: number;
      kill_switch_active: boolean;
    };
    model_routing_visibility?: {
      policy_output_label: string;
      selected_lane_count: Record<string, number>;
      routing_status_count: Record<string, number>;
      blocked_or_deferred_count: number;
      budget_note: string;
    };
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
  cost_tracking?: ForgeEstimatedCost;
  lifecycle_status_label?: string;
  last_action_label?: string;
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
  delivery_summary?: ForgeDeliverySummary;
  timeline: Array<Record<string, unknown>>;
  execution_feedback: ForgeExecutionFeedback;
  model_routing_policy?: ForgeModelRoutingPolicy;
  cost_summary?: {
    operation_cost: ForgeEstimatedCost;
    timeline_estimated_cost_total: number;
    cost_unit: string;
    label: string;
    budget_caps: ForgeBudgetCaps;
    budget_control: ForgeBudgetControl;
    budget_status: ForgeBudgetControl["budget_status"];
    budget_scope: ForgeBudgetControl["budget_scope"];
    budget_cap: number;
    current_estimated_cost: number;
    remaining_estimated_budget: number;
    kill_switch_active: boolean;
    budget_reason: string;
  };
  review_center: ForgeReviewCenterSnapshot;
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
  system_status: ForgeSystemStatus;
  workflow_activity: ForgeWorkflowActivity;
  approval_summary: Record<string, unknown>;
  delivery_summary?: ForgeDeliverySummary;
  intake_workspace: ForgeIntakeWorkspace | null;
  cost_summary?: {
    cost_per_operation: ForgeEstimatedCost[];
    cost_per_project: {
      estimated_cost_total: number;
      cost_unit: string;
    };
    session_cost_summary: {
      run_id: string;
      estimated_cost_total: number;
      cost_unit: string;
      operation_count: number;
    };
    operation_count: number;
    budget_caps: ForgeBudgetCaps;
    budget_control: ForgeBudgetControl;
    budget_status: ForgeBudgetControl["budget_status"];
    budget_scope: ForgeBudgetControl["budget_scope"];
    budget_cap: number;
    current_estimated_cost: number;
    remaining_estimated_budget: number;
    kill_switch_active: boolean;
    budget_reason: string;
  };
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

export type SurfaceMode = "read_only" | "supervised_control" | "client_safe";

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
  intakeDraft: {
    requestKind: string;
    objective: string;
    projectContext: string;
    structuredConstraints: ForgeConstraintSections;
    requestedArtifacts: ForgeRequestedArtifactsDraft;
    leadIntake: ForgeLeadIntakeProfile;
    leadQualificationDraft: ForgeLeadQualificationDraft;
    autonomyMode: string;
    linkedAttachmentIds: string[];
    previewing: boolean;
    uploading: boolean;
    uploadPurpose: string;
    lastMessage: string;
  };
  intakePreview: ForgeIntakePreview | null;
  selectedAttachmentId: string;
  approvalCenterState: ApprovalCenterState;
  controlDraft: ControlDraft;
  dataFreshness: DataFreshness;
  surfaceMode: SurfaceMode;
  degradedSources: string[];
  clientViewSnapshot: ForgeClientViewSnapshot | null;
};
