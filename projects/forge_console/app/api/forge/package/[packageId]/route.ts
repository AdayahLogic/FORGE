import { NextResponse } from "next/server";
import { runForgeBridge } from "../../../../../lib/forge-bridge";

export const dynamic = "force-dynamic";

export async function GET(
  request: Request,
  context: { params: Promise<{ packageId: string }> },
) {
  const params = await context.params;
  const { searchParams } = new URL(request.url);
  const projectKey = searchParams.get("projectKey") ?? "";
  try {
    const args = ["package", "--package-id", params.packageId];
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
          package_id: params.packageId,
          project_key: projectKey,
          project_path: "",
          review_header: {},
          sections: {},
          evaluation: {},
          local_analysis: {},
          package_json: {},
          timeline: [],
          execution_feedback: {
            package_created: false,
            package_created_at: "",
            package_status: "Backend offline",
            status_summary: "Backend offline",
            active_transition: "Backend offline",
            lifecycle_transitions: [],
          },
          review_center: {
            package_id: params.packageId,
            approval_ready_context: {
              review_status: "waiting_for_input",
              sealed: false,
              seal_reason: "",
              approval_id_refs: [],
              requires_human_approval: false,
              decision_status: "waiting_for_input",
              release_status: "waiting_for_input",
              review_checklist: [],
            },
            returned_artifacts: [],
            patch_context: {
              patch_summary: "",
              changed_files: [],
              candidate_paths: [],
              requested_outputs: [],
            },
            test_results: {
              execution_result_status: "waiting_for_input",
              exit_code: null,
              log_ref: "",
              integrity_status: "backend_offline",
              evaluation_quality_band: "",
              suggested_next_action: "",
            },
            execution_feedback: {
              package_created: false,
              package_created_at: "",
              package_status: "Backend offline",
              status_summary: "Backend offline",
              active_transition: "Backend offline",
              lifecycle_transitions: [],
            },
            evaluation_summary: {},
            local_analysis_summary: {},
            related_attachments: [],
          },
        },
      },
    );
  }
}
