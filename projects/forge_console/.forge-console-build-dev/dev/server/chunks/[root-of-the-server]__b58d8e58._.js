module.exports = [
"[externals]/next/dist/compiled/next-server/app-route-turbo.runtime.dev.js [external] (next/dist/compiled/next-server/app-route-turbo.runtime.dev.js, cjs)", ((__turbopack_context__, module, exports) => {

const mod = __turbopack_context__.x("next/dist/compiled/next-server/app-route-turbo.runtime.dev.js", () => require("next/dist/compiled/next-server/app-route-turbo.runtime.dev.js"));

module.exports = mod;
}),
"[externals]/next/dist/compiled/@opentelemetry/api [external] (next/dist/compiled/@opentelemetry/api, cjs)", ((__turbopack_context__, module, exports) => {

const mod = __turbopack_context__.x("next/dist/compiled/@opentelemetry/api", () => require("next/dist/compiled/@opentelemetry/api"));

module.exports = mod;
}),
"[externals]/next/dist/compiled/next-server/app-page-turbo.runtime.dev.js [external] (next/dist/compiled/next-server/app-page-turbo.runtime.dev.js, cjs)", ((__turbopack_context__, module, exports) => {

const mod = __turbopack_context__.x("next/dist/compiled/next-server/app-page-turbo.runtime.dev.js", () => require("next/dist/compiled/next-server/app-page-turbo.runtime.dev.js"));

module.exports = mod;
}),
"[externals]/next/dist/server/app-render/work-unit-async-storage.external.js [external] (next/dist/server/app-render/work-unit-async-storage.external.js, cjs)", ((__turbopack_context__, module, exports) => {

const mod = __turbopack_context__.x("next/dist/server/app-render/work-unit-async-storage.external.js", () => require("next/dist/server/app-render/work-unit-async-storage.external.js"));

module.exports = mod;
}),
"[externals]/next/dist/server/app-render/work-async-storage.external.js [external] (next/dist/server/app-render/work-async-storage.external.js, cjs)", ((__turbopack_context__, module, exports) => {

const mod = __turbopack_context__.x("next/dist/server/app-render/work-async-storage.external.js", () => require("next/dist/server/app-render/work-async-storage.external.js"));

module.exports = mod;
}),
"[externals]/next/dist/shared/lib/no-fallback-error.external.js [external] (next/dist/shared/lib/no-fallback-error.external.js, cjs)", ((__turbopack_context__, module, exports) => {

const mod = __turbopack_context__.x("next/dist/shared/lib/no-fallback-error.external.js", () => require("next/dist/shared/lib/no-fallback-error.external.js"));

module.exports = mod;
}),
"[externals]/next/dist/server/app-render/after-task-async-storage.external.js [external] (next/dist/server/app-render/after-task-async-storage.external.js, cjs)", ((__turbopack_context__, module, exports) => {

const mod = __turbopack_context__.x("next/dist/server/app-render/after-task-async-storage.external.js", () => require("next/dist/server/app-render/after-task-async-storage.external.js"));

module.exports = mod;
}),
"[externals]/node:child_process [external] (node:child_process, cjs)", ((__turbopack_context__, module, exports) => {

const mod = __turbopack_context__.x("node:child_process", () => require("node:child_process"));

module.exports = mod;
}),
"[externals]/node:util [external] (node:util, cjs)", ((__turbopack_context__, module, exports) => {

const mod = __turbopack_context__.x("node:util", () => require("node:util"));

module.exports = mod;
}),
"[project]/lib/forge-bridge.ts [app-route] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "runForgeBridge",
    ()=>runForgeBridge
]);
var __TURBOPACK__imported__module__$5b$externals$5d2f$node$3a$child_process__$5b$external$5d$__$28$node$3a$child_process$2c$__cjs$29$__ = __turbopack_context__.i("[externals]/node:child_process [external] (node:child_process, cjs)");
var __TURBOPACK__imported__module__$5b$externals$5d2f$node$3a$util__$5b$external$5d$__$28$node$3a$util$2c$__cjs$29$__ = __turbopack_context__.i("[externals]/node:util [external] (node:util, cjs)");
;
;
const execFileAsync = (0, __TURBOPACK__imported__module__$5b$externals$5d2f$node$3a$util__$5b$external$5d$__$28$node$3a$util$2c$__cjs$29$__["promisify"])(__TURBOPACK__imported__module__$5b$externals$5d2f$node$3a$child_process__$5b$external$5d$__$28$node$3a$child_process$2c$__cjs$29$__["execFile"]);
const BRIDGE_PATH = "C:/FORGE/ops/forge_console_bridge.py";
const PYTHON_CANDIDATES = [
    "python",
    "py",
    "python3"
];
async function runForgeBridge(args) {
    let lastError = null;
    for (const candidate of PYTHON_CANDIDATES){
        try {
            const candidateArgs = candidate === "py" ? [
                "-3",
                BRIDGE_PATH,
                ...args
            ] : [
                BRIDGE_PATH,
                ...args
            ];
            const { stdout } = await execFileAsync(candidate, candidateArgs, {
                cwd: "C:/FORGE",
                windowsHide: true
            });
            return JSON.parse(stdout);
        } catch (error) {
            lastError = error;
        }
    }
    throw lastError;
}
}),
"[project]/app/api/forge/project/[projectKey]/route.ts [app-route] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "GET",
    ()=>GET,
    "dynamic",
    ()=>dynamic
]);
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$server$2e$js__$5b$app$2d$route$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/node_modules/next/server.js [app-route] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$forge$2d$bridge$2e$ts__$5b$app$2d$route$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/lib/forge-bridge.ts [app-route] (ecmascript)");
;
;
const dynamic = "force-dynamic";
async function GET(_request, context) {
    const params = await context.params;
    try {
        const payload = await (0, __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$forge$2d$bridge$2e$ts__$5b$app$2d$route$5d$__$28$ecmascript$29$__["runForgeBridge"])([
            "project",
            "--project-key",
            params.projectKey
        ]);
        return __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$server$2e$js__$5b$app$2d$route$5d$__$28$ecmascript$29$__["NextResponse"].json(payload);
    } catch (error) {
        return __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$server$2e$js__$5b$app$2d$route$5d$__$28$ecmascript$29$__["NextResponse"].json({
            status: "error",
            message: error instanceof Error ? error.message : "Bridge failed.",
            payload: {
                project_key: params.projectKey,
                project_name: params.projectKey,
                project_path: "",
                project_meta: {},
                project_summary: {},
                project_state: {},
                latest_session: {},
                system_health: {},
                package_queue: {
                    project_key: params.projectKey,
                    project_path: "",
                    count: 0,
                    pending_count: 0,
                    packages: []
                },
                current_package: null,
                system_status: {
                    backend_reachable: false,
                    status: "offline",
                    label: "Forge Not Running",
                    reason: error instanceof Error ? error.message : "Bridge failed."
                },
                workflow_activity: {
                    current_phase: "planning",
                    phase_label: "Planning",
                    last_action: "Backend offline",
                    current_project: params.projectKey,
                    active_package_id: "",
                    package_status: "Backend offline",
                    package_created_at: ""
                },
                approval_summary: {},
                intake_workspace: null,
                degraded_sources: [
                    "bridge"
                ]
            }
        });
    }
}
}),
];

//# sourceMappingURL=%5Broot-of-the-server%5D__b58d8e58._.js.map