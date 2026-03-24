import { groupPackagesByLifecycle, LIFECYCLE_COLUMNS } from "../lib/forge-selectors";
import type { PackageQueueRow } from "../lib/forge-types";

type Props = {
  packages: PackageQueueRow[];
  selectedPackageId: string;
  includeCompleted: boolean;
  showOnlyRisk: boolean;
  onSelectPackage: (packageId: string) => void;
};

function chipClass(status: string) {
  if (["blocked", "failed", "critical", "error_fallback", "rolled_back"].includes(status)) {
    return "chip danger";
  }
  if (["pending", "review_pending", "guarded", "elevated"].includes(status)) {
    return "chip warn";
  }
  if (["completed", "eligible", "released", "authorized", "succeeded"].includes(status)) {
    return "chip success";
  }
  return "chip";
}

export function PackageLifecycleBoard({
  packages,
  selectedPackageId,
  includeCompleted,
  showOnlyRisk,
  onSelectPackage,
}: Props) {
  const grouped = groupPackagesByLifecycle(packages, includeCompleted, showOnlyRisk);
  return (
    <section className="panel center-canvas">
      <div className="section-title">
        <div>
          <div className="eyebrow">Execution Surface</div>
          <h3>Package Lifecycle Board</h3>
        </div>
        <div className="chip-row">
          <span className="chip">Real package stages only</span>
          <span className="chip info">{packages.length} packages visible</span>
        </div>
      </div>
      <div className="board-columns">
        {LIFECYCLE_COLUMNS.map((column) => (
          <div className="board-column" key={column}>
            <h3>{column}</h3>
            <div className="board-column-count">
              {grouped[column].length} package{grouped[column].length === 1 ? "" : "s"}
            </div>
            <div className="package-stack">
              {grouped[column].length === 0 ? (
                <div className="audit-item muted">
                  No packages are in this lifecycle state right now. Create or preview an intake request to help Forge prepare the next governed execution package.
                </div>
              ) : (
                grouped[column].map((pkg) => {
                  const active = pkg.package_id === selectedPackageId;
                  return (
                    <div
                      className={`package-card ${active ? "active" : ""}`}
                      key={pkg.package_id}
                    >
                      <button
                        className="package-button"
                        type="button"
                        onClick={() => onSelectPackage(pkg.package_id)}
                      >
                        <div className="package-title">
                          <span className="mono">{pkg.package_id}</span>
                          <span className={chipClass(pkg.execution_status)}>
                            {pkg.execution_status || "No active execution"}
                          </span>
                        </div>
                        <div className="package-path">
                          {pkg.runtime_target_id || "Waiting for input"}
                        </div>
                        <div className="detail-list" style={{ marginTop: 10 }}>
                          <div className="detail-row">
                            <span>Status</span>
                            <strong>{pkg.lifecycle_status_label || "Not started"}</strong>
                          </div>
                          <div className="detail-row">
                            <span>Last Action</span>
                            <strong>{pkg.last_action_label || "Waiting for input"}</strong>
                          </div>
                          <div className="detail-row">
                            <span>Package Created</span>
                            <strong>{pkg.created_at || "Not started"}</strong>
                          </div>
                        </div>
                        <div className="chip-row" style={{ marginTop: 10 }}>
                          <span className={chipClass(pkg.review_status)}>
                            review {pkg.review_status || "waiting_for_input"}
                          </span>
                          <span className={chipClass(pkg.evaluation_status)}>
                            eval {pkg.evaluation_status || "waiting_for_input"}
                          </span>
                          <span className={chipClass(pkg.local_analysis_status)}>
                            local {pkg.local_analysis_status || "waiting_for_input"}
                          </span>
                        </div>
                        <div className="metric-list" style={{ marginTop: 12 }}>
                          <div>
                            <div className="stat-label">Failure Risk</div>
                            <div className="bar">
                              <div
                                className={`bar-fill ${
                                  ["high", "critical"].includes(pkg.failure_risk_band)
                                    ? "danger"
                                    : ["guarded", "elevated"].includes(pkg.failure_risk_band)
                                      ? "warn"
                                      : "success"
                                }`}
                                style={{
                                  width:
                                    pkg.failure_risk_band === "critical"
                                      ? "100%"
                                      : pkg.failure_risk_band === "high"
                                        ? "82%"
                                        : pkg.failure_risk_band === "elevated"
                                          ? "62%"
                                          : pkg.failure_risk_band === "guarded"
                                            ? "46%"
                                            : "24%",
                                }}
                              />
                            </div>
                          </div>
                          <div className="chip-row">
                            {pkg.suggested_next_action ? (
                              <span className="chip info">{pkg.suggested_next_action}</span>
                            ) : null}
                            {pkg.failure_class ? (
                              <span className="chip danger">{pkg.failure_class}</span>
                            ) : null}
                          </div>
                        </div>
                      </button>
                    </div>
                  );
                })
              )}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
