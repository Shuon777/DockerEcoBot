from typing import Dict, Any
from .base import BaseValidator


class MapValidator(BaseValidator):
    def __init__(self, img_checker, map_classifier, map_semantic, text_checker):
        self.img_checker = img_checker
        self.classifier = map_classifier
        self.semantic = map_semantic
        self.text_checker = text_checker

    async def validate(self, template: str, query: str, bot_res: Dict[str, Any], mode: str) -> Dict[str, Any]:
        # Поиск ссылок на гео-платформы (2ГИС, Яндекс, Google)
        static_map_url = str(bot_res.get("static_map", ""))
        geo_links = await self.img_checker.check_geo_links(static_map_url or str(bot_res))


        results = {
            "Шаблон": template,
            "Сгенерированный вопрос": query,
            "Работоспособность ГИС-ссылок": self._format_status(
                len(geo_links) > 0 and all(g["is_valid"] for g in geo_links), "Ок", "Битая или отсутствует"),
            "Тип картографического сервиса": geo_links[0]["provider"] if geo_links else "Не определен",
            "Визуальная валидация карты": "N/A",
            "Гео-контекстное соответствие (LLM)": "N/A"
        }

        # Визуальная проверка картинки карты нейросетью CLIP
        img_urls = self.img_checker.extract_image_urls(bot_res)
        if img_urls:
            url = img_urls[0]
            valid_res = await self.img_checker.validate_url_and_size(url)

            if valid_res["is_valid"]:
                # Проверяем нейросетью CLIP, действительно ли это карта
                m_res = await self.classifier.is_it_a_map(url)
                results["Визуальная валидация карты"] = self._format_status(
                    m_res["is_passed"], "Подтверждено (Карта)", f"Это не карта ({m_res['top_prediction']})"
                )

                # Проверка карты через LLM
                if mode != 'no llm':
                    text_content = str(bot_res.get("content", ""))
                    map_res = await self.semantic.validate_map_context(query, text_content, url)
                    results["Гео-контекстное соответствие (LLM)"] = self._format_status(
                        map_res.get("is_passed"), "Соответствует", map_res.get("reasoning")
                    )
            else:
                results["Визуальная валидация карты"] = "Пропуск (Ссылка битая)"
                results["Гео-контекстное соответствие (LLM)"] = "Пропуск (Ссылка битая)"

        return results