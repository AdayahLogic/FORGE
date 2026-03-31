import test from "node:test";
import assert from "node:assert/strict";
import type {
  ForgeActivitySnapshot,
  ForgeConsoleMessageResponse,
  ForgeOperatorConsoleSnapshot,
} from "../lib/forge-types.ts";
import {
  getApprovalConfirmationPhrase as _getApprovalConfirmationPhrase,
  getConsoleCards as _getConsoleCards,
  getFeedPreview as _getFeedPreview,
  getMissionCounts as _getMissionCounts,
} from "../lib/experience-adapters.ts";

const getApprovalConfirmationPhrase = _getApprovalConfirmationPhrase;
const getConsoleCards = _getConsoleCards;
const getFeedPreview = _getFeedPreview;
const getMissionCounts = _getMissionCounts;

test("approval confirmation phrase resolves by action", () => {
  assert.equal(
    getApprovalConfirmationPhrase("complete_review"),
    "CONFIRM COMPLETE REVIEW",
  );
  assert.equal(
    getApprovalConfirmationPhrase("complete_approval"),
    "CONFIRM COMPLETE APPROVAL",
  );
  assert.equal(getApprovalConfirmationPhrase("unknown"), "");
});

test("console cards use response cards when available", () => {
  const cards = getConsoleCards(
    {
      reply: "ok",
      response_cards: [{ card_id: "1", title: "x", lines: ["a"] }],
      console_snapshot: {} as unknown as ForgeOperatorConsoleSnapshot,
    } as ForgeConsoleMessageResponse,
    null,
  );
  assert.equal(cards.length, 1);
  assert.equal(cards[0]?.card_id, "1");
});

test("console cards build fallback from snapshot", () => {
  const cards = getConsoleCards(null, {
    generated_at: "",
    selected_project_key: "demo",
    context: {
      active_project: {
        project_key: "demo",
        project_name: "Demo",
        project_path: "",
        status: "planning",
      },
      current_mission: { mission_id: "m-1", status: "queued", summary: "queued" },
      active_strategy: {
        routing_status: "",
        selected_model_lane: "",
        summary: "",
      },
      autonomy_mode: "supervised_build",
      next_best_action: "Review mission",
      current_blockers: [],
    },
    approvals: {
      pending_count: 0,
      requires_action: false,
      items: [],
      allowed_actions: [],
    },
    system_awareness: {
      execution_lane_status: "idle",
      kill_switch_state: "inactive",
      queue_pressure: "idle",
      queue_depth: 0,
      pending_queue_items: 0,
      worker_state: "healthy",
      revenue_lane_status: "idle",
      control_state: {
        studio_health: "healthy",
        budget_status: "within_budget",
        budget_scope: "project",
      },
    },
    live_activity: {
      operation_status: "idle",
      current_phase: "",
      current_step: "",
      last_action: "",
      recent_activity: [],
    },
    quick_actions: {
      quick_actions_status: "none",
      available_actions: [],
      quick_actions_reason: "",
    },
  } as ForgeOperatorConsoleSnapshot);
  assert.equal(cards.length, 1);
  assert.equal(cards[0]?.title, "Operator Context");
});

test("activity adapters return mission counts and feed preview", () => {
  const snapshot = {
    live_feed: [
      { event_type: "a" },
      { event_type: "b" },
      { event_type: "c" },
      { event_type: "d" },
      { event_type: "e" },
      { event_type: "f" },
      { event_type: "g" },
    ],
    mission_status: {
      active: [1, 2],
      queued: [3],
      failed_or_stalled: [4, 5, 6],
    },
  } as unknown as ForgeActivitySnapshot;
  const feed = getFeedPreview(snapshot);
  const counts = getMissionCounts(snapshot);
  assert.equal(feed.length, 6);
  assert.deepEqual(counts, { active: 2, queued: 1, failed: 3 });
});
