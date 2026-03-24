import { NextResponse } from "next/server";
import { runForgeBridge } from "../../../../../lib/forge-bridge";

export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  const body = (await request.json()) as {
    requestKind?: string;
    projectKey?: string;
    objective?: string;
    projectContext?: string;
    constraints?: Record<string, unknown>;
    requestedArtifacts?: Record<string, unknown>;
    linkedAttachmentIds?: string[];
    autonomyMode?: string;
    leadIntake?: Record<string, unknown>;
  };
  try {
    const payload = await runForgeBridge([
      "intake_preview",
      "--request-kind",
      body.requestKind ?? "update_request",
      "--project-key",
      body.projectKey ?? "",
      "--objective",
      body.objective ?? "",
      "--project-context",
      body.projectContext ?? "",
      "--constraints-json",
      JSON.stringify(body.constraints ?? {}),
      "--requested-artifacts-json",
      JSON.stringify(body.requestedArtifacts ?? {}),
      "--linked-attachment-ids-json",
      JSON.stringify(body.linkedAttachmentIds ?? []),
      "--autonomy-mode",
      body.autonomyMode ?? "supervised_build",
      "--lead-intake-json",
      JSON.stringify(body.leadIntake ?? {}),
    ]);
    return NextResponse.json(payload, {
      status: payload.status === "ok" ? 200 : 400,
    });
  } catch (error) {
    return NextResponse.json(
      {
        status: "error",
        message: error instanceof Error ? error.message : "Bridge failed.",
        payload: {},
      },
      { status: 500 },
    );
  }
}
