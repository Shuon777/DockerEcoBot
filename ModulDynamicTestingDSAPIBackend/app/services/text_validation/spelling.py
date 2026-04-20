import httpx
from typing import Dict, Any, List
from spellchecker import SpellChecker
import re

class SpellingChecker:
    """
    Надежный сервис проверки орфографии через прямое обращение к Yandex Speller API.
    Не требует сторонних бинарных библиотек.
    """

    API_URL = "https://speller.yandex.net/services/spellservice.json/checkText"

    async def check_spelling(self, text: str) -> Dict[str, Any]:
        """
        Проверяет текст на ошибки через официальный API Яндекса.
        """
        if not text.strip():
            return {"test_name": "spelling_check", "is_passed": True, "details": "Текст пуст"}

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                # Параметры: текст и языки (ru, en)
                params = {"text": text, "lang": "ru,en", "options": 7}  # 7 = игнорировать ссылки, цифры и флаги
                response = await client.get(self.API_URL, params=params)

                if response.status_code != 200:
                    return {"test_name": "spelling_check", "is_passed": False, "details": "Ошибка API Яндекса"}

                errors = response.json()

                # Формируем исправленный текст (грубая замена для демонстрации)
                fixed_text = text
                error_list = []

                for err in reversed(errors):  # Идем с конца, чтобы индексы не поплыли
                    word = err['word']
                    suggestions = err['s']
                    error_list.append({
                        "word": word,
                        "suggestions": suggestions,
                        "row": err['row'],
                        "col": err['col']
                    })
                    if suggestions:
                        # Заменяем слово на первый вариант из предложенных
                        fixed_text = fixed_text[:err['pos']] + suggestions[0] + fixed_text[err['pos'] + len(word):]

                is_passed = len(errors) == 0
                return {
                    "test_name": "spelling_check",
                    "is_passed": is_passed,
                    "details": "Ошибок не найдено" if is_passed else f"Найдено ошибок: {len(errors)}",
                    "data": {
                        "errors": error_list,
                        "fixed_text": fixed_text
                    }
                }
        except Exception as e:
            return {"test_name": "spelling_check", "is_passed": False, "details": f"Ошибка сервиса: {str(e)}"}


class LocalSpellingChecker:
    """
    Локальная проверка орфографии без внешних запросов.
    Использует библиотеку pyspellchecker.
    """

    def __init__(self):
        # Инициализируем для русского и английского
        self.spell_ru = SpellChecker(language='ru')
        self.spell_en = SpellChecker(language='en')

    def check_spelling(self, text: str) -> Dict[str, Any]:
        """Проверяет текст на ошибки, используя локальные словари."""
        # Очистка текста от знаков препинания для корректного сплита
        words = re.findall(r'\b\w+\b', text.lower())

        misspelled = []
        # Проверяем каждое слово в обоих словарях
        unknown = self.spell_ru.unknown(words)
        unknown = self.spell_en.unknown(unknown)  # То, что не нашел русский, ищем в английском

        for word in unknown:
            misspelled.append({
                "word": word,
                "suggestions": list(self.spell_ru.candidates(word) or self.spell_en.candidates(word) or [])[:3]
            })

        is_passed = len(misspelled) == 0
        return {
            "test_name": "local_spelling_check",
            "is_passed": is_passed,
            "data": {"errors": misspelled}
        }