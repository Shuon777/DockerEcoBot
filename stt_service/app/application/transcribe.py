
from __future__ import annotations

import logging
import re
import tempfile
import time
from dataclasses import replace
from pathlib import Path

from app.domain.exceptions import AudioTooLargeError, AudioValidationError
from app.domain.models import AudioPayload, Transcript
from app.domain.ports import IAudioNormalizer, ITranscriber

logger = logging.getLogger(__name__)

_SAFE_SUFFIX = re.compile(r"^\.[a-z0-9]{1,5}$")

_CONTENT_TYPE_SUFFIXES = {
    "audio/ogg": ".ogg",
    "audio/opus": ".opus",
    "audio/webm": ".webm",
    "audio/mpeg": ".mp3",
    "audio/mp3": ".mp3",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/mp4": ".m4a",
    "audio/x-m4a": ".m4a",
    "audio/flac": ".flac",
    "audio/amr": ".amr",
}


class TranscribeAudioUseCase:
    # Главный сценарий превращения загруженного аудиофайла в текст

    def __init__(
        self,
        transcriber: ITranscriber,
        normalizer: IAudioNormalizer,
        *,
        max_upload_bytes: int,
    ) -> None:
        self._transcriber = transcriber
        self._normalizer = normalizer
        self._max_upload_bytes = max_upload_bytes

    async def execute(self, payload: AudioPayload) -> Transcript:
        # Распознаёт аудио и возвращает текст с таймингами
        self._validate(payload)
        started = time.perf_counter()

        # Создание временной директории для работы с файлом
        with tempfile.TemporaryDirectory(prefix="stt-simple-") as directory:
            workdir = Path(directory)
            source = workdir / f"source{self._suffix(payload)}"
            source.write_bytes(payload.content)

            normalized = await self._normalizer.normalize(source, workdir / "audio.wav")
            transcript = await self._transcriber.transcribe(normalized)

        elapsed = time.perf_counter() - started
        logger.info(
            "Распознано: %d байт → %d символов за %.2f с (модель %s)",
            payload.size_bytes,
            len(transcript.text),
            elapsed,
            transcript.model,
        )
        return replace(transcript, processing_seconds=round(elapsed, 3))

    def _validate(self, payload: AudioPayload) -> None:
        # убирает пустые и слишком большие файлы
        if payload.size_bytes == 0:
            raise AudioValidationError("Файл пустой")
        if payload.size_bytes > self._max_upload_bytes:
            raise AudioTooLargeError(
                f"Файл больше {self._max_upload_bytes // (1024 * 1024)} МБ",
                details={"size_bytes": payload.size_bytes, "limit_bytes": self._max_upload_bytes},
            )

    @staticmethod
    def _suffix(payload: AudioPayload) -> str:
        # Проверка расширения звукового файла
        suffix = Path(payload.filename or "").suffix.lower()
        if _SAFE_SUFFIX.match(suffix):
            return suffix
        content_type = (payload.content_type or "").split(";")[0].strip().lower()
        return _CONTENT_TYPE_SUFFIXES.get(content_type, ".bin")
