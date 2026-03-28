"""Safe ElevenLabs voice artifact bridge for Forge."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib import request


def _to_text(value: Any) -> str:
    return str(value or "").strip()


def generate_voice_safe(*, text: str, voice_id: str | None = None, output_path: str | None = None, timeout_seconds: int = 25) -> dict[str, Any]:
    api_key = _to_text(os.environ.get("ELEVENLABS_API_KEY"))
    if not api_key:
        return {"status": "not_configured", "reason": "ElevenLabs not configured", "audio_path": ""}

    normalized_voice = _to_text(voice_id) or _to_text(os.environ.get("ELEVENLABS_DEFAULT_VOICE_ID")) or "JBFqnCBsd6RMkjVDRZzb"
    body = json.dumps({"text": _to_text(text)[:4000], "model_id": "eleven_multilingual_v2"}).encode("utf-8")

    req = request.Request(
        f"https://api.elevenlabs.io/v1/text-to-speech/{normalized_voice}",
        data=body,
        headers={"xi-api-key": api_key, "Content-Type": "application/json", "Accept": "audio/mpeg"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=max(5, int(timeout_seconds))) as response:
            audio = response.read()
        if not audio:
            return {"status": "failed", "reason": "Empty ElevenLabs audio response", "audio_path": ""}

        if output_path:
            target = Path(output_path).expanduser().resolve()
            target.parent.mkdir(parents=True, exist_ok=True)
        else:
            stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
            target = (Path.cwd() / "logs" / "voice" / f"forge_voice_{stamp}.mp3").resolve()
            target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(audio)
        return {"status": "ok", "audio_path": str(target), "voice_id": normalized_voice, "bytes_written": len(audio)}
    except Exception as exc:
        return {"status": "failed", "reason": f"ElevenLabs request failed: {exc}", "audio_path": ""}
