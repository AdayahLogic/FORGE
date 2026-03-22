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
          label="Studio Health"
          value={String(data?.studio_health ?? "unknown")}
          subvalue={`Executor ${String(
            (executorHealth.execution_environment_status as string) ?? "unknown",
          )}`}
        />
        <StatCard
          label="AEGIS Posture"
          value={String((aegis.aegis_decision as string) ?? "unknown")}
          subvalue={`Scope ${String((aegis.aegis_scope as string) ?? "runtime_dispatch_only")}`}
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
          value={String(
            (executorHealth.runtime_infrastructure_status as string) ?? "unknown",
          )}
          subvalue={`${Number(executorHealth.integrity_issues_count_total ?? 0)} integrity issues`}
        />
      </div>
    </section>
  );
}
