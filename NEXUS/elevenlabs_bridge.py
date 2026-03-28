"""
ElevenLabs voice generation bridge.

Voice generation only. No calling or realtime agent behavior.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any
from urllib import request


ELEVENLABS_API_BASE = "https://api.elevenlabs.io/v1"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _artifact_dir() -> Path:
    path = (Path(__file__).resolve().parent.parent / "ops" / "artifacts" / "voice").resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def elevenlabs_status() -> dict[str, Any]:
    api_key = _text(os.getenv("ELEVENLABS_API_KEY"))
    voice_id = _text(os.getenv("ELEVENLABS_VOICE_ID"))
    configured = bool(api_key and voice_id)
    return {
        "status": "ready" if configured else "not_configured",
        "configured": configured,
    }


def generate_voice_audio(text: str, voice_id: str | None = None, model_id: str | None = None) -> dict[str, Any]:
    api_key = _text(os.getenv("ELEVENLABS_API_KEY"))
    resolved_voice_id = _text(voice_id) or _text(os.getenv("ELEVENLABS_VOICE_ID"))
    resolved_model_id = _text(model_id) or _text(os.getenv("ELEVENLABS_MODEL_ID")) or "eleven_multilingual_v2"

    if not api_key or not resolved_voice_id:
        return {
            "status": "not_configured",
            "reason": "ElevenLabs key or voice is missing",
            "audio_path": "",
        }

    content = _text(text)
    if not content:
        return {
            "status": "failed",
            "reason": "text is required",
            "audio_path": "",
        }

    endpoint = f"{ELEVENLABS_API_BASE}/text-to-speech/{resolved_voice_id}"
    payload = {
        "text": content,
        "model_id": resolved_model_id,
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
    }
    headers = {
        "xi-api-key": api_key,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }
    try:
        req = request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers=headers,
        )
        with request.urlopen(req, timeout=45.0) as response:
            audio_bytes = response.read()
        output_path = _artifact_dir() / f"voice_{int(time.time())}.mp3"
        output_path.write_bytes(audio_bytes)
        return {
            "status": "ready",
            "reason": "",
            "audio_path": str(output_path),
        }
    except Exception as exc:
        return {
            "status": "failed",
            "reason": str(exc),
            "audio_path": "",
        }
