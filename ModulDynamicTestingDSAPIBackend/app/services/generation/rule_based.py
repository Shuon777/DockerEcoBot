import random
import pymorphy3
from typing import List

# Инициализируем морфологический анализатор для русского языка
morph = pymorphy3.MorphAnalyzer()


class RuleBasedGenerator:
    """
    Класс для алгоритмической генерации вариаций текста.
    Реализует методы внесения опечаток и изменения грамматических форм.
    """

    @staticmethod
    def add_typos(text: str, error_rate: float = 0.1) -> str:
        """
        Вносит случайные опечатки в текст: перестановка соседних букв или удаление.

        :param text: Исходный текст.
        :param error_rate: Вероятность ошибки в слове.
        :return: Текст с опечатками.
        """
        words = text.split()
        new_words = []
        for word in words:
            if len(word) > 3 and random.random() < error_rate:
                idx = random.randint(1, len(word) - 2)
                # Вариант 1: Перестановка букв
                char_list = list(word)
                char_list[idx], char_list[idx + 1] = char_list[idx + 1], char_list[idx]
                word = "".join(char_list)
            new_words.append(word)
        return " ".join(new_words)

    @staticmethod
    def change_morphology(text: str) -> str:
        """
        Случайно меняет падеж или число существительных и прилагательных.

        :param text: Исходный текст.
        :return: Текст с измененными грамматическими формами.
        """
        words = text.split()
        new_words = []
        # Список возможных падежей в pymorphy3
        cases = {'gent', 'datv', 'accs', 'ablt', 'loct'}

        for word in words:
            parsed = morph.parse(word)[0]
            # Проверяем, является ли слово существительным или прилагательным
            if 'NOUN' in parsed.tag or 'ADJF' in parsed.tag:
                target_case = random.choice(list(cases))
                try:
                    inflected = parsed.inflect({target_case})
                    if inflected:
                        word = inflected.word
                except Exception:
                    pass  # Если не удалось склонить, оставляем как есть
            new_words.append(word)
        return " ".join(new_words)

    def generate_variants(self, template: str, count: int, use_typos: bool, use_morph: bool) -> List[str]:
        """
        Генерирует список уникальных вариаций вопроса.
        """
        variants = set()
        attempts = 0
        while len(variants) < count and attempts < count * 5:
            current = template
            if use_morph:
                current = self.change_morphology(current)
            if use_typos:
                current = self.add_typos(current)

            if current != template:
                variants.add(current)
            attempts += 1

        return list(variants)