from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    """
    Настройки приложения, загружаемые из переменных окружения или .env файла.
    """
    # Настройки API
    PROJECT_NAME: str = "Dialogue System Testing"
    API_V1_STR: str = "/api/v1"

    # Ключ для доступа к API
    API_AUTH_TOKEN: str

    # Настройки LLM (Qwen)
    QWEN_API_KEY: str = "your-api-key"
    QWEN_API_BASE: str = "https://api.openai.com/v1"  # Или локальный URL
    QWEN_MODEL_NAME: str = "qwen-max"

    # Настройки валидации
    DEFAULT_LANGUAGE: str = "ru"

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True)

    # Настройки Ollama
    REMOTE_OLLAMA_URL: str = "http://host.docker.internal:11434"
    REMOTE_MODEL: str = "qwen3-next:80b-a3b-instruct-q4_K_M"
    REMOTE_MODEL_new: str = "qwen3:30b"
    REMOTE_VL_MODEL: str = "qwen3-vl:32b"  # Модель для зрения

    # Путь к папке с промптами
    PROMPTS_DIR: str = "prompts_structure"

settings = Settings()