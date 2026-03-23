import type {
  CommandResult,
  ForgeAttachmentRecord,
  ForgeIntakePreview,
  ForgeOverviewSnapshot,
  PackageDetailSnapshot,
  ProjectSnapshot,
} from "./forge-types";

async function fetchJson<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options?.headers ?? {}),
    },
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return (await response.json()) as T;
}

export function getOverviewSnapshot() {
  return fetchJson<CommandResult<ForgeOverviewSnapshot>>("/api/forge/overview");
}

export function getProjectSnapshot(projectKey: string) {
  return fetchJson<CommandResult<ProjectSnapshot>>(
    `/api/forge/project/${encodeURIComponent(projectKey)}`,
  );
}

export function getPackageSnapshot(packageId: string, projectKey: string) {
  const suffix = projectKey
    ? `?projectKey=${encodeURIComponent(projectKey)}`
    : "";
  return fetchJson<CommandResult<PackageDetailSnapshot>>(
    `/api/forge/package/${encodeURIComponent(packageId)}${suffix}`,
  );
}

export function runControlAction(input: {
  action: string;
  projectKey: string;
  confirmed: boolean;
  confirmationText: string;
}) {
  return fetchJson<CommandResult<Record<string, unknown>>>("/api/forge/control", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function previewIntakeRequest(input: {
  projectKey: string;
  objective: string;
  constraints: string[];
  requestedArtifacts: string[];
  linkedAttachmentIds: string[];
  autonomyMode: string;
}) {
  return fetchJson<CommandResult<ForgeIntakePreview>>("/api/forge/intake/preview", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function uploadAttachment(input: {
  projectKey: string;
  file: File;
  purpose: string;
  source?: string;
  requestId?: string;
}) {
  const formData = new FormData();
  formData.set("projectKey", input.projectKey);
  formData.set("purpose", input.purpose);
  formData.set("source", input.source ?? "console_upload");
  formData.set("requestId", input.requestId ?? "");
  formData.set("file", input.file);
  const response = await fetch("/api/forge/attachment", {
    method: "POST",
    body: formData,
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return (await response.json()) as CommandResult<{
    status: string;
    reason: string;
    attachment: ForgeAttachmentRecord;
  }>;
}
