import random
import os
from transformers import pipeline
from .base import IQuestionGenerator
from typing import List

class SimpleGenerator(IQuestionGenerator):
    """Возвращает исходный вопрос без изменений."""
    async def generate(self, query: str, error_rate: float = 0.1) -> List[str]:
        return [query]

class MorphologicalGenerator(IQuestionGenerator):
    def __init__(self, morph_analyzer):
        self.morph = morph_analyzer

    async def generate(self, query: str, count: int, error_rate: float = 0.1) -> List[str]:
        """
        Случайно меняет падеж или число существительных и прилагательных.

        :param text: Исходный текст.
        :return: Текст с измененными грамматическими формами.
        """
        words = query.split()
        new_words = []
        # Список возможных падежей в pymorphy3
        cases = {'gent', 'datv', 'accs', 'ablt', 'loct'}

        for word in words:
            parsed = self.morph.parse(word)[0]
            # Провер, является ли слово существительным или прилагательным
            if 'NOUN' in parsed.tag or 'ADJF' in parsed.tag:
                target_case = random.choice(list(cases))
                try:
                    inflected = parsed.inflect({target_case})
                    if inflected:
                        word = inflected.word
                except Exception:
                    pass
            new_words.append(word)
        return " ".join(new_words)

class TyposGenerator(IQuestionGenerator):
    def __init__(self):
        pass

    async def generate(self, query: str, count: int, error_rate: float = 0.1) -> List[str]:
        """
           Вносит случайные опечатки в текст: перестановка соседних букв или удаление.

           :param text: Исходный текст.
           :param error_rate: Вероятность ошибки в слове.
           :return: Текст с опечатками.
       """
        words = query.split()
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

class HFParaphraseGenerator(IQuestionGenerator):
    """

    """
    def __init__(self, model_path: str = "cointegrated/rut5-base-paraphraser"):
        print(f"⏳ Загрузка модели парафраза {model_path}...")
        path_sen = os.path.join("./local_models", "rut5")
        self.para_pipe = pipeline("text2text-generation", model=path_sen, tokenizer=path_sen)

    async def generate(self, query: str, count: int, error_rate: float = 0.1) -> List[str]:
        # Генерируем парафразы через локальную нейросеть T5
        results = self.para_pipe(
            query,
            num_return_sequences=5,
            do_sample=True,
            max_length=64
        )
        return [res['generated_text'] for res in results]