from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.application.transcribe import TranscribeAudioUseCase
from app.domain.exceptions import (
    AudioTooLargeError,
    AudioValidationError,
    ModelUnavailableError,
    SpeechToTextError,
    TranscriptionFailedError,
    UnsupportedAudioFormatError,
)
from app.domain.models import AudioPayload, Transcript

logger = logging.getLogger(__name__)

router = APIRouter()

_STATUS_BY_CODE: dict[str, int] = {
    AudioValidationError.code: 422,
    AudioTooLargeError.code: 413,
    UnsupportedAudioFormatError.code: 415,
    ModelUnavailableError.code: 503,
    TranscriptionFailedError.code: 502,
}

class TranscriptResponse(BaseModel):

    text: str = Field(description="Распознанный текст")
    language: str | None = Field(default=None, description="Определённый язык")
    duration_seconds: float | None = Field(default=None, description="Длительность аудио, с")
    processing_seconds: float = Field(default=0.0, description="Сколько заняла обработка, с")
    model: str = Field(default="", description="Идентификатор модели")

    @classmethod
    def from_domain(cls, transcript: Transcript) -> TranscriptResponse:
        return cls(
            text=transcript.text,
            language=transcript.language,
            duration_seconds=transcript.duration_seconds,
            processing_seconds=transcript.processing_seconds,
            model=transcript.model,
        )

class HealthResponse(BaseModel):

    status: str
    model: str
    model_loaded: bool

def get_use_case(request: Request) -> TranscribeAudioUseCase:
    return request.app.state.use_case

UseCaseDep = Annotated[TranscribeAudioUseCase, Depends(get_use_case)]

@router.get("/health", response_model=HealthResponse, tags=["service"], summary="Состояние сервиса")
async def health(request: Request) -> HealthResponse:
    transcriber = request.app.state.transcriber
    return HealthResponse(status="ok", model=transcriber.model_id, model_loaded=transcriber.is_loaded)

@router.post(
    "/transcribe",
    response_model=TranscriptResponse,
    tags=["recognition"],
    summary="Распознать аудиофайл",
    description="Принимает файл в любом формате, который понимает ffmpeg, и возвращает текст.",
    responses={
        413: {"description": "Файл больше лимита"},
        415: {"description": "Формат аудио не поддерживается"},
        422: {"description": "Пустой файл или превышен таймаут конвертации"},
        502: {"description": "Ошибка распознавания"},
        503: {"description": "Модель недоступна"},
    },
)

async def transcribe(
    use_case: UseCaseDep,
    file: Annotated[UploadFile, File(description="Аудиофайл: ogg, opus, mp3, wav, webm, m4a, flac…")],
) -> TranscriptResponse:
    content = await file.read()
    payload = AudioPayload(
        content=content,
        filename=file.filename or "",
        content_type=file.content_type or "",
    )
    transcript = await use_case.execute(payload)
    return TranscriptResponse.from_domain(transcript)

async def handle_speech_error(request: Request, exc: SpeechToTextError) -> JSONResponse:
    status_code = _STATUS_BY_CODE.get(exc.code, 500)
    logger.warning("Ошибка %s: %s", exc.code, exc.message)
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
            }
        },
    )