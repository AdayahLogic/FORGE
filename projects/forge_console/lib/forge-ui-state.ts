import type {
  ApprovalCenterState,
  ControlDraft,
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
    approvalCenterState: createInitialApprovalCenterState(),
    controlDraft: createInitialControlDraft(),
    dataFreshness: "idle",
    surfaceMode: "read_only",
    degradedSources: [],
  };
}
