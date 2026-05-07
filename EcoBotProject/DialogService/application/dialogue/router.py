import os
import logging
from typing import Optional, List, Literal
from pydantic import BaseModel, Field
from infrastructure.llm.factory import LLMFactory

logger = logging.getLogger("SemanticRouter")


def _load_known_objects(file_name: str) -> List[str]:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(current_dir, file_name)
    with open(file_path, "r", encoding="utf-8") as f:
        return [line.strip().lower() for line in f if line.strip()]


class Route(BaseModel):
    intent: Literal["BIOLOGY", "INFRASTRUCTURE", "KNOWLEDGE", "CHITCHAT"] = Field(
        description="BIOLOGY — флора/фауна, INFRASTRUCTURE — музеи/памятники, KNOWLEDGE — история/FAQ, CHITCHAT — болталка"
    )


class SemanticRouter:
    def __init__(self, provider: str = "qwen"):
        llm = LLMFactory.get_model(provider)
        self.runnable = llm.with_structured_output(Route, method="json_mode")
        self.KNOWN_OBJECTS_LOWER = _load_known_objects("biological_entity.txt")
        logger.info("Биологические сущности загружены")

    async def _fast_intent(self, query: str) -> Optional[str]:
        q = query.lower()
        knowledge_triggers = ["билет", "цен", "график", "экспонат", "выставк", "чучело", "картина", "экспозици", "оформить", "сколько стоит", "проект"]
        if any(t in q for t in knowledge_triggers):
            return "KNOWLEDGE"
        if any(obj in q for obj in self.KNOWN_OBJECTS_LOWER):
            return "BIOLOGY"
        infra_triggers = ["музей", "памятник", "база отдыха", "кафе", "туалет", "маршрут", "музе"]
        if any(t in q for t in infra_triggers):
            return "INFRASTRUCTURE"
        return None

    async def get_intent(self, query: str, last_intent: Optional[str] = None) -> tuple[str, str]:
        fast = await self._fast_intent(query)
        if fast:
            return fast, "FAST_RULES"

        context_hint = f"\nКОНТЕКСТ: Предыдущая тема: {last_intent}\n" if last_intent else ""
        prompt = f"""
        ЗАДАЧА: КЛАССИФИЦИРОВАТЬ ТИП ЗАПРОСА.

        {context_hint}

        КРИТЕРИИ:
        1. BIOLOGY: запрос о растении или животном.
        2. INFRASTRUCTURE: запрос о созданных человеком объектах (здания, музеи, памятники, заповедники, топонимы).
        3. KNOWLEDGE: запрос об услугах (процедуры, правила, цены, билеты, история, экспозиция).
        4. CHITCHAT: small talk (приветствие, благодарность).

        ЗАПРОС: "{query}"

        Ответь ТОЛЬКО JSON: {{"intent": "BIOLOGY"}} или {{"intent": "INFRASTRUCTURE"}} или {{"intent": "KNOWLEDGE"}} или {{"intent": "CHITCHAT"}}
        """
        try:
            result = await self.runnable.ainvoke(prompt)
            return result.intent, "LLM"
        except Exception as e:
            logger.error(f"Router error: {e}")
            return last_intent or "CHITCHAT", "ERROR_FALLBACK"
