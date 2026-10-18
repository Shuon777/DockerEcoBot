"""Настройки сервиса. Всё берётся из переменных окружения (см. .env.example)."""
import os
from pathlib import Path
from typing import Dict, List, Optional

BASE_DIR = Path(__file__).resolve().parent


def _list(name: str, default: str) -> List[str]:
    return [x.strip() for x in os.getenv(name, default).split(",") if x.strip()]


def _weights(raw: str) -> Dict[str, float]:
    result = {}
    for pair in raw.split(","):
        if "=" in pair:
            key, value = pair.split("=", 1)
            result[key.strip()] = float(value)
    return result


class Settings:
    """Значения читаются из окружения в момент создания объекта (не при импорте)."""

    def __init__(self):
        env = os.getenv
        # Какие исполнители загружать при старте (порядок = порядок выполнения)
        self.executors: List[str] = _list("ANNOTATOR_EXECUTORS", "clip,grounding_dino,owlv2,phenovision")
        # Вес голоса каждой модели в итоговом вердикте
        self.weights: Dict[str, float] = _weights(env(
            "EXECUTOR_WEIGHTS", "clip=1.0,grounding_dino=0.8,owlv2=0.8,phenovision=2.0,gigachat=1.2"))
        # Ниже этого порога итог = «не определено» и в БД не пишется
        self.confidence_threshold = float(env("CONFIDENCE_THRESHOLD", "0.4"))
        # Уверенность, которую подставляем моделям без вероятностей (LLM)
        self.llm_confidence = float(env("LLM_CONFIDENCE", "0.7"))

        self.features_path = Path(env("FEATURES_PATH", str(BASE_DIR / "features.json")))
        self.models_dir = Path(env("MODELS_DIR", str(BASE_DIR.parent / "models")))
        self.device = env("DEVICE", "auto")  # auto | cuda | cpu

        # Детекторы (DINO, OWLv2): минимальный score, чтобы бокс вообще учитывался
        self.detection_threshold = float(env("DETECTION_THRESHOLD", "0.1"))
        # Подпись к фото (BLIP). Не голосует, просто текст в ответе
        self.enable_caption = env("ENABLE_CAPTION", "true").lower() == "true"

        # Безопасность и ресурсы
        self.api_token: Optional[str] = env("ANNOTATOR_API_TOKEN") or None
        self.image_base_url = env("IMAGE_BASE_URL", "")  # для относительных путей /images/...
        # Подмена префиксов ссылок: «http://localhost=http://nginx» — внутри контейнера
        # localhost указывает на сам контейнер, а картинки раздаёт nginx
        self.image_url_rewrite = [tuple(x.split("=", 1)) for x in _list("IMAGE_URL_REWRITE", "") if "=" in x]
        self.max_image_bytes = int(env("MAX_IMAGE_MB", "15")) * 1024 * 1024
        self.image_timeout_sec = float(env("IMAGE_TIMEOUT_SEC", "60"))
        self.max_queue = int(env("MAX_QUEUE", "100"))
        self.task_ttl_sec = int(env("TASK_TTL_SEC", "3600"))

        # GigaChat (платный, по умолчанию выключен — не входит в ANNOTATOR_EXECUTORS)
        self.gigachat_credentials: Optional[str] = env("GIGACHAT_CREDENTIALS") or None
        self.gigachat_scope = env("GIGACHAT_SCOPE", "GIGACHAT_API_CORP")
        self.gigachat_model = env("GIGACHAT_MODEL", "GigaChat-Pro")

    def model_path(self, name: str) -> str:
        """Путь к весам: <NAME>_PATH из окружения или MODELS_DIR/<name>."""
        return os.getenv(f"{name.upper()}_PATH", str(self.models_dir / name))

    def weight(self, executor_id: str) -> float:
        return self.weights.get(executor_id, 1.0)

    def resolve_device(self) -> str:
        if self.device != "auto":
            return self.device
        try:
            import torch
            return "cuda" if torch.cuda.is_available() else "cpu"
        except ImportError:
            return "cpu"
