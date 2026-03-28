import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";
const FORGE_API_URL = (process.env.FORGE_API_URL || "http://localhost:8000").replace(
  /\/+$/,
  "",
);
const FORGE_CONSOLE_TOKEN = process.env.FORGE_CONSOLE_TOKEN || "";

export async function POST(request: Request) {
  try {
    const formData = await request.formData();
    const projectKey = String(formData.get("projectKey") ?? "");
    const purpose = String(formData.get("purpose") ?? "supporting_context");
    const source = String(formData.get("source") ?? "console_upload");
    const packageId = String(formData.get("packageId") ?? "");
    const requestId = String(formData.get("requestId") ?? "");
    const file = formData.get("file");
    if (!(file instanceof File)) {
      return NextResponse.json(
        {
          status: "error",
          message: "Attachment file is required.",
          payload: {},
        },
        { status: 400 },
      );
    }

    const outbound = new FormData();
    outbound.append("project_key", projectKey);
    outbound.append("source", source);
    outbound.append("purpose", purpose);
    outbound.append("package_id", packageId);
    outbound.append("request_id", requestId);
    outbound.append("file", file);

    const response = await fetch(`${FORGE_API_URL}/attachment-upload`, {
      method: "POST",
      headers: FORGE_CONSOLE_TOKEN
        ? { "x-forge-token": FORGE_CONSOLE_TOKEN }
        : undefined,
      body: outbound,
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
        message: error instanceof Error ? error.message : "Attachment upload failed.",
        payload: {},
      },
      { status: 500 },
    );
  }
}
