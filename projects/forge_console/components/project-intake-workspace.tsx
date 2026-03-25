import type {
  ForgeConstraintSections,
  ForgeIntakePreview,
  ForgeLeadIntakeProfile,
  ForgeIntakeWorkspace,
  ForgeLeadQualificationDraft,
  ForgeRequestedArtifactsDraft,
} from "../lib/forge-types";
import { AttachmentDrawer } from "./attachment-drawer";

type IntakeDraft = {
  requestKind: string;
  objective: string;
  projectContext: string;
  structuredConstraints: ForgeConstraintSections;
  requestedArtifacts: ForgeRequestedArtifactsDraft;
  leadIntake: ForgeLeadIntakeProfile;
  leadQualificationDraft: ForgeLeadQualificationDraft;
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

const AUTONOMY_MODE_OPTIONS = [
  {
    value: "supervised_build",
    label: "supervised_build",
    summary: "Forge prepares governed work and pauses for operator review at key progression points.",
  },
  {
    value: "assisted_autopilot",
    label: "assisted_autopilot",
    summary: "Forge may continue through bounded steps, but governance, approval, and elevated-risk triggers still stop or escalate.",
  },
  {
    value: "low_risk_autonomous_development",
    label: "low_risk_autonomous_development",
    summary: "Forge may continue only through explicitly low-risk development loops and must escalate ambiguous or risky work.",
  },
] as const;

const REQUESTED_ARTIFACT_OPTIONS = [
  { value: "implementation_plan", label: "Implementation plan" },
  { value: "code_artifacts", label: "Code artifacts" },
  { value: "tests", label: "Tests" },
  { value: "review_package", label: "Review package" },
  { value: "summary_report", label: "Summary / report" },
] as const;

const LEAD_BUDGET_BANDS = ["", "none", "very_low", "low", "medium", "high", "enterprise"] as const;
const LEAD_URGENCY_LEVELS = ["", "low", "medium", "high", "critical"] as const;
const LEAD_PROBLEM_CLARITY_LEVELS = ["", "unclear", "partial", "clear", "very_clear"] as const;
const LEAD_DECISION_READINESS_LEVELS = ["", "exploring", "evaluating", "ready", "committed"] as const;

const CONSTRAINT_FIELDS = [
  {
    key: "scope_boundaries",
    label: "Scope Boundaries",
    help: "Define what this request must stay inside or explicitly avoid.",
  },
  {
    key: "risk_notes",
    label: "Risk Notes",
    help: "Capture sensitive areas, hazards, or reasons to proceed carefully.",
  },
  {
    key: "runtime_preferences",
    label: "Runtime Preferences / Restrictions",
    help: "State environment preferences or runtime limits without making execution decisions in the UI.",
  },
  {
    key: "output_expectations",
    label: "Output Expectations",
    help: "Describe what the returned work should contain or prove.",
  },
  {
    key: "review_expectations",
    label: "Review Expectations",
    help: "Describe what reviewers should be able to inspect later in Review Center.",
  },
] as const;

function getChipClass(value: string) {
  if (["denied", "quarantined", "error"].includes(value)) {
    return "chip danger";
  }
  if (
    [
      "needs_input",
      "ready_with_attachment_limits",
      "preview_only",
      "stale_preview",
      "underqualified",
      "needs_more_info",
      "no_offer_yet",
      "offer_needs_more_info",
      "high_touch_review_recommended",
      "no_response",
      "needs_more_info",
      "high_touch_required",
    ].includes(value)
  ) {
    return "chip warn";
  }
  if (
    [
      "classified",
      "ready_for_governed_request",
      "qualified",
      "high_priority",
      "offer_ready",
      "response_ready",
    ].includes(value)
  ) {
    return "chip success";
  }
  return "chip";
}

function toLines(value: string) {
  return value
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function fromLines(value: string[]) {
  return value.join("\n");
}

function labelForMissingField(value: string) {
  const labels: Record<string, string> = {
    objective: "Objective",
    project_context: "Project / request context",
    requested_artifacts: "Requested artifacts",
    scope_boundaries: "Scope boundaries",
    output_expectations: "Output expectations",
    review_expectations: "Review expectations",
    lead_contact_name: "Lead contact name",
    lead_contact_email: "Lead contact email",
    lead_company_name: "Lead company name",
    lead_problem_summary: "Lead problem summary",
    preview_error: "Preview availability",
  };
  return labels[value] ?? value.replace(/_/g, " ");
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
  const effectivePreview = preview ?? null;
  const draftMode =
    AUTONOMY_MODE_OPTIONS.find((item) => item.value === draft.autonomyMode) ??
    AUTONOMY_MODE_OPTIONS[0];

  return (
    <section className="panel center-canvas">
      <div className="section-title">
        <div>
          <div className="eyebrow">Phase C Intake</div>
          <h3>Build Request Workspace</h3>
        </div>
        <div className="chip-row">
          <span className="chip info">Preview first</span>
          <span className="chip">Project {selectedProjectKey || "none"}</span>
          <span className="chip">UI composes only</span>
        </div>
      </div>
      <div className="intake-grid">
        <div className="detail-grid-two">
          <div className="control-card">
            <div className="eyebrow">Request Composition</div>
            <div className="form-grid intake-form-grid" style={{ marginTop: 10 }}>
              <label className="field">
                <span>Request Type</span>
                <select
                  className="project-select"
                  value={draft.requestKind}
                  onChange={(event) => onDraftChange({ requestKind: event.target.value })}
                >
                  <option value="update_request">Update request</option>
                  <option value="create_request">Create request</option>
                  <option value="lead_intake">Lead intake (revenue)</option>
                </select>
              </label>
              <div className="field">
                <span>Autonomy Intent</span>
                <div className="autonomy-mode-list">
                  {AUTONOMY_MODE_OPTIONS.map((option) => {
                    const active = draft.autonomyMode === option.value;
                    return (
                      <button
                        className={`autonomy-mode-card ${active ? "active" : ""}`}
                        key={option.value}
                        onClick={() => onDraftChange({ autonomyMode: option.value })}
                        type="button"
                      >
                        <div className="package-title">
                          <span>{option.label}</span>
                          <span className={`chip ${active ? "info" : ""}`}>
                            {active ? "Selected" : "Available"}
                          </span>
                        </div>
                        <div className="muted">{option.summary}</div>
                      </button>
                    );
                  })}
                </div>
                <div className="muted">
                  Selecting a mode only sets governed request intent. Routing, governance, and execution remain backend-controlled.
                </div>
              </div>
              <label className="field field-span-2">
                <span>Objective</span>
                <textarea
                  className="text-area"
                  rows={4}
                  value={draft.objective}
                  onChange={(event) => onDraftChange({ objective: event.target.value })}
                />
              </label>
              <label className="field field-span-2">
                <span>Project / Request Context</span>
                <textarea
                  className="text-area"
                  rows={4}
                  value={draft.projectContext}
                  onChange={(event) => onDraftChange({ projectContext: event.target.value })}
                />
              </label>
              {draft.requestKind === "lead_intake" ? (
                <div className="field field-span-2">
                  <div className="package-title" style={{ marginBottom: 10 }}>
                    <span>Lead Intake Profile (Phase 79)</span>
                    <span className="chip">Governed preview profile</span>
                  </div>
                  <div className="constraint-grid">
                  <label className="field">
                    <span>Contact Name</span>
                    <input
                      className="project-select"
                      type="text"
                      value={draft.leadIntake.contact_name}
                      onChange={(event) =>
                        onDraftChange({
                          leadIntake: {
                            ...draft.leadIntake,
                            contact_name: event.target.value,
                          },
                        })
                      }
                    />
                  </label>
                  <label className="field">
                    <span>Contact Email</span>
                    <input
                      className="project-select"
                      type="email"
                      value={draft.leadIntake.contact_email}
                      onChange={(event) =>
                        onDraftChange({
                          leadIntake: {
                            ...draft.leadIntake,
                            contact_email: event.target.value,
                          },
                        })
                      }
                    />
                  </label>
                  <label className="field">
                    <span>Company Name</span>
                    <input
                      className="project-select"
                      type="text"
                      value={draft.leadIntake.company_name}
                      onChange={(event) =>
                        onDraftChange({
                          leadIntake: {
                            ...draft.leadIntake,
                            company_name: event.target.value,
                          },
                        })
                      }
                    />
                  </label>
                  <label className="field">
                    <span>Contact Channel</span>
                    <input
                      className="project-select"
                      type="text"
                      value={draft.leadIntake.contact_channel}
                      onChange={(event) =>
                        onDraftChange({
                          leadIntake: {
                            ...draft.leadIntake,
                            contact_channel: event.target.value,
                          },
                        })
                      }
                    />
                  </label>
                  <label className="field">
                    <span>Lead Source</span>
                    <input
                      className="project-select"
                      type="text"
                      value={draft.leadIntake.lead_source}
                      onChange={(event) =>
                        onDraftChange({
                          leadIntake: {
                            ...draft.leadIntake,
                            lead_source: event.target.value,
                          },
                        })
                      }
                    />
                  </label>
                  <label className="field field-span-2">
                    <span>Problem Summary</span>
                    <textarea
                      className="text-area"
                      rows={4}
                      value={draft.leadIntake.problem_summary}
                      onChange={(event) =>
                        onDraftChange({
                          leadIntake: {
                            ...draft.leadIntake,
                            problem_summary: event.target.value,
                          },
                        })
                      }
                    />
                  </label>
                  <label className="field field-span-2">
                    <span>Requested Outcome</span>
                    <textarea
                      className="text-area"
                      rows={3}
                      value={draft.leadIntake.requested_outcome}
                      onChange={(event) =>
                        onDraftChange({
                          leadIntake: {
                            ...draft.leadIntake,
                            requested_outcome: event.target.value,
                          },
                        })
                      }
                    />
                  </label>
                  <label className="field">
                    <span>Budget Context (raw)</span>
                    <textarea
                      className="text-area"
                      rows={3}
                      value={draft.leadIntake.budget_context}
                      onChange={(event) =>
                        onDraftChange({
                          leadIntake: {
                            ...draft.leadIntake,
                            budget_context: event.target.value,
                          },
                        })
                      }
                    />
                  </label>
                  <label className="field">
                    <span>Urgency Context (raw)</span>
                    <textarea
                      className="text-area"
                      rows={3}
                      value={draft.leadIntake.urgency_context}
                      onChange={(event) =>
                        onDraftChange({
                          leadIntake: {
                            ...draft.leadIntake,
                            urgency_context: event.target.value,
                          },
                        })
                      }
                    />
                  </label>
                  </div>
                  <div className="package-title" style={{ margin: "14px 0 10px" }}>
                    <span>Lead Qualification (Phase 80, Preview-Only)</span>
                    <span className="chip warn">No automation</span>
                  </div>
                  <div className="constraint-grid">
                    <label className="field">
                      <span>Budget Band</span>
                      <select
                        className="project-select"
                        value={draft.leadQualificationDraft.budget_band}
                        onChange={(event) =>
                          onDraftChange({
                            leadQualificationDraft: {
                              ...draft.leadQualificationDraft,
                              budget_band: event.target.value,
                            },
                          })
                        }
                      >
                        {LEAD_BUDGET_BANDS.map((value) => (
                          <option key={value || "empty"} value={value}>
                            {value || "select"}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label className="field">
                      <span>Urgency</span>
                      <select
                        className="project-select"
                        value={draft.leadQualificationDraft.urgency}
                        onChange={(event) =>
                          onDraftChange({
                            leadQualificationDraft: {
                              ...draft.leadQualificationDraft,
                              urgency: event.target.value,
                            },
                          })
                        }
                      >
                        {LEAD_URGENCY_LEVELS.map((value) => (
                          <option key={value || "empty"} value={value}>
                            {value || "select"}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label className="field">
                      <span>Problem Clarity</span>
                      <select
                        className="project-select"
                        value={draft.leadQualificationDraft.problem_clarity}
                        onChange={(event) =>
                          onDraftChange({
                            leadQualificationDraft: {
                              ...draft.leadQualificationDraft,
                              problem_clarity: event.target.value,
                            },
                          })
                        }
                      >
                        {LEAD_PROBLEM_CLARITY_LEVELS.map((value) => (
                          <option key={value || "empty"} value={value}>
                            {value || "select"}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label className="field">
                      <span>Decision Readiness</span>
                      <select
                        className="project-select"
                        value={draft.leadQualificationDraft.decision_readiness}
                        onChange={(event) =>
                          onDraftChange({
                            leadQualificationDraft: {
                              ...draft.leadQualificationDraft,
                              decision_readiness: event.target.value,
                            },
                          })
                        }
                      >
                        {LEAD_DECISION_READINESS_LEVELS.map((value) => (
                          <option key={value || "empty"} value={value}>
                            {value || "select"}
                          </option>
                        ))}
                      </select>
                    </label>
                  </div>
                  <label className="field" style={{ marginTop: 10 }}>
                    <span>Fit Notes (optional)</span>
                    <textarea
                      className="text-area"
                      rows={3}
                      value={draft.leadQualificationDraft.fit_notes}
                      onChange={(event) =>
                        onDraftChange({
                          leadQualificationDraft: {
                            ...draft.leadQualificationDraft,
                            fit_notes: event.target.value,
                          },
                        })
                      }
                    />
                  </label>
                </div>
              ) : null}
            </div>
            <div className="detail-card-subsection">
              <div className="package-title">
                <span>Structured Constraints</span>
                <span className="chip warn">Descriptive only</span>
              </div>
              <div className="constraint-grid">
                {CONSTRAINT_FIELDS.map((field) => (
                  <label className="field" key={field.key}>
                    <span>{field.label}</span>
                    <textarea
                      className="text-area"
                      rows={4}
                      value={fromLines(draft.structuredConstraints[field.key])}
                      onChange={(event) =>
                        onDraftChange({
                          structuredConstraints: {
                            ...draft.structuredConstraints,
                            [field.key]: toLines(event.target.value),
                          },
                        })
                      }
                    />
                    <span className="field-help">{field.help}</span>
                  </label>
                ))}
              </div>
            </div>
            <div className="detail-card-subsection">
              <div className="package-title">
                <span>Requested Artifacts</span>
                <span className="chip">Preview intent only</span>
              </div>
              <div className="artifact-grid">
                {REQUESTED_ARTIFACT_OPTIONS.map((option) => {
                  const checked = draft.requestedArtifacts.selected.includes(option.value);
                  return (
                    <label className="artifact-option" key={option.value}>
                      <input
                        checked={checked}
                        onChange={() => {
                          const selected = checked
                            ? draft.requestedArtifacts.selected.filter((item) => item !== option.value)
                            : [...draft.requestedArtifacts.selected, option.value];
                          onDraftChange({
                            requestedArtifacts: {
                              ...draft.requestedArtifacts,
                              selected,
                            },
                          });
                        }}
                        type="checkbox"
                      />
                      <span>{option.label}</span>
                    </label>
                  );
                })}
              </div>
              <label className="field" style={{ marginTop: 12 }}>
                <span>Additional Governed Artifact Requests</span>
                <textarea
                  className="text-area"
                  rows={3}
                  value={fromLines(draft.requestedArtifacts.custom)}
                  onChange={(event) =>
                    onDraftChange({
                      requestedArtifacts: {
                        ...draft.requestedArtifacts,
                        custom: toLines(event.target.value),
                      },
                    })
                  }
                />
                <span className="field-help">
                  Use one line per additional output request. This does not create or modify execution packages from the UI.
                </span>
              </label>
            </div>
            <div className="chip-row" style={{ marginTop: 12 }}>
              <span className="chip info">Routing stays in NEXUS</span>
              <span className="chip">{selectedProjectKey ? "No package created" : "Waiting for project selection"}</span>
              <span className="chip">No implicit execution</span>
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
              <div className="muted">
                {draft.lastMessage ||
                  (selectedProjectKey
                    ? "Draft changes remain local until you explicitly refresh preview."
                    : "Select a project first, then create an intake request preview to populate this workspace.")}
              </div>
            </div>
          </div>

          <div className="control-card">
            <div className="eyebrow">Linked Attachments</div>
            <AttachmentDrawer
              attachments={attachments}
              emptyMessage="No governed attachments yet. Linked inputs remain review-only unless backend preview marks them eligible."
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
              <h3>Request Intent Preview</h3>
            </div>
            <span className={getChipClass(effectivePreview?.readiness ?? "stale_preview")}>
              {effectivePreview?.readiness ?? "preview_required"}
            </span>
          </div>
          {effectivePreview ? (
            <>
              <div className="chip-row" style={{ marginBottom: 12 }}>
                <span className="chip info">{effectivePreview.autonomy_mode_detail.label}</span>
                <span className="chip">
                  {effectivePreview.intake_mode === "revenue_lead" ? "Revenue lead intake" : "Development intake"}
                </span>
                <span className="chip">{effectivePreview.package_preview.creation_mode}</span>
                <span className="chip">linked {effectivePreview.package_preview.attachment_input_count}</span>
                <span className="chip">
                  preview-eligible {effectivePreview.package_preview.attachment_preview_count}
                </span>
              </div>
              <div className="detail-grid-three">
                <div className="detail-card">
                  <h4>Requested Work</h4>
                  <div className="detail-list">
                    <div className="detail-row">
                      <span>Request Type</span>
                      <strong>{effectivePreview.request_kind}</strong>
                    </div>
                    <div className="detail-row">
                      <span>Objective</span>
                      <strong>{effectivePreview.objective || "missing"}</strong>
                    </div>
                  </div>
                  <div className="detail-card-subsection">
                    <div className="stat-label">Project / Request Context</div>
                    <div style={{ marginTop: 8 }}>
                      {effectivePreview.project_context || "Context is still required before the request can be considered ready."}
                    </div>
                  </div>
                  {effectivePreview.intake_mode === "revenue_lead" ? (
                    <div className="detail-card-subsection">
                      <div className="stat-label">Lead Intake</div>
                      <div className="detail-list" style={{ marginTop: 8 }}>
                        <div className="detail-row">
                          <span>Contact</span>
                          <strong>{effectivePreview.lead_intake_profile.contact_name || "missing"}</strong>
                        </div>
                        <div className="detail-row">
                          <span>Email</span>
                          <strong>{effectivePreview.lead_intake_profile.contact_email || "missing"}</strong>
                        </div>
                        <div className="detail-row">
                          <span>Company</span>
                          <strong>{effectivePreview.lead_intake_profile.company_name || "missing"}</strong>
                        </div>
                        <div className="detail-row">
                          <span>Problem</span>
                          <strong>{effectivePreview.lead_intake_profile.problem_summary || "missing"}</strong>
                        </div>
                      </div>
                    </div>
                  ) : null}
                </div>
                <div className="detail-card">
                  <h4>Constraint Coverage</h4>
                  <div className="detail-list">
                    {CONSTRAINT_FIELDS.map((field) => {
                      const entries = effectivePreview.structured_constraints[field.key];
                      return (
                        <div className="detail-card-subsection" key={field.key}>
                          <div className="stat-label">{field.label}</div>
                          <div className="detail-list" style={{ marginTop: 8 }}>
                            {entries.length > 0 ? (
                              entries.map((item) => (
                                <div className="audit-item" key={`${field.key}-${item}`}>
                                  {item}
                                </div>
                              ))
                            ) : (
                              <div className="audit-item muted">No entries yet.</div>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
                <div className="detail-card">
                  <h4>Requested Artifacts</h4>
                  <div className="detail-list">
                    {effectivePreview.requested_artifact_details.length > 0 ? (
                      effectivePreview.requested_artifact_details.map((item) => (
                        <div className="audit-item" key={`${item.source}-${item.artifact_id}`}>
                          <div className="chip-row" style={{ marginBottom: 8 }}>
                            <span className="chip info">{item.source}</span>
                          </div>
                          <div>{item.label}</div>
                        </div>
                      ))
                    ) : (
                      <div className="audit-item muted">Select at least one desired output before launch preview can be ready.</div>
                    )}
                  </div>
                </div>
              </div>

              <div className="detail-grid-two" style={{ marginTop: 12 }}>
                <div className="detail-card">
                  <h4>Autonomy Intent</h4>
                  <div className="chip-row" style={{ marginBottom: 10 }}>
                    <span className="chip info">{effectivePreview.autonomy_mode}</span>
                    <span className="chip">{draftMode.label}</span>
                  </div>
                  <div className="detail-card-subsection">
                    <div className="stat-label">Operational Meaning</div>
                    <div style={{ marginTop: 8 }}>{effectivePreview.autonomy_mode_detail.summary}</div>
                  </div>
                  <div className="detail-card-subsection">
                    <div className="stat-label">Operator Guidance</div>
                    <div style={{ marginTop: 8 }}>{effectivePreview.autonomy_mode_detail.operator_posture}</div>
                  </div>
                </div>

                <div className="detail-card">
                  <h4>Composition Status</h4>
                  <div className="chip-row" style={{ marginBottom: 10 }}>
                    <span
                      className={
                        effectivePreview.composition_status.is_complete &&
                        effectivePreview.readiness === "ready_for_governed_request"
                          ? "chip success"
                          : "chip warn"
                      }
                    >
                      {effectivePreview.composition_status.is_complete &&
                      effectivePreview.readiness === "ready_for_governed_request"
                        ? "Ready for governed request"
                        : "Not ready for launch"}
                    </span>
                    <span className="chip">
                      warnings {effectivePreview.composition_status.warning_count}
                    </span>
                  </div>
                  <div className="detail-list">
                    {effectivePreview.composition_status.missing_fields.length > 0 ? (
                      effectivePreview.composition_status.missing_fields.map((item) => (
                        <div className="audit-item" key={item}>
                          Missing: {labelForMissingField(item)}
                        </div>
                      ))
                    ) : (
                      <div className="audit-item muted">
                        Required request composition fields are present in the preview payload.
                      </div>
                    )}
                  </div>
                </div>
              </div>

              <div className="detail-grid-two" style={{ marginTop: 12 }}>
                {effectivePreview.qualification_summary ? (
                  <div className="detail-card">
                    <h4>Lead Qualification Summary</h4>
                    <div className="chip-row" style={{ marginBottom: 10 }}>
                      <span className={getChipClass(effectivePreview.qualification_summary.qualification_status)}>
                        {effectivePreview.qualification_summary.qualification_status}
                      </span>
                      <span className="chip">
                        readiness {effectivePreview.qualification_summary.lead_readiness_level}
                      </span>
                    </div>
                    <div className="detail-list">
                      {Object.entries(effectivePreview.qualification_summary.qualification_signals).map(
                        ([key, value]) => (
                          <div className="detail-row" key={key}>
                            <span>{key.replace(/_/g, " ")}</span>
                            <strong>{value || "missing"}</strong>
                          </div>
                        ),
                      )}
                    </div>
                    <div className="detail-card-subsection">
                      <div className="stat-label">Reasoning</div>
                      <div style={{ marginTop: 8 }}>
                        {effectivePreview.qualification_summary.qualification_reasoning_summary}
                      </div>
                    </div>
                    <div className="detail-list">
                      {effectivePreview.qualification_summary.missing_qualification_fields.length > 0 ? (
                        effectivePreview.qualification_summary.missing_qualification_fields.map((field) => (
                          <div className="audit-item" key={field}>
                            Missing qualification: {field.replace(/_/g, " ")}
                          </div>
                        ))
                      ) : (
                        <div className="audit-item muted">No required qualification fields are missing.</div>
                      )}
                    </div>
                  </div>
                ) : null}
                {effectivePreview.offer_summary ? (
                  <div className="detail-card">
                    <h4>Revenue Offer Framing (Preview Only)</h4>
                    <div className="chip-row" style={{ marginBottom: 10 }}>
                      <span className={getChipClass(effectivePreview.offer_summary.offer_status)}>
                        {effectivePreview.offer_summary.offer_status}
                      </span>
                      <span className="chip">non-executing</span>
                    </div>
                    <div className="detail-list">
                      <div className="detail-row">
                        <span>Service Type</span>
                        <strong>{effectivePreview.offer_summary.recommended_service_type || "undetermined"}</strong>
                      </div>
                      <div className="detail-row">
                        <span>Package Tier</span>
                        <strong>{effectivePreview.offer_summary.recommended_package_tier || "undetermined"}</strong>
                      </div>
                      <div className="detail-row">
                        <span>Complexity Band</span>
                        <strong>{effectivePreview.offer_summary.estimated_complexity_band || "undetermined"}</strong>
                      </div>
                      <div className="detail-row">
                        <span>Pricing Direction</span>
                        <strong>{effectivePreview.offer_summary.pricing_direction || "undetermined"}</strong>
                      </div>
                    </div>
                    <div className="detail-card-subsection">
                      <div className="stat-label">Reasoning</div>
                      <div style={{ marginTop: 8 }}>
                        {effectivePreview.offer_summary.offer_reasoning_summary || "Offer framing not available yet."}
                      </div>
                    </div>
                    <div className="detail-list">
                      {effectivePreview.offer_summary.offer_constraints_or_notes.length > 0 ? (
                        effectivePreview.offer_summary.offer_constraints_or_notes.map((note) => (
                          <div className="audit-item" key={note}>
                            {note}
                          </div>
                        ))
                      ) : (
                        <div className="audit-item muted">No additional offer constraints noted.</div>
                      )}
                    </div>
                  </div>
                ) : null}
                {effectivePreview.response_summary ? (
                  <div className="detail-card">
                    <h4>Draft Response (Preview Only)</h4>
                    <div className="chip-row" style={{ marginBottom: 10 }}>
                      <span className={getChipClass(effectivePreview.response_summary.response_status)}>
                        {effectivePreview.response_summary.response_status}
                      </span>
                      <span className="chip">{effectivePreview.response_summary.response_tone}</span>
                      <span className="chip warn">not sent</span>
                    </div>
                    <div className="detail-card-subsection">
                      <div className="stat-label">Response Summary</div>
                      <div style={{ marginTop: 8 }}>
                        {effectivePreview.response_summary.response_summary || "No response summary yet."}
                      </div>
                    </div>
                    <div className="detail-card-subsection">
                      <div className="stat-label">Response Message</div>
                      <div style={{ marginTop: 8 }}>
                        {effectivePreview.response_summary.response_message || "No draft response generated yet."}
                      </div>
                    </div>
                    <div className="detail-list">
                      {effectivePreview.response_summary.response_constraints.length > 0 ? (
                        effectivePreview.response_summary.response_constraints.map((constraint) => (
                          <div className="audit-item" key={constraint}>
                            {constraint}
                          </div>
                        ))
                      ) : (
                        <div className="audit-item muted">No response constraints provided.</div>
                      )}
                    </div>
                  </div>
                ) : null}
                <div className="detail-card">
                  <h4>Package Preview Boundary</h4>
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
                    {effectivePreview.linked_attachments.length > 0 ? (
                      effectivePreview.linked_attachments.map((attachment) => (
                        <div className="audit-item" key={attachment.attachment_id}>
                          <div className="chip-row" style={{ marginBottom: 8 }}>
                            <span className={getChipClass(attachment.status)}>{attachment.status}</span>
                            <span className="chip">{attachment.classification}</span>
                            <span className="chip">
                              {attachment.allowed_for_request_preview ? "preview-eligible" : "preview-limited"}
                            </span>
                          </div>
                          <div>{attachment.file_name}</div>
                          <div className="muted" style={{ marginTop: 6 }}>
                            {attachment.extracted_summary || "No extracted summary available."}
                          </div>
                        </div>
                      ))
                    ) : (
                      <div className="audit-item muted">No attachments linked into the current request composition.</div>
                    )}
                    {effectivePreview.warnings.length > 0 ? (
                      effectivePreview.warnings.map((warning) => (
                        <div className="audit-item" key={warning}>
                          {warning}
                        </div>
                      ))
                    ) : (
                      <div className="audit-item muted">Linked attachments are eligible for governed preview use.</div>
                    )}
                  </div>
                </div>
              </div>
            </>
          ) : (
            <div className="audit-item muted">
              This panel is empty because no governed intake preview has been requested yet. Start with an objective, request context, and desired outputs, then click `Preview Governed Request` to let Forge explain what will happen next.
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
