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
        payload: {},
      },
      { status: 500 },
    );
  }
}
