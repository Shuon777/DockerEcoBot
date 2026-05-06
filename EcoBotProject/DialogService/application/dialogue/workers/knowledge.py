import logging
from typing import Literal
from pydantic import BaseModel, Field
from infrastructure.llm.factory import LLMFactory

logger = logging.getLogger("KnowledgeWorker")


class KnowledgeAnalysis(BaseModel):
    search_query: str = Field(description="Очищенный поисковый запрос для базы знаний")
    topic: Literal["History", "Staff", "Rules", "Prices", "General"] = "General"


class KnowledgeWorker:
    def __init__(self, provider: str = "qwen"):
        llm = LLMFactory.get_model(provider)
        self.parser = llm.with_structured_output(KnowledgeAnalysis, method="json_mode")

    async def analyze(self, query: str) -> KnowledgeAnalysis:
        prompt = f"""
        Ты — справочный ассистент Байкальского музея.
        Очисти запрос пользователя от шума для поиска в текстовой базе знаний.

        Примеры:
        "Где посмотреть список сотрудников?" -> "список сотрудников музея"
        "Почему обсерваторию построили именно тут?" -> "причина строительства обсерватории в Листвянке"

        Запрос: {query}

        Ответь ТОЛЬКО JSON: {{"search_query": "очищенный запрос", "topic": "General"}}
        """
        logger.info(f"Analyzing knowledge request: '{query}'")
        return await self.parser.ainvoke(prompt)
