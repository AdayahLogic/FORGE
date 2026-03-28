from __future__ import annotations

from pathlib import Path


def test_integration_status_surface_bounded(monkeypatch):
    from NEXUS import integration_router as router

    for key in [
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_ALLOWED_CHAT_IDS",
        "PUSHOVER_API_TOKEN",
        "PUSHOVER_USER_KEY",
        "TAVILY_API_KEY",
        "FIRECRAWL_API_KEY",
        "STRIPE_SECRET_KEY",
        "ELEVENLABS_API_KEY",
        "TWILIO_ACCOUNT_SID",
        "TWILIO_AUTH_TOKEN",
        "TWILIO_FROM_NUMBER",
    ]:
        monkeypatch.delenv(key, raising=False)

    payload = router.integration_status_safe(project_path=None)
    integrations = dict(payload.get("integrations") or {})
    assert set(integrations.keys()) == {
        "telegram",
        "pushover",
        "tavily",
        "firecrawl",
        "stripe",
        "elevenlabs",
        "twilio",
    }
    allowed = set(payload.get("allowed_statuses") or [])
    assert allowed == {"ready", "not_configured", "degraded", "failed"}
    for row in integrations.values():
        assert row.get("status") in allowed


def test_run_lead_mission_default_query(monkeypatch, tmp_path):
    from NEXUS import integration_router as router

    project_dir = tmp_path / "demo"
    (project_dir / "state").mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(router, "PROJECTS", {"demo": {"path": str(project_dir)}})

    def fake_tavily(*, query: str, max_results: int = 5):
        return {
            "status": "ok",
            "query": query,
            "leads": [
                {"name": "Alpha Clean", "website": "https://alpha.example", "snippet": "cleaning"},
                {"name": "Beta Clean", "website": "https://beta.example", "snippet": "janitorial"},
            ],
        }

    def fake_firecrawl(*, leads):
        return {"status": "ok", "enrichment_occurred": True, "leads": leads}

    stored: list[dict] = []

    def fake_inject(*, project_path, lead_payload, package_id=None):
        stored.append(dict(lead_payload))
        return {"status": "ok", "lead": {"lead_id": f"lead-{len(stored)}"}}

    monkeypatch.setattr("NEXUS.tavily_bridge.discover_leads_safe", fake_tavily)
    monkeypatch.setattr("NEXUS.firecrawl_bridge.enrich_leads_safe", fake_firecrawl)
    monkeypatch.setattr(router, "inject_manual_lead_safe", fake_inject)

    result = router.discover_leads_safe(query=None)
    assert result["status"] == "ok"
    assert result["query"] == "cleaning businesses in Baltimore"
    assert result["lead_count"] == 2
    assert result["stored_count"] == 2
    assert result["outreach_enabled"] is False
    assert result["approval_required_for_outreach"] is True


def test_notification_router_high_priority(monkeypatch):
    from NEXUS import notification_router as nr

    monkeypatch.setattr(
        "NEXUS.telegram_bridge.send_operator_message_safe",
        lambda message: {"status": "sent", "message": message},
    )
    monkeypatch.setattr(
        nr,
        "notify_operator_safe",
        lambda **kwargs: {"status": "sent", "channel": "pushover"},
    )

    result = nr.route_operator_notification_safe(
        project_path=None,
        event_type="integration_test",
        event_message="critical event",
        priority="critical",
        payload={},
    )
    assert result["status"] == "ok"
    assert result["delivery"]["telegram"]["status"] == "sent"
    assert result["delivery"]["pushover"]["status"] == "sent"


def test_payment_link_is_approval_gated():
    from NEXUS.integration_router import create_payment_link_safe

    result = create_payment_link_safe(
        amount_cents=5000,
        currency="usd",
        description="Test",
        approval_granted=False,
    )
    assert result["status"] == "approval_required"
    assert result["one_time_only"] is True
    assert result["auto_billing_enabled"] is False


def test_twilio_is_approval_gated():
    from NEXUS.integration_router import send_twilio_sms_safe

    result = send_twilio_sms_safe(
        to_number="+14155550123",
        message="hello",
        approval_granted=False,
    )
    assert result["status"] == "approval_required"
    assert result["auto_send_enabled"] is False
    assert result["auto_calling_enabled"] is False


def test_telegram_commands(monkeypatch):
    from NEXUS import telegram_bridge as tg

    monkeypatch.setattr(
        tg,
        "integration_status_safe",
        lambda: {
            "integrations": {
                "telegram": {"status": "ready", "reason": "ok"},
                "pushover": {"status": "not_configured", "reason": "missing"},
                "tavily": {"status": "ready", "reason": "ok"},
                "firecrawl": {"status": "ready", "reason": "ok"},
                "stripe": {"status": "not_configured", "reason": "missing"},
                "elevenlabs": {"status": "not_configured", "reason": "missing"},
                "twilio": {"status": "not_configured", "reason": "missing"},
            }
        },
    )
    monkeypatch.setattr(
        tg,
        "discover_leads_safe",
        lambda query: {
            "status": "ok",
            "query": query or "cleaning businesses in Baltimore",
            "lead_count": 1,
            "top_lead_names": ["Alpha Clean"],
            "enrichment_occurred": False,
        },
    )

    integration = tg.handle_telegram_command_safe(command="integration status")
    assert integration["status"] == "ok"
    assert "Integration Status" in integration["response_text"]

    mission = tg.handle_telegram_command_safe(command="run lead mission cleaning businesses baltimore")
    assert mission["status"] == "ok"
    assert "Run Lead Mission" in mission["response_text"]
    assert "cleaning businesses baltimore" in mission["response_text"]
