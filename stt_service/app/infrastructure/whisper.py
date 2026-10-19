from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from app.config import Settings
from app.domain.exceptions import ModelUnavailableError, TranscriptionFailedError
from app.domain.models import NormalizedAudio, Transcript
from app.domain.ports import ITranscriber

logger = logging.getLogger(__name__)

class WhisperTranscriber(ITranscriber):
    def __init__(self, settings: Settings, *, beam_size: int = 5) -> None:
        self._settings = settings
        self._beam_size = beam_size # чем выше, тем точее, но дольше расшифровка, 5 - стандарт
        self._model: Any | None = None
        self._lock = asyncio.Lock() # загрузка модели будет единожды

    @property
    def model_id(self) -> str:
        return self._settings.model_size

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    async def transcribe(self, audio: NormalizedAudio) -> Transcript:
        model = await self._ensure_model()
        started = time.perf_counter() # время начала распознавания
        try:
            # убирает распознавание в отдельный поток
            segments, info = await asyncio.to_thread(self._run, model, str(audio.path))
        except Exception as exc:
            logger.exception("Whisper не смог распознать аудио")
            raise TranscriptionFailedError(
                "Не удалось распознать аудио",
                details={"error": str(exc), "error_type": type(exc).__name__},
            ) from exc

        # Whisper дает распознанные сегменты, нужно обрезать пустые и соединить
        text = " ".join(part for part in (segment.text.strip() for segment in segments) if part)

        return Transcript(
            text=text,
            language=getattr(info, "language", None),
            duration_seconds=audio.duration_seconds,
            processing_seconds=round(time.perf_counter() - started, 3),
            model=self.model_id,
        )

    async def shutdown(self) -> None:
        # При остановке отпускает модель
        self._model = None

    async def _ensure_model(self) -> Any:
        if self._model is not None:
            return self._model

        async with self._lock:
            if self._model is not None:
                return self._model

            logger.info(
                "Загружаю Whisper %s (device=%s, compute_type=%s, словарь=%s)",
                self._settings.model_size,
                self._settings.device,
                self._settings.compute_type,
                self._settings.words_prompt or "нет",
            )
            try:
                self._model = await asyncio.to_thread(self._load_model)
            except Exception as exc:
                logger.exception("Модель Whisper не загрузилась")
                raise ModelUnavailableError(
                    "Не удалось загрузить модель Whisper",
                    details={
                        "model": self._settings.model_size,
                        "error": str(exc),
                        "error_type": type(exc).__name__,
                    },
                ) from exc

        logger.info("Модель Whisper %s загружена", self._settings.model_size)
        return self._model

    def _load_model(self) -> Any:
        # Загрузка модели
        from faster_whisper import WhisperModel

        self._settings.model_cache_dir.mkdir(parents=True, exist_ok=True)
        return WhisperModel(
            self._settings.model_size,
            device=self._settings.device,
            compute_type=self._settings.compute_type,
            download_root=str(self._settings.model_cache_dir),
            cpu_threads=self._settings.cpu_threads or 0,
        )
    def _run(self, model: Any, path: str) -> tuple[list[Any], Any]:
        # Запуск модели
        segments, info = model.transcribe(
            path,
            language=self._settings.language or None,
            beam_size=self._beam_size,
            vad_filter=True,
            initial_prompt=self._settings.words_prompt,
        )
        return list(segments), info