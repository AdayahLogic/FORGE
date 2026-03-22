import type {
  ForgeOverviewSnapshot,
  PackageDetailSnapshot,
  PackageQueueRow,
  ProjectSnapshot,
} from "./forge-types";

export const LIFECYCLE_COLUMNS = [
  "Review Pending",
  "Decision",
  "Eligibility",
  "Release",
  "Handoff",
  "Execution",
  "Abacus Evaluation",
  "NemoClaw Advisory",
] as const;

export type LifecycleColumn = (typeof LIFECYCLE_COLUMNS)[number];

export function getLifecycleColumn(pkg: PackageQueueRow): LifecycleColumn {
  if (pkg.local_analysis_status && pkg.local_analysis_status !== "pending") {
    return "NemoClaw Advisory";
  }
  if (pkg.evaluation_status && pkg.evaluation_status !== "pending") {
    return "Abacus Evaluation";
  }
  if (pkg.execution_status && pkg.execution_status !== "pending") {
    return "Execution";
  }
  if (pkg.handoff_status && pkg.handoff_status !== "pending") {
    return "Handoff";
  }
  if (pkg.release_status && pkg.release_status !== "pending") {
    return "Release";
  }
  if (pkg.eligibility_status && pkg.eligibility_status !== "pending") {
    return "Eligibility";
  }
  if (pkg.decision_status && pkg.decision_status !== "pending") {
    return "Decision";
  }
  return "Review Pending";
}

export function groupPackagesByLifecycle(
  packages: PackageQueueRow[],
  includeCompleted: boolean,
  showOnlyRisk: boolean,
): Record<LifecycleColumn, PackageQueueRow[]> {
  const grouped = Object.fromEntries(
    LIFECYCLE_COLUMNS.map((column) => [column, [] as PackageQueueRow[]]),
  ) as Record<LifecycleColumn, PackageQueueRow[]>;
  for (const pkg of packages) {
    const isCompleted =
      pkg.local_analysis_status === "completed" ||
      pkg.execution_status === "succeeded";
    const isRisky =
      ["high", "critical"].includes(pkg.failure_risk_band) ||
      ["blocked", "failed", "rolled_back"].includes(pkg.execution_status) ||
      ["blocked", "error_fallback"].includes(pkg.evaluation_status) ||
      ["blocked", "error_fallback"].includes(pkg.local_analysis_status);
    if (!includeCompleted && isCompleted) {
      continue;
    }
    if (showOnlyRisk && !isRisky) {
      continue;
    }
    grouped[getLifecycleColumn(pkg)].push(pkg);
  }
  return grouped;
}

export function getSelectedProjectKey(
  overview: ForgeOverviewSnapshot | null,
  currentKey: string,
): string {
  if (currentKey) {
    return currentKey;
  }
  return overview?.projects[0]?.project_key ?? "";
}

export function getCurrentPackagePointer(project: ProjectSnapshot | null): string {
  const value = project?.project_state?.execution_package_id;
  return typeof value === "string" ? value : "";
}

export function getEvaluationSummary(
  detail: PackageDetailSnapshot | null,
): Record<string, unknown> {
  const evaluation = detail?.evaluation ?? {};
  const summary = evaluation.evaluation_summary;
  return typeof summary === "object" && summary ? (summary as Record<string, unknown>) : {};
}

export function getLocalAnalysisSummary(
  detail: PackageDetailSnapshot | null,
): Record<string, unknown> {
  const analysis = detail?.local_analysis ?? {};
  const summary = analysis.local_analysis_summary;
  return typeof summary === "object" && summary ? (summary as Record<string, unknown>) : {};
}
