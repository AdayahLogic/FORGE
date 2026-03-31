import type {
  ForgeActivitySnapshot,
  ForgeConsoleMessageResponse,
  ForgeOperatorConsoleSnapshot,
} from "./forge-types";

export function getApprovalConfirmationPhrase(action: string): string {
  if (action === "complete_approval") {
    return "CONFIRM COMPLETE APPROVAL";
  }
  if (action === "complete_review") {
    return "CONFIRM COMPLETE REVIEW";
  }
  return "";
}

export function getConsoleCards(
  response: ForgeConsoleMessageResponse | null,
  snapshot: ForgeOperatorConsoleSnapshot | null,
) {
  if (response?.response_cards?.length) {
    return response.response_cards;
  }
  if (!snapshot) {
    return [];
  }
  return [
    {
      card_id: "context-fallback",
      title: "Operator Context",
      lines: [
        `Project: ${snapshot.context.active_project.project_name || "none"}`,
        `Mission: ${snapshot.context.current_mission.mission_id || "none"}`,
        `Next action: ${snapshot.context.next_best_action || "review queue"}`,
      ],
    },
  ];
}

export function getFeedPreview(snapshot: ForgeActivitySnapshot | null) {
  const events = snapshot?.live_feed ?? [];
  return events.slice(0, 6);
}

export function getMissionCounts(snapshot: ForgeActivitySnapshot | null) {
  return {
    active: snapshot?.mission_status.active.length ?? 0,
    queued: snapshot?.mission_status.queued.length ?? 0,
    failed: snapshot?.mission_status.failed_or_stalled.length ?? 0,
  };
}
