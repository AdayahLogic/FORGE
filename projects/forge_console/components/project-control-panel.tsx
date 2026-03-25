import type {
  ForgeClientProjectRow,
  ForgeClientProjectSnapshot,
  ForgeProjectRow,
  ProjectSnapshot,
  SurfaceMode,
} from "../lib/forge-types";

type Props = {
  projects: ForgeProjectRow[] | ForgeClientProjectRow[];
  selectedProjectKey: string;
  projectSnapshot: ProjectSnapshot | null;
  clientProject: ForgeClientProjectSnapshot | null;
  surfaceMode: SurfaceMode;
  onSelectProject: (projectKey: string) => void;
};

function getChipClass(value: string) {
  if (["blocked", "failed", "critical", "error", "error_fallback"].includes(value)) {
    return "chip danger";
  }
  if (["pending", "queued", "guarded", "review_pending", "in_progress", "ready_for_review"].includes(value)) {
    return "chip warn";
  }
  if (["ok", "clear", "ready", "completed", "succeeded", "approved", "complete"].includes(value)) {
    return "chip success";
  }
  return "chip";
}

function displayValue(value: unknown, fallback: string) {
  const text = String(value ?? "").trim();
  if (!text || ["unknown", "none", "n/a", "null"].includes(text.toLowerCase())) {
    return fallback;
  }
  return text;
}

export function ProjectControlPanel({
  projects,
  selectedProjectKey,
  projectSnapshot,
  clientProject,
  surfaceMode,
  onSelectProject,
}: Props) {
  if (surfaceMode === "client_safe") {
    const clientProjects = projects as ForgeClientProjectRow[];
    return (
      <section className="panel left-rail">
        <div className="section-title">
          <div>
            <div className="eyebrow">Client View</div>
            <h3>Project Progress</h3>
          </div>
          <span className="chip info">Display-only</span>
        </div>
        <div className="left-stack">
          <div className="project-list client-project-list">
            {clientProjects.map((project) => {
              const active = project.project_key === selectedProjectKey;
              return (
                <div
                  key={project.project_key}
                  className={`project-card ${active ? "active" : ""}`}
                >
                  <button
                    className="project-button"
                    type="button"
                    onClick={() => onSelectProject(project.project_key)}
                  >
                    <div className="package-title">
                      <span>{project.project_name}</span>
                      <span className={getChipClass(project.client_status)}>
                        {project.client_status}
                      </span>
                    </div>
                    <div className="muted">{project.description}</div>
                    <div className="client-progress-block">
                      <div className="detail-row">
                        <span>Current Phase</span>
                        <strong>{project.current_phase}</strong>
                      </div>
                      <div className="bar" style={{ marginTop: 8 }}>
                        <div
                          className="bar-fill success"
                          style={{ width: `${project.progress_percent}%` }}
                        />
                      </div>
                      <div className="stat-subvalue">{project.progress_label}</div>
                    </div>
                  </button>
                </div>
              );
            })}
          </div>
          <div className="control-card">
            <div className="eyebrow">Selected Project</div>
            {!clientProject ? (
              <div className="audit-item muted" style={{ marginTop: 10 }}>
                Select a project to view approved deliverables, milestones, and safe updates.
              </div>
            ) : (
              <div className="detail-list" style={{ marginTop: 10 }}>
                <div className="detail-row">
                  <span>Status</span>
                  <strong>{clientProject.client_status}</strong>
                </div>
                <div className="detail-row">
                  <span>Current Phase</span>
                  <strong>{clientProject.current_phase}</strong>
                </div>
                <div className="detail-row">
                  <span>Progress</span>
                  <strong>{clientProject.progress_percent}%</strong>
                </div>
                <div className="detail-row">
                  <span>Milestones</span>
                  <strong>{clientProject.milestones.length}</strong>
                </div>
                <div className="detail-row">
                  <span>Deliverables</span>
                  <strong>{clientProject.deliverables.length}</strong>
                </div>
                <div className="detail-row">
                  <span>Shared Attachments</span>
                  <strong>{clientProject.approved_attachments.length}</strong>
                </div>
                <div className="detail-row">
                  <span>Delivery State</span>
                  <strong>{clientProject.delivery_summary.delivery_progress_state}</strong>
                </div>
                <div className="detail-row">
                  <span>Artifact Types</span>
                  <strong>{clientProject.delivery_summary.delivered_artifact_count}</strong>
                </div>
                <div className="detail-card-subsection">
                  <div className="stat-label">Safe Summary</div>
                  <div style={{ marginTop: 8 }}>{clientProject.safe_summary}</div>
                </div>
                <div className="detail-card-subsection">
                  <div className="stat-label">Client-Ready Summary</div>
                  <div style={{ marginTop: 8 }}>
                    {clientProject.delivery_summary.delivery_summary_title}
                    {": "}
                    {clientProject.delivery_summary.delivery_summary_text}
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      </section>
    );
  }

  const state = projectSnapshot?.project_state ?? {};
  const session = projectSnapshot?.latest_session ?? {};
  const health = projectSnapshot?.system_health ?? {};
  const intake = projectSnapshot?.intake_workspace;
  const preview = intake?.preview;
  const modelRouting = preview?.model_routing_policy;
  const workflow = projectSnapshot?.workflow_activity;
  const systemStatus = projectSnapshot?.system_status;
  const backendOffline = systemStatus?.status === "offline";
  const operatorProjects = projects as ForgeProjectRow[];
  const currentPackageId =
    typeof state.execution_package_id === "string" ? state.execution_package_id : "";
  return (
    <section className="panel left-rail">
      <div className="section-title">
        <div>
          <div className="eyebrow">Project Rail</div>
          <h3>Project Control Panel</h3>
        </div>
        <span className="chip info">Read-only default</span>
        </div>
        <div className="left-stack">
          <div className="project-list">
          {operatorProjects.map((project) => {
            const active = project.project_key === selectedProjectKey;
            return (
              <div
                key={project.project_key}
                className={`project-card ${active ? "active" : ""}`}
              >
                <button
                  className="project-button"
                  type="button"
                  onClick={() => onSelectProject(project.project_key)}
                >
                  <div className="package-title">
                    <span>{project.project_name}</span>
                    <span className="chip info">{project.workspace_type}</span>
                  </div>
                  <div className="muted">{project.description}</div>
                  <div className="chip-row" style={{ marginTop: 10 }}>
                    <span className={getChipClass(project.lifecycle_status)}>
                      {project.lifecycle_status}
                    </span>
                    <span className={getChipClass(project.dispatch_status)}>
                      dispatch {project.dispatch_status}
                    </span>
                    <span className={getChipClass(project.enforcement_status)}>
                      {project.enforcement_status}
                    </span>
                    <span className="chip info">
                      est ${Number(project.estimated_cost_total_usd ?? 0).toFixed(4)}
                    </span>
                    <span className={getChipClass(String(project.budget_status ?? "within_budget"))}>
                      budget {String(project.budget_status ?? "within_budget")}
                    </span>
                    {project.selected_model_lane ? (
                      <span className="chip info">{project.selected_model_lane}</span>
                    ) : null}
                  </div>
                </button>
              </div>
            );
          })}
          </div>
          <div className="control-card">
            <div className="eyebrow">Selected Project</div>
            {!projectSnapshot ? (
              <div className="audit-item muted" style={{ marginTop: 10 }}>
                Select a project to see its current lifecycle, intake readiness, and workflow activity.
              </div>
            ) : (
              <div className="detail-list" style={{ marginTop: 10 }}>
                <div className="chip-row" style={{ marginBottom: 6 }}>
                  <span className={backendOffline ? "chip danger" : "chip success"}>
                    {systemStatus?.label ?? "Forge Running"}
                  </span>
                  <span className="chip info">
                    {displayValue(projectSnapshot.project_name, "Waiting for input")}
                  </span>
                </div>
                <div className="detail-row">
                  <span>Lifecycle</span>
                  <strong>{displayValue(state.project_lifecycle_status, "Not started")}</strong>
                </div>
                <div className="detail-row">
                  <span>Dispatch</span>
                  <strong>{displayValue(state.dispatch_status, "Waiting for input")}</strong>
                </div>
                <div className="detail-row">
                  <span>Governance</span>
                  <strong>{displayValue(state.governance_status, "Waiting for input")}</strong>
                </div>
                <div className="detail-row">
                  <span>Enforcement</span>
                  <strong>{displayValue(state.enforcement_status, "Waiting for input")}</strong>
                </div>
                <div className="detail-row">
                  <span>Current Package</span>
                  <strong className="mono">{currentPackageId || "No active execution"}</strong>
                </div>
                <div className="detail-row">
                  <span>Latest Session</span>
                  <strong className="mono">
                    {displayValue(session.run_id ?? state.run_id, "Waiting for input")}
                  </strong>
                </div>
                <div className="detail-row">
                  <span>System Health</span>
                  <strong>
                    {displayValue(
                      health.overall_status,
                      backendOffline ? "Backend offline" : "Waiting for input",
                    )}
                  </strong>
                </div>
                <div className="detail-row">
                  <span>Attachments</span>
                  <strong>{String(intake?.attachments.length ?? 0)}</strong>
                </div>
                <div className="detail-row">
                  <span>Autonomy Mode</span>
                  <strong>
                    {displayValue(
                      state.autonomy_mode ?? intake?.draft_seed.autonomy_mode,
                      "Waiting for input",
                    )}
                  </strong>
                </div>
                <div className="detail-row">
                  <span>Intake Preview</span>
                  <strong>{displayValue(preview?.readiness, "Waiting for input")}</strong>
                </div>
                <div className="detail-row">
                  <span>Model Lane (Policy)</span>
                  <strong>{displayValue(modelRouting?.selected_model_lane, "Waiting for policy output")}</strong>
                </div>
                <div className="detail-row">
                  <span>Routing Status (Policy)</span>
                  <strong>{displayValue(modelRouting?.routing_status, "Waiting for policy output")}</strong>
                </div>
                <div className="detail-row">
                  <span>Delivery Summary State</span>
                  <strong>
                    {displayValue(projectSnapshot.delivery_summary?.delivery_progress_state, "no_delivery_summary")}
                  </strong>
                </div>
                <div className="detail-row">
                  <span>Packaged Artifacts</span>
                  <strong>{String(projectSnapshot.delivery_summary?.delivered_artifact_count ?? 0)}</strong>
                </div>
                <div className="detail-row">
                  <span>Requested Outputs</span>
                  <strong>
                    {String(
                      preview?.requested_artifacts.length ??
                        intake?.draft_seed.requested_artifacts.length ??
                        0,
                    )}
                  </strong>
                </div>
                <div className="detail-row">
                  <span>Estimated Cost (Project)</span>
                  <strong>
                    $
                    {Number(
                      projectSnapshot.cost_summary?.cost_per_project.estimated_cost_total ?? 0,
                    ).toFixed(4)}
                  </strong>
                </div>
                <div className="detail-row">
                  <span>Estimated Cost (Session)</span>
                  <strong>
                    $
                    {Number(
                      projectSnapshot.cost_summary?.session_cost_summary.estimated_cost_total ?? 0,
                    ).toFixed(4)}
                  </strong>
                </div>
                <div className="detail-row">
                  <span>Estimated Budget Status</span>
                  <strong>{displayValue(projectSnapshot.cost_summary?.budget_status, "within_budget")}</strong>
                </div>
                <div className="detail-row">
                  <span>Budget Scope</span>
                  <strong>{displayValue(projectSnapshot.cost_summary?.budget_scope, "operation")}</strong>
                </div>
                <div className="detail-row">
                  <span>Budget Cap</span>
                  <strong>${Number(projectSnapshot.cost_summary?.budget_cap ?? 0).toFixed(4)}</strong>
                </div>
                <div className="detail-row">
                  <span>Remaining Budget</span>
                  <strong>
                    $
                    {Number(projectSnapshot.cost_summary?.remaining_estimated_budget ?? 0).toFixed(4)}
                  </strong>
                </div>
                <div className="detail-row">
                  <span>Kill Switch</span>
                  <strong>
                    {projectSnapshot.cost_summary?.kill_switch_active ? "active" : "inactive"}
                  </strong>
                </div>
                <div className="detail-card-subsection">
                  <div className="stat-label">Routing Reason (Policy Output)</div>
                  <div style={{ marginTop: 8 }}>
                    {displayValue(modelRouting?.routing_reason, "Model routing policy output is not available yet.")}
                  </div>
                </div>
              </div>
            )}
          </div>
          <div className="control-card">
            <div className="eyebrow">Active Workflow</div>
            {!workflow ? (
              <div className="audit-item muted" style={{ marginTop: 10 }}>
                No active workflow yet. Create or preview an intake request to let Forge start planning the next governed package.
              </div>
            ) : (
              <div className="detail-list" style={{ marginTop: 10 }}>
                <div className="detail-row">
                  <span>Current Phase</span>
                  <strong>{displayValue(workflow.phase_label, "Planning")}</strong>
                </div>
                <div className="detail-row">
                  <span>Last Action</span>
                  <strong>{displayValue(workflow.last_action, "Waiting for input")}</strong>
                </div>
                <div className="detail-row">
                  <span>Current Project</span>
                  <strong>{displayValue(workflow.current_project, "Waiting for input")}</strong>
                </div>
                <div className="detail-row">
                  <span>Active Package</span>
                  <strong className="mono">
                    {displayValue(workflow.active_package_id, "No active execution")}
                  </strong>
                </div>
                <div className="detail-row">
                  <span>Package Status</span>
                  <strong>{displayValue(workflow.package_status, "No active execution")}</strong>
                </div>
                <div className="detail-row">
                  <span>Package Created</span>
                  <strong>{displayValue(workflow.package_created_at, "Not started")}</strong>
                </div>
              </div>
            )}
          </div>
        </div>
      </section>
  );
}
