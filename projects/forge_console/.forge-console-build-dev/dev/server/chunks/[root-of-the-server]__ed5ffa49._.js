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
"[project]/app/api/forge/overview/route.ts [app-route] (ecmascript)", ((__turbopack_context__) => {
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
async function GET() {
    try {
        const payload = await (0, __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$forge$2d$bridge$2e$ts__$5b$app$2d$route$5d$__$28$ecmascript$29$__["runForgeBridge"])([
            "overview"
        ]);
        return __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$server$2e$js__$5b$app$2d$route$5d$__$28$ecmascript$29$__["NextResponse"].json(payload);
    } catch (error) {
        return __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$server$2e$js__$5b$app$2d$route$5d$__$28$ecmascript$29$__["NextResponse"].json({
            status: "error",
            message: error instanceof Error ? error.message : "Bridge failed.",
            payload: {
                generated_at: "",
                studio_name: "FORGE",
                overview: {
                    system_status: {
                        backend_reachable: false,
                        status: "offline",
                        label: "Forge Not Running",
                        reason: error instanceof Error ? error.message : "Bridge failed."
                    },
                    studio_health: "Backend offline",
                    aegis_posture: {},
                    queue_counts: {
                        queued_projects: 0,
                        review_required_projects: 0,
                        approval_pending_total: 0,
                        reapproval_required_total: 0
                    },
                    package_counts: {
                        review_pending: 0,
                        decision_pending: 0,
                        eligibility_pending: 0,
                        release_pending: 0,
                        handoff_pending: 0,
                        execution_pending: 0,
                        execution_blocked: 0,
                        execution_failed: 0,
                        execution_succeeded: 0
                    },
                    evaluation_counts: {
                        pending: 0,
                        completed: 0,
                        blocked: 0,
                        error: 0,
                        bands: {}
                    },
                    local_analysis_counts: {
                        pending: 0,
                        completed: 0,
                        blocked: 0,
                        error: 0,
                        confidence_bands: {},
                        next_actions: {}
                    },
                    project_count: 0,
                    executor_health: {}
                },
                projects: [],
                approval_center: {
                    approval_summary: {},
                    approval_lifecycle: {},
                    allowed_actions: [],
                    surface_mode: "read_only"
                },
                raw: {
                    dashboard_summary: {}
                }
            }
        });
    }
}
}),
];

//# sourceMappingURL=%5Broot-of-the-server%5D__ed5ffa49._.js.map