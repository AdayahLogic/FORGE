/* eslint-disable @typescript-eslint/no-require-imports */
const childProcess = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const buildDir = path.join(root, ".forge-console-build");

if (!fs.existsSync(buildDir)) {
  process.exit(0);
}

try {
  childProcess.execFileSync(
    "powershell.exe",
    [
      "-NoProfile",
      "-NonInteractive",
      "-Command",
      `if (Test-Path -LiteralPath '${buildDir.replace(/'/g, "''")}') { Remove-Item -LiteralPath '${buildDir.replace(/'/g, "''")}' -Recurse -Force }`,
    ],
    { stdio: "pipe" },
  );
} catch (error) {
  const message =
    error && typeof error === "object" && "message" in error
      ? String(error.message)
      : "Unknown build cleanup failure.";
  console.error(
    `Forge Console build cleanup could not remove ${buildDir}. ` +
      `This usually means a lingering Next/node process still has the folder locked. ${message}`,
  );
  process.exit(1);
}
