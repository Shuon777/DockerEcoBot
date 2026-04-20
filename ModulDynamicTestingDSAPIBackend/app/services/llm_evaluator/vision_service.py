import httpx
import base64
import json
from io import BytesIO
from PIL import Image
from typing import Dict, Any
from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage
from app.core.config import settings


class VisionLL_Service:
    def __init__(self):
        self.llm = ChatOllama(
            model=settings.REMOTE_VL_MODEL,
            temperature=0,
            base_url=settings.REMOTE_OLLAMA_URL,
            # ВАЖНО: Убираем format="json" для Vision, так как некоторые
            # версии Ollama VL конфликтуют с жестким JSON-режимом
            num_ctx=10000,
        )

    async def _get_image_base64(self, url: str) -> str:
        """
        Скачивает изображение с защитой от пустых ответов и блокировок.
        """
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

        async with httpx.AsyncClient(timeout=20.0, headers=headers, follow_redirects=True) as client:
            try:
                response = await client.get(url)

                # Проверяем статус ответа
                if response.status_code != 200:
                    raise Exception(f"Ошибка загрузки: статус {response.status_code}")

                # Проверяем, что нам прислали именно картинку, а не HTML
                content_type = response.headers.get("content-type", "").lower()
                if "text/html" in content_type or response.content.startswith(b"<!DOCTYPE"):
                    raise Exception("URL ведет на HTML-страницу, а не на изображение")

                # Пытаемся открыть изображение
                try:
                    img = Image.open(BytesIO(response.content))

                    # Принудительная конвертация в RGB (убирает прозрачность и экзотические форматы)
                    if img.mode in ("RGBA", "P"):
                        img = img.convert("RGB")
                    elif img.mode != "RGB":
                        img = img.convert("RGB")

                    # Сохраняем в буфер как стандартный JPEG
                    buffered = BytesIO()
                    img.save(buffered, format="JPEG", quality=85)

                    return base64.b64encode(buffered.getvalue()).decode("utf-8")

                except Exception as e:
                    # Для отладки запишем первые 100 байт ответа)
                    raise Exception(f"Некорректный формат изображения: {str(e)}")

            except httpx.RequestError as e:

                raise Exception(f"Сетевая ошибка: {str(e)}")

    async def get_image_description(self, image_url: str) -> Dict[str, Any]:
        """Получает описание через чистый Base64."""
        img_b64 = await self._get_image_base64(image_url)

        # Для Ollama в LangChain передаем только саму строку base64
        message = HumanMessage(
            content=[
                {"type": "text",
                 "text": "Опиши подробно, что на фото. Верни ответ в формате JSON: {'description': '...'}"},
                {
                    "type": "image_url",
                    "image_url": {"url": img_b64}  # ПЕРЕДАЕМ ЧИСТЫЙ BASE64
                }
            ]
        )

        try:
            response = await self.llm.ainvoke([message])
            content = response.content
            # Ручной парсинг на случай, если модель добавила текст вокруг JSON
            json_start = content.find('{')
            json_end = content.rfind('}') + 1
            return json.loads(content[json_start:json_end])
        except Exception as e:
            return {"description": "Ошибка анализа", "raw": str(e)}

    async def verify_object_in_image(self, image_url: str, metadata_entity: str) -> Dict[str, Any]:
        """Проверка соответствия метаданным."""
        img_b64 = await self._get_image_base64(image_url)

        prompt = (
            f"Есть ли на фото объект '{metadata_entity}'? "
            "Ответь в JSON: {'found': bool, 'details': 'почему'}"
        )

        message = HumanMessage(
            content=[
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": img_b64}}
            ]
        )

        response = await self.llm.ainvoke([message])
        content = response.content
        try:
            json_start = content.find('{')
            json_end = content.rfind('}') + 1
            return json.loads(content[json_start:json_end])
        except:
            return {"found": False, "raw": content}