import type {
  ForgeClientProjectSnapshot,
  ForgeReviewCenterSnapshot,
  PackageDetailSnapshot,
  SurfaceMode,
} from "../lib/forge-types";

type Props = {
  detail: PackageDetailSnapshot | null;
  clientProject?: ForgeClientProjectSnapshot | null;
  surfaceMode?: SurfaceMode;
};

function chipClass(value: string) {
  if (["failed", "denied", "quarantined", "critical", "error"].includes(value)) {
    return "chip danger";
  }
  if (["pending", "guarded", "watch", "project_scoped", "in_progress", "ready_for_review"].includes(value)) {
    return "chip warn";
  }
  if (["completed", "succeeded", "classified", "package_linked", "request_linked", "approved", "complete"].includes(value)) {
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

function displayValue(value: unknown, fallback: string) {
  const text = String(value ?? "").trim();
  if (!text || ["unknown", "none", "n/a", "null"].includes(text.toLowerCase())) {
    return fallback;
  }
  return text;
}

export function ReviewCenter({
  detail,
  clientProject = null,
  surfaceMode = "read_only",
}: Props) {
  if (surfaceMode === "client_safe") {
    return (
      <section className="panel" style={{ padding: 18 }}>
        <div className="section-title">
          <div>
            <div className="eyebrow">Client Surface</div>
            <h3>Approved Deliverables And Timeline</h3>
          </div>
          <div className="chip-row">
            <span className="chip info">Sanitized</span>
            <span className="chip">Read only</span>
          </div>
        </div>
        {!clientProject ? (
          <div className="audit-item muted">
            Select a project to review safe milestones, approved deliverables, and shareable artifacts.
          </div>
        ) : (
          <div className="review-grid">
            <div className="detail-card">
              <h4>Project Summary</h4>
              <div className="chip-row" style={{ marginBottom: 10 }}>
                <span className={chipClass(clientProject.client_status)}>
                  {clientProject.client_status}
                </span>
                <span className="chip">{clientProject.current_phase}</span>
                <span className="chip info">client-ready summary</span>
              </div>
              <div>{clientProject.safe_summary}</div>
              <div className="detail-card-subsection">
                <div className="stat-label">Safe Packaged Output</div>
                <div style={{ marginTop: 8 }}>
                  {clientProject.delivery_summary.delivery_summary_title}
                </div>
                <div className="muted" style={{ marginTop: 6 }}>
                  {clientProject.delivery_summary.delivery_summary_text}
                </div>
              </div>
              <div className="detail-card-subsection">
                <div className="stat-label">Progress</div>
                <div className="bar" style={{ marginTop: 8 }}>
                  <div
                    className="bar-fill success"
                    style={{ width: `${clientProject.progress_percent}%` }}
                  />
                </div>
                <div className="stat-subvalue">{clientProject.progress_label}</div>
              </div>
            </div>

            <div className="detail-card">
              <h4>Milestones</h4>
              <div className="detail-list">
                {clientProject.milestones.map((milestone) => (
                  <div className="audit-item" key={milestone.milestone_id}>
                    <div className="chip-row" style={{ marginBottom: 8 }}>
                      <span className={chipClass(milestone.status)}>
                        {milestone.status}
                      </span>
                      <span className="chip">{milestone.target_label}</span>
                    </div>
                    <div style={{ fontWeight: 600 }}>{milestone.title}</div>
                    <div className="muted" style={{ marginTop: 6 }}>
                      {milestone.summary}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="detail-card">
              <h4>Deliverables</h4>
              <div className="chip-row" style={{ marginBottom: 10 }}>
                <span className={chipClass(clientProject.delivery_summary.delivery_progress_state)}>
                  {clientProject.delivery_summary.delivery_progress_state}
                </span>
                <span className="chip">
                  {clientProject.delivery_summary.delivered_artifact_count} artifact types
                </span>
              </div>
              <div className="detail-list">
                {clientProject.deliverables.length > 0 ? (
                  clientProject.deliverables.map((deliverable) => (
                    <div className="audit-item" key={deliverable.deliverable_id}>
                      <div className="chip-row" style={{ marginBottom: 8 }}>
                        <span className={chipClass(deliverable.status)}>
                          {deliverable.status}
                        </span>
                        {deliverable.safe_to_share ? (
                          <span className="chip success">safe to share</span>
                        ) : (
                          <span className="chip">internal progress</span>
                        )}
                      </div>
                      <div style={{ fontWeight: 600 }}>{deliverable.title}</div>
                      <div className="muted" style={{ marginTop: 6 }}>
                        {deliverable.summary}
                      </div>
                    </div>
                  ))
                ) : (
                  <div className="audit-item muted">
                    No approved deliverables are available for this project yet.
                  </div>
                )}
              </div>
            </div>

            <div className="detail-card">
              <h4>Shareable Attachments</h4>
              <div className="detail-list">
                {clientProject.approved_attachments.length > 0 ? (
                  clientProject.approved_attachments.map((attachment) => (
                    <div className="audit-item" key={attachment.attachment_id}>
                      <div className="chip-row" style={{ marginBottom: 8 }}>
                        <span className="chip success">{attachment.status}</span>
                        <span className="chip">{attachment.purpose}</span>
                      </div>
                      <div style={{ fontWeight: 600 }}>{attachment.file_name}</div>
                      <div className="muted" style={{ marginTop: 6 }}>
                        {attachment.summary}
                      </div>
                    </div>
                  ))
                ) : (
                  <div className="audit-item muted">
                    No attachments have been explicitly marked safe to share.
                  </div>
                )}
              </div>
            </div>

            <div className="detail-card">
              <h4>High-Level Timeline</h4>
              <div className="detail-list">
                {clientProject.timeline.map((event) => (
                  <div className="audit-item" key={event.event_id}>
                    <div className="chip-row" style={{ marginBottom: 8 }}>
                      <span className={chipClass(event.status)}>{event.status}</span>
                      {event.occurred_at ? (
                        <span className="chip mono">{event.occurred_at}</span>
                      ) : null}
                    </div>
                    <div style={{ fontWeight: 600 }}>{event.label}</div>
                    <div className="muted" style={{ marginTop: 6 }}>
                      {event.summary}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </section>
    );
  }

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
          No package is active for review yet. Create an intake request or select an execution package to inspect returned artifacts, lifecycle transitions, tests, and related attachments.
        </div>
      ) : (
        <div className="review-grid">
          <div className="detail-card">
            <h4>Execution Feedback</h4>
            <div className="chip-row" style={{ marginBottom: 10 }}>
              <span className={chipClass(review.execution_feedback.package_status)}>
                {displayValue(review.execution_feedback.package_status, "No active execution")}
              </span>
              <span className="chip">
                {review.execution_feedback.package_created
                  ? "package created"
                  : "package not created"}
              </span>
            </div>
            <div className="detail-list">
              <div className="detail-row">
                <span>Package Created</span>
                <strong>
                  {displayValue(review.execution_feedback.package_created_at, "Not started")}
                </strong>
              </div>
              <div className="detail-row">
                <span>Current Transition</span>
                <strong>
                  {displayValue(review.execution_feedback.active_transition, "No active execution")}
                </strong>
              </div>
            </div>
            <div className="detail-card-subsection">
              <div className="stat-label">Status Summary</div>
              <div style={{ marginTop: 8 }}>
                {displayValue(review.execution_feedback.status_summary, "Waiting for input")}
              </div>
            </div>
            <div className="detail-card-subsection">
              <div className="stat-label">Lifecycle Transitions</div>
              <div className="detail-list" style={{ marginTop: 8 }}>
                {review.execution_feedback.lifecycle_transitions.length > 0 ? (
                  review.execution_feedback.lifecycle_transitions.map((item) => (
                    <div className="audit-item" key={`${item.stage_id}-${item.state}`}>
                      <div className="chip-row" style={{ marginBottom: 8 }}>
                        <span className="chip info">{item.stage_label}</span>
                        <span className={chipClass(item.state)}>{item.state}</span>
                      </div>
                      <div>{item.detail}</div>
                    </div>
                  ))
                ) : (
                  <div className="audit-item muted">
                    No lifecycle transitions have been recorded yet.
                  </div>
                )}
              </div>
            </div>
          </div>

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

          <div className="detail-card">
            <h4>Delivery Summary Packaging</h4>
            <div className="chip-row" style={{ marginBottom: 10 }}>
              <span className={chipClass(review.delivery_summary?.delivery_progress_state || "no_delivery_summary")}>
                {review.delivery_summary?.delivery_progress_state || "no_delivery_summary"}
              </span>
              <span className="chip info">not raw internal system state</span>
            </div>
            <div className="detail-card-subsection">
              <div className="stat-label">
                {review.client_safe_delivery_summary?.delivery_summary_title || "Client-Ready Summary"}
              </div>
              <div style={{ marginTop: 8 }}>
                {review.client_safe_delivery_summary?.delivery_summary_text || "No client-ready delivery summary available."}
              </div>
            </div>
            <div className="detail-list" style={{ marginTop: 10 }}>
              <div className="detail-row">
                <span>Artifact Types</span>
                <strong>{String(review.client_safe_delivery_summary?.delivered_artifact_count ?? 0)}</strong>
              </div>
              <div className="detail-row">
                <span>Packaging Reason</span>
                <strong>{review.client_safe_delivery_summary?.packaging_reason || "No packaging reason recorded."}</strong>
              </div>
            </div>
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
                <strong>
                  {displayValue(review.test_results.evaluation_quality_band, "Waiting for input")}
                </strong>
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
