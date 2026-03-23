import { NextResponse } from "next/server";
import { runForgeBridge } from "../../../../../lib/forge-bridge";

export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  const body = (await request.json()) as {
    projectKey?: string;
    objective?: string;
    constraints?: string[];
    requestedArtifacts?: string[];
    linkedAttachmentIds?: string[];
    autonomyMode?: string;
  };
  try {
    const payload = await runForgeBridge([
      "intake_preview",
      "--project-key",
      body.projectKey ?? "",
      "--objective",
      body.objective ?? "",
      "--constraints-json",
      JSON.stringify(body.constraints ?? []),
      "--requested-artifacts-json",
      JSON.stringify(body.requestedArtifacts ?? []),
      "--linked-attachment-ids-json",
      JSON.stringify(body.linkedAttachmentIds ?? []),
      "--autonomy-mode",
      body.autonomyMode ?? "supervised_build",
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
