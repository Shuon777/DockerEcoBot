from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    """
    Настройки приложения, загружаемые из переменных окружения или .env файла.
    """
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"  # Игнорировать лишние переменные в .env
    )

    # Настройки API
    PROJECT_NAME: str = "Dialogue System Testing"
    API_V1_STR: str = "/api/v1"

    # Ключ для доступа к API
    API_AUTH_TOKEN: str

    # --- Настройки тестируемого бота ---
    BOT_DOMAIN: str
    BOT_TEST_QUERY_PATH: str

    # Настройки LLM (Qwen)
    QWEN_MODEL_NAME: str = "qwen-max"

    # Настройки валидации
    DEFAULT_LANGUAGE: str = "ru"

    # Настройки Ollama
    REMOTE_OLLAMA_URL: str
    REMOTE_MODEL: str = "qwen3-next:80b-a3b-instruct-q4_K_M"
    REMOTE_MODEL_new: str = "qwen3:30b"
    REMOTE_VL_MODEL: str = "qwen3-vl:32b"  # Модель для зрения

    # Путь к папке с промптами
    PROMPTS_DIR: str = "prompts_structure"

    PATH_TEMPLATES_EXCEL: str
    PATH_OFF_LIST_EXCEL: str
    PATH_LOCAL_MODELS: str
    PATH_RESULTS_DIR: str
    PATH_LOGS_DIR: str


settings = Settings()