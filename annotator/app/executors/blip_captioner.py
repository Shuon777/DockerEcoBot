"""BLIP: короткая подпись к фото на английском. В голосовании не участвует."""
from PIL import Image


class BlipCaptioner:
    id = "blip"

    def __init__(self, settings):
        self.settings = settings
        self.device = settings.resolve_device()

    def load(self) -> None:
        import torch
        from transformers import BlipForConditionalGeneration, BlipProcessor

        self.torch = torch
        path = self.settings.model_path("blip")
        self.processor = BlipProcessor.from_pretrained(path)
        self.model = BlipForConditionalGeneration.from_pretrained(path).to(self.device).eval()

    def caption(self, image: Image.Image) -> str:
        inputs = self.processor(image, return_tensors="pt").to(self.device)
        with self.torch.no_grad():
            out = self.model.generate(**inputs, max_new_tokens=30, num_beams=3,
                                      no_repeat_ngram_size=2, repetition_penalty=1.3)
        return self.processor.decode(out[0], skip_special_tokens=True)
