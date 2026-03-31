import { NextResponse } from "next/server";
import { runForgeBridge } from "../../../../lib/forge-bridge";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const projectKey = searchParams.get("projectKey") ?? "";
  try {
    const args = ["operator_console_snapshot"];
    if (projectKey) {
      args.push("--project-key", projectKey);
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
          context: {
            active_project: {
              project_key: projectKey,
              project_name: projectKey || "No active project",
              project_path: "",
              status: "offline",
            },
            current_mission: {
              mission_id: "",
              status: "offline",
              summary: "Backend offline",
            },
            active_strategy: {
              routing_status: "offline",
              selected_model_lane: "",
              summary: "Backend unavailable.",
            },
            autonomy_mode: "supervised_build",
            next_best_action: "Bring Forge backend online.",
            current_blockers: ["Bridge unavailable."],
          },
          approvals: {
            pending_count: 0,
            requires_action: false,
            items: [],
            allowed_actions: [],
          },
          system_awareness: {
            execution_lane_status: "offline",
            kill_switch_state: "unknown",
            queue_pressure: "unknown",
            queue_depth: 0,
            pending_queue_items: 0,
            worker_state: "offline",
            revenue_lane_status: "unknown",
            control_state: {
              studio_health: "offline",
              budget_status: "unknown",
              budget_scope: "project",
            },
          },
          live_activity: {
            operation_status: "offline",
            current_phase: "",
            current_step: "",
            last_action: "Backend unavailable.",
            recent_activity: [],
          },
          quick_actions: {
            quick_actions_status: "none",
            available_actions: [],
            quick_actions_reason: "Bridge unavailable.",
          },
        },
      },
      { status: 500 },
    );
  }
}

export async function POST(request: Request) {
  const body = (await request.json()) as {
    projectKey?: string;
    message?: string;
    executeAction?: string;
    confirmed?: boolean;
    confirmationText?: string;
  };
  try {
    const args = ["operator_console_message"];
    if (body.projectKey) {
      args.push("--project-key", body.projectKey);
    }
    args.push("--message", body.message ?? "");
    if (body.executeAction) {
      args.push("--execute-action", body.executeAction);
    }
    if (body.confirmed) {
      args.push("--confirmed");
    }
    args.push("--confirmation-text", body.confirmationText ?? "");
    const payload = await runForgeBridge(args);
    return NextResponse.json(payload, {
      status: payload.status === "ok" ? 200 : 400,
    });
  } catch (error) {
    return NextResponse.json(
      {
        status: "error",
        message: error instanceof Error ? error.message : "Bridge failed.",
        payload: {
          reply: "Forge could not process the request because the backend bridge is offline.",
          response_cards: [],
          suggested_actions: [],
          console_snapshot: null,
        },
      },
      { status: 500 },
    );
  }
}
