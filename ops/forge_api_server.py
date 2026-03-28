"""
Forge Console HTTP API server.

Additive API layer that mirrors the command modes exposed by
ops/forge_console_bridge.py so the Next.js console can use HTTP instead of
shelling out to a local Python subprocess.
"""

from __future__ import annotations

import json
import os
import tempfile
from typing import Any

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Security, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader
from pydantic import BaseModel

from ops.forge_console_bridge import (
    build_client_view_snapshot,
    build_intake_preview,
    build_package_snapshot,
    build_project_snapshot,
    build_studio_snapshot,
    execute_control_action,
    upload_attachment,
)


app = FastAPI(title="Forge API", version="1.0.0")

_TOKEN_HEADER = APIKeyHeader(name="x-forge-token", auto_error=False)


def _allowed_origins() -> list[str]:
    raw = str(os.getenv("FORGE_CORS_ORIGINS", "")).strip()
    if raw:
        return [item.strip() for item in raw.split(",") if item.strip()]
    return ["http://localhost:3000", "http://127.0.0.1:3000"]


def _require_token(token: str | None = Security(_TOKEN_HEADER)) -> None:
    expected = str(os.getenv("FORGE_CONSOLE_TOKEN", "")).strip()
    if not expected:
        raise HTTPException(status_code=503, detail="FORGE_CONSOLE_TOKEN not configured.")
    if token != expected:
        raise HTTPException(status_code=401, detail="Unauthorized.")


app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _ok(payload: dict[str, Any], message: str = "") -> dict[str, Any]:
    return {
        "status": "ok",
        "message": message,
        "payload": payload,
    }


def _error(message: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "status": "error",
        "message": message,
        "payload": payload or {},
    }


class ControlRequest(BaseModel):
    action: str
    project_key: str = ""
    confirmed: bool = False
    confirmation_text: str = ""


class IntakePreviewRequest(BaseModel):
    request_kind: str = "update_request"
    project_key: str
    objective: str = ""
    project_context: str = ""
    constraints: dict[str, Any] | list[Any] = {}
    requested_artifacts: dict[str, Any] | list[Any] = {}
    linked_attachment_ids: list[str] = []
    autonomy_mode: str = "supervised_build"
    lead_intake: dict[str, Any] = {}
    qualification: dict[str, Any] = {}


class AttachmentRequest(BaseModel):
    project_key: str
    file_path: str
    file_name: str
    file_type: str
    source: str = "console_upload"
    purpose: str = "supporting_context"
    package_id: str = ""
    request_id: str = ""


class BillingUnblockRequest(BaseModel):
    customer_id: str
    reason: str = "manual_operator_override"


@app.get("/overview")
def overview(_auth: None = Depends(_require_token)) -> dict[str, Any]:
    return _ok(build_studio_snapshot())


@app.get("/project/{project_key}")
def project(project_key: str, _auth: None = Depends(_require_token)) -> dict[str, Any]:
    return build_project_snapshot(project_key)


@app.get("/package/{package_id}")
def package(
    package_id: str,
    project_key: str = "",
    _auth: None = Depends(_require_token),
) -> dict[str, Any]:
    return build_package_snapshot(package_id, project_key=project_key or None)


@app.get("/client-view")
def client_view(project_key: str = "", _auth: None = Depends(_require_token)) -> dict[str, Any]:
    return build_client_view_snapshot(project_key or None)


@app.post("/control")
def control(req: ControlRequest, _auth: None = Depends(_require_token)) -> dict[str, Any]:
    return execute_control_action(
        action=req.action,
        project_key=req.project_key or None,
        confirmed=bool(req.confirmed),
        confirmation_text=req.confirmation_text,
    )


@app.post("/intake-preview")
def intake_preview(
    req: IntakePreviewRequest,
    _auth: None = Depends(_require_token),
) -> dict[str, Any]:
    return build_intake_preview(
        request_kind=req.request_kind,
        project_key=req.project_key,
        objective=req.objective,
        project_context=req.project_context,
        constraints_json=json.dumps(req.constraints),
        requested_artifacts_json=json.dumps(req.requested_artifacts),
        linked_attachment_ids_json=json.dumps(req.linked_attachment_ids),
        autonomy_mode=req.autonomy_mode,
        lead_intake_json=json.dumps(req.lead_intake),
        qualification_json=json.dumps(req.qualification),
    )


@app.post("/attachment")
def attachment(req: AttachmentRequest, _auth: None = Depends(_require_token)) -> dict[str, Any]:
    return upload_attachment(
        project_key=req.project_key,
        file_path=req.file_path,
        file_name=req.file_name,
        file_type=req.file_type,
        source=req.source,
        purpose=req.purpose,
        package_id=req.package_id,
        request_id=req.request_id,
    )


@app.post("/attachment-upload")
async def attachment_upload(
    project_key: str = Form(...),
    source: str = Form("console_upload"),
    purpose: str = Form("supporting_context"),
    package_id: str = Form(""),
    request_id: str = Form(""),
    file: UploadFile = File(...),
    _auth: None = Depends(_require_token),
) -> dict[str, Any]:
    suffix = ""
    if file.filename and "." in file.filename:
        suffix = file.filename[file.filename.rfind(".") :]
    tmp_path = ""
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix or ".bin") as tmp:
            file_bytes = await file.read()
            tmp.write(file_bytes)
            tmp_path = tmp.name
        return upload_attachment(
            project_key=project_key,
            file_path=tmp_path,
            file_name=file.filename or "upload",
            file_type=file.content_type or "application/octet-stream",
            source=source,
            purpose=purpose,
            package_id=package_id,
            request_id=request_id,
        )
    finally:
        try:
            if tmp_path and os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass


@app.post("/webhooks/stripe")
async def stripe_webhook(request: Request) -> dict[str, Any]:
    webhook_secret = str(os.getenv("STRIPE_WEBHOOK_SECRET") or "").strip()
    if not webhook_secret:
        raise HTTPException(status_code=503, detail="STRIPE_WEBHOOK_SECRET not configured.")
    try:
        import stripe as stripe_sdk  # type: ignore
    except Exception:
        raise HTTPException(status_code=503, detail="Stripe SDK is unavailable.")

    signature = request.headers.get("stripe-signature", "")
    payload = await request.body()
    try:
        event = stripe_sdk.Webhook.construct_event(payload, signature, webhook_secret)  # type: ignore[attr-defined]
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid webhook signature.")
    try:
        from NEXUS.billing_engine import dispatch_webhook_event

        dispatch_result = dispatch_webhook_event(
            str(event.get("type") or ""),
            dict(event.get("data") or {}),
        )
    except Exception:
        dispatch_result = {"status": "dispatch_error"}
    return {
        "received": True,
        "type": str(event.get("type") or ""),
        "dispatch": dispatch_result,
    }


@app.post("/billing/unblock-customer")
def billing_unblock(req: BillingUnblockRequest, _auth: None = Depends(_require_token)) -> dict[str, Any]:
    from NEXUS.billing_engine import _unmark_customer_blocked

    return _ok(_unmark_customer_blocked(req.customer_id, reason=req.reason))


@app.get("/billing/blocked-customers")
def billing_blocked_customers(_auth: None = Depends(_require_token)) -> dict[str, Any]:
    from NEXUS.billing_engine import _read_blocked_customers

    return _ok(_read_blocked_customers())


@app.get("/health")
def health() -> dict[str, Any]:
    return _ok({"service": "forge_api", "status": "ok"})
