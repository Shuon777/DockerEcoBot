import httpx
import re
import sys
from typing import List, Dict, Any
from langdetect import detect, DetectorFactory
from bs4 import BeautifulSoup
import pymorphy3
from app.core.constants import URL_PATTERN, PII_PATTERNS, UNICODE_ESCAPE_PATTERN, MOJIBAKE_SAMPLES

# 1. Фикс для работы Natasha и Pymorphy3 на Python 3.12
try:
    import pymorphy3

    sys.modules['pymorphy2'] = pymorphy3
except:
    pass

from natasha import (
    Segmenter, MorphVocab, NewsEmbedding,
    NewsNERTagger, NamesExtractor, Doc
)
from app.core.constants import PII_PATTERNS
from typing import Dict, Any, List


# Для воспроизводимости результатов детекции языка
DetectorFactory.seed = 0


class TextChecker:
    """
    Класс для выполнения формальных тестов текстового ответа бота.
    """

    @staticmethod
    def check_not_empty(text: str | None) -> Dict[str, Any]:
        """Проверяет, что текст не пустой и не null."""
        is_passed = bool(text and text.strip())
        return {
            "test_name": "not_empty",
            "is_passed": is_passed,
            "details": "Текст получен" if is_passed else "Текст пуст или отсутствует"
        }

    @staticmethod
    async def check_links(text: str) -> Dict[str, Any]:
        """Находит ссылки в тексте и проверяет их доступность (HTTP 200)."""
        urls = URL_PATTERN.findall(text)
        if not urls:
            return {"test_name": "links_validity", "is_passed": True, "details": "Ссылок не обнаружено"}

        results = []
        async with httpx.AsyncClient(timeout=5.0) as client:
            for url in urls:
                try:
                    response = await client.get(url)
                    results.append({"url": url, "status": response.status_code, "ok": response.status_code == 200})
                except Exception as e:
                    results.append({"url": url, "status": None, "ok": False, "error": str(e)})

        all_ok = all(r["ok"] for r in results)
        return {
            "test_name": "links_validity",
            "is_passed": all_ok,
            "data": {"checked_links": results},
            "details": "Все ссылки доступны" if all_ok else "Обнаружены битые ссылки"
        }

    @staticmethod
    def check_encoding_and_markup(text: str) -> Dict[str, Any]:
        """Проверяет текст на битые кодировки и валидность HTML-разметки."""
        errors = []

        # Проверка на \uXXXX
        if UNICODE_ESCAPE_PATTERN.search(text):
            errors.append("Обнаружены неэкранированные Unicode-последовательности")

        # Проверка на "кракозябры"
        if any(sample in text for sample in MOJIBAKE_SAMPLES):
            errors.append("Обнаружены признаки нарушения кодировки (Mojibake)")

        # Проверка разметки через BeautifulSoup
        # Если BeautifulSoup нашел серьезные несоответствия (например, незакрытые теги в режиме xml)
        soup = BeautifulSoup(text, "html.parser")
        if bool(soup.find()) and not soup.find_all():  # Очень грубая проверка на структуру
            errors.append("Возможные ошибки в HTML/XML разметке")

        is_passed = len(errors) == 0
        return {
            "test_name": "encoding_and_markup",
            "is_passed": is_passed,
            "details": "; ".join(errors) if errors else "Кодировка и разметка в норме"
        }

    @staticmethod
    def check_pii(text: str) -> Dict[str, Any]:
        """Сканирует текст на наличие персональных данных (PII) через Regex."""
        found_pii = {}
        for pii_type, pattern in PII_PATTERNS.items():
            matches = pattern.findall(text)
            if matches:
                found_pii[pii_type] = matches

        is_passed = len(found_pii) == 0
        return {
            "test_name": "pii_leak",
            "is_passed": is_passed,
            "details": "Данные не обнаружены" if is_passed else f"Обнаружены конфиденциальные данные: {list(found_pii.keys())}",
            "data": found_pii if not is_passed else None
        }

    @staticmethod
    def check_language(text: str, expected_lang: str) -> Dict[str, Any]:
        """Проверяет соответствие языка текста ожидаемому."""
        try:
            detected_lang = detect(text)
            is_passed = detected_lang == expected_lang
            return {
                "test_name": "language_match",
                "is_passed": is_passed,
                "details": f"Ожидался {expected_lang}, определен {detected_lang}",
                "data": {"detected": detected_lang}
            }
        except Exception as e:
            return {"test_name": "language_match", "is_passed": False,
                    "details": f"Не удалось определить язык: {str(e)}"}


class TextCheckerPiiFIO:
    """Расширенный чекер с использованием NLP для поиска ФИО."""

    def __init__(self):

        # Инициализация Natasha для поиска имен
        self.segmenter = Segmenter()
        self.morph_vocab = MorphVocab()
        self.emb = NewsEmbedding()
        self.ner_tagger = NewsNERTagger(self.emb)
        self.names_extractor = NamesExtractor(self.morph_vocab)
        self.morph = pymorphy3.MorphAnalyzer()

    def check_pii_and_fio(self, text: str) -> Dict[str, Any]:
        """
        Ищет персональные данные: Email, Телефон (через Regex) и ФИО (через Natasha).
        """
        found_pii = {}

        # 1. Поиск стандартных PII через регулярки
        for pii_type, pattern in PII_PATTERNS.items():
            matches = pattern.findall(text)
            if matches:
                found_pii[pii_type] = matches

        # 2. Поиск ФИО через Natasha
        doc = Doc(text)
        doc.segment(self.segmenter)
        doc.tag_ner(self.ner_tagger)

        raw_names = []
        for span in doc.spans:
            if span.type == 'PER':
                raw_names.append(span.text)

            # --- ФИЛЬТРАЦИЯ ---
        filtered_fio = []
        for name in raw_names:
            # 1. Убираем латынь и технические пометки (слова со скобками или латинскими буквами)
            # Ботаника часто содержит (Larix), (Pinaceae) - это не люди.
            if any(char in name for char in "()[]") or re.search(r'[a-zA-Z]', name):
                continue

            # 2. Проверка через морфологию (отсекаем прилагательные и неодушевленные сущности)
            # Например, 'Светолюбива' - это краткое прилагательное.
            first_word = name.split()[0]
            parsed = self.morph.parse(first_word)[0]

            # Если слово — это прилагательное (ADJF, ADJS) или причастие, это не имя.
            if 'ADJF' in parsed.tag or 'ADJS' in parsed.tag or 'PRTF' in parsed.tag:
                continue

            # Если слово неодушевленное (inan) и при этом не является распространенной фамилией
            if 'inan' in parsed.tag and 'Surn' not in parsed.tag:
                continue

            # 3. Фильтр по списку ОФФ (если мы знаем, о чем диалог)
            # Если найденное 'имя' совпадает с названием растения из базы
            # if species_list and name.lower() in [s.lower() for s in species_list]:
            #     continue

            filtered_fio.append(name)

        is_passed = len(filtered_fio) == 0
        return {
            "test_name": "pii_fio_leak",
            "is_passed": is_passed,
            "data": {"FIO": filtered_fio} if filtered_fio else None
        }