# Forge Operator Runbook

## Prerequisites
- Python 3.11+
- Node 20+
- Copy `.env.example` to `.env` and set values

## Start the Python API

```bash
cd /path/to/fhi
PYTHONPATH=. uvicorn ops.forge_api_server:app --reload --port 8000
```

## Start the Forge Console

```bash
cd projects/forge_console
npm run dev
```

## Environment Variables
- `FORGE_API_URL` - URL the Next.js server calls for Forge API (default `http://localhost:8000`)
- `FORGE_CORS_ORIGINS` - Comma-separated allowed origins for FastAPI CORS (default localhost values)
- `FORGE_CONSOLE_TOKEN` - Shared secret required by both Next middleware and FastAPI server
- `OPENAI_API_KEY` - Required for AI operations
- `FORGE_ROOT` and `AI_STUDIO_ROOT` - Optional root overrides for local studio/runtime paths
- `STRIPE_SECRET_KEY` and `STRIPE_METER_ITEM_ID` - Optional billing settings
- `STRIPE_CUSTOMER_ITEMS` - Per-customer subscription item map (`cus_x:si_y,cus_a:si_b`)
- `STRIPE_WEBHOOK_SECRET` - Required for Stripe webhook signature verification
- `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` - Required for Telegram operator alert routing
- `PUSHOVER_USER_KEY` and `PUSHOVER_APP_TOKEN` - Optional Pushover fallback for high/critical alerts

## Auth Flow
Both Next.js middleware (`/api/forge/*`) and FastAPI enforce `x-forge-token` against `FORGE_CONSOLE_TOKEN`.
Use the same token value in both process environments.

## Billing Management

### List blocked customers
`GET /billing/blocked-customers` (requires `x-forge-token` header).

### Unblock a customer manually
`POST /billing/unblock-customer`

`Content-Type: application/json`

`{"customer_id":"cus_xxx","reason":"payment_resolved_manually"}`

### When is a customer blocked?
On receipt of `invoice.payment_failed` and `customer.subscription.deleted`.

### When is a customer automatically unblocked?
On receipt of `invoice.payment_succeeded`, `customer.subscription.updated` (when `status=active`), and `customer.subscription.created` (when `status=active`).

### Notification channel health
Confirm `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` are configured. Billing alerts route through `NEXUS/notification_router.py` once the notification router branch is merged.
