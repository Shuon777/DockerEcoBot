from typing import Dict, Any
from .base import BaseValidator


class TextValidator(BaseValidator):
    def __init__(self, speller, pii, neural, llm, text_checker):
        self.speller = speller
        self.pii = pii
        self.neural = neural
        self.llm = llm
        self.text_checker = text_checker

    async def validate(self, template: str, query: str, bot_res: Dict[str, Any], mode: str) -> Dict[str, Any]:
        text = bot_res.get("content", str(bot_res))


        empty_res = self.text_checker.check_not_empty(text)
        lang_res = self.text_checker.check_language(text, "ru")
        res_encode = self.text_checker.check_encoding_and_markup(text)


        spell = self.speller.check_spelling(text)
        pii_res = self.pii.check_pii_and_fio(text)
        tox = self.neural.analyze_detailed_toxicity(text)
        emo = self.neural.analyze_detailed_emotions(text)

        results = {
            "Шаблон": template,
            "Сгенерированный вопрос": query,
            "Наличие ответа": self._format_status(empty_res["is_passed"], "Ок", "ПУСТО"),
            "Техническая целостность текста": self._format_status(res_encode["is_passed"], "Чисто",
                                                                  f"ОШИБКА: {res_encode.get('details')}"),
            "Лингвистическая грамотность": self._format_status(spell["is_passed"], "Нет ошибок",
                                                               f"Ошибок: {len(spell['data']['errors'])}"),
            "Эмоциональный профиль": emo["details"]
        }

        if mode != 'no llm':
            rel = await self.llm.check_relevance(query, text)
            results.update({
                "Смысловое соответствие (LLM)": self._format_status(rel["is_passed"], "Ок", "Не релевантно"),
                "Заключение (LLM)": rel.get("reasoning", "")
            })

        return results