from typing import Dict, Any
from .base import BaseValidator


class ImageValidator(BaseValidator):
    def __init__(self, img_checker, nsfw_checker, vision_service, text_checker):
        self.img_checker = img_checker
        self.nsfw = nsfw_checker
        self.vlm = vision_service
        self.text_checker = text_checker

    async def validate(self, template: str, query: str, bot_res: Dict[str, Any], mode: str) -> Dict[str, Any]:
        # Извлекаем все ссылки на изображения из ответа
        content_to_search = str(bot_res.get("content", bot_res))
        img_urls = self.img_checker.extract_image_urls(content_to_search)

        # Значения по умолчанию (если фото нет)
        results = {
            "Шаблон": template,
            "Сгенерированный вопрос": query,
            "Наличие и полнота ответа": self._format_status(True, "Пройдено", "ПУСТО"),
            "Доступность медиа-ресурса": "Нет фото",
            "Техническое качество (Разрешение)": "N/A",
            "Визуальная цензура (NSFW)": "Пропуск (Нет фото)",
            "Визуальный анализ содержимого (LLM)": "Пропуск (Нет фото)",
            "Верификация объекта на фото (LLM)": "Пропуск (Нет фото)"
        }

        if img_urls:
            url = img_urls[0]
            # техническая проверка (Размер и доступность ссылки)
            size_res = await self.img_checker.validate_url_and_size(url)

            if size_res["is_valid"]:
                results["Доступность медиа-ресурса"] = "✅ Ссылка активна"
                results["Техническое качество (Разрешение)"] = f"{size_res.get('width')}x{size_res.get('height')}"

                # NSFW
                n_res = await self.nsfw.analyze_image_safety(url)
                results["Визуальная цензура (NSFW)"] = self._format_status(n_res["is_safe"], "Безопасно",
                                                                           "NSFW КОНТЕНТ")

                # анализ (VLM)
                if mode != 'no llm':
                    # Описание содержимого
                    v_res = await self.vlm.get_image_description(url)
                    results["Визуальный анализ содержимого (LLM)"] = v_res.get("description", "Ошибка анализа")

                    # Сверка объекта с текстом ответа
                    sync_res = await self.vlm.verify_object_in_image(url, content_to_search)
                    results["Верификация объекта на фото (LLM)"] = self._format_status(
                        sync_res.get('found'), "Объект подтвержден", f"Рассинхрон: {sync_res.get('detected_what')}"
                    )
                else:
                    results["Визуальный анализ содержимого (LLM)"] = "Выключено (No LLM)"
                    results["Верификация объекта на фото (LLM)"] = "Выключено (No LLM)"
            else:
                results["Доступность медиа-ресурса"] = f"❌ Ошибка: {size_res.get('error')}"
                results["Визуальная цензура (NSFW)"] = "Пропуск (Ссылка битая)"
                results["Визуальный анализ содержимого (LLM)"] = "Пропуск (Ссылка битая)"
                results["Верификация объекта на фото (LLM)"] = "Пропуск (Ссылка битая)"

        return results