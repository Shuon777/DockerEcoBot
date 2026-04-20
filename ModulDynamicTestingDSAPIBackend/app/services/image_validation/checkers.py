import httpx
import re
import json
from io import BytesIO
from PIL import Image
from typing import List, Dict, Any


class ImageChecker:
    """Обновленный сервис для поиска и валидации изображений и гео-ссылок."""

    # Регулярки для гео-платформ
    GEO_PATTERNS = {
        "2GIS": re.compile(r'2gis\.ru|doublegis\.com'),
        "GoogleMaps": re.compile(r'google\.com/maps|goo\.gl/maps'),
        "YandexMaps": re.compile(r'yandex\.ru/maps|yandex\.net/maps')
    }

    # Расширения изображений
    IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.webp', '.gif')

    @classmethod
    def extract_image_urls(cls, data: Any) -> List[str]:
        """
        Рекурсивно извлекает все ссылки на изображения из любой структуры данных.
        """
        urls = []

        if isinstance(data, str):
            # Базовый случай: если это строка, проверяем, является ли она ссылкой на картинку
            clean_url = data.split('?')[0].lower()  # Убираем query-параметры для проверки расширения
            if data.startswith('http') and clean_url.endswith(cls.IMAGE_EXTENSIONS):
                urls.append(data)

        elif isinstance(data, dict):
            # Если словарь, рекурсивно проверяем все значения
            for value in data.values():
                urls.extend(cls.extract_image_urls(value))

        elif isinstance(data, list):
            # Если список, рекурсивно проверяем все элементы
            for item in data:
                urls.extend(cls.extract_image_urls(item))

        return list(set(urls))  # Возвращаем только уникальные ссылки

    @classmethod
    async def check_geo_links(cls, data: Any) -> List[Dict[str, Any]]:
        """
        Ищет гео-ссылки во всей структуре JSON и проверяет их валидность.
        """
        # 1. Превращаем весь JSON в строку для быстрого поиска всех URL
        json_str = json.dumps(data, ensure_ascii=False)
        all_urls = re.findall(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+',
                              json_str)

        found_links = []
        async with httpx.AsyncClient(timeout=5.0) as client:
            for url in all_urls:
                provider = "Unknown"
                for name, pattern in cls.GEO_PATTERNS.items():
                    if pattern.search(url):
                        provider = name
                        break

                if provider != "Unknown":
                    try:
                        # Используем GET вместо HEAD, так как некоторые карты блокируют HEAD запросы
                        res = await client.get(url, follow_redirects=True)
                        found_links.append({
                            "url": url,
                            "provider": provider,
                            "is_valid": res.status_code == 200,
                            "status_code": res.status_code
                        })
                    except Exception as e:
                        found_links.append({
                            "url": url,
                            "provider": provider,
                            "is_valid": False,
                            "error": str(e)
                        })

        return found_links

    @staticmethod
    async def validate_url_and_size(url: str, min_size: int = 100) -> Dict[str, Any]:
        """Проверяет доступность URL и физические размеры картинки."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                response = await client.get(url)
                if response.status_code != 200:
                    return {"is_valid": False, "error": f"Status {response.status_code}"}

                img = Image.open(BytesIO(response.content))
                width, height = img.size

                return {
                    "is_valid": True,
                    "width": width,
                    "height": height,
                    "format": img.format,
                    "is_not_tiny": width >= min_size and height >= min_size
                }
            except Exception as e:
                return {"is_valid": False, "error": str(e)}