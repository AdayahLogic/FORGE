/* eslint-disable @typescript-eslint/no-require-imports */
const childProcess = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const buildDir = path.join(root, ".forge-console-build");
const staleEntries = [
  "app-path-routes-manifest.json",
  "build-manifest.json",
  "BUILD_ID",
  "cache",
  "diagnostics",
  "export-marker.json",
  "images-manifest.json",
  "next-minimal-server.js.nft.json",
  "next-server.js.nft.json",
  "package.json",
  "prerender-manifest.json",
  "react-loadable-manifest.json",
  "required-server-files.js",
  "required-server-files.json",
  "routes-manifest.json",
  "server",
  "static",
  "trace",
  "trace-build",
  "types",
];

if (!fs.existsSync(buildDir)) {
  process.exit(0);
}

function escapePowerShellLiteralPath(targetPath) {
  return targetPath.replace(/'/g, "''");
}

function removeEntry(targetPath) {
  childProcess.execFileSync(
    "powershell.exe",
    [
      "-NoProfile",
      "-NonInteractive",
      "-Command",
      `if (Test-Path -LiteralPath '${escapePowerShellLiteralPath(targetPath)}') { Remove-Item -LiteralPath '${escapePowerShellLiteralPath(targetPath)}' -Recurse -Force -ErrorAction Stop }`,
    ],
    { stdio: "pipe" },
  );
}

function retryRemove(targetPath) {
  const attempts = 3;
  let lastError = null;

  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    try {
      removeEntry(targetPath);
      return;
    } catch (error) {
      lastError = error;

      if (attempt < attempts) {
        Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, attempt * 250);
      }
    }
  }

  throw lastError;
}

try {
  for (const entry of staleEntries) {
    retryRemove(path.join(buildDir, entry));
  }
} catch (error) {
  const message =
    error && typeof error === "object" && "message" in error
      ? String(error.message)
      : "Unknown build cleanup failure.";
  console.error(
    `Forge Console build cleanup could not remove a stale production artifact under ${buildDir}. ` +
      `This usually means a lingering Next/node process still has the production output locked. ${message}`,
  );
  process.exit(1);
}
