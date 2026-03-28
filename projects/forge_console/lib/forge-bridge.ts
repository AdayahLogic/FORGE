const FORGE_API_URL = (process.env.FORGE_API_URL || "http://localhost:8000").replace(
  /\/+$/,
  "",
);
const FORGE_CONSOLE_TOKEN = process.env.FORGE_CONSOLE_TOKEN || "";
const BRIDGE_TIMEOUT_MS = 15_000;

function getFlagValue(args: string[], flag: string, fallback = ""): string {
  const idx = args.indexOf(flag);
  if (idx < 0 || idx + 1 >= args.length) {
    return fallback;
  }
  return args[idx + 1] ?? fallback;
}

function hasFlag(args: string[], flag: string): boolean {
  return args.includes(flag);
}

function parseJsonArg(raw: string, fallback: unknown): unknown {
  if (!raw.trim()) {
    return fallback;
  }
  try {
    return JSON.parse(raw);
  } catch {
    return fallback;
  }
}

async function requestBridge(
  path: string,
  init?: RequestInit,
): Promise<Record<string, unknown>> {
  const headers = new Headers(init?.headers);
  if (FORGE_CONSOLE_TOKEN) {
    headers.set("x-forge-token", FORGE_CONSOLE_TOKEN);
  }
  const response = await fetch(`${FORGE_API_URL}${path}`, {
    ...init,
    headers,
    signal: init?.signal ?? AbortSignal.timeout(BRIDGE_TIMEOUT_MS),
  });
  const text = await response.text();
  if (!text.trim()) {
    throw new Error("Forge API returned an empty response.");
  }
  const payload = JSON.parse(text) as Record<string, unknown>;
  if (!response.ok && payload.status !== "error") {
    throw new Error(`Forge API request failed (${response.status}).`);
  }
  return payload;
}

export async function runForgeBridge(args: string[]) {
  const mode = args[0];
  if (!mode) {
    throw new Error("Bridge mode is required.");
  }

  if (mode === "overview") {
    return requestBridge("/overview");
  }

  if (mode === "project") {
    const projectKey = getFlagValue(args, "--project-key");
    return requestBridge(`/project/${encodeURIComponent(projectKey)}`);
  }

  if (mode === "package") {
    const packageId = getFlagValue(args, "--package-id");
    const projectKey = getFlagValue(args, "--project-key");
    const query = projectKey
      ? `?project_key=${encodeURIComponent(projectKey)}`
      : "";
    return requestBridge(`/package/${encodeURIComponent(packageId)}${query}`);
  }

  if (mode === "client_view") {
    const projectKey = getFlagValue(args, "--project-key");
    const query = projectKey
      ? `?project_key=${encodeURIComponent(projectKey)}`
      : "";
    return requestBridge(`/client-view${query}`);
  }

  if (mode === "control") {
    return requestBridge("/control", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        action: getFlagValue(args, "--action"),
        project_key: getFlagValue(args, "--project-key"),
        confirmed: hasFlag(args, "--confirmed"),
        confirmation_text: getFlagValue(args, "--confirmation-text"),
      }),
    });
  }

  if (mode === "intake_preview") {
    return requestBridge("/intake-preview", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        request_kind: getFlagValue(args, "--request-kind", "update_request"),
        project_key: getFlagValue(args, "--project-key"),
        objective: getFlagValue(args, "--objective"),
        project_context: getFlagValue(args, "--project-context"),
        constraints: parseJsonArg(getFlagValue(args, "--constraints-json", "{}"), {}),
        requested_artifacts: parseJsonArg(
          getFlagValue(args, "--requested-artifacts-json", "{}"),
          {},
        ),
        linked_attachment_ids: parseJsonArg(
          getFlagValue(args, "--linked-attachment-ids-json", "[]"),
          [],
        ),
        autonomy_mode: getFlagValue(args, "--autonomy-mode", "supervised_build"),
        lead_intake: parseJsonArg(getFlagValue(args, "--lead-intake-json", "{}"), {}),
        qualification: parseJsonArg(getFlagValue(args, "--qualification-json", "{}"), {}),
      }),
    });
  }

  if (mode === "upload_attachment") {
    return requestBridge("/attachment", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        project_key: getFlagValue(args, "--project-key"),
        file_path: getFlagValue(args, "--file-path"),
        file_name: getFlagValue(args, "--file-name"),
        file_type: getFlagValue(args, "--file-type", "application/octet-stream"),
        source: getFlagValue(args, "--source", "console_upload"),
        purpose: getFlagValue(args, "--purpose", "supporting_context"),
        package_id: getFlagValue(args, "--package-id"),
        request_id: getFlagValue(args, "--request-id"),
      }),
    });
  }

  throw new Error(`Unsupported bridge mode: ${mode}`);
}
