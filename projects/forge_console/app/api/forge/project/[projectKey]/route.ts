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
        payload: {},
      },
      { status: 500 },
    );
  }
}
