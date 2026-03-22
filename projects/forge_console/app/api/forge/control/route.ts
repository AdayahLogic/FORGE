import { NextResponse } from "next/server";
import { runForgeBridge } from "../../../../lib/forge-bridge";

export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  const body = (await request.json()) as {
    action?: string;
    projectKey?: string;
    confirmed?: boolean;
    confirmationText?: string;
  };
  try {
    const args = [
      "control",
      "--action",
      body.action ?? "",
      "--project-key",
      body.projectKey ?? "",
      "--confirmation-text",
      body.confirmationText ?? "",
    ];
    if (body.confirmed) {
      args.push("--confirmed");
    }
    const payload = await runForgeBridge(args);
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
