import type { ForgeReviewCenterSnapshot, PackageDetailSnapshot } from "../lib/forge-types";

type Props = {
  detail: PackageDetailSnapshot | null;
};

function chipClass(value: string) {
  if (["failed", "denied", "quarantined", "critical", "error"].includes(value)) {
    return "chip danger";
  }
  if (["pending", "guarded", "watch", "project_scoped"].includes(value)) {
    return "chip warn";
  }
  if (["completed", "succeeded", "classified", "package_linked", "request_linked"].includes(value)) {
    return "chip success";
  }
  return "chip";
}

function entryList(value: Record<string, unknown>) {
  return Object.entries(value).filter(([, item]) => item !== undefined && item !== null && item !== "");
}

function getReview(detail: PackageDetailSnapshot | null): ForgeReviewCenterSnapshot | null {
  return detail?.review_center ?? null;
}

export function ReviewCenter({ detail }: Props) {
  const review = getReview(detail);
  const approval = review?.approval_ready_context;

  return (
    <section className="panel" style={{ padding: 18 }}>
      <div className="section-title">
        <div>
          <div className="eyebrow">Review Center</div>
          <h3>Approval-Oriented Review Surface</h3>
        </div>
        <div className="chip-row">
          <span className={chipClass(String(approval?.review_status ?? "pending"))}>
            {String(approval?.review_status ?? "pending")}
          </span>
          <span className="chip">
            package {detail?.package_id ? "selected" : "none"}
          </span>
        </div>
      </div>
      {!review ? (
        <div className="audit-item muted">
          Select a package to review returned artifacts, diff context, tests, and related attachments.
        </div>
      ) : (
        <div className="review-grid">
          <div className="detail-card">
            <h4>Approval Ready Context</h4>
            <div className="chip-row" style={{ marginBottom: 10 }}>
              <span className={chipClass(String(approval?.review_status ?? ""))}>
                {String(approval?.review_status ?? "pending")}
              </span>
              <span className={chipClass(String(approval?.decision_status ?? ""))}>
                decision {String(approval?.decision_status ?? "pending")}
              </span>
              <span className={chipClass(String(approval?.release_status ?? ""))}>
                release {String(approval?.release_status ?? "pending")}
              </span>
            </div>
            <div className="detail-list">
              <div className="detail-row">
                <span>Requires Human Approval</span>
                <strong>{String(approval?.requires_human_approval ?? false)}</strong>
              </div>
              <div className="detail-row">
                <span>Sealed</span>
                <strong>{String(approval?.sealed ?? false)}</strong>
              </div>
              <div className="detail-row">
                <span>Approval Refs</span>
                <strong>{approval?.approval_id_refs.join(", ") || "none"}</strong>
              </div>
            </div>
            <div className="detail-card-subsection">
              <div className="stat-label">Seal Reason</div>
              <div style={{ marginTop: 8 }}>{approval?.seal_reason || "No seal reason recorded."}</div>
            </div>
            <div className="detail-card-subsection">
              <div className="stat-label">Review Checklist</div>
              <div className="detail-list" style={{ marginTop: 8 }}>
                {(approval?.review_checklist ?? []).length > 0 ? (
                  approval?.review_checklist.map((item) => (
                    <div className="audit-item" key={item}>
                      {item}
                    </div>
                  ))
                ) : (
                  <div className="audit-item muted">No checklist stored.</div>
                )}
              </div>
            </div>
          </div>

          <div className="detail-card">
            <h4>Returned Artifacts</h4>
            <div className="detail-list">
              {review.returned_artifacts.length > 0 ? (
                review.returned_artifacts.map((artifact, index) => (
                  <div className="audit-item" key={`${artifact.artifact_type}-${index}`}>
                    <div className="chip-row" style={{ marginBottom: 8 }}>
                      <span className="chip info">{artifact.artifact_type}</span>
                      <span className={chipClass(artifact.status)}>{artifact.status}</span>
                      <span className="chip">{artifact.source}</span>
                    </div>
                    <div>{artifact.summary || "No artifact summary stored."}</div>
                  </div>
                ))
              ) : (
                <div className="audit-item muted">No returned artifacts recorded for this package.</div>
              )}
            </div>
          </div>

          <div className="detail-card">
            <h4>Patch / Diff Summary</h4>
            <div className="detail-card-subsection">
              <div className="stat-label">Patch Summary</div>
              <div style={{ marginTop: 8 }}>
                {review.patch_context.patch_summary || "No patch summary returned."}
              </div>
            </div>
            <div className="detail-grid-two" style={{ marginTop: 12 }}>
              <div className="detail-card-subsection">
                <div className="stat-label">Changed Files</div>
                <div className="detail-list" style={{ marginTop: 8 }}>
                  {review.patch_context.changed_files.length > 0 ? (
                    review.patch_context.changed_files.map((item) => (
                      <div className="audit-item mono" key={item}>
                        {item}
                      </div>
                    ))
                  ) : (
                    <div className="audit-item muted">No changed files recorded.</div>
                  )}
                </div>
              </div>
              <div className="detail-card-subsection">
                <div className="stat-label">Requested Outputs</div>
                <div className="detail-list" style={{ marginTop: 8 }}>
                  {review.patch_context.requested_outputs.length > 0 ? (
                    review.patch_context.requested_outputs.map((item) => (
                      <div className="audit-item" key={item}>
                        {item}
                      </div>
                    ))
                  ) : (
                    <div className="audit-item muted">No requested outputs recorded.</div>
                  )}
                </div>
              </div>
            </div>
          </div>

          <div className="detail-card">
            <h4>Test Results</h4>
            <div className="chip-row" style={{ marginBottom: 10 }}>
              <span className={chipClass(review.test_results.execution_result_status)}>
                {review.test_results.execution_result_status}
              </span>
              <span className={chipClass(review.test_results.integrity_status)}>
                integrity {review.test_results.integrity_status}
              </span>
              <span className="chip">
                next {review.test_results.suggested_next_action || "none"}
              </span>
            </div>
            <div className="detail-list">
              <div className="detail-row">
                <span>Exit Code</span>
                <strong>{String(review.test_results.exit_code ?? "n/a")}</strong>
              </div>
              <div className="detail-row">
                <span>Execution Log</span>
                <strong className="mono">{review.test_results.log_ref || "none"}</strong>
              </div>
              <div className="detail-row">
                <span>Evaluation Quality Band</span>
                <strong>{review.test_results.evaluation_quality_band || "unknown"}</strong>
              </div>
            </div>
          </div>

          <div className="detail-card">
            <h4>Evaluation Summary</h4>
            <div className="detail-list">
              {entryList(review.evaluation_summary).length > 0 ? (
                entryList(review.evaluation_summary).map(([key, value]) => (
                  <div className="detail-row" key={key}>
                    <span>{key}</span>
                    <strong>{String(value)}</strong>
                  </div>
                ))
              ) : (
                <div className="audit-item muted">No evaluation summary recorded.</div>
              )}
            </div>
          </div>

          <div className="detail-card">
            <h4>Attachment-Linked Review Context</h4>
            <div className="detail-list">
              {review.related_attachments.length > 0 ? (
                review.related_attachments.map((attachment) => (
                  <div className="audit-item" key={attachment.attachment_id}>
                    <div className="chip-row" style={{ marginBottom: 8 }}>
                      <span className={chipClass(attachment.status)}>{attachment.status}</span>
                      <span className={chipClass(attachment.review_relevance)}>
                        {attachment.review_relevance}
                      </span>
                    </div>
                    <div>{attachment.file_name}</div>
                    <div className="muted" style={{ marginTop: 6 }}>
                      {attachment.extracted_summary || attachment.status_reason}
                    </div>
                  </div>
                ))
              ) : (
                <div className="audit-item muted">No governed attachments available for review context.</div>
              )}
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
