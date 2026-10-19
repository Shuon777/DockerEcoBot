
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_WORD_SEPARATOR = re.compile(r"[,;\n]+") # для деления слов в словаре

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix = "STT_",
        env_file = ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "STT"

    # Настройки модели
    model_size: str = "small"
    device: str = "cpu" #Cuda, если есть видеокарта
    compute_type: str = "int8"
    cpu_threads: int = 0
    model_cache_dir : Path = Path("/models/whisper")
    language: str = "ru"

    # Словарь
    words: str = ""
    words_file: Path | None = None
    # Настройки приёма файлов
    max_upload_mb: int = 25 # максимальный размер файла в МБ

    # Логирование
    log_level: str = "INFO"

    @property
    def words_prompt(self) -> str | None:
        raw = self._words_source()
        items = [item.strip() for item in _WORD_SEPARATOR.split(raw) if item.strip()]
        return ", ".join(items) or None

    def _words_source(self) -> str:
        if self.words_file is None:
            return self.words
        try:
            return self.words_file.read_text(encoding="utf-8-sig")
        except OSError as exc:
            return self.words

    @property
    def max_upload_bytes(self) -> int:
        # Переводит мегобайты в байты
        return self.max_upload_mb * 1024 * 1024

@lru_cache
# Кэширует заданные настройки
def get_settings() -> Settings:
    return Settings()