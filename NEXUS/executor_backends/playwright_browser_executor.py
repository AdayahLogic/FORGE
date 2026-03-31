"""
Governed Playwright browser executor backend.

This backend executes a bounded browser action contract and emits auditable
evidence artifacts under the execution run directory.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from NEXUS.browser_execution_contract import validate_browser_execution_request
from NEXUS.executor_backends.contracts import build_executor_response_v1


ADAPTER_STATUS = "active"
BACKEND_ID = "playwright_browser"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _append_log(log_path: str | None, lines: list[str]) -> None:
    if not log_path:
        return
    try:
        Path(log_path).parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(("\n".join(lines).strip() + "\n"))
    except Exception:
        pass


def _load_playwright() -> Any:
    from playwright.sync_api import sync_playwright  # type: ignore

    return sync_playwright


def get_adapter_status() -> dict[str, Any]:
    try:
        _load_playwright()
        status = ADAPTER_STATUS
    except Exception:
        status = "inactive"
    return {
        "backend_id": BACKEND_ID,
        "adapter_status": status,
        "controlled_executor_only": True,
        "browser_execution_supported": status == "active",
    }


def _request_from_package(package: dict[str, Any]) -> dict[str, Any]:
    metadata = package.get("metadata")
    if isinstance(metadata, dict) and isinstance(metadata.get("browser_execution_request"), dict):
        return dict(metadata.get("browser_execution_request") or {})
    payload = package.get("browser_execution_request")
    return dict(payload) if isinstance(payload, dict) else {}


def execute_playwright_browser_package(
    *,
    project_path: str | None,
    package: dict[str, Any] | None,
    execution_id: str,
    execution_actor: str,
    log_path: str | None,
) -> dict[str, Any]:
    p = package or {}
    request = _request_from_package(p)
    validation = validate_browser_execution_request(request)
    contract = validation.get("contract") or {}
    if validation.get("status") != "valid":
        _append_log(log_path, [f"[browser][invalid_contract] errors={validation.get('errors') or []}"])
        return build_executor_response_v1(
            status="error",
            result_status="failed",
            exit_code=None,
            stderr_summary=f"browser_contract_invalid:{','.join(validation.get('errors') or [])}",
            log_ref=str(log_path or ""),
            artifacts_written_count=1 if log_path else 0,
            failure_class="preflight_block",
            runtime_artifact={
                "artifact_type": "execution_log",
                "execution_id": execution_id,
                "log_ref": str(log_path or ""),
                "runtime_target_id": str(p.get("execution_executor_target_id") or p.get("handoff_executor_target_id") or ""),
            } if log_path else {},
            adapter_status=get_adapter_status().get("adapter_status") or "inactive",
            backend_id=BACKEND_ID,
        )

    adapter_status = get_adapter_status().get("adapter_status") or "inactive"
    if adapter_status != "active":
        _append_log(log_path, ["[browser][inactive] playwright not available"])
        return build_executor_response_v1(
            status="error",
            result_status="failed",
            exit_code=None,
            stderr_summary="playwright_not_available",
            log_ref=str(log_path or ""),
            artifacts_written_count=1 if log_path else 0,
            failure_class="runtime_start_failure",
            runtime_artifact={
                "artifact_type": "execution_log",
                "execution_id": execution_id,
                "log_ref": str(log_path or ""),
                "runtime_target_id": str(p.get("execution_executor_target_id") or p.get("handoff_executor_target_id") or ""),
            } if log_path else {},
            adapter_status=adapter_status,
            backend_id=BACKEND_ID,
        )

    evidence_dir = None
    manifest_path = None
    evidence_files: list[str] = []
    extracted_data: list[dict[str, Any]] = []
    step_summaries: list[dict[str, Any]] = []
    runtime_target_id = str(p.get("execution_executor_target_id") or p.get("handoff_executor_target_id") or "openclaw_browser")

    try:
        if project_path:
            evidence_dir = Path(project_path) / "state" / "browser_evidence" / execution_id
            evidence_dir.mkdir(parents=True, exist_ok=True)
            manifest_path = evidence_dir / "evidence_manifest.json"
    except Exception:
        evidence_dir = None
        manifest_path = None

    _append_log(
        log_path,
        [
            f"[browser][start] execution_id={execution_id}",
            f"[browser][start] actor={execution_actor}",
            f"[browser][start] action_count={contract.get('action_count')}",
            f"[browser][start] allowed_domains={contract.get('allowed_domains')}",
        ],
    )

    playwright = _load_playwright()
    page = None
    browser = None
    context = None
    status = "ok"
    result_status = "succeeded"
    failure_class = ""
    stderr_summary = ""

    try:
        with playwright() as pw:
            browser = pw.chromium.launch(headless=bool(contract.get("headless", True)))
            context = browser.new_context()
            page = context.new_page()
            page.set_default_timeout(int(contract.get("timeout_ms") or 15000))

            for idx, action in enumerate(contract.get("actions") or []):
                action_type = str(action.get("type") or "")
                step_record: dict[str, Any] = {
                    "step_index": idx + 1,
                    "action_type": action_type,
                    "status": "ok",
                }
                if action_type == "open_url":
                    page.goto(str(action.get("url")), wait_until="domcontentloaded")
                    step_record["url"] = str(action.get("url"))
                elif action_type == "wait_for_selector":
                    page.wait_for_selector(str(action.get("selector")))
                    step_record["selector"] = str(action.get("selector"))
                elif action_type == "click_selector":
                    page.click(str(action.get("selector")))
                    step_record["selector"] = str(action.get("selector"))
                elif action_type == "fill_selector":
                    page.fill(str(action.get("selector")), str(action.get("value") or ""))
                    step_record["selector"] = str(action.get("selector"))
                elif action_type == "extract_text":
                    extracted = page.locator(str(action.get("selector"))).all_inner_texts()
                    extracted_data.append({
                        "type": "extract_text",
                        "selector": str(action.get("selector")),
                        "values": extracted[:100],
                    })
                    step_record["selector"] = str(action.get("selector"))
                    step_record["value_count"] = len(extracted)
                elif action_type == "extract_links":
                    links = page.eval_on_selector_all(
                        str(action.get("selector")),
                        "els => els.map(el => ({href: el.href || '', text: (el.textContent || '').trim()}))",
                    )
                    if isinstance(links, list):
                        links = links[:200]
                    else:
                        links = []
                    extracted_data.append({
                        "type": "extract_links",
                        "selector": str(action.get("selector")),
                        "values": links,
                    })
                    step_record["selector"] = str(action.get("selector"))
                    step_record["value_count"] = len(links)
                elif action_type == "capture_screenshot":
                    if evidence_dir:
                        label = str(action.get("label") or f"step_{idx + 1}").replace(" ", "_")
                        screenshot_path = evidence_dir / f"{idx + 1:02d}_{label}.png"
                        page.screenshot(path=str(screenshot_path), full_page=True)
                        evidence_files.append(str(screenshot_path))
                        step_record["screenshot"] = str(screenshot_path)
                step_summaries.append(step_record)

            if evidence_dir and page:
                final_shot = evidence_dir / "final.png"
                page.screenshot(path=str(final_shot), full_page=True)
                evidence_files.append(str(final_shot))
    except Exception as e:
        status = "error"
        result_status = "failed"
        failure_class = "runtime_execution_failure"
        stderr_summary = str(e)
        _append_log(log_path, [f"[browser][error] {e}"])
        if evidence_dir and page:
            try:
                fail_shot = evidence_dir / "failure.png"
                page.screenshot(path=str(fail_shot), full_page=True)
                evidence_files.append(str(fail_shot))
            except Exception:
                pass
    finally:
        try:
            if context:
                context.close()
        except Exception:
            pass
        try:
            if browser:
                browser.close()
        except Exception:
            pass

    manifest = {
        "execution_id": execution_id,
        "captured_at": _utc_now_iso(),
        "runtime_target_id": runtime_target_id,
        "backend_id": BACKEND_ID,
        "contract": contract,
        "step_summaries": step_summaries,
        "extracted_data": extracted_data,
        "evidence_files": evidence_files,
        "result_status": result_status,
        "failure_class": failure_class,
    }
    if manifest_path:
        try:
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
            evidence_files.append(str(manifest_path))
        except Exception:
            pass

    stdout_summary = f"browser_actions={len(step_summaries)} extracted_items={len(extracted_data)} evidence_files={len(evidence_files)}"
    runtime_artifact = {
        "artifact_type": "execution_log",
        "execution_id": execution_id,
        "log_ref": str(log_path or ""),
        "runtime_target_id": runtime_target_id,
        "browser_evidence_manifest_ref": str(manifest_path or ""),
        "browser_evidence_file_count": len(evidence_files),
        "browser_extracted_item_count": len(extracted_data),
        "browser_lane": "playwright_governed_v1",
    }
    return build_executor_response_v1(
        status=status,
        result_status=result_status,
        exit_code=0 if result_status == "succeeded" else 1,
        stdout_summary=stdout_summary,
        stderr_summary=stderr_summary,
        log_ref=str(log_path or ""),
        files_touched_count=0,
        artifacts_written_count=max(1 if log_path else 0, len(evidence_files)),
        failure_class=failure_class,
        runtime_artifact=runtime_artifact,
        rollback_summary={},
        adapter_status=adapter_status,
        backend_id=BACKEND_ID,
    )
