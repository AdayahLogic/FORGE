import type { ApprovalCenterState, ControlDraft } from "../lib/forge-types";

type Props = {
  approvalSummary: Record<string, unknown>;
  lifecycleSummary: Record<string, unknown>;
  selectedProjectKey: string;
  controlDraft: ControlDraft;
  approvalCenterState: ApprovalCenterState;
  onActionChange: (action: string) => void;
  onConfirmationTextChange: (value: string) => void;
  onConfirmedChange: (value: boolean) => void;
  onSubmit: () => void;
};

export function ApprovalControlCenter({
  approvalSummary,
  lifecycleSummary,
  selectedProjectKey,
  controlDraft,
  approvalCenterState,
  onActionChange,
  onConfirmationTextChange,
  onConfirmedChange,
  onSubmit,
}: Props) {
  const pendingCount = Number(approvalSummary.pending_count_total ?? 0);
  const staleCount = Number(approvalSummary.stale_count ?? 0);
  const reapprovalCount = Number(lifecycleSummary.reapproval_required_count ?? 0);
  return (
    <section className="panel" style={{ padding: 18 }}>
      <div className="section-title">
        <div>
          <div className="eyebrow">Human Gate</div>
          <h3>Approval / Control Center</h3>
        </div>
        <span className="chip warn">Supervised control only</span>
      </div>
      <div className="metric-grid">
        <div className="metric">
          <div className="stat-label">Pending Approvals</div>
          <strong>{pendingCount}</strong>
        </div>
        <div className="metric">
          <div className="stat-label">Reapproval Warnings</div>
          <strong>{reapprovalCount}</strong>
        </div>
        <div className="metric">
          <div className="stat-label">Stale Approvals</div>
          <strong>{staleCount}</strong>
        </div>
        <div className="metric">
          <div className="stat-label">Project Scope</div>
          <strong className="mono">{selectedProjectKey || "none"}</strong>
        </div>
      </div>
      <div className="control-actions" style={{ marginTop: 16 }}>
        <select
          className="project-select"
          value={controlDraft.action}
          onChange={(event) => onActionChange(event.target.value)}
        >
          <option value="complete_review">complete_review</option>
          <option value="complete_approval">complete_approval</option>
        </select>
        <input
          className="confirmation-input"
          placeholder={approvalCenterState.requiredConfirmationPhrase}
          value={controlDraft.confirmationText}
          onChange={(event) => onConfirmationTextChange(event.target.value)}
        />
        <label className="chip">
          <input
            checked={controlDraft.confirmed}
            onChange={(event) => onConfirmedChange(event.target.checked)}
            style={{ marginRight: 8 }}
            type="checkbox"
          />
          Explicitly confirm supervised action
        </label>
        <button
          className="action-button"
          disabled={controlDraft.submitting || !selectedProjectKey}
          type="button"
          onClick={onSubmit}
        >
          {controlDraft.submitting ? "Submitting..." : "Run Explicit Action"}
        </button>
        <div className="control-card">
          <div className="stat-label">Last Action Result</div>
          <div style={{ marginTop: 8 }}>
            <span
              className={
                approvalCenterState.lastActionStatus === "success"
                  ? "chip success"
                  : approvalCenterState.lastActionStatus === "error"
                    ? "chip danger"
                    : "chip"
              }
            >
              {approvalCenterState.lastActionStatus}
            </span>
          </div>
          <div className="muted" style={{ marginTop: 10 }}>
            {approvalCenterState.lastActionMessage ||
              "No supervised action has been submitted in this session."}
          </div>
        </div>
      </div>
    </section>
  );
}
