import type {
  ForgeActivitySnapshot,
  ForgeClientViewSnapshot,
  ForgeConsoleMessageResponse,
  CommandResult,
  ForgeAttachmentRecord,
  ForgeConstraintSections,
  ForgeIntakePreview,
  ForgeLeadIntakeProfile,
  ForgeLeadQualificationDraft,
  ForgeOperatorConsoleSnapshot,
  ForgeOverviewSnapshot,
  ForgeRequestedArtifactsDraft,
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

export function getClientViewSnapshot(projectKey: string) {
  const suffix = projectKey
    ? `?projectKey=${encodeURIComponent(projectKey)}`
    : "";
  return fetchJson<CommandResult<ForgeClientViewSnapshot>>(
    `/api/forge/client-view${suffix}`,
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

export function getOperatorConsoleSnapshot(projectKey: string) {
  const suffix = projectKey
    ? `?projectKey=${encodeURIComponent(projectKey)}`
    : "";
  return fetchJson<CommandResult<ForgeOperatorConsoleSnapshot>>(
    `/api/forge/console${suffix}`,
  );
}

export function sendOperatorMessage(input: {
  projectKey: string;
  message: string;
  executeAction?: string;
  confirmed?: boolean;
  confirmationText?: string;
}) {
  return fetchJson<CommandResult<ForgeConsoleMessageResponse>>("/api/forge/console", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function getActivitySnapshot(input?: { projectKey?: string; limit?: number }) {
  const params = new URLSearchParams();
  if (input?.projectKey) {
    params.set("projectKey", input.projectKey);
  }
  if (typeof input?.limit === "number") {
    params.set("limit", String(input.limit));
  }
  const query = params.toString();
  return fetchJson<CommandResult<ForgeActivitySnapshot>>(
    `/api/forge/activity${query ? `?${query}` : ""}`,
  );
}

export function previewIntakeRequest(input: {
  projectKey: string;
  requestKind: string;
  objective: string;
  projectContext: string;
  constraints: ForgeConstraintSections;
  requestedArtifacts: ForgeRequestedArtifactsDraft;
  leadIntake: ForgeLeadIntakeProfile;
  qualification: ForgeLeadQualificationDraft;
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
