import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

const FORGE_API_URL = (process.env.FORGE_API_URL || "http://localhost:8000").replace(
  /\/+$/,
  "",
);
const FORGE_CONSOLE_TOKEN = process.env.FORGE_CONSOLE_TOKEN || "";

export async function GET() {
  try {
    const response = await fetch(`${FORGE_API_URL}/billing/blocked-customers`, {
      method: "GET",
      headers: FORGE_CONSOLE_TOKEN
        ? { "x-forge-token": FORGE_CONSOLE_TOKEN }
        : undefined,
      cache: "no-store",
    });
    const text = await response.text();
    if (!text.trim()) {
      throw new Error("Forge API returned an empty response.");
    }
    const payload = JSON.parse(text) as Record<string, unknown>;
    return NextResponse.json(payload, {
      status:
        response.ok && payload.status === "ok"
          ? 200
          : response.ok
            ? 400
            : response.status,
    });
  } catch (error) {
    return NextResponse.json(
      {
        status: "error",
        message: error instanceof Error ? error.message : "Billing blocked-customers request failed.",
        payload: {},
      },
      { status: 500 },
    );
  }
}
