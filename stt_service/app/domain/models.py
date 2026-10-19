"""Данные, которыми обмениваются слои."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class AudioPayload:
    # Файл от пользователя

    content: bytes
    filename: str
    content_type: str

    @property
    def size_bytes(self) -> int:
        return len(self.content)


@dataclass(frozen=True, slots=True)
class NormalizedAudio:
    # Нормализованное аудио

    path: Path
    duration_seconds: float | None = None


@dataclass(frozen=True, slots=True)
class Transcript:
    # Результат распознавания

    text: str
    language: str | None = None
    duration_seconds: float | None = None
    processing_seconds: float = 0.0
    model: str = ""
