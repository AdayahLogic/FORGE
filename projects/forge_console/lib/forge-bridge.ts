import { execFile } from "node:child_process";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);

const BRIDGE_PATH = "C:/FORGE/ops/forge_console_bridge.py";
const PYTHON_CANDIDATES = ["python", "py", "python3"];

export async function runForgeBridge(args: string[]) {
  let lastError: unknown = null;
  for (const candidate of PYTHON_CANDIDATES) {
    try {
      const candidateArgs =
        candidate === "py" ? ["-3", BRIDGE_PATH, ...args] : [BRIDGE_PATH, ...args];
      const { stdout } = await execFileAsync(candidate, candidateArgs, {
        cwd: "C:/FORGE",
        windowsHide: true,
      });
      return JSON.parse(stdout);
    } catch (error) {
      lastError = error;
    }
  }
  throw lastError;
}
