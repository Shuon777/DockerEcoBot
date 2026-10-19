# Типы ошибок

from __future__ import annotations

from typing import Any


class SpeechToTextError(Exception):
    # Базовая ошибка

    code = "speech_to_text_error"

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class AudioValidationError(SpeechToTextError):
    # Файл не принят: пустой или не удалось конвертировать за отведённое время

    code = "audio_validation_error"


class AudioTooLargeError(SpeechToTextError):
    # Файл слишком большой

    code = "audio_too_large"


class UnsupportedAudioFormatError(SpeechToTextError):
    # ffmpeg не смог декодировать файл

    code = "unsupported_audio_format"


class ModelUnavailableError(SpeechToTextError):
    # Модель не загрузилась

    code = "model_unavailable"


class TranscriptionFailedError(SpeechToTextError):
    # Движок вернул ошибку во время распознавания

    code = "transcription_failed"
