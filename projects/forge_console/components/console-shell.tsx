"use client";

import { startTransition, useEffect, useState } from "react";
import {
  getClientViewSnapshot,
  getOverviewSnapshot,
  getPackageSnapshot,
  getProjectSnapshot,
  previewIntakeRequest,
  runControlAction,
  uploadAttachment,
} from "../lib/forge-client";
import {
  getCurrentPackagePointer,
  getSelectedProjectKey,
} from "../lib/forge-selectors";
import type {
  ForgeConstraintSections,
  ForgeLeadQualificationDraft,
  ForgeQuickAction,
  ForgeRequestedArtifactsDraft,
  ForgeUiState,
} from "../lib/forge-types";
import { createInitialUiState } from "../lib/forge-ui-state";
import { AbacusEvaluationPanel } from "./abacus-evaluation-panel";
import { ApprovalControlCenter } from "./approval-control-center";
import { ExecutionDetailDrawer } from "./execution-detail-drawer";
import { NemoClawAdvisoryPanel } from "./nemoclaw-advisory-panel";
import { PackageLifecycleBoard } from "./package-lifecycle-board";
import { ProjectControlPanel } from "./project-control-panel";
import { ProjectIntakeWorkspace } from "./project-intake-workspace";
import { ReviewCenter } from "./review-center";
import { SystemOverview } from "./system-overview";

export function ConsoleShell() {
  const [uiState, setUiState] = useState<ForgeUiState>(createInitialUiState());

  const emptyConstraintSections = (): ForgeConstraintSections => ({
    scope_boundaries: [],
    risk_notes: [],
    runtime_preferences: [],
    output_expectations: [],
    review_expectations: [],
  });

  const normalizeConstraintSections = (
    value: ForgeConstraintSections | null | undefined,
  ): ForgeConstraintSections => ({
    scope_boundaries: value?.scope_boundaries ?? [],
    risk_notes: value?.risk_notes ?? [],
    runtime_preferences: value?.runtime_preferences ?? [],
    output_expectations: value?.output_expectations ?? [],
    review_expectations: value?.review_expectations ?? [],
  });

  const normalizeRequestedArtifacts = (
    value: ForgeRequestedArtifactsDraft | null | undefined,
    fallback: string[] | null | undefined,
  ): ForgeRequestedArtifactsDraft => ({
    selected:
      value?.selected ??
      (fallback ?? []).filter(Boolean),
    custom: value?.custom ?? [],
  });

  const normalizeLeadQualification = (
    value: ForgeLeadQualificationDraft | null | undefined,
  ): ForgeLeadQualificationDraft => ({
    budget_band: value?.budget_band ?? "",
    urgency: value?.urgency ?? "",
    problem_clarity: value?.problem_clarity ?? "",
    decision_readiness: value?.decision_readiness ?? "",
    fit_notes: value?.fit_notes ?? "",
  });

  const applyIntakeDraftPatch = (
    patch:
      | Partial<ForgeUiState["intakeDraft"]>
      | ((current: ForgeUiState["intakeDraft"]) => Partial<ForgeUiState["intakeDraft"]>),
  ) => {
    setUiState((current) => {
      const nextPatch = typeof patch === "function" ? patch(current.intakeDraft) : patch;
      return {
        ...current,
        intakePreview: null,
        intakeDraft: {
          ...current.intakeDraft,
          ...nextPatch,
          lastMessage: "Draft updated. Preview again to refresh governed request intent.",
        },
      };
    });
  };

  async function loadPackage(packageId: string, projectKey: string) {
    const response = await getPackageSnapshot(packageId, projectKey);
    setUiState((current) => ({
      ...current,
      selectedPackageId: packageId,
      packageDetail: response.payload,
      detailDrawerOpen: true,
      dataFreshness: response.status === "ok" ? "ready" : "error",
    }));
  }

  async function loadProject(projectKey: string, preservePackageSelection = false) {
    const response = await getProjectSnapshot(projectKey);
    const project = response.payload;
    const workspace = project.intake_workspace;
    const currentPointer = getCurrentPackagePointer(project);
    const nextSelectedPackageId =
      preservePackageSelection && uiState.selectedPackageId
        ? uiState.selectedPackageId
        : currentPointer || project.package_queue.packages[0]?.package_id || "";
    setUiState((current) => ({
      ...current,
      selectedProjectKey: projectKey,
      projectSnapshot: project,
      packageQueue: project.package_queue.packages,
      selectedPackageId: nextSelectedPackageId,
      intakeDraft: {
        requestKind: workspace?.draft_seed.request_kind ?? "update_request",
        objective: workspace?.draft_seed.objective ?? "",
        projectContext: workspace?.draft_seed.project_context ?? "",
        structuredConstraints: normalizeConstraintSections(
          workspace?.draft_seed.structured_constraints ?? emptyConstraintSections(),
        ),
        requestedArtifacts: normalizeRequestedArtifacts(
          workspace?.draft_seed.requested_artifacts_draft,
          workspace?.draft_seed.requested_artifacts,
        ),
        leadIntake: workspace?.draft_seed.lead_intake_profile ?? {
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
        leadQualificationDraft: normalizeLeadQualification(
          workspace?.draft_seed.lead_qualification,
        ),
        autonomyMode: workspace?.draft_seed.autonomy_mode ?? "supervised_build",
        linkedAttachmentIds: workspace?.draft_seed.linked_attachment_ids ?? [],
        previewing: false,
        uploading: false,
        uploadPurpose: current.intakeDraft.uploadPurpose,
        lastMessage: "",
      },
      intakePreview: workspace?.preview ?? null,
      selectedAttachmentId:
        current.selectedAttachmentId ||
        workspace?.attachments[0]?.attachment_id ||
        "",
      detailDrawerOpen: Boolean(nextSelectedPackageId),
      degradedSources: project.degraded_sources,
      dataFreshness: response.status === "ok" ? "ready" : "error",
    }));
    if (nextSelectedPackageId) {
      await loadPackage(nextSelectedPackageId, projectKey);
    }
  }

  async function loadOverview() {
    setUiState((current) => ({ ...current, dataFreshness: "loading" }));
    const response = await getOverviewSnapshot();
    const overview = response.payload;
    const selectedProjectKey = getSelectedProjectKey(
      overview,
      uiState.selectedProjectKey,
    );
    setUiState((current) => ({
      ...current,
      overviewSnapshot: overview,
      selectedProjectKey,
      dataFreshness: response.status === "ok" ? "ready" : "error",
      degradedSources: [],
    }));
    if (selectedProjectKey) {
      await loadProject(selectedProjectKey, true);
    }
  }

  async function loadClientView(projectKey = "") {
    setUiState((current) => ({
      ...current,
      dataFreshness: "loading",
    }));
    const response = await getClientViewSnapshot(projectKey);
    setUiState((current) => ({
      ...current,
      surfaceMode: "client_safe",
      clientViewSnapshot: response.payload,
      selectedProjectKey:
        response.payload.selected_project_key || current.selectedProjectKey,
      dataFreshness: response.status === "ok" ? "ready" : "error",
      degradedSources: [],
    }));
  }

  useEffect(() => {
    void loadOverview();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const refresh = () => {
    startTransition(() => {
      if (uiState.surfaceMode === "client_safe") {
        void loadClientView(uiState.selectedProjectKey);
        return;
      }
      void loadOverview();
    });
  };

  const selectProject = (projectKey: string) => {
    startTransition(() => {
      if (uiState.surfaceMode === "client_safe") {
        void loadClientView(projectKey);
        return;
      }
      void loadProject(projectKey);
    });
  };

  const selectPackage = (packageId: string) => {
    if (!uiState.selectedProjectKey) {
      return;
    }
    startTransition(() => {
      void loadPackage(packageId, uiState.selectedProjectKey);
    });
  };

  const runPreview = async () => {
    if (!uiState.selectedProjectKey) {
      return;
    }
    setUiState((current) => ({
      ...current,
      intakeDraft: {
        ...current.intakeDraft,
        previewing: true,
        lastMessage: "Building governed request preview...",
      },
    }));
    try {
      const response = await previewIntakeRequest({
        projectKey: uiState.selectedProjectKey,
        requestKind: uiState.intakeDraft.requestKind,
        objective: uiState.intakeDraft.objective,
        projectContext: uiState.intakeDraft.projectContext,
        constraints: uiState.intakeDraft.structuredConstraints,
        requestedArtifacts: uiState.intakeDraft.requestedArtifacts,
        leadIntake: uiState.intakeDraft.leadIntake,
        qualification: uiState.intakeDraft.leadQualificationDraft,
        linkedAttachmentIds: uiState.intakeDraft.linkedAttachmentIds,
        autonomyMode: uiState.intakeDraft.autonomyMode,
      });
      setUiState((current) => ({
        ...current,
        intakePreview: response.payload,
        intakeDraft: {
          ...current.intakeDraft,
          previewing: false,
          lastMessage:
            response.payload.package_preview.summary || "Governed request preview ready.",
        },
      }));
    } catch (error) {
      setUiState((current) => ({
        ...current,
        intakeDraft: {
          ...current.intakeDraft,
          previewing: false,
          lastMessage:
            error instanceof Error ? error.message : "Request preview failed.",
        },
      }));
    }
  };

  const handleAttachmentUpload = async (file: File) => {
    if (!uiState.selectedProjectKey) {
      return;
    }
    setUiState((current) => ({
      ...current,
      intakeDraft: {
        ...current.intakeDraft,
        uploading: true,
        lastMessage: `Uploading ${file.name}...`,
      },
    }));
    try {
      const response = await uploadAttachment({
        projectKey: uiState.selectedProjectKey,
        file,
        purpose: uiState.intakeDraft.uploadPurpose,
      });
      await loadProject(uiState.selectedProjectKey, true);
      setUiState((current) => ({
        ...current,
        intakeDraft: {
          ...current.intakeDraft,
          uploading: false,
          lastMessage:
            response.payload.reason || "Attachment stored for governed review.",
        },
        selectedAttachmentId:
          response.payload.attachment?.attachment_id || current.selectedAttachmentId,
      }));
    } catch (error) {
      setUiState((current) => ({
        ...current,
        intakeDraft: {
          ...current.intakeDraft,
          uploading: false,
          lastMessage:
            error instanceof Error ? error.message : "Attachment upload failed.",
        },
      }));
    }
  };

  const submitControl = async () => {
    if (!uiState.selectedProjectKey) {
      return;
    }
    setUiState((current) => ({
      ...current,
      controlDraft: { ...current.controlDraft, submitting: true },
      approvalCenterState: {
        ...current.approvalCenterState,
        lastActionStatus: "submitting",
        lastActionMessage: "Submitting supervised command...",
      },
    }));
    try {
      const response = await runControlAction({
        action: uiState.controlDraft.action,
        projectKey: uiState.selectedProjectKey,
        confirmed: uiState.controlDraft.confirmed,
        confirmationText: uiState.controlDraft.confirmationText,
      });
      setUiState((current) => ({
        ...current,
        controlDraft: { ...current.controlDraft, submitting: false },
        approvalCenterState: {
          ...current.approvalCenterState,
          lastActionStatus: response.status === "ok" ? "success" : "error",
          lastActionMessage: response.message || "No response summary.",
        },
      }));
      await loadProject(uiState.selectedProjectKey, true);
    } catch (error) {
      setUiState((current) => ({
        ...current,
        controlDraft: { ...current.controlDraft, submitting: false },
        approvalCenterState: {
          ...current.approvalCenterState,
          lastActionStatus: "error",
          lastActionMessage:
            error instanceof Error ? error.message : "Control action failed.",
        },
      }));
    }
  };

  const requiredPhrase =
    uiState.controlDraft.action === "complete_approval"
      ? "CONFIRM COMPLETE APPROVAL"
      : "CONFIRM COMPLETE REVIEW";

  const clientProject = uiState.clientViewSnapshot?.project ?? null;
  const clientProjects = uiState.clientViewSnapshot?.projects ?? [];
  const clientGeneratedAt = uiState.clientViewSnapshot?.generated_at ?? "";

  const scrollToPanel = (panelId: string) => {
    const node = document.getElementById(panelId);
    if (node) {
      node.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  };

  const runQuickAction = (action: ForgeQuickAction) => {
    switch (action.action_id) {
      case "navigate_review_center":
      case "open_review_context":
        scrollToPanel("review-center-panel");
        return;
      case "input_request_missing_fields":
        scrollToPanel("project-intake-workspace");
        return;
      case "inspect_current_package":
        if (uiState.selectedPackageId && uiState.selectedProjectKey) {
          void loadPackage(uiState.selectedPackageId, uiState.selectedProjectKey);
        }
        setUiState((current) => ({ ...current, detailDrawerOpen: true }));
        return;
      case "open_delivery_summary":
      case "inspect_package_attachments":
        scrollToPanel("review-center-panel");
        return;
      case "inspect_budget_blockers":
        scrollToPanel("project-control-panel");
        return;
      case "refresh_system_overview":
      case "refresh_project_snapshot":
      case "refresh_package_snapshot":
      default:
        refresh();
    }
  };

  return (
    <main className="console-root">
      <div className="console-grid">
        {uiState.surfaceMode === "client_safe" ? (
          <section className="panel top-band">
            <div className="section-title">
              <div>
                <div className="eyebrow">Forge Console</div>
                <h2>Client-Facing Safe View</h2>
              </div>
              <div className="chip-row">
                <span className="chip info">Sanitized snapshot</span>
                <span className="chip">Display only</span>
                {clientGeneratedAt ? (
                  <span className="chip mono">{clientGeneratedAt}</span>
                ) : null}
              </div>
            </div>
            <div className="detail-grid-three">
              <div className="stat-card">
                <div className="stat-label">Current Project</div>
                <div className="stat-value">
                  {clientProject?.project_name || "No project selected"}
                </div>
                <div className="stat-subvalue">
                  {clientProject?.safe_summary || "Safe project updates appear here."}
                </div>
              </div>
              <div className="stat-card">
                <div className="stat-label">Current Phase</div>
                <div className="stat-value">
                  {clientProject?.current_phase || "Project Intake"}
                </div>
                <div className="stat-subvalue">
                  {clientProject?.progress_label || "Waiting for project selection"}
                </div>
              </div>
              <div className="stat-card">
                <div className="stat-label">Safe To Share</div>
                <div className="stat-value">
                  {clientProject
                    ? clientProject.deliverables.filter((item) => item.safe_to_share).length
                    : 0}
                </div>
                <div className="stat-subvalue">
                  approved deliverables visible in this surface
                </div>
              </div>
            </div>
          </section>
        ) : (
          <SystemOverview
            onQuickAction={runQuickAction}
            overview={uiState.overviewSnapshot}
          />
        )}
        <ProjectControlPanel
          onSelectProject={selectProject}
          clientProject={clientProject}
          projectSnapshot={uiState.projectSnapshot}
          projects={
            uiState.surfaceMode === "client_safe"
              ? clientProjects
              : (uiState.overviewSnapshot?.projects ?? [])
          }
          selectedProjectKey={uiState.selectedProjectKey}
          surfaceMode={uiState.surfaceMode}
          onQuickAction={runQuickAction}
        />
        <div className="center-stack">
          {uiState.surfaceMode === "client_safe" ? null : (
            <ProjectIntakeWorkspace
              draft={uiState.intakeDraft}
              onAttachmentSelect={(attachmentId) =>
                setUiState((current) => ({
                  ...current,
                  selectedAttachmentId: attachmentId,
                }))
              }
              onAttachmentToggle={(attachmentId) =>
                applyIntakeDraftPatch((draft) => {
                  const nextIds = draft.linkedAttachmentIds.includes(attachmentId)
                    ? draft.linkedAttachmentIds.filter((item) => item !== attachmentId)
                    : [...draft.linkedAttachmentIds, attachmentId];
                  return {
                    linkedAttachmentIds: nextIds,
                  };
                })
              }
              onDraftChange={applyIntakeDraftPatch}
              onPreview={() => {
                void runPreview();
              }}
              onUpload={(file) => {
                void handleAttachmentUpload(file);
              }}
              preview={uiState.intakePreview}
              selectedAttachmentId={uiState.selectedAttachmentId}
              selectedProjectKey={uiState.selectedProjectKey}
              workspace={uiState.projectSnapshot?.intake_workspace ?? null}
            />
          )}
          <ReviewCenter
            clientProject={clientProject}
            detail={uiState.packageDetail}
            onQuickAction={runQuickAction}
            surfaceMode={uiState.surfaceMode}
          />
          {uiState.surfaceMode === "client_safe" ? null : (
            <PackageLifecycleBoard
              includeCompleted={uiState.boardFilters.includeCompleted}
              onSelectPackage={selectPackage}
              packages={uiState.packageQueue}
              selectedPackageId={uiState.selectedPackageId}
              showOnlyRisk={uiState.boardFilters.showOnlyRisk}
            />
          )}
        </div>
        {uiState.surfaceMode === "client_safe" ? (
          <div className="right-rail">
            <section className="panel client-mode-panel">
              <div className="section-title">
                <div>
                  <div className="eyebrow">Surface Mode</div>
                  <h3>Console Access</h3>
                </div>
              </div>
              <div className="control-actions">
                <button
                  className="action-button"
                  onClick={() => {
                    setUiState((current) => ({ ...current, surfaceMode: "read_only" }));
                    void loadOverview();
                  }}
                  type="button"
                >
                  Switch To Operator Mode
                </button>
                <div className="audit-item muted">
                  Client mode stays display-only and reads only the backend client snapshot.
                </div>
              </div>
            </section>
          </div>
        ) : (
          <div className="right-rail">
            <ApprovalControlCenter
              approvalCenterState={{
                ...uiState.approvalCenterState,
                requiredConfirmationPhrase: requiredPhrase,
              }}
              approvalSummary={
                uiState.projectSnapshot?.approval_summary ??
                uiState.overviewSnapshot?.approval_center.approval_summary ??
                {}
              }
              controlDraft={uiState.controlDraft}
              lifecycleSummary={
                uiState.overviewSnapshot?.approval_center.approval_lifecycle ?? {}
              }
              onActionChange={(action) =>
                setUiState((current) => ({
                  ...current,
                  controlDraft: {
                    ...current.controlDraft,
                    action,
                    confirmationText: "",
                    confirmed: false,
                  },
                }))
              }
              onConfirmedChange={(confirmed) =>
                setUiState((current) => ({
                  ...current,
                  controlDraft: { ...current.controlDraft, confirmed },
                }))
              }
              onConfirmationTextChange={(confirmationText) =>
                setUiState((current) => ({
                  ...current,
                  controlDraft: { ...current.controlDraft, confirmationText },
                }))
              }
              onSubmit={() => {
                void submitControl();
              }}
              selectedProjectKey={uiState.selectedProjectKey}
            />
            <AbacusEvaluationPanel detail={uiState.packageDetail} />
            <NemoClawAdvisoryPanel detail={uiState.packageDetail} />
          </div>
        )}
        <div className="drawer-wrap">
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              gap: 12,
              marginBottom: 10,
            }}
          >
            <div className="chip-row">
              <span className="chip info">Surface {uiState.surfaceMode}</span>
              <span className="chip">Freshness {uiState.dataFreshness}</span>
              {uiState.degradedSources.map((source) => (
                <span className="chip warn" key={source}>
                  degraded {source}
                </span>
              ))}
            </div>
            <div className="chip-row">
              <button
                className={`action-button ${uiState.surfaceMode === "client_safe" ? "selected-surface" : ""}`}
                onClick={() => {
                  void loadClientView(uiState.selectedProjectKey);
                }}
                type="button"
              >
                Client View
              </button>
              {uiState.surfaceMode === "client_safe" ? null : (
                <>
                  <label className="chip">
                    <input
                      checked={uiState.boardFilters.showOnlyRisk}
                      onChange={(event) =>
                        setUiState((current) => ({
                          ...current,
                          boardFilters: {
                            ...current.boardFilters,
                            showOnlyRisk: event.target.checked,
                          },
                        }))
                      }
                      style={{ marginRight: 8 }}
                      type="checkbox"
                    />
                    Risk focus
                  </label>
                  <label className="chip">
                    <input
                      checked={uiState.boardFilters.includeCompleted}
                      onChange={(event) =>
                        setUiState((current) => ({
                          ...current,
                          boardFilters: {
                            ...current.boardFilters,
                            includeCompleted: event.target.checked,
                          },
                        }))
                      }
                      style={{ marginRight: 8 }}
                      type="checkbox"
                    />
                    Show completed
                  </label>
                </>
              )}
              <button className="refresh-button" onClick={refresh} type="button">
                Refresh Surface
              </button>
            </div>
          </div>
          {uiState.surfaceMode === "client_safe" ? (
            <section className="panel client-mode-panel">
              <div className="section-title">
                <div>
                  <div className="eyebrow">Client Guardrail</div>
                  <h3>Read-Only Surface</h3>
                </div>
                <span className="chip success">No actions wired</span>
              </div>
              <div className="audit-item muted">
                This mode does not expose execution, approval, runtime, or governance controls and does not call mutation endpoints.
              </div>
            </section>
          ) : (
            <ExecutionDetailDrawer
              detail={uiState.packageDetail}
              onToggle={() =>
                setUiState((current) => ({
                  ...current,
                  detailDrawerOpen: !current.detailDrawerOpen,
                }))
              }
              open={uiState.detailDrawerOpen}
            />
          )}
        </div>
      </div>
    </main>
  );
}
