import json
import os
import time
from typing import List, Dict, Any, Tuple
from abc import ABC, abstractmethod
from app.services.generation.base import IQuestionGenerator

from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import HumanMessage, SystemMessage
from app.core.config import settings

class ILLMServiceGenerationQuestions(ABC):
    @abstractmethod
    async def generate_questions_llm(self, template: str, count: int) -> List[str]:
        pass

class LLMServiceGenerationQuestions(IQuestionGenerator):
    """
    Реализует генерацию вопросов
    """

    def __init__(self):
        # self.llm = ChatOllama(
        #     model=settings.REMOTE_MODEL,
        #     temperature=0,
        #     format="json",
        #     base_url=settings.REMOTE_OLLAMA_URL,
        #     num_ctx=10000,
        #     num_predict=512,
        # )
        self.llm = ChatOllama(
            model=settings.REMOTE_VL_MODEL,
            temperature=0,
            base_url=settings.REMOTE_OLLAMA_URL,
            # ВАЖНО!: Убираем format="json" для Vision, так как некоторые
            # версии Ollama VL конфликтуют с жестким JSON-режимом
            num_ctx=10000,
        )

    async def generate(self, query: str, count: int, error_rate: float = 0.1) -> List[str]:
        """
        Генерирует вариативные вопросы на основе шаблона.
        """
        system_prompt = (
            "Ты — помощник по тестированию диалоговых систем. "
            f"Твоя задача: на основе входного вопроса создать {count} его вариаций. "
            "Вариации должны включать: разные формулировки, разный порядок слов, "
            "возможные опечатки и использование разных падежей, с изменениям структуры, " 
            " с изменениями склонений по числам, с вариацией по уровню вежливости, со слэнгом"
            "Ответ верни строго в формате JSON: {'variants': [('вопрос1', 'вид вариации1'), ('вопрос2', 'вид вариации2')]}"
        )
        # prompt = ChatPromptTemplate.from_messages([
        #     ("system", system_prompt),
        #     ("human", "{template}")
        # ])
        # 2. Формируем запрос пользователя (контекст)
        user_query = f"Шаблон вопроса: {query}"

        # 3. Создаем список сообщений (Messages List)
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_query)
        ]
        # chain = prompt | self.llm

        print("⏳ ПРОГРЕВ МОДЕЛИ 80B (Может занять минуту)...")
        start_warm = time.time()
        # response = await chain.ainvoke({"template": template, "count": count})
        response = await self.llm.ainvoke(messages)
        print(f"🔥 Прогрев завершен за {time.time() - start_warm:.2f} сек.")

        try:
            data = json.loads(response.content)
            return data.get("variants", [])
        except Exception:
            return []