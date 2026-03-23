import type {
  ForgeIntakePreview,
  ForgeIntakeWorkspace,
} from "../lib/forge-types";
import { AttachmentDrawer } from "./attachment-drawer";

type IntakeDraft = {
  requestKind: string;
  objective: string;
  constraintsText: string;
  requestedArtifactsText: string;
  autonomyMode: string;
  linkedAttachmentIds: string[];
  previewing: boolean;
  uploading: boolean;
  uploadPurpose: string;
  lastMessage: string;
};

type Props = {
  selectedProjectKey: string;
  workspace: ForgeIntakeWorkspace | null;
  draft: IntakeDraft;
  preview: ForgeIntakePreview | null;
  selectedAttachmentId: string;
  onDraftChange: (patch: Partial<IntakeDraft>) => void;
  onAttachmentToggle: (attachmentId: string) => void;
  onAttachmentSelect: (attachmentId: string) => void;
  onPreview: () => void;
  onUpload: (file: File) => void;
};

function getChipClass(value: string) {
  if (["denied", "quarantined", "error"].includes(value)) {
    return "chip danger";
  }
  if (["needs_input", "ready_with_attachment_limits", "preview_only"].includes(value)) {
    return "chip warn";
  }
  if (["classified", "ready_for_governed_request"].includes(value)) {
    return "chip success";
  }
  return "chip";
}

export function ProjectIntakeWorkspace({
  selectedProjectKey,
  workspace,
  draft,
  preview,
  selectedAttachmentId,
  onDraftChange,
  onAttachmentToggle,
  onAttachmentSelect,
  onPreview,
  onUpload,
}: Props) {
  const attachments = workspace?.attachments ?? [];
  const selectedAttachment =
    attachments.find((item) => item.attachment_id === selectedAttachmentId) ?? attachments[0] ?? null;
  const effectivePreview = preview ?? workspace?.preview ?? null;

  return (
    <section className="panel center-canvas">
      <div className="section-title">
        <div>
          <div className="eyebrow">Phase 1 Intake</div>
          <h3>Project Intake Workspace</h3>
        </div>
        <div className="chip-row">
          <span className="chip info">Preview only</span>
          <span className="chip">Project {selectedProjectKey || "none"}</span>
        </div>
      </div>
      <div className="intake-grid">
        <div className="detail-grid-two">
          <div className="control-card">
            <div className="eyebrow">Build Request</div>
            <div className="form-grid" style={{ marginTop: 10 }}>
              <label className="field">
                <span>Request Type</span>
                <select
                  className="project-select"
                  value={draft.requestKind}
                  onChange={(event) => onDraftChange({ requestKind: event.target.value })}
                >
                  <option value="update_request">Update request</option>
                  <option value="create_request">Create request</option>
                </select>
              </label>
              <label className="field">
                <span>Autonomy Mode</span>
                <select
                  className="project-select"
                  value={draft.autonomyMode}
                  onChange={(event) => onDraftChange({ autonomyMode: event.target.value })}
                >
                  <option value="supervised_build">supervised_build</option>
                  <option value="bounded_low_risk">bounded_low_risk</option>
                  <option value="manual_only">manual_only</option>
                </select>
              </label>
              <label className="field field-span-2">
                <span>Objective</span>
                <textarea
                  className="text-area"
                  rows={4}
                  value={draft.objective}
                  onChange={(event) => onDraftChange({ objective: event.target.value })}
                />
              </label>
              <label className="field">
                <span>Constraints</span>
                <textarea
                  className="text-area"
                  rows={6}
                  value={draft.constraintsText}
                  onChange={(event) => onDraftChange({ constraintsText: event.target.value })}
                />
              </label>
              <label className="field">
                <span>Requested Artifacts</span>
                <textarea
                  className="text-area"
                  rows={6}
                  value={draft.requestedArtifactsText}
                  onChange={(event) =>
                    onDraftChange({ requestedArtifactsText: event.target.value })
                  }
                />
              </label>
            </div>
            <div className="chip-row" style={{ marginTop: 12 }}>
              <span className="chip info">Routing stays in NEXUS</span>
              <span className="chip">No package created</span>
              <span className="chip">No execution side effects</span>
            </div>
            <div className="button-row" style={{ marginTop: 14 }}>
              <button
                className="refresh-button"
                disabled={!selectedProjectKey || draft.previewing}
                onClick={onPreview}
                type="button"
              >
                {draft.previewing ? "Previewing..." : "Preview Governed Request"}
              </button>
              <div className="muted">{draft.lastMessage || "Draft changes stay local until previewed."}</div>
            </div>
          </div>

          <div className="control-card">
            <div className="eyebrow">Attachment Drawer</div>
            <AttachmentDrawer
              attachments={attachments}
              emptyMessage="No governed attachments yet. Phase 1 stores them as review-only artifacts."
              eyebrow="Attachment Drawer"
              onSelectAttachment={onAttachmentSelect}
              renderListAction={(attachment) => {
                const linked = draft.linkedAttachmentIds.includes(attachment.attachment_id);
                return (
                  <input
                    checked={linked}
                    onChange={() => onAttachmentToggle(attachment.attachment_id)}
                    onClick={(event) => event.stopPropagation()}
                    type="checkbox"
                  />
                );
              }}
              renderToolbar={
                <div className="attachment-toolbar" style={{ marginBottom: 12 }}>
                  <label className="field">
                    <span>Purpose</span>
                    <select
                      className="project-select"
                      value={draft.uploadPurpose}
                      onChange={(event) => onDraftChange({ uploadPurpose: event.target.value })}
                    >
                      <option value="supporting_context">supporting_context</option>
                      <option value="specification">specification</option>
                      <option value="evidence">evidence</option>
                    </select>
                  </label>
                  <label className="upload-button">
                    <input
                      disabled={!selectedProjectKey || draft.uploading}
                      onChange={(event) => {
                        const file = event.target.files?.[0];
                        event.currentTarget.value = "";
                        if (file) {
                          onUpload(file);
                        }
                      }}
                      type="file"
                    />
                    {draft.uploading ? "Uploading..." : "Attach File"}
                  </label>
                </div>
              }
              selectedAttachmentId={selectedAttachment?.attachment_id ?? ""}
              title="Governed Attachment Details"
            />
          </div>
        </div>

        <div className="control-card">
          <div className="section-title">
            <div>
              <div className="eyebrow">Governed Preview</div>
              <h3>Request And Package Preview</h3>
            </div>
            {effectivePreview ? (
              <span className={getChipClass(effectivePreview.readiness)}>
                {effectivePreview.readiness}
              </span>
            ) : null}
          </div>
          {effectivePreview ? (
            <>
              <div className="chip-row" style={{ marginBottom: 12 }}>
                <span className="chip info">{effectivePreview.autonomy_mode}</span>
                <span className="chip">{effectivePreview.package_preview.creation_mode}</span>
                <span className="chip">
                  linked {effectivePreview.package_preview.attachment_input_count}
                </span>
              </div>
              <div className="detail-grid-three">
                <div className="detail-card">
                  <h4>Objective</h4>
                  <div className="muted">
                    {effectivePreview.objective || "Objective required before a governed request can be formed."}
                  </div>
                </div>
                <div className="detail-card">
                  <h4>Constraints</h4>
                  <div className="detail-list">
                    {effectivePreview.constraints.length > 0 ? (
                      effectivePreview.constraints.map((item) => (
                        <div className="audit-item" key={item}>
                          {item}
                        </div>
                      ))
                    ) : (
                      <div className="audit-item muted">No explicit constraints yet.</div>
                    )}
                  </div>
                </div>
                <div className="detail-card">
                  <h4>Requested Artifacts</h4>
                  <div className="detail-list">
                    {effectivePreview.requested_artifacts.map((item) => (
                      <div className="audit-item" key={item}>
                        {item}
                      </div>
                    ))}
                  </div>
                </div>
              </div>
              <div className="detail-grid-two" style={{ marginTop: 12 }}>
                <div className="detail-card">
                  <h4>Package Preview</h4>
                  <div className="detail-list">
                    <div className="detail-row">
                      <span>Governance Required</span>
                      <strong>{String(effectivePreview.package_preview.governance_required)}</strong>
                    </div>
                    <div className="detail-row">
                      <span>Routing Authority</span>
                      <strong>{effectivePreview.package_preview.routing_authority}</strong>
                    </div>
                    <div className="detail-row">
                      <span>Package Creation Allowed</span>
                      <strong>{String(effectivePreview.package_preview.package_creation_allowed)}</strong>
                    </div>
                  </div>
                  <p className="muted" style={{ marginBottom: 0 }}>
                    {effectivePreview.package_preview.summary}
                  </p>
                </div>
                <div className="detail-card">
                  <h4>Attachment Warnings</h4>
                  <div className="detail-list">
                    {effectivePreview.warnings.length > 0 ? (
                      effectivePreview.warnings.map((warning) => (
                        <div className="audit-item" key={warning}>
                          {warning}
                        </div>
                      ))
                    ) : (
                      <div className="audit-item muted">
                        Linked attachments are eligible for request preview.
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </>
          ) : (
            <div className="audit-item muted">
              Preview data appears after the first governed request preview.
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
