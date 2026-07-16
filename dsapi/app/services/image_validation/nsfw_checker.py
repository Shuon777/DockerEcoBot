import httpx
from io import BytesIO
from PIL import Image
from transformers import pipeline
from typing import Dict, Any


class ImageSafetyValidator:
    """
    Современная нейронная проверка изображений на NSFW (безопасность).
    Использует библиотеку Transformers и модель ViT.
    Совместима с Python 3.12.
    """

    _instance = None

    def __init__(self, local_path: str = "./local_models/nsfw"):
        print("⏳ Загрузка локальной модели NSFW...")
        self.classifier = pipeline("image-classification", model=local_path)

    # def __new__(cls):
    #     if cls._instance is None:
    #         cls._instance = super(ImageSafetyValidator, cls).__new__(cls)
    #         try:
    #             print("⏳ Загрузка нейросети для проверки изображений (Transformers ViT)...")
    #             # Используем пайплайн для классификации изображений
    #             cls._instance.classifier = pipeline(
    #                 "image-classification",
    #                 model="Falconsai/nsfw_image_detection"
    #             )
    #             print("✅ Модель проверки картинок успешно загружена!")
    #         except Exception as e:
    #             print(f"❌ Ошибка загрузки модели картинок: {e}")
    #             cls._instance.classifier = None
    #     return cls._instance

    async def analyze_image_safety(self, url: str) -> Dict[str, Any]:
        """
        Скачивает изображение и проверяет его на наличие нежелательного контента.
        """
        if not self.classifier:
            return {"test_name": "image_safety", "is_passed": False, "details": "Модель не загружена"}

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                # Скачиваем изображение в память
                response = await client.get(url)
                if response.status_code != 200:
                    return {"is_safe": False, "details": f"Ошибка скачивания: {response.status_code}"}

                # Конвертируем байты в объект PIL Image
                img = Image.open(BytesIO(response.content)).convert("RGB")

                # Получаем предсказания
                results = self.classifier(img)

                # Модель возвращает список словарей, например:
                # [{'label': 'normal', 'score': 0.99}, {'label': 'nsfw', 'score': 0.01}]

                # Ищем метку 'nsfw'
                nsfw_score = 0.0
                normal_score = 0.0
                for res in results:
                    if res['label'] == 'nsfw':
                        nsfw_score = res['score']
                    elif res['label'] == 'normal':
                        normal_score = res['score']

                # Порог срабатывания — 0.5
                is_safe = nsfw_score < 0.5

                return {
                    "is_safe": is_safe,
                    "scores": {
                        "nsfw": round(nsfw_score, 4),
                        "normal": round(normal_score, 4)
                    },
                    "details": "Safe" if is_safe else "NSFW Content Detected"
                }

            except Exception as e:
                return {"is_safe": False, "details": f"Ошибка анализа: {str(e)}"}