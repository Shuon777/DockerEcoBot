"""Zero-shot детекторы: ищут на фото объекты по текстовым промптам значений признака.
Значение, по которому найден бокс с наибольшим score, — ответ модели.
Если ни одного бокса выше порога — модель воздерживается (value=None)."""
from typing import Dict, Optional

from PIL import Image

from app.executors.base import Executor, Prediction
from app.features import FeatureSpec


def _best_value(scores: Dict[str, float]) -> Prediction:
    if not scores:
        return Prediction(note="нет детекций выше порога")
    value = max(scores, key=scores.get)
    return Prediction(value=value, confidence=scores[value])


class GroundingDinoExecutor(Executor):
    id = "grounding_dino"
    title = "Grounding DINO tiny"
    kind = "zero-shot детекция"

    def load(self) -> None:
        import torch
        from transformers import AutoModelForZeroShotObjectDetection, AutoProcessor

        self.torch = torch
        path = self.settings.model_path("grounding_dino")
        self.processor = AutoProcessor.from_pretrained(path)
        self.model = AutoModelForZeroShotObjectDetection.from_pretrained(path).to(self.device).eval()

    def _post_process(self, outputs, inputs, image: Image.Image):
        kwargs = dict(text_threshold=0.2, target_sizes=[image.size[::-1]])
        thr = self.settings.detection_threshold
        try:  # transformers >= 4.51
            return self.processor.post_process_grounded_object_detection(
                outputs, inputs.input_ids, threshold=thr, **kwargs)[0]
        except TypeError:  # старые версии
            return self.processor.post_process_grounded_object_detection(
                outputs, inputs.input_ids, box_threshold=thr, **kwargs)[0]

    @staticmethod
    def _match(label: str, feature: FeatureSpec) -> Optional[str]:
        """DINO возвращает кусок текста промпта — сопоставляем его со значением признака."""
        label = label.strip().lower()
        if not label:
            return None
        best, best_len = None, 0
        for value, prompt in feature.values.items():
            p = prompt.lower()
            if label == p:
                return value
            if (label in p or p in label) and len(p) > best_len:
                best, best_len = value, len(p)
        return best

    def predict(self, image: Image.Image, feature: FeatureSpec) -> Prediction:
        text = " . ".join(p.lower() for p in feature.prompts) + " ."
        inputs = self.processor(images=image, text=text, return_tensors="pt").to(self.device)
        with self.torch.no_grad():
            outputs = self.model(**inputs)
        result = self._post_process(outputs, inputs, image)
        labels = result.get("text_labels") or result.get("labels") or []
        scores: Dict[str, float] = {}
        for label, score in zip(labels, result["scores"].tolist()):
            value = self._match(str(label), feature)
            if value is not None:
                scores[value] = max(scores.get(value, 0.0), float(score))
        return _best_value(scores)


class Owlv2Executor(Executor):
    id = "owlv2"
    title = "OWLv2 base"
    kind = "zero-shot детекция"

    def load(self) -> None:
        import torch
        from transformers import Owlv2ForObjectDetection, Owlv2Processor

        self.torch = torch
        path = self.settings.model_path("owlv2")
        self.processor = Owlv2Processor.from_pretrained(path)
        self.model = Owlv2ForObjectDetection.from_pretrained(path).to(self.device).eval()

    def _post_process(self, outputs, image: Image.Image):
        # OWLv2 паддит картинку до квадрата; для score размеры не важны, для боксов — да
        side = max(image.size)
        target = self.torch.tensor([[side, side]], device=self.device)
        thr = self.settings.detection_threshold
        fn = getattr(self.processor, "post_process_grounded_object_detection", None) \
            or self.processor.post_process_object_detection
        return fn(outputs=outputs, threshold=thr, target_sizes=target)[0]

    def predict(self, image: Image.Image, feature: FeatureSpec) -> Prediction:
        prompts = feature.prompts
        inputs = self.processor(text=[prompts], images=image, return_tensors="pt").to(self.device)
        with self.torch.no_grad():
            outputs = self.model(**inputs)
        result = self._post_process(outputs, image)
        scores: Dict[str, float] = {}
        for label_idx, score in zip(result["labels"].tolist(), result["scores"].tolist()):
            if 0 <= label_idx < len(prompts):
                value = feature.value_names[label_idx]
                scores[value] = max(scores.get(value, 0.0), float(score))
        return _best_value(scores)
