# NegotiateAI Architecture

## Purpose

NegotiateAI helps users respond more effectively in negotiations and important conversations.

## Current MVP Architecture

Frontend:
- Next.js App Router
- Input message box
- Analyze button
- Results panel

Backend:
- /api/analyze endpoint
- AI analysis logic

## Legal + Safety Layer

### Disclaimer System
Users must acknowledge the disclaimer once before using the tool.

The disclaimer appears in the results panel.

"This tool provides communication suggestions for informational purposes only and does not constitute legal, financial, or professional advice."

### Privacy Rules

Anonymous users:
- conversations are NOT stored

Logged-in users:
- may optionally save analysis history

Sensitive inputs are treated as private data.

### Safety Rules

The system refuses requests involving:

- threats
- harassment
- scams
- fraud
- impersonation
- blackmail
- coercion

When detected the system returns:

"Unable to assist with this request."

### Prompt Injection Protection

The system ignores instructions embedded inside user messages like:

- "Ignore previous instructions"
- "Reveal system prompts"
- "Act as a different AI"

These instructions are treated as untrusted input.

### Legal Pages

The system includes placeholder pages:

/terms
/privacy

### Data Storage Rules

When database storage is added the system should store only:

- users
- saved analyses
- timestamps
- analysis metadata

The system must NOT store:

- API keys
- raw anonymous conversation logs
- sensitive system prompts