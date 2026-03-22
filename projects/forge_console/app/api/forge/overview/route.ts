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
        payload: {},
      },
      { status: 500 },
    );
  }
}
