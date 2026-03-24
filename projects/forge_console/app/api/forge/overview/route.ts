import { NextResponse } from "next/server";
import { runForgeBridge } from "../../../../lib/forge-bridge";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const payload = await runForgeBridge(["overview"]);
    return NextResponse.json(payload);
  } catch (error) {
    return NextResponse.json(
      {
        status: "error",
        message: error instanceof Error ? error.message : "Bridge failed.",
        payload: {
          generated_at: "",
          studio_name: "FORGE",
          overview: {
            system_status: {
              backend_reachable: false,
              status: "offline",
              label: "Forge Not Running",
              reason: error instanceof Error ? error.message : "Bridge failed.",
            },
            studio_health: "Backend offline",
            aegis_posture: {},
            queue_counts: {
              queued_projects: 0,
              review_required_projects: 0,
              approval_pending_total: 0,
              reapproval_required_total: 0,
            },
            package_counts: {
              review_pending: 0,
              decision_pending: 0,
              eligibility_pending: 0,
              release_pending: 0,
              handoff_pending: 0,
              execution_pending: 0,
              execution_blocked: 0,
              execution_failed: 0,
              execution_succeeded: 0,
            },
            evaluation_counts: {
              pending: 0,
              completed: 0,
              blocked: 0,
              error: 0,
              bands: {},
            },
            local_analysis_counts: {
              pending: 0,
              completed: 0,
              blocked: 0,
              error: 0,
              confidence_bands: {},
              next_actions: {},
            },
            project_count: 0,
            executor_health: {},
          },
          projects: [],
          approval_center: {
            approval_summary: {},
            approval_lifecycle: {},
            allowed_actions: [],
            surface_mode: "read_only",
          },
          raw: {
            dashboard_summary: {},
          },
        },
      },
    );
  }
}
