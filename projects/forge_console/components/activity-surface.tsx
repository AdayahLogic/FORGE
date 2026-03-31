"use client";

import { useEffect, useState } from "react";
import { getActivitySnapshot } from "../lib/forge-client";
import { getFeedPreview, getMissionCounts } from "../lib/experience-adapters";
import type { ForgeActivitySnapshot } from "../lib/forge-types";

export function ActivitySurface() {
  const [snapshot, setSnapshot] = useState<ForgeActivitySnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [projectKey, setProjectKey] = useState("");
  const [errorMessage, setErrorMessage] = useState("");

  async function loadActivity(selectedProject = projectKey) {
    setLoading(true);
    setErrorMessage("");
    try {
      const response = await getActivitySnapshot({
        projectKey: selectedProject,
        limit: 80,
      });
      setSnapshot(response.payload);
      setProjectKey(response.payload.selected_project_key || selectedProject);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Failed to refresh activity.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadActivity("");
    const handle = window.setInterval(() => {
      void loadActivity(projectKey);
    }, 6000);
    return () => window.clearInterval(handle);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const feed = getFeedPreview(snapshot);
  const missionCounts = getMissionCounts(snapshot);

  return (
    <div className="experience-grid">
      <section className="panel experience-main-panel">
        <div className="section-title">
          <div>
            <div className="eyebrow">Live Activity Feed</div>
            <h3>What Forge Is Doing Now</h3>
          </div>
          <div className="chip-row">
            <span className="chip info">
              Project {snapshot?.selected_project_key || "all"}
            </span>
            <span className="chip">
              Updated {snapshot?.generated_at || "pending"}
            </span>
          </div>
        </div>
        <div className="audit-list">
          {feed.length ? (
            feed.map((event) => (
              <article className="audit-item" key={`${event.timestamp}-${event.event_type}`}>
                <div className="status-row">
                  <span className="chip info">{event.event_type || "activity"}</span>
                  <span className="chip">{event.project_name}</span>
                  <span className="chip mono">{event.timestamp || "no timestamp"}</span>
                </div>
                <div style={{ marginTop: 8 }}>{event.summary || "No summary available."}</div>
              </article>
            ))
          ) : (
            <div className="audit-item muted">
              No live events yet. Forge activity appears here when missions or execution states move.
            </div>
          )}
        </div>
      </section>

      <section className="panel experience-side-panel">
        <div className="section-title">
          <div>
            <div className="eyebrow">Mission + Queue Status</div>
            <h3>Execution Visibility</h3>
          </div>
        </div>
        <div className="detail-grid-three">
          <div className="stat-card">
            <div className="stat-label">Active Missions</div>
            <div className="stat-value">{missionCounts.active}</div>
          </div>
          <div className="stat-card">
            <div className="stat-label">Queued Missions</div>
            <div className="stat-value">{missionCounts.queued}</div>
          </div>
          <div className="stat-card">
            <div className="stat-label">Failed/Stalled</div>
            <div className="stat-value">{missionCounts.failed}</div>
          </div>
        </div>
        <div className="detail-card-subsection">
          <div className="audit-list">
            {(snapshot?.mission_status.failed_or_stalled.length
              ? snapshot.mission_status.failed_or_stalled
              : snapshot?.mission_status.queued ?? []
            )
              .slice(0, 6)
              .map((mission) => (
                <article className="audit-item" key={`${mission.project_key}-${mission.mission_id}`}>
                  <div className="status-row">
                    <span className="chip warn">{mission.status}</span>
                    <span className="chip">{mission.project_name}</span>
                  </div>
                  <div style={{ marginTop: 8 }}>
                    Mission {mission.mission_id || "none"} - Next action: {mission.next_action || "awaiting input"}
                  </div>
                </article>
              ))}
          </div>
        </div>
      </section>

      <section className="panel experience-right-panel">
        <div className="section-title">
          <div>
            <div className="eyebrow">Approvals + Outcomes</div>
            <h3>Operator Action Queue</h3>
          </div>
        </div>
        <div className="detail-grid-two">
          <div className="detail-card">
            <h4>Approvals</h4>
            <div className="stat-value">{snapshot?.approvals.pending_count ?? 0}</div>
            <div className="muted">pending approvals</div>
            <div className="audit-list" style={{ marginTop: 10 }}>
              {Object.entries(snapshot?.approvals.pending_by_urgency ?? {}).map(([urgency, count]) => (
                <div className="audit-item" key={urgency}>
                  {urgency}: {count}
                </div>
              ))}
            </div>
          </div>
          <div className="detail-card">
            <h4>Outcomes</h4>
            <div className="audit-item">
              Verifications: {snapshot?.outcomes.verification_count ?? 0}
            </div>
            <div className="audit-item">
              Revenue lane ready: {snapshot?.outcomes.revenue_lane_ready_count ?? 0}
            </div>
          </div>
        </div>
        <div className="detail-card-subsection">
          <h4>Connector + Control Posture</h4>
          <div className="audit-list">
            <div className="audit-item">
              Execution lane: {snapshot?.connector_posture.execution_lane_status || "unknown"}
            </div>
            <div className="audit-item">
              Runtime infra: {snapshot?.connector_posture.runtime_infrastructure_status || "unknown"}
            </div>
            <div className="audit-item">
              Kill switch: {snapshot?.connector_posture.kill_switch_state || "unknown"}
            </div>
            <div className="audit-item">
              Control state: {snapshot?.connector_posture.control_state || "unknown"}
            </div>
          </div>
        </div>
      </section>
      <div className="chip-row">
        <button className="refresh-button" onClick={() => void loadActivity(projectKey)} type="button">
          Refresh Activity
        </button>
        {loading ? <span className="chip">Loading</span> : null}
        {errorMessage ? <span className="chip danger">{errorMessage}</span> : null}
      </div>
    </div>
  );
}
