import type { ReactNode } from "react";
import type { ForgeAttachmentRecord, ForgeReviewAttachmentRecord } from "../lib/forge-types";

type AttachmentRecord = ForgeAttachmentRecord | ForgeReviewAttachmentRecord;

type Props = {
  attachments: AttachmentRecord[];
  selectedAttachmentId: string;
  title: string;
  eyebrow: string;
  emptyMessage: string;
  onSelectAttachment: (attachmentId: string) => void;
  renderToolbar?: ReactNode;
  renderListAction?: (attachment: AttachmentRecord) => ReactNode;
};

function chipClass(value: string) {
  if (["denied", "quarantined", "error"].includes(value)) {
    return "chip danger";
  }
  if (["project_scoped", "needs_input", "ready_with_attachment_limits"].includes(value)) {
    return "chip warn";
  }
  if (["classified", "package_linked", "request_linked"].includes(value)) {
    return "chip success";
  }
  return "chip";
}

function asReviewAttachment(
  attachment: AttachmentRecord,
): attachment is ForgeReviewAttachmentRecord {
  return "review_relevance" in attachment;
}

export function AttachmentDrawer({
  attachments,
  selectedAttachmentId,
  title,
  eyebrow,
  emptyMessage,
  onSelectAttachment,
  renderToolbar,
  renderListAction,
}: Props) {
  const selected =
    attachments.find((item) => item.attachment_id === selectedAttachmentId) ?? attachments[0] ?? null;

  return (
    <div className="control-card">
      <div className="section-title">
        <div>
          <div className="eyebrow">{eyebrow}</div>
          <h3>{title}</h3>
        </div>
        {selected ? <span className={chipClass(selected.status)}>{selected.status}</span> : null}
      </div>
      {renderToolbar}
      <div className="attachment-list">
        {attachments.length === 0 ? (
          <div className="audit-item muted">{emptyMessage}</div>
        ) : (
          attachments.map((attachment) => {
            const active = selected?.attachment_id === attachment.attachment_id;
            return (
              <button
                className={`attachment-card ${active ? "active" : ""}`}
                key={attachment.attachment_id}
                onClick={() => onSelectAttachment(attachment.attachment_id)}
                type="button"
              >
                <div className="package-title">
                  <span>{attachment.file_name}</span>
                  {renderListAction ? renderListAction(attachment) : null}
                </div>
                <div className="chip-row">
                  <span className={chipClass(attachment.status)}>{attachment.status}</span>
                  <span className="chip">{attachment.classification}</span>
                  {"purpose" in attachment ? (
                    <span className="chip">{attachment.purpose}</span>
                  ) : null}
                  {asReviewAttachment(attachment) ? (
                    <span className={chipClass(attachment.review_relevance)}>
                      {attachment.review_relevance}
                    </span>
                  ) : null}
                </div>
                <div className="muted">
                  {attachment.extracted_summary || attachment.status_reason}
                </div>
              </button>
            );
          })
        )}
      </div>
      {selected ? (
        <div className="detail-card" style={{ marginTop: 12 }}>
          <div className="package-title">
            <span>{selected.file_name}</span>
            <span className={chipClass(selected.status)}>{selected.status}</span>
          </div>
          <div className="detail-grid-two">
            <div className="detail-list">
              <div className="detail-row">
                <span>Classification</span>
                <strong>{selected.classification}</strong>
              </div>
              <div className="detail-row">
                <span>Allowed Consumers</span>
                <strong>{selected.allowed_consumers.join(", ") || "none"}</strong>
              </div>
              <div className="detail-row">
                <span>Linked Project</span>
                <strong>{selected.linked_context.project_id || selected.project_id}</strong>
              </div>
              <div className="detail-row">
                <span>Linked Package</span>
                <strong>{selected.linked_context.package_id || "none"}</strong>
              </div>
              <div className="detail-row">
                <span>Linked Request</span>
                <strong>{selected.linked_context.request_id || "none"}</strong>
              </div>
            </div>
            <div className="detail-list">
              <div className="detail-row">
                <span>Review Ready</span>
                <strong>
                  {asReviewAttachment(selected)
                    ? String(selected.review_ready)
                    : String(selected.allowed_consumers.includes("console_review"))}
                </strong>
              </div>
              {asReviewAttachment(selected) ? (
                <div className="detail-row">
                  <span>Review Relevance</span>
                  <strong>{selected.review_relevance}</strong>
                </div>
              ) : null}
              <div className="detail-row">
                <span>Stored Path</span>
                <strong className="mono">{selected.raw_storage_path || "not stored"}</strong>
              </div>
              <div className="detail-row">
                <span>Status Reason</span>
                <strong>{selected.status_reason}</strong>
              </div>
              <div className="detail-row">
                <span>Trace</span>
                <strong>{selected.governance_trace.origin}</strong>
              </div>
            </div>
          </div>
          <div className="detail-card-subsection">
            <div className="stat-label">Extracted Summary</div>
            <div style={{ marginTop: 8 }}>
              {selected.extracted_summary || "No extracted summary available for this attachment."}
            </div>
          </div>
          <div className="detail-card-subsection">
            <div className="stat-label">Quarantine / Deny Reasoning</div>
            <div style={{ marginTop: 8 }}>{selected.status_reason}</div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
