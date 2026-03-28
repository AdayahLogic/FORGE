import { NextResponse } from "next/server";
import { runForgeBridge } from "../../../../lib/forge-bridge";
import { z } from "zod";

export const dynamic = "force-dynamic";

const ControlRequestSchema = z.object({
  action: z.string().min(1),
  projectKey: z.string().optional().default(""),
  confirmed: z.boolean().optional().default(false),
  confirmationText: z.string().optional().default(""),
});

export async function POST(request: Request) {
  try {
    const body = ControlRequestSchema.parse(await request.json());
    const args = [
      "control",
      "--action",
      body.action,
      "--project-key",
      body.projectKey,
      "--confirmation-text",
      body.confirmationText,
    ];
    if (body.confirmed) {
      args.push("--confirmed");
    }
    const payload = await runForgeBridge(args);
    return NextResponse.json(payload, {
      status: payload.status === "ok" ? 200 : 400,
    });
  } catch (error) {
    if (error instanceof z.ZodError) {
      return NextResponse.json(
        {
          status: "error",
          message: "Invalid control request payload.",
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
