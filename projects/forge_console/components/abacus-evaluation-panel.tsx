import { getEvaluationSummary } from "../lib/forge-selectors";
import type { PackageDetailSnapshot } from "../lib/forge-types";

type Props = {
  detail: PackageDetailSnapshot | null;
};

function bandClass(value: string) {
  if (["critical", "weak"].includes(value)) {
    return "danger";
  }
  if (["mixed", "guarded", "elevated"].includes(value)) {
    return "warn";
  }
  if (["strong", "excellent", "low"].includes(value)) {
    return "success";
  }
  return "info";
}

export function AbacusEvaluationPanel({ detail }: Props) {
  const evaluation = detail?.evaluation ?? {};
  const summary = getEvaluationSummary(detail);
  return (
    <section className="panel" style={{ padding: 18 }}>
      <div className="section-title">
        <div>
          <div className="eyebrow">Abacus</div>
          <h3>Evaluation Panel</h3>
        </div>
        <span className={`chip ${bandClass(String(summary.failure_risk_band ?? ""))}`}>
          {String(evaluation.evaluation_status ?? "pending")}
        </span>
      </div>
      <div className="metric-grid">
        <div className="metric">
          <div className="stat-label">Execution Quality</div>
          <strong>{Number(summary.execution_quality_score ?? 0)}</strong>
          <span className={`chip ${bandClass(String(summary.execution_quality_band ?? ""))}`}>
            {String(summary.execution_quality_band ?? "unknown")}
          </span>
        </div>
        <div className="metric">
          <div className="stat-label">Integrity</div>
          <strong>{Number(summary.integrity_score ?? 0)}</strong>
          <span className={`chip ${bandClass(String(summary.integrity_band ?? ""))}`}>
            {String(summary.integrity_band ?? "unknown")}
          </span>
        </div>
        <div className="metric">
          <div className="stat-label">Rollback Quality</div>
          <strong>{Number(summary.rollback_quality ?? 0)}</strong>
          <span
            className={`chip ${bandClass(String(summary.rollback_quality_band ?? ""))}`}
          >
            {String(summary.rollback_quality_band ?? "unknown")}
          </span>
        </div>
        <div className="metric">
          <div className="stat-label">Failure Risk</div>
          <strong>{Number(summary.failure_risk_score ?? 0)}</strong>
          <span className={`chip ${bandClass(String(summary.failure_risk_band ?? ""))}`}>
            {String(summary.failure_risk_band ?? "unknown")}
          </span>
        </div>
      </div>
      <div className="control-card" style={{ marginTop: 14 }}>
        <div className="stat-label">Evaluation Basis</div>
        <div className="detail-list" style={{ marginTop: 10 }}>
          {Object.entries(
            (evaluation.evaluation_basis as Record<string, unknown>) ?? {},
          ).map(([key, value]) => (
            <div className="detail-row" key={key}>
              <span>{key}</span>
              <strong>{String(value ?? "")}</strong>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
