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
                <div className="detail-card-subsection">
                  <div className="stat-label">Safe Summary</div>
                  <div style={{ marginTop: 8 }}>{clientProject.safe_summary}</div>
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
                  </div>
                </button>
              </div>
            );
          })}
        </div>
        <div className="control-card">
          <div className="eyebrow">Selected Project</div>
          <div className="detail-list" style={{ marginTop: 10 }}>
            <div className="detail-row">
              <span>Lifecycle</span>
              <strong>{String(state.project_lifecycle_status ?? "unknown")}</strong>
            </div>
            <div className="detail-row">
              <span>Dispatch</span>
              <strong>{String(state.dispatch_status ?? "unknown")}</strong>
            </div>
            <div className="detail-row">
              <span>Governance</span>
              <strong>{String(state.governance_status ?? "unknown")}</strong>
            </div>
            <div className="detail-row">
              <span>Enforcement</span>
              <strong>{String(state.enforcement_status ?? "unknown")}</strong>
            </div>
            <div className="detail-row">
              <span>Current Package</span>
              <strong className="mono">{currentPackageId || "none"}</strong>
            </div>
            <div className="detail-row">
              <span>Latest Session</span>
              <strong className="mono">
                {String(session.run_id ?? state.run_id ?? "n/a")}
              </strong>
            </div>
            <div className="detail-row">
              <span>System Health</span>
              <strong>{String(health.overall_status ?? "unknown")}</strong>
            </div>
            <div className="detail-row">
              <span>Attachments</span>
              <strong>{String(intake?.attachments.length ?? 0)}</strong>
            </div>
            <div className="detail-row">
              <span>Autonomy Mode</span>
              <strong>{String(state.autonomy_mode ?? intake?.draft_seed.autonomy_mode ?? "unknown")}</strong>
            </div>
            <div className="detail-row">
              <span>Intake Preview</span>
              <strong>{String(preview?.readiness ?? "preview_required")}</strong>
            </div>
            <div className="detail-row">
              <span>Requested Outputs</span>
              <strong>{String(preview?.requested_artifacts.length ?? intake?.draft_seed.requested_artifacts.length ?? 0)}</strong>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
