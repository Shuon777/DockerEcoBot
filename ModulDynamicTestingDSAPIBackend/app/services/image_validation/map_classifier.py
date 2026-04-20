import httpx
from io import BytesIO
from PIL import Image
from transformers import pipeline
from typing import Dict, Any


class MapClassifier:
    """
    Улучшенный сервис на базе CLIP для определения типа изображения.
    CLIP понимает концепцию 'карты' без привязки к жестким ID ImageNet.
    """
    _instance = None

    def __init__(self, local_path: str = "./local_models/map_clip"):
        print("⏳ Загрузка локальной модели CLIP...")
        # Загрузка из локальной папки
        self.classifier = pipeline("zero-shot-image-classification", model=local_path)

    # def __new__(cls):
    #     if cls._instance is None:
    #         cls._instance = super(MapClassifier, cls).__new__(cls)
    #         print("⏳ Загрузка модели CLIP для классификации (Zero-shot)...")
    #         # Эта модель сопоставляет изображение с любым текстовым описанием
    #         cls._instance.classifier = pipeline(
    #             "zero-shot-image-classification",
    #             model="openai/clip-vit-base-patch32"
    #         )
    #     return cls._instance

    async def is_it_a_map(self, url: str) -> Dict[str, Any]:
        """Проверяет, является ли изображение по ссылке картой или схемой."""
        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                res = await client.get(url)
                img = Image.open(BytesIO(res.content)).convert("RGB")

                # Задаем метки для сравнения
                candidate_labels = ["a map or atlas", "a geographic schematic", "a photograph of nature", "a person",
                                    "an animal"]

                # CLIP сравнивает картинку с этими фразами
                results = self.classifier(img, candidate_labels=candidate_labels)

                # Получаем самую вероятную метку
                top_result = results[0]
                label = top_result['label']
                score = top_result['score']

                is_map = label in ["a map or atlas", "a geographic schematic"] and score > 0.4

                return {
                    "test_name": "is_map_detection_clip",
                    "is_passed": is_map,
                    "top_prediction": label,
                    "confidence": round(score, 4),
                    "details": "Изображение идентифицировано как карта" if is_map else f"Это больше похоже на {label}"
                }
            except Exception as e:
                return {"is_passed": False, "details": f"Ошибка анализа: {e}"}