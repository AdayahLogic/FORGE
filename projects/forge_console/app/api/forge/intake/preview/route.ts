import { NextResponse } from "next/server";
import { runForgeBridge } from "../../../../../lib/forge-bridge";
import { z } from "zod";

export const dynamic = "force-dynamic";

const IntakePreviewSchema = z.object({
  requestKind: z.string().optional().default("update_request"),
  projectKey: z.string().min(1),
  objective: z.string().optional().default(""),
  projectContext: z.string().optional().default(""),
  constraints: z.record(z.string(), z.unknown()).or(z.array(z.unknown())).optional().default({}),
  requestedArtifacts: z.record(z.string(), z.unknown()).or(z.array(z.unknown())).optional().default({}),
  linkedAttachmentIds: z.array(z.string()).optional().default([]),
  autonomyMode: z.string().optional().default("supervised_build"),
  leadIntake: z.record(z.string(), z.unknown()).optional().default({}),
  qualification: z.record(z.string(), z.unknown()).optional().default({}),
});

export async function POST(request: Request) {
  try {
    const body = IntakePreviewSchema.parse(await request.json());
    const payload = await runForgeBridge([
      "intake_preview",
      "--request-kind",
      body.requestKind,
      "--project-key",
      body.projectKey,
      "--objective",
      body.objective,
      "--project-context",
      body.projectContext,
      "--constraints-json",
      JSON.stringify(body.constraints),
      "--requested-artifacts-json",
      JSON.stringify(body.requestedArtifacts),
      "--linked-attachment-ids-json",
      JSON.stringify(body.linkedAttachmentIds),
      "--autonomy-mode",
      body.autonomyMode,
      "--lead-intake-json",
      JSON.stringify(body.leadIntake),
      "--qualification-json",
      JSON.stringify(body.qualification),
    ]);
    return NextResponse.json(payload, {
      status: payload.status === "ok" ? 200 : 400,
    });
  } catch (error) {
    if (error instanceof z.ZodError) {
      return NextResponse.json(
        {
          status: "error",
          message: "Invalid intake preview payload.",
          payload: { issues: error.issues },
        },
        { status: 400 },
      );
    }
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
