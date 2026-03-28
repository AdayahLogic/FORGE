import type { ForgeOverviewSnapshot } from "../lib/forge-types";

type BillingUsagePanelProps = {
  overview: ForgeOverviewSnapshot | null;
};

export function BillingUsagePanel({ overview }: BillingUsagePanelProps) {
  const cost = overview?.overview?.cost_visibility;
  const budget = overview?.overview?.budget_visibility;

  if (!cost && !budget) {
    return null;
  }

  return (
    <section className="panel">
      <div className="section-title">
        <div>
          <div className="eyebrow">Billing</div>
          <h3>Usage This Cycle</h3>
        </div>
        <span className="chip info">Estimated (non-billed preview)</span>
      </div>
      <div className="detail-grid-three">
        <div className="stat-card">
          <div className="stat-label">Estimated Total</div>
          <div className="stat-value">
            ${(cost?.estimated_cost_total_usd ?? 0).toFixed(4)}
          </div>
          <div className="stat-subvalue">{cost?.label ?? ""}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Budget Status</div>
          <div className="stat-value">{budget?.budget_status ?? "within_budget"}</div>
          <div className="stat-subvalue">
            Cap ${(budget?.budget_cap ?? 0).toFixed(2)} / Remaining $
            {(budget?.remaining_estimated_budget ?? 0).toFixed(4)}
          </div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Kill Switch</div>
          <div className="stat-value">
            {budget?.kill_switch_active ? "Active" : "Inactive"}
          </div>
          <div className="stat-subvalue">
            Budget scope: {budget?.budget_scope ?? "-"}
          </div>
        </div>
      </div>
    </section>
  );
}
