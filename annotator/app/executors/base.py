"""Интерфейс модели-исполнителя.

Чтобы подключить новую модель:
1. Создать класс-наследник Executor в этой папке, реализовать load() и predict()
   (или predict_many(), если модель умеет отвечать на все признаки за один вызов — как LLM).
2. Зарегистрировать его в registry.py.
3. Добавить id в ANNOTATOR_EXECUTORS и вес в EXECUTOR_WEIGHTS.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

from PIL import Image

from app.features import FeatureSpec


@dataclass
class Prediction:
    value: Optional[str] = None          # одно из FeatureSpec.values или None (модель воздержалась)
    confidence: Optional[float] = None   # 0..1; None — модель не даёт вероятность (LLM)
    note: Optional[str] = None           # пояснение: «сомнительно», «нет детекций»…
    error: Optional[str] = None          # модель упала на этом признаке

    def to_dict(self) -> dict:
        return {
            "value": self.value,
            "confidence": None if self.confidence is None else round(float(self.confidence), 4),
            "note": self.note,
            "error": self.error,
        }


ProgressCallback = Callable[[int], None]  # сколько признаков обработано этим вызовом


class Executor(ABC):
    id: str = "base"
    title: str = "Base"
    kind: str = "zero-shot"   # для отображения в UI
    # Универсальная модель (CLIP и т.п.) берёт любой признак без явного списка executors.
    # Специализированная (PhenoVision) — только признаки, где она указана явно.
    universal: bool = True

    def __init__(self, settings):
        self.settings = settings
        self.device = settings.resolve_device()

    @abstractmethod
    def load(self) -> None:
        """Загрузить веса. Вызывается один раз при старте сервиса."""

    def supports(self, feature: FeatureSpec) -> bool:
        if feature.executors is not None:
            return self.id in feature.executors
        return self.universal

    @abstractmethod
    def predict(self, image: Image.Image, feature: FeatureSpec) -> Prediction:
        """Ответ по одному признаку."""

    def predict_many(
        self,
        image: Image.Image,
        features: List[FeatureSpec],
        on_progress: Optional[ProgressCallback] = None,
    ) -> Dict[str, Prediction]:
        """По умолчанию — цикл по признакам. Ошибка на одном признаке не валит остальные."""
        self.prepare_image(image)
        out: Dict[str, Prediction] = {}
        try:
            for feature in features:
                try:
                    out[feature.name] = self.predict(image, feature)
                except Exception as exc:  # noqa: BLE001 — модель не должна ронять задачу
                    out[feature.name] = Prediction(error=f"{type(exc).__name__}: {exc}")
                if on_progress:
                    on_progress(1)
        finally:
            self.release_image()
        return out

    # Хуки для кэширования эмбеддинга картинки между признаками (см. CLIP)
    def prepare_image(self, image: Image.Image) -> None:
        pass

    def release_image(self) -> None:
        pass

    def describe(self) -> dict:
        return {"id": self.id, "title": self.title, "kind": self.kind,
                "weight": self.settings.weight(self.id)}
