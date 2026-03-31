import { NextResponse } from "next/server";
import { runForgeBridge } from "../../../../lib/forge-bridge";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const projectKey = searchParams.get("projectKey") ?? "";
  const limit = searchParams.get("limit") ?? "";
  try {
    const args = ["activity_snapshot"];
    if (projectKey) {
      args.push("--project-key", projectKey);
    }
    if (limit) {
      args.push("--limit", limit);
    }
    const payload = await runForgeBridge(args);
    return NextResponse.json(payload);
  } catch (error) {
    return NextResponse.json(
      {
        status: "error",
        message: error instanceof Error ? error.message : "Bridge failed.",
        payload: {
          generated_at: "",
          selected_project_key: projectKey,
          live_feed: [],
          mission_status: {
            active: [],
            queued: [],
            failed_or_stalled: [],
          },
          queue_worker_visibility: {
            queue_depth: 0,
            project_queue_status: {},
            worker_state: "offline",
            retry_or_backoff_state: "Bridge unavailable.",
          },
          approvals: {
            pending_count: 0,
            pending_by_urgency: {},
            items: [],
          },
          outcomes: {
            recent_outcomes: [],
            revenue_lane_ready_count: 0,
            verification_count: 0,
          },
          connector_posture: {
            execution_lane_status: "offline",
            control_state: "offline",
            kill_switch_state: "unknown",
            degraded_mode: true,
            runtime_infrastructure_status: "offline",
          },
        },
      },
      { status: 500 },
    );
  }
}
