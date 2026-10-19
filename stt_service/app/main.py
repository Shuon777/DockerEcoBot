from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import __version__
from app.adapters.api import handle_speech_error, router
from app.application.transcribe import TranscribeAudioUseCase
from app.config import Settings, get_settings
from app.domain.exceptions import SpeechToTextError
from app.domain.ports import IAudioNormalizer, ITranscriber
from app.infrastructure.ffmpeg import FfmpegAudioNormalizer
from app.infrastructure.whisper import WhisperTranscriber

logger = logging.getLogger(__name__)

def configure_logging(level: str) -> None:
    logging.basicConfig(
        level = getattr(logging, level.upper(), logging.INFO),
        format = "%(asctime)s %(levelname)s %(name)s: %(message)s",
        force = True,
    )

def create_app(
        settings: Settings | None = None,
        *,
        transcriber: ITranscriber | None = None,
        normalizer: IAudioNormalizer | None = None,
) -> FastAPI:
    """
    Сборка приложения
    Аргументы:
        settings: Настройки по умолчанию из окружения
        transcriber: Движок распознавания (по умолчанию whisper)
        normalizer: Нормализатор аудио (по умолчанию ffmpeg)
    """
    resolved = settings or get_settings() # Настройки по умолчанию или особенные

    @asynccontextmanager # перед запуском
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        configure_logging(resolved.log_level)
        engine = transcriber or WhisperTranscriber(resolved)
        app.state.transcriber = engine # сохраняет модель в состоянии

        app.state.use_case = TranscribeAudioUseCase(
            # базовый сценарий: движок, нормалайзер, максимальный размер файла
            engine,
            normalizer or FfmpegAudioNormalizer(),
            max_upload_bytes=resolved.max_upload_bytes,
        )

        logger.info(
            "STT-сервис запущен: модель=%s язык=%s словарь=%s лимит=%d МБ",
            engine.model_id,
            resolved.language or "авто",
            resolved.words_prompt or "нет",
            resolved.max_upload_mb,
        )

        try:
            yield
        finally:
            await engine.shutdown()
            logger.info("STT-сервис остановлен")

    application = FastAPI(
        title=resolved.app_name,
        version=__version__,
        lifespan=lifespan,
    )

    application.add_exception_handler(SpeechToTextError, handle_speech_error) # Специальный обработчик ошибок
    application.include_router(router) # Маршруты
    return application

app = create_app()