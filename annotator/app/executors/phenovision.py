"""PhenoVision (phenobase/phenovision): ViT-L, обучена на 1.5 млн фото iNaturalist
определять наличие цветков и плодов. Лицензия MIT.

Выход — 2 сигмоиды, ПОРЯДОК [fruit, flower] (index 0 = плоды, 1 = цветки) — см. карточку модели.
Пороги и «буферы неуверенности» — из карточки модели (final_buffer_params.csv):
  выше threshold + buffer_upper   -> «Да»
  ниже threshold - buffer_lower   -> «Нет»
  между                           -> модель воздерживается (equivocal)

Важно: модель presence-only. «Нет» значит «на фото не видно», а не «растение не цветёт».
"""
from PIL import Image

from app.executors.base import Executor, Prediction
from app.features import FeatureSpec

# признак -> (индекс выхода, threshold, buffer_lower, buffer_upper)
PHENO_MAP = {
    "Цветение": (1, 0.48, 0.325, 0.385),
    "Наличие плодов": (0, 0.60, 0.405, 0.305),
}


class PhenoVisionExecutor(Executor):
    id = "phenovision"
    title = "PhenoVision"
    kind = "специализированная: цветение/плоды"
    universal = False  # берёт только признаки, где указан явно

    def load(self) -> None:
        import torch
        from transformers import AutoImageProcessor, AutoModelForImageClassification

        self.torch = torch
        path = self.settings.model_path("phenovision")
        self.processor = AutoImageProcessor.from_pretrained(path)
        self.model = AutoModelForImageClassification.from_pretrained(path).to(self.device).eval()
        self._probs = None

    def supports(self, feature: FeatureSpec) -> bool:
        return feature.name in PHENO_MAP and super().supports(feature)

    def prepare_image(self, image: Image.Image) -> None:
        # Один прогон даёт оба признака сразу
        inputs = self.processor(images=image, return_tensors="pt").to(self.device)
        with self.torch.no_grad():
            logits = self.model(**inputs).logits
        self._probs = self.torch.sigmoid(logits)[0].tolist()

    def release_image(self) -> None:
        self._probs = None

    def predict(self, image: Image.Image, feature: FeatureSpec) -> Prediction:
        if self._probs is None:
            self.prepare_image(image)
        idx, thr, lower, upper = PHENO_MAP[feature.name]
        p = float(self._probs[idx])
        if p >= thr + upper:
            return Prediction(value="Да", confidence=p)
        if p <= thr - lower:
            return Prediction(value="Нет", confidence=1.0 - p,
                              note="presence-only: на фото не видно")
        return Prediction(confidence=p, note=f"сомнительно (p={p:.2f}), модель воздержалась")
