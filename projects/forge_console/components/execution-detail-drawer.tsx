import type { PackageDetailSnapshot } from "../lib/forge-types";

type Props = {
  open: boolean;
  detail: PackageDetailSnapshot | null;
  onToggle: () => void;
};

function DetailCard({
  title,
  value,
}: {
  title: string;
  value: Record<string, unknown> | unknown[];
}) {
  const entries = Array.isArray(value)
    ? value.map((item, index) => [String(index), item] as const)
    : Object.entries(value);
  return (
    <div className="detail-card">
      <h4>{title}</h4>
      <div className="detail-list">
        {entries.length === 0 ? (
          <div className="muted">No stored data.</div>
        ) : (
          entries.map(([key, item]) => (
            <div className="detail-row" key={key}>
              <span>{key}</span>
              <strong className="mono">
                {typeof item === "object" && item !== null
                  ? JSON.stringify(item)
                  : String(item ?? "")}
              </strong>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

export function ExecutionDetailDrawer({ open, detail, onToggle }: Props) {
  const reviewHeader = (detail?.review_header ?? {}) as Record<string, unknown>;
  const sections = (detail?.sections ?? {}) as Record<string, unknown>;
  const feedback = detail?.execution_feedback;
  const costSummary = detail?.cost_summary;
  return (
    <section className={`drawer-panel ${open ? "open" : "closed"}`}>
      <div className="drawer-header">
        <div>
          <div className="eyebrow">Execution Detail Drawer</div>
          <h3 style={{ margin: "4px 0 0" }}>
            {detail?.package_id ? `Package ${detail.package_id}` : "No package selected"}
          </h3>
        </div>
        <button className="refresh-button" onClick={onToggle} type="button">
          {open ? "Collapse Drawer" : "Open Drawer"}
        </button>
      </div>
      {open ? (
        <div className="drawer-body">
          <div className="detail-grid">
            <DetailCard title="Review Header" value={reviewHeader} />
            <DetailCard
              title="Scope"
              value={(sections.scope as Record<string, unknown>) ?? {}}
            />
            <DetailCard
              title="Approval"
              value={(sections.approval as Record<string, unknown>) ?? {}}
            />
            <DetailCard
              title="Safety"
              value={(sections.safety as Record<string, unknown>) ?? {}}
            />
            <DetailCard
              title="Rollback"
              value={(sections.rollback as Record<string, unknown>) ?? {}}
            />
            <DetailCard
              title="Execution Receipt"
              value={(sections.execution as Record<string, unknown>) ?? {}}
            />
            <DetailCard title="Evaluation" value={detail?.evaluation ?? {}} />
            <DetailCard title="Local Analysis" value={detail?.local_analysis ?? {}} />
          </div>
          <div className="detail-card-subsection">
            <div className="stat-label">Execution Feedback</div>
            <div style={{ marginTop: 8 }}>
              {feedback?.status_summary ||
                "No active execution yet. Create an intake request and let Forge prepare a governed package to populate this drawer."}
            </div>
          </div>
          <div className="detail-card-subsection">
            <div className="stat-label">Estimated Cost (Preview/Non-Billed)</div>
            <div style={{ marginTop: 8 }}>
              Operation: ${Number(costSummary?.operation_cost?.cost_estimate ?? 0).toFixed(4)} | Timeline total: $
              {Number(costSummary?.timeline_estimated_cost_total ?? 0).toFixed(4)}
            </div>
          </div>
          <div className="detail-card-subsection">
            <div className="stat-label">Estimated Budget (Non-Billed Governance Control)</div>
            <div style={{ marginTop: 8 }}>
              Status: {String(costSummary?.budget_status ?? "within_budget")} | Scope:{" "}
              {String(costSummary?.budget_scope ?? "operation")} | Remaining: $
              {Number(costSummary?.remaining_estimated_budget ?? 0).toFixed(4)} | Kill switch:{" "}
              {costSummary?.kill_switch_active ? "active" : "inactive"}
            </div>
          </div>
          <div className="section-title" style={{ marginTop: 18 }}>
            <div>
              <div className="eyebrow">Timeline</div>
              <h3>Audit Trail</h3>
            </div>
          </div>
          <div className="audit-list">
            {(detail?.timeline ?? []).length > 0 ? (
              (detail?.timeline ?? []).map((item, index) => (
                <div className="audit-item" key={`${index}-${String(item.created_at ?? "")}`}>
                  <div className="chip-row">
                    <span className="chip info">{String(item.created_at ?? "Not started")}</span>
                    <span className="chip">{String(item.review_status ?? "waiting_for_input")}</span>
                    <span className="chip">{String(item.decision_status ?? "waiting_for_input")}</span>
                    <span className="chip">{String(item.execution_status ?? "waiting_for_input")}</span>
                    <span className="chip">{String(item.evaluation_status ?? "waiting_for_input")}</span>
                    <span className="chip">{String(item.local_analysis_status ?? "waiting_for_input")}</span>
                    <span className="chip info">
                      est $
                      {Number(
                        Number(
                          ((item.cost_tracking as Record<string, unknown> | undefined)?.cost_estimate as number) ?? 0,
                        ) || 0,
                      ).toFixed(4)}
                    </span>
                    <span className="chip">{String(item.budget_status ?? "within_budget")}</span>
                  </div>
                </div>
              ))
            ) : (
              <div className="audit-item muted">
                No lifecycle transitions are recorded yet. The drawer will show review, routing, execution, and advisory updates after a package is created.
              </div>
            )}
          </div>
        </div>
      ) : null}
    </section>
  );
}
