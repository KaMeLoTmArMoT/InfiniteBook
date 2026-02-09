# utils/tts/audio_store.py
from __future__ import annotations

import re
from pathlib import Path

from fastapi import HTTPException

# Providers exposed to UI/backend
TTS_PROVIDERS: tuple[str, ...] = ("piper", "xtts", "qwen", "f5")

# Per provider job state
# key = (project_id, chapter, beat_index, provider) -> "generating"|"done"|"error"
AUDIO_JOBS: dict[tuple[str, int, int, str], str] = {}

# Disk root for all projects' audio
AUDIO_ROOT = Path("data/wavs")


def norm_provider(p: str) -> str:
    p = (p or "").strip().lower()
    if not p:
        raise HTTPException(status_code=400, detail="provider is required")
    if not re.fullmatch(r"[a-z0-9_-]+", p):
        raise HTTPException(status_code=400, detail="provider has invalid characters")
    if p not in TTS_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"unknown provider: {p}")
    return p


def job_key(
    project_id: str, chapter: int, beat_index: int, provider: str
) -> tuple[str, int, int, str]:
    provider = norm_provider(provider)
    return (project_id, int(chapter), int(beat_index), provider)


def wav_path(project_id: str, provider: str, chapter: int, beat_index: int) -> Path:
    """
    data/wavs/{project_id}/audio/{provider}/ch_{chapter}/beat_{beat_index}.wav
    """
    provider = norm_provider(provider)
    chapter = int(chapter)
    beat_index = int(beat_index)

    return (
        AUDIO_ROOT
        / project_id
        / "audio"
        / provider
        / f"ch_{chapter}"
        / f"beat_{beat_index}.wav"
    )


def wav_url(project_id: str, provider: str, chapter: int, beat_index: int) -> str:
    provider = norm_provider(provider)
    return (
        f"/api/projects/{project_id}/audio/wav"
        f"?chapter={int(chapter)}&beat_index={int(beat_index)}&provider={provider}"
    )
