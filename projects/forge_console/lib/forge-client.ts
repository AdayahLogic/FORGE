import type {
  CommandResult,
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
