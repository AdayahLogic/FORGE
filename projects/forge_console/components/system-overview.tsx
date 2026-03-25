import type {
  ForgeOverviewSnapshot,
  ForgeQuickAction,
  ForgeQuickActions,
} from "../lib/forge-types";

type Props = {
  overview: ForgeOverviewSnapshot | null;
  onQuickAction?: (action: ForgeQuickAction) => void;
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

function QuickActionsCard({
  title,
  quickActions,
  onQuickAction,
}: {
  title: string;
  quickActions: ForgeQuickActions | undefined;
  onQuickAction?: (action: ForgeQuickAction) => void;
}) {
  if (!quickActions) {
    return null;
  }
  return (
    <div className="detail-card" style={{ marginTop: 14 }}>
      <h4>{title}</h4>
      <div className="chip-row" style={{ marginBottom: 10 }}>
        <span className="chip info">{quickActions.quick_actions_status}</span>
        <span className="chip">{quickActions.quick_actions_reason}</span>
      </div>
      <div className="detail-list">
        {quickActions.available_actions.length > 0 ? (
          quickActions.available_actions.map((action) => (
            <div className="audit-item" key={action.action_id}>
              <div className="chip-row" style={{ marginBottom: 8 }}>
                <span className="chip info">{action.action_kind}</span>
                <span className="chip">{action.action_scope}</span>
              </div>
              <button
                className="action-button"
                disabled={!action.action_enabled}
                onClick={() => onQuickAction?.(action)}
                style={{ marginBottom: 8 }}
                type="button"
              >
                {action.action_label}
              </button>
              <div className="muted">
                {action.action_enabled
                  ? action.action_reason
                  : action.blocked_reason || action.action_reason}
              </div>
            </div>
          ))
        ) : (
          <div className="audit-item muted">No suggested quick actions available.</div>
        )}
      </div>
    </div>
  );
}

export function SystemOverview({ overview, onQuickAction }: Props) {
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
  const quickActions = data?.quick_actions;
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
    <section className="panel top-band" id="system-overview-panel">
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
      </div>
      <QuickActionsCard
        title="Suggested Quick Actions"
        quickActions={quickActions}
        onQuickAction={onQuickAction}
      />
    </section>
  );
}
