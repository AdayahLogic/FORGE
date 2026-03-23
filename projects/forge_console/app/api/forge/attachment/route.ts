import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { NextResponse } from "next/server";
import { runForgeBridge } from "../../../../lib/forge-bridge";

export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  let tempDir = "";
  try {
    const formData = await request.formData();
    const projectKey = String(formData.get("projectKey") ?? "");
    const purpose = String(formData.get("purpose") ?? "supporting_context");
    const source = String(formData.get("source") ?? "console_upload");
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

    tempDir = await mkdtemp(join(tmpdir(), "forge-console-"));
    const tempFilePath = join(tempDir, file.name);
    const buffer = Buffer.from(await file.arrayBuffer());
    await writeFile(tempFilePath, buffer);

    const payload = await runForgeBridge([
      "upload_attachment",
      "--project-key",
      projectKey,
      "--file-path",
      tempFilePath,
      "--file-name",
      file.name,
      "--file-type",
      file.type || "application/octet-stream",
      "--source",
      source,
      "--purpose",
      purpose,
      "--request-id",
      requestId,
    ]);
    return NextResponse.json(payload, {
      status: payload.status === "ok" ? 200 : 400,
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
  } finally {
    if (tempDir) {
      await rm(tempDir, { recursive: true, force: true });
    }
  }
}
