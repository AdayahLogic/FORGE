import type {
  ApprovalCenterState,
  ControlDraft,
  ForgeConstraintSections,
  ForgeUiState,
} from "./forge-types";

export const DEFAULT_CONFIRMATION_PHRASE = "CONFIRM COMPLETE REVIEW";

export function createInitialApprovalCenterState(): ApprovalCenterState {
  return {
    lastActionStatus: "idle",
    lastActionMessage: "",
    requiredConfirmationPhrase: DEFAULT_CONFIRMATION_PHRASE,
  };
}

export function createInitialControlDraft(): ControlDraft {
  return {
    action: "complete_review",
    confirmationText: "",
    confirmed: false,
    submitting: false,
  };
}

function createEmptyConstraintSections(): ForgeConstraintSections {
  return {
    scope_boundaries: [],
    risk_notes: [],
    runtime_preferences: [],
    output_expectations: [],
    review_expectations: [],
  };
}

export function createInitialUiState(): ForgeUiState {
  return {
    selectedProjectKey: "",
    selectedPackageId: "",
    boardFilters: {
      showOnlyRisk: false,
      includeCompleted: true,
    },
    detailDrawerOpen: false,
    overviewSnapshot: null,
    projectSnapshot: null,
    packageQueue: [],
    packageDetail: null,
    intakeDraft: {
      requestKind: "update_request",
      objective: "",
      projectContext: "",
      structuredConstraints: createEmptyConstraintSections(),
      requestedArtifacts: {
        selected: ["implementation_plan", "code_artifacts", "tests", "review_package", "summary_report"],
        custom: [],
      },
      leadIntake: {
        contact_name: "",
        contact_email: "",
        company_name: "",
        contact_channel: "",
        lead_source: "",
        problem_summary: "",
        requested_outcome: "",
        budget_context: "",
        urgency_context: "",
      },
      autonomyMode: "supervised_build",
      linkedAttachmentIds: [],
      previewing: false,
      uploading: false,
      uploadPurpose: "supporting_context",
      lastMessage: "",
    },
    intakePreview: null,
    selectedAttachmentId: "",
    approvalCenterState: createInitialApprovalCenterState(),
    controlDraft: createInitialControlDraft(),
    dataFreshness: "idle",
    surfaceMode: "read_only",
    degradedSources: [],
    clientViewSnapshot: null,
  };
}
