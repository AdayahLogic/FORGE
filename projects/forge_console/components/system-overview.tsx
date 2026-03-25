import type { ForgeOverviewSnapshot } from "../lib/forge-types";

type Props = {
  overview: ForgeOverviewSnapshot | null;
};

function StatCard({
  label,
  value,
  subvalue,
}: {
  label: string;
  value: string | number;
  subvalue: string;
}) {
  return (
    <div className="stat-card pulse">
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value}</div>
      <div className="stat-subvalue">{subvalue}</div>
    </div>
  );
}

export function SystemOverview({ overview }: Props) {
  const data = overview?.overview;
  const aegis = data?.aegis_posture ?? {};
  const queue = data?.queue_counts ?? {};
  const packages = data?.package_counts ?? {};
  const evaluation = data?.evaluation_counts;
  const local = data?.local_analysis_counts;
  const executorHealth = data?.executor_health ?? {};
  const costVisibility = data?.cost_visibility;
  const budgetVisibility = data?.budget_visibility;
  const modelRouting = data?.model_routing_visibility;
  const operatorGuidance = data?.operator_guidance;
  const liveOperation = data?.live_operation_status;
  const systemStatus = data?.system_status;
  const backendOffline = systemStatus?.status === "offline";
  const displayState = (value: unknown, fallback: string) => {
    const text = String(value ?? "").trim();
    if (!text || ["unknown", "none", "n/a", "null"].includes(text.toLowerCase())) {
      return fallback;
    }
    return text;
  };

  return (
    <section className="panel top-band">
      <div className="section-title">
        <div>
          <div className="eyebrow">Forge Console</div>
          <h2>System Overview</h2>
        </div>
        <div className="chip-row">
          <span className="chip info">
            Studio {(overview?.studio_name ?? "FORGE").toUpperCase()}
          </span>
          <span className="chip">
            Generated {overview?.generated_at ? "live" : "pending"}
          </span>
        </div>
      </div>
      <div className="overview-grid">
        <StatCard
          label="System Status"
          value={systemStatus?.label ?? "Forge Not Running"}
          subvalue={systemStatus?.reason || "Backend offline"}
        />
        <StatCard
          label="Studio Health"
          value={displayState(data?.studio_health, backendOffline ? "Backend offline" : "Waiting for input")}
          subvalue={`Executor ${displayState(
            executorHealth.execution_environment_status,
            backendOffline ? "Backend offline" : "Waiting for input",
          )}`}
        />
        <StatCard
          label="AEGIS Posture"
          value={displayState(aegis.aegis_decision, backendOffline ? "Backend offline" : "Waiting for input")}
          subvalue={`Scope ${displayState(aegis.aegis_scope, "runtime_dispatch_only")}`}
        />
        <StatCard
          label="Queue Load"
          value={Number(queue.queued_projects ?? 0)}
          subvalue={`${Number(queue.approval_pending_total ?? 0)} pending approvals`}
        />
        <StatCard
          label="Package Review"
          value={Number(packages.review_pending ?? 0)}
          subvalue={`${Number(packages.execution_pending ?? 0)} awaiting execution`}
        />
        <StatCard
          label="Abacus"
          value={Number(evaluation?.completed ?? 0)}
          subvalue={`${Number(evaluation?.blocked ?? 0)} blocked`}
        />
        <StatCard
          label="NemoClaw"
          value={Number(local?.completed ?? 0)}
          subvalue={`${Number(local?.blocked ?? 0)} blocked`}
        />
        <StatCard
          label="Projects"
          value={Number(data?.project_count ?? 0)}
          subvalue={`${Number(queue.review_required_projects ?? 0)} need review`}
        />
        <StatCard
          label="Executor Health"
          value={displayState(
            executorHealth.runtime_infrastructure_status,
            backendOffline ? "Backend offline" : "Waiting for input",
          )}
          subvalue={`${Number(executorHealth.integrity_issues_count_total ?? 0)} integrity issues`}
        />
        <StatCard
          label="Estimated Cost"
          value={`$${Number(costVisibility?.estimated_cost_total_usd ?? 0).toFixed(4)}`}
          subvalue={costVisibility?.label ?? "Estimated Cost (Preview/Non-Billed)"}
        />
        <StatCard
          label="Estimated Budget"
          value={String(budgetVisibility?.budget_status ?? "within_budget")}
          subvalue={
            budgetVisibility
              ? `${budgetVisibility.label} | remaining $${Number(
                  budgetVisibility.remaining_estimated_budget ?? 0,
                ).toFixed(4)}`
              : "Estimated Budget (Non-Billed Governance Control)"
          }
        />
        <StatCard
          label="Model Routing Policy"
          value={Number(modelRouting?.blocked_or_deferred_count ?? 0)}
          subvalue={modelRouting?.policy_output_label ?? "Policy Output (Read-only)"}
        />
        <StatCard
          label="Operator Guidance (Suggested, Not Executed)"
          value={String(operatorGuidance?.guidance_status ?? "idle")}
          subvalue={operatorGuidance?.next_best_action || "No action is currently required."}
        />
      </div>
      <div className="detail-card-subsection" style={{ marginTop: 12 }}>
        <div className="stat-label">Operator Guidance (Suggested, Not Executed)</div>
        <div style={{ marginTop: 8 }}>
          <strong>Posture:</strong> {String(operatorGuidance?.system_posture ?? "healthy")}
        </div>
        <div style={{ marginTop: 6 }}>
          <strong>Reason:</strong> {operatorGuidance?.action_reason || "No active guidance reason."}
        </div>
        <div style={{ marginTop: 6 }}>
          <strong>Priority:</strong> {String(operatorGuidance?.recommended_priority ?? "low")}
        </div>
      </div>
      <div className="review-grid" style={{ marginTop: 16 }}>
        <div className="detail-card">
          <h4>Live Operation Status</h4>
          <div className="detail-list">
            <div className="detail-row">
              <span>Status</span>
              <strong>{displayState(liveOperation?.operation_status, "idle")}</strong>
            </div>
            <div className="detail-row">
              <span>Current Phase</span>
              <strong>{displayState(liveOperation?.current_phase, "idle")}</strong>
            </div>
            <div className="detail-row">
              <span>Current Step</span>
              <strong>{displayState(liveOperation?.current_step, "Waiting for input")}</strong>
            </div>
            <div className="detail-row">
              <span>Active Project</span>
              <strong>{displayState(liveOperation?.active_project, "No active project")}</strong>
            </div>
            <div className="detail-row">
              <span>Active Package</span>
              <strong className="mono">{displayState(liveOperation?.active_package_id, "No active package")}</strong>
            </div>
          </div>
        </div>
        <div className="detail-card">
          <h4>Recent Activity</h4>
          <div className="detail-list">
            {(liveOperation?.recent_activity ?? []).length > 0 ? (
              (liveOperation?.recent_activity ?? []).map((item, index) => (
                <div className="audit-item" key={`${item.activity_type}-${item.timestamp}-${index}`}>
                  <div className="chip-row" style={{ marginBottom: 8 }}>
                    <span className="chip info">{item.activity_type}</span>
                    <span className="chip mono">{item.timestamp}</span>
                  </div>
                  <div>{item.activity_summary}</div>
                </div>
              ))
            ) : (
              <div className="audit-item muted">No recent governed activity.</div>
            )}
          </div>
          <div className="detail-card-subsection">
            <div className="stat-label">Idle Reason</div>
            <div style={{ marginTop: 8 }}>
              {displayState(liveOperation?.idle_reason, "No idle reason while operation is active.")}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
