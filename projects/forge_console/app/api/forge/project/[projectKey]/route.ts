import { NextResponse } from "next/server";
import { runForgeBridge } from "../../../../../lib/forge-bridge";

export const dynamic = "force-dynamic";

export async function GET(
  _request: Request,
  context: { params: Promise<{ projectKey: string }> },
) {
  const params = await context.params;
  try {
    const payload = await runForgeBridge([
      "project",
      "--project-key",
      params.projectKey,
    ]);
    return NextResponse.json(payload);
  } catch (error) {
    return NextResponse.json(
      {
        status: "error",
        message: error instanceof Error ? error.message : "Bridge failed.",
        payload: {
          project_key: params.projectKey,
          project_name: params.projectKey,
          project_path: "",
          project_meta: {},
          project_summary: {},
          project_state: {},
          latest_session: {},
          system_health: {},
          package_queue: {
            project_key: params.projectKey,
            project_path: "",
            count: 0,
            pending_count: 0,
            packages: [],
          },
          current_package: null,
          system_status: {
            backend_reachable: false,
            status: "offline",
            label: "Forge Not Running",
            reason: error instanceof Error ? error.message : "Bridge failed.",
          },
          workflow_activity: {
            current_phase: "planning",
            phase_label: "Planning",
            last_action: "Backend offline",
            current_project: params.projectKey,
            active_package_id: "",
            package_status: "Backend offline",
            package_created_at: "",
          },
          approval_summary: {},
          intake_workspace: null,
          degraded_sources: ["bridge"],
        },
      },
    );
  }
}
