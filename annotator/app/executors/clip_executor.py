"""CLIP ViT-B/32: zero-shot классификация — какое из значений признака лучше описывает фото."""
from typing import Dict

from PIL import Image

from app.executors.base import Executor, Prediction
from app.features import FeatureSpec


class ClipExecutor(Executor):
    id = "clip"
    title = "CLIP ViT-B/32"
    kind = "zero-shot классификация"

    def load(self) -> None:
        import torch
        from transformers import CLIPModel, CLIPProcessor

        self.torch = torch
        path = self.settings.model_path("clip")
        self.processor = CLIPProcessor.from_pretrained(path)
        self.model = CLIPModel.from_pretrained(path).to(self.device).eval()
        self._text_cache: Dict[str, "torch.Tensor"] = {}
        self._image_emb = None

    def _text_embeddings(self, feature: FeatureSpec):
        # Промпты статичны — считаем один раз на признак и держим в памяти
        if feature.name not in self._text_cache:
            inputs = self.processor(text=feature.prompts, return_tensors="pt", padding=True).to(self.device)
            with self.torch.no_grad():
                emb = self.model.get_text_features(**inputs)
            self._text_cache[feature.name] = emb / emb.norm(dim=-1, keepdim=True)
        return self._text_cache[feature.name]

    def prepare_image(self, image: Image.Image) -> None:
        # Эмбеддинг картинки один на все признаки задачи
        inputs = self.processor(images=image, return_tensors="pt").to(self.device)
        with self.torch.no_grad():
            emb = self.model.get_image_features(**inputs)
        self._image_emb = emb / emb.norm(dim=-1, keepdim=True)

    def release_image(self) -> None:
        self._image_emb = None

    def predict(self, image: Image.Image, feature: FeatureSpec) -> Prediction:
        if self._image_emb is None:
            self.prepare_image(image)
        text_emb = self._text_embeddings(feature)
        scale = self.model.logit_scale.exp()
        probs = (scale * self._image_emb @ text_emb.T).softmax(dim=-1)[0]
        idx = int(probs.argmax().item())
        return Prediction(value=feature.value_names[idx], confidence=float(probs[idx].item()))
