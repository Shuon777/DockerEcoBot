
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from app.domain.models import NormalizedAudio, Transcript


class IAudioNormalizer(ABC):
    # Приводит любой входной файл к формату, который понимает модель

    @abstractmethod
    async def normalize(self, source_path: Path, destination_path: Path) -> NormalizedAudio:
        # Конвертирует файл в WAV и возвращает результат с длительностью

        """
        Raises:
            UnsupportedAudioFormatError: Файл не декодируется.
            AudioValidationError: Конвертация не уложилась в таймаут.
        """


class ITranscriber(ABC):
    # Движок распознавания речи

    @property
    @abstractmethod
    def model_id(self) -> str:
        """Идентификатор модели"""

    @property
    @abstractmethod
    def is_loaded(self) -> bool:
        """Загружена ли модель в память"""

    @abstractmethod
    async def transcribe(self, audio: NormalizedAudio) -> Transcript:
        # Распознаёт аудио и возвращает текст.

        """
        Raises:
            TranscriptionFailedError: Движок вернул ошибку
            ModelUnavailableError: Модель не загрузилась
        """

    @abstractmethod
    async def shutdown(self) -> None:
        """Освобождает ресурсы при остановке сервиса"""
