"use client";

import { useEffect, useMemo, useState } from "react";
import {
  getOperatorConsoleSnapshot,
  sendOperatorMessage,
} from "../lib/forge-client";
import {
  getApprovalConfirmationPhrase,
  getConsoleCards,
} from "../lib/experience-adapters";
import type {
  ForgeConsoleMessageResponse,
  ForgeOperatorConsoleSnapshot,
} from "../lib/forge-types";

type ChatRow = {
  id: string;
  role: "operator" | "forge";
  text: string;
  timestamp: string;
};

export function OperatorConsoleSurface() {
  const [projectKey, setProjectKey] = useState("");
  const [snapshot, setSnapshot] = useState<ForgeOperatorConsoleSnapshot | null>(null);
  const [lastResponse, setLastResponse] = useState<ForgeConsoleMessageResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");
  const [chatRows, setChatRows] = useState<ChatRow[]>([]);
  const [controlAction, setControlAction] = useState("complete_review");
  const [confirmText, setConfirmText] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [controlBusy, setControlBusy] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");

  const requiredPhrase = useMemo(
    () => getApprovalConfirmationPhrase(controlAction),
    [controlAction],
  );

  async function loadSnapshot(selectedProject = projectKey) {
    setLoading(true);
    setErrorMessage("");
    try {
      const response = await getOperatorConsoleSnapshot(selectedProject);
      setSnapshot(response.payload);
      setProjectKey(response.payload.selected_project_key || selectedProject);
      if (!chatRows.length) {
        setChatRows([
          {
            id: "bootstrap",
            role: "forge",
            text:
              response.payload.context.next_best_action ||
              "Forge is online. Ask what it is doing right now.",
            timestamp: response.payload.generated_at || new Date().toISOString(),
          },
        ]);
      }
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Failed to load console snapshot.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadSnapshot("");
    const handle = window.setInterval(() => {
      void loadSnapshot(projectKey);
    }, 7000);
    return () => window.clearInterval(handle);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const onSendMessage = async () => {
    const trimmed = message.trim();
    if (!trimmed) {
      return;
    }
    const now = new Date().toISOString();
    setChatRows((current) => [
      ...current,
      {
        id: `${now}-operator`,
        role: "operator",
        text: trimmed,
        timestamp: now,
      },
    ]);
    setMessage("");
    try {
      const response = await sendOperatorMessage({
        projectKey,
        message: trimmed,
      });
      setLastResponse(response.payload);
      setSnapshot(response.payload.console_snapshot);
      setProjectKey(response.payload.console_snapshot.selected_project_key || projectKey);
      setChatRows((current) => [
        ...current,
        {
          id: `${Date.now()}-forge`,
          role: "forge",
          text: response.payload.reply,
          timestamp: new Date().toISOString(),
        },
      ]);
    } catch (error) {
      const text = error instanceof Error ? error.message : "Message failed.";
      setErrorMessage(text);
      setChatRows((current) => [
        ...current,
        {
          id: `${Date.now()}-forge-error`,
          role: "forge",
          text: `I could not complete that request: ${text}`,
          timestamp: new Date().toISOString(),
        },
      ]);
    }
  };

  const onExecuteControlAction = async () => {
    setControlBusy(true);
    setErrorMessage("");
    try {
      const response = await sendOperatorMessage({
        projectKey,
        message: "",
        executeAction: controlAction,
        confirmed,
        confirmationText: confirmText,
      });
      setLastResponse(response.payload);
      setSnapshot(response.payload.console_snapshot);
      setChatRows((current) => [
        ...current,
        {
          id: `${Date.now()}-forge-control`,
          role: "forge",
          text: response.payload.reply,
          timestamp: new Date().toISOString(),
        },
      ]);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Control action failed.");
    } finally {
      setControlBusy(false);
    }
  };

  const cards = getConsoleCards(lastResponse, snapshot);
  const approvals = snapshot?.approvals.items ?? [];
  const blockers = snapshot?.context.current_blockers ?? [];

  return (
    <div className="experience-grid">
      <section className="panel experience-main-panel">
        <div className="section-title">
          <div>
            <div className="eyebrow">Operator Chat</div>
            <h3>Talk To Forge</h3>
          </div>
          <div className="chip-row">
            <span className="chip info">
              Project {snapshot?.selected_project_key || "none"}
            </span>
            <span className="chip">
              Lane {snapshot?.system_awareness.execution_lane_status || "idle"}
            </span>
          </div>
        </div>
        <div className="chat-log">
          {chatRows.length ? (
            chatRows.map((row) => (
              <article
                className={`chat-row ${row.role === "operator" ? "operator" : "forge"}`}
                key={row.id}
              >
                <div className="chat-row-meta">
                  <strong>{row.role === "operator" ? "Operator" : "Forge"}</strong>
                  <span className="muted mono">{row.timestamp}</span>
                </div>
                <div>{row.text}</div>
              </article>
            ))
          ) : (
            <div className="audit-item muted">No messages yet. Ask Forge for system status.</div>
          )}
        </div>
        <div className="chat-input-row">
          <input
            className="confirmation-input"
            onChange={(event) => setMessage(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                void onSendMessage();
              }
            }}
            placeholder="Ask Forge what it is doing, what is blocked, or what to do next..."
            value={message}
          />
          <button className="action-button" onClick={() => void onSendMessage()} type="button">
            Send
          </button>
        </div>
        {errorMessage ? <div className="audit-item muted">{errorMessage}</div> : null}
      </section>

      <section className="panel experience-side-panel">
        <div className="section-title">
          <div>
            <div className="eyebrow">Context</div>
            <h3>Current Mission Posture</h3>
          </div>
        </div>
        <div className="detail-grid-two">
          <div className="detail-card">
            <h4>Active Project</h4>
            <div className="detail-list">
              <div className="detail-row">
                <span>Name</span>
                <span>{snapshot?.context.active_project.project_name || "None"}</span>
              </div>
              <div className="detail-row">
                <span>Mission</span>
                <span>{snapshot?.context.current_mission.mission_id || "None"}</span>
              </div>
              <div className="detail-row">
                <span>Autonomy</span>
                <span>{snapshot?.context.autonomy_mode || "supervised_build"}</span>
              </div>
            </div>
          </div>
          <div className="detail-card">
            <h4>Strategy + Action</h4>
            <div className="audit-list">
              <div className="audit-item">{snapshot?.context.active_strategy.summary || "No strategy summary."}</div>
              <div className="audit-item">
                Next best action: {snapshot?.context.next_best_action || "Review queue posture."}
              </div>
            </div>
          </div>
        </div>
        <div className="detail-card-subsection">
          <div className="status-row">
            <span className="chip">Queue pressure {snapshot?.system_awareness.queue_pressure || "idle"}</span>
            <span className="chip">Workers {snapshot?.system_awareness.worker_state || "unknown"}</span>
            <span className="chip">
              Kill switch {snapshot?.system_awareness.kill_switch_state || "inactive"}
            </span>
          </div>
          <div className="audit-list" style={{ marginTop: 12 }}>
            {(blockers.length ? blockers : ["No blockers currently reported by Forge."]).map(
              (blocker) => (
                <div className="audit-item" key={blocker}>
                  {blocker}
                </div>
              ),
            )}
          </div>
        </div>
      </section>

      <section className="panel experience-right-panel">
        <div className="section-title">
          <div>
            <div className="eyebrow">Governed Actions</div>
            <h3>Approvals + Control</h3>
          </div>
          <span className="chip warn">{snapshot?.approvals.pending_count ?? 0} pending</span>
        </div>
        <div className="audit-list">
          {(approvals.length ? approvals : [
            {
              approval_id: "none",
              reason: "No pending approvals.",
              urgency: "normal",
              risk: "",
            },
          ]).map((item) => (
            <article className="audit-item" key={item.approval_id}>
              <div className="status-row">
                <span className="chip info">{item.urgency || "normal"}</span>
                {item.risk ? <span className="chip danger">{item.risk}</span> : null}
              </div>
              <div style={{ marginTop: 8 }}>{item.reason || "Approval pending."}</div>
            </article>
          ))}
        </div>
        <div className="control-actions" style={{ marginTop: 12 }}>
          <select
            className="project-select"
            onChange={(event) => setControlAction(event.target.value)}
            value={controlAction}
          >
            <option value="complete_review">complete_review</option>
            <option value="complete_approval">complete_approval</option>
          </select>
          <input
            className="confirmation-input"
            onChange={(event) => setConfirmText(event.target.value)}
            placeholder={requiredPhrase || "Confirmation phrase"}
            value={confirmText}
          />
          <label className="chip">
            <input
              checked={confirmed}
              onChange={(event) => setConfirmed(event.target.checked)}
              style={{ marginRight: 8 }}
              type="checkbox"
            />
            Confirmed
          </label>
          <button
            className="action-button"
            disabled={
              controlBusy ||
              !confirmed ||
              !requiredPhrase ||
              confirmText.trim() !== requiredPhrase
            }
            onClick={() => void onExecuteControlAction()}
            type="button"
          >
            {controlBusy ? "Submitting..." : "Execute Governed Action"}
          </button>
        </div>
        <div className="detail-card-subsection" style={{ marginTop: 12 }}>
          <h4>Response Cards</h4>
          <div className="audit-list">
            {cards.map((card) => (
              <article className="audit-item" key={card.card_id}>
                <strong>{card.title}</strong>
                {card.lines.map((line) => (
                  <div className="muted" key={line}>
                    {line}
                  </div>
                ))}
              </article>
            ))}
          </div>
        </div>
      </section>

      {loading ? <div className="audit-item muted">Refreshing console snapshot...</div> : null}
    </div>
  );
}
