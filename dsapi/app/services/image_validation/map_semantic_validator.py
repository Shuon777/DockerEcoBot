from app.services.llm_evaluator.evaluator import LLMService
import json
from typing import List, Dict, Any, Tuple
from langchain_core.messages import HumanMessage, SystemMessage

class MapSemanticValidator:
    """Проверка соответствия карты запросу пользователя через LLM."""

    def __init__(self):
        self.llm_service = LLMService()

    async def validate_map_context(self, user_query: str, map_description: str, maps: str) -> Dict[str, Any]:
        """
        Логика: Пользователь спросил [X]. Бот прислал карту [Y]. Подходит ли это?
        """
        system_instr = (
            f"Ты — эксперт по ГИС и навигации.\n"
            f"Задание: Оцени, насколько данная карта и её описание решают запрос пользователя.\n"
            f"Верни строго JSON: {{\"is_passed\": bool, \"reasoning\": \"аргументация\", \"score\": int}}"
        )

        # 2. Формируем запрос пользователя (контекст)
        user_query = f"Пользователь спросил: {user_query}\nБот предоставил описание: : {map_description}. Бот предоставил ссылку на карту: '{maps}"

        # 3. Создаем список сообщений (Messages List)
        messages = [
            SystemMessage(content=system_instr),
            HumanMessage(content=user_query)
        ]

        # chain = prompt | self.llm
        # Используем наш существующий LLM Service
        response = await self.llm_service.llm.ainvoke(messages)
        try:
            return json.loads(response.content)
        except:
            return {"is_passed": False, "reasoning": "Ошибка парсинга ответа LLM"}