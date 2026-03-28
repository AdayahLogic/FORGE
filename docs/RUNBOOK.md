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
- `FORGE_CONSOLE_TOKEN` - Shared secret required by both Next middleware and FastAPI server
- `OPENAI_API_KEY` - Required for AI operations
- `STRIPE_SECRET_KEY` and `STRIPE_METER_ITEM_ID` - Optional billing settings
- `STRIPE_WEBHOOK_SECRET` - Required for Stripe webhook signature verification

## Auth Flow
Both Next.js middleware (`/api/forge/*`) and FastAPI enforce `x-forge-token` against `FORGE_CONSOLE_TOKEN`.
Use the same token value in both process environments.
