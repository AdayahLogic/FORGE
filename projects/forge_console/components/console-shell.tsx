"use client";

import { startTransition, useEffect, useState } from "react";
import {
  getOverviewSnapshot,
  getPackageSnapshot,
  getProjectSnapshot,
  runControlAction,
} from "../lib/forge-client";
import {
  getCurrentPackagePointer,
  getSelectedProjectKey,
} from "../lib/forge-selectors";
import type { ForgeUiState } from "../lib/forge-types";
import { createInitialUiState } from "../lib/forge-ui-state";
import { AbacusEvaluationPanel } from "./abacus-evaluation-panel";
import { ApprovalControlCenter } from "./approval-control-center";
import { ExecutionDetailDrawer } from "./execution-detail-drawer";
import { NemoClawAdvisoryPanel } from "./nemoclaw-advisory-panel";
import { PackageLifecycleBoard } from "./package-lifecycle-board";
import { ProjectControlPanel } from "./project-control-panel";
import { SystemOverview } from "./system-overview";

export function ConsoleShell() {
  const [uiState, setUiState] = useState<ForgeUiState>(createInitialUiState());

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

  useEffect(() => {
    void loadOverview();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const refresh = () => {
    startTransition(() => {
      void loadOverview();
    });
  };

  const selectProject = (projectKey: string) => {
    startTransition(() => {
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

  return (
    <main className="console-root">
      <div className="console-grid">
        <SystemOverview overview={uiState.overviewSnapshot} />
        <ProjectControlPanel
          onSelectProject={selectProject}
          projectSnapshot={uiState.projectSnapshot}
          projects={uiState.overviewSnapshot?.projects ?? []}
          selectedProjectKey={uiState.selectedProjectKey}
        />
        <PackageLifecycleBoard
          includeCompleted={uiState.boardFilters.includeCompleted}
          onSelectPackage={selectPackage}
          packages={uiState.packageQueue}
          selectedPackageId={uiState.selectedPackageId}
          showOnlyRisk={uiState.boardFilters.showOnlyRisk}
        />
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
              <button className="refresh-button" onClick={refresh} type="button">
                Refresh Surface
              </button>
            </div>
          </div>
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
        </div>
      </div>
    </main>
  );
}
