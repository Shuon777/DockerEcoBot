import logging
import json
from typing import List, Optional, Literal
from pydantic import BaseModel, Field, ConfigDict
from infrastructure.llm.factory import LLMFactory

logger = logging.getLogger("InfrastructureWorker")


class LLMInfraExtraction(BaseModel):
    model_config = ConfigDict(extra='forbid')
    action: Optional[Literal["describe", "show_map", "list_items", "count_items"]] = None
    object_name: Optional[str] = Field(None)
    entity_type: Literal["Infrastructure", "GeoPlace", "Service", "Unknown"] = "Unknown"
    category: Optional[Literal["Природный объект", "Достопримечательности", "Unknown"]] = "Unknown"
    subcategory: List[str] = Field(default_factory=list)
    area_name: Optional[str] = Field(None)


class InfraAnalysis(BaseModel):
    action: Optional[str] = None
    object_name: Optional[str] = None
    entity_type: str = "Unknown"
    category: str = "Unknown"
    subcategory: List[str] = Field(default_factory=list)
    area_name: Optional[str] = None


class InfrastructureWorker:
    def __init__(self, provider: str = "qwen"):
        llm = LLMFactory.get_model(provider)
        self.parser = llm.with_structured_output(LLMInfraExtraction, method="json_mode")

    def _detect_action_by_triggers(self, query: str) -> Optional[str]:
        q = query.lower()
        if any(w in q for w in ["скольк"]): return "count_items"
        if any(w in q for w in ["какие", "список", "перечисли", "что интересного", "все "]): return "list_items"
        if any(w in q for w in ["карт", "где находит", "где располож", "покажи где"]): return "show_map"
        if any(w in q for w in ["расскажи", "история", "что такое", "описание", "про "]): return "describe"
        return None

    async def analyze(self, query: str) -> tuple[InfraAnalysis, str]:
        fast_action = self._detect_action_by_triggers(query)
        action_hint = f"\nСИСТЕМНАЯ НАВОДКА: action = '{fast_action}'.\n" if fast_action else ""

        prompt = f"""
        ЗАДАЧА: ИЗВЛЕЧЬ ДАННЫЕ ИЗ ЗАПРОСА ПОЛЬЗОВАТЕЛЯ В JSON.
        ЯЗЫК: ТОЛЬКО РУССКИЙ.
        {action_hint}

        СТРОГИЕ ПРАВИЛА:
        1. object_name: что ищем (именительный падеж).
        2. area_name: где ищем (населённый пункт, остров). null если нет.
        3. entity_type: всегда "Infrastructure" для объектов.
        4. category: "Достопримечательности" (рукотворные) / "Природный объект" (природа).
        5. subcategory: уточняющий тип ["Памятники"], ["Музеи"] и т.п.

        ЗАПРОС: {query}

        Ответь ТОЛЬКО JSON: {{"action": "...", "object_name": "...", "entity_type": "...", "category": "...", "subcategory": [], "area_name": "..."}}
        """
        logger.info(f"Analyzing infrastructure request: '{query}'")
        try:
            llm_result: LLMInfraExtraction = await self.parser.ainvoke(prompt)
            final_action = fast_action if fast_action else (llm_result.action or "describe")
            result = InfraAnalysis(
                action=final_action,
                object_name=llm_result.object_name,
                entity_type=llm_result.entity_type,
                category=llm_result.category,
                subcategory=llm_result.subcategory,
                area_name=llm_result.area_name,
            )
            source = "FAST_ACTION+LLM" if fast_action else "FULL_LLM"
            debug = f"Infra NLU ({source}):\n{json.dumps(result.model_dump(), indent=2, ensure_ascii=False)}"
            return result, debug
        except Exception as e:
            logger.error(f"InfrastructureWorker error: {e}")
            fallback = InfraAnalysis(action=fast_action or "describe")
            return fallback, "Infra NLU: ERROR, fallback to python rules"
