import { getLocalAnalysisSummary } from "../lib/forge-selectors";
import type { PackageDetailSnapshot } from "../lib/forge-types";

type Props = {
  detail: PackageDetailSnapshot | null;
};

function confidenceClass(value: string) {
  if (value === "low") {
    return "danger";
  }
  if (["guarded", "moderate"].includes(value)) {
    return "warn";
  }
  if (value === "high") {
    return "success";
  }
  return "info";
}

export function NemoClawAdvisoryPanel({ detail }: Props) {
  const analysis = detail?.local_analysis ?? {};
  const summary = getLocalAnalysisSummary(detail);
  return (
    <section className="panel" style={{ padding: 18 }}>
      <div className="section-title">
        <div>
          <div className="eyebrow">NemoClaw</div>
          <h3>Advisory Panel</h3>
        </div>
        <span className={`chip ${confidenceClass(String(summary.confidence_band ?? ""))}`}>
          {String(analysis.local_analysis_status ?? "pending")}
        </span>
      </div>
      <div className="metric-grid">
        <div className="metric">
          <div className="stat-label">Confidence</div>
          <strong>{Number(summary.confidence_score ?? 0)}</strong>
          <span className={`chip ${confidenceClass(String(summary.confidence_band ?? ""))}`}>
            {String(summary.confidence_band ?? "unknown")}
          </span>
        </div>
        <div className="metric">
          <div className="stat-label">Suggested Action</div>
          <strong style={{ fontSize: 16 }}>
            {String(summary.suggested_next_action ?? "none")}
          </strong>
        </div>
      </div>
      <div className="control-card" style={{ marginTop: 14 }}>
        <div className="stat-label">Risk Interpretation</div>
        <div style={{ marginTop: 10 }}>
          {String(summary.risk_interpretation ?? "No advisory interpretation available.")}
        </div>
      </div>
      <div className="control-card" style={{ marginTop: 12 }}>
        <div className="stat-label">Evaluation Interpretation</div>
        <div style={{ marginTop: 10 }}>
          {String(
            summary.execution_evaluation_interpretation ??
              "No execution evaluation interpretation available.",
          )}
        </div>
      </div>
    </section>
  );
}
