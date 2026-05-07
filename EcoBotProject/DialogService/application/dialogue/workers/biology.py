import logging
import json
from typing import Optional, Literal, Dict, Any
from pydantic import BaseModel, Field, ConfigDict
from infrastructure.llm.factory import LLMFactory

logger = logging.getLogger("BiologyWorker")


class LLMBiologyExtraction(BaseModel):
    model_config = ConfigDict(extra='forbid')
    action: Optional[Literal["describe", "show_image", "show_map", "list_items", "find_nearby"]] = None
    species_name: Optional[str] = Field(None, description="Название вида в именительном падеже")
    category: Optional[Literal["Flora", "Fauna", "Unknown"]] = None
    location_context: Optional[str] = Field(None, description="Только если явно указан город/место. Иначе null.")


class BiologyAnalysis(BaseModel):
    action: Optional[str] = None
    species_name: Optional[str] = None
    category: Optional[str] = None
    attributes: Dict[str, str] = Field(default_factory=dict)
    location_context: Optional[str] = None


class BiologyWorker:
    def __init__(self, provider: str = "qwen"):
        llm = LLMFactory.get_model(provider)
        self.parser = llm.with_structured_output(LLMBiologyExtraction, method="json_mode")

    def _detect_action_by_triggers(self, query: str) -> Optional[str]:
        q = query.lower()
        if any(w in q for w in ["карт", "где обитает", "где растет", "ареал"]): return "show_map"
        if any(w in q for w in ["рядом", "около", "возле", "в районе", "поблизости"]): return "find_nearby"
        if any(w in q for w in ["фото", "выглядит", "покажи", "картинк"]): return "show_image"
        if any(w in q for w in ["список", "какие", "перечисли", "какая флора", "какая фауна"]): return "list_items"
        if any(w in q for w in ["расскажи", "что такое", "описание", "информаци"]): return "describe"
        return None

    def _detect_attributes_by_triggers(self, query: str) -> Dict[str, str]:
        q = query.lower()
        attrs = {}
        if any(w in q for w in ["зим"]): attrs["Время года"] = "Зима"
        elif any(w in q for w in ["весн"]): attrs["Время года"] = "Весна"
        elif any(w in q for w in ["летом", "летн"]): attrs["Время года"] = "Лето"
        elif any(w in q for w in ["осен"]): attrs["Время года"] = "Осень"
        if any(w in q for w in ["цветущ", "цветет", "расцвел"]): attrs["Цветение"] = "Да"
        if any(w in q for w in ["шишк"]): attrs["Наличие плодов"] = "Шишка"
        elif any(w in q for w in ["ягод"]): attrs["Наличие плодов"] = "Ягода"
        elif any(w in q for w in ["плод"]): attrs["Наличие плодов"] = "Плод"
        if any(w in q for w in ["болот"]): attrs["Среда обитания"] = "Болото"
        elif any(w in q for w in ["берег", "побереж"]): attrs["Среда обитания"] = "Побережье"
        elif any(w in q for w in ["степ"]): attrs["Среда обитания"] = "Степь"
        elif any(w in q for w in ["гор", "скал"]): attrs["Среда обитания"] = "Горы"
        elif any(w in q for w in ["лес"]): attrs["Среда обитания"] = "Лес"
        return attrs

    async def analyze(self, query: str) -> tuple[BiologyAnalysis, str]:
        fast_action = self._detect_action_by_triggers(query)
        python_attributes = self._detect_attributes_by_triggers(query)
        action_hint = f"СИСТЕМНАЯ НАВОДКА: action = '{fast_action}'. Твоя задача только извлечь species_name." if fast_action else ""

        prompt = f"""
        ЗАДАЧА: ИЗВЛЕЧЬ ДАННЫЕ ИЗ ЗАПРОСА ПОЛЬЗОВАТЕЛЯ В JSON.
        ЯЗЫК: ТОЛЬКО РУССКИЙ.

        {action_hint}

        СТРОГИЕ ПРАВИЛА ИЗВЛЕЧЕНИЯ:
        1. ПОЛЕ species_name: биологический объект в именительном падеже.
        2. ПОЛЕ action: describe/show_image/show_map/list_items/find_nearby
        3. ПОЛЕ category: Flora (растения/грибы) / Fauna (животные/рыбы) / Unknown
        4. ПОЛЕ location_context: место или null. Не выдумывать.

        ЗАПРОС: {query}

        Ответь ТОЛЬКО JSON: {{"action": "...", "species_name": "...", "category": "...", "location_context": "..."}}
        """
        logger.info(f"Analyzing biology request: '{query}'")
        try:
            llm_result: LLMBiologyExtraction = await self.parser.ainvoke(prompt)
            final_action = fast_action if fast_action else (llm_result.action or "describe")
            result = BiologyAnalysis(
                action=final_action,
                species_name=llm_result.species_name,
                category=llm_result.category,
                attributes=python_attributes,
                location_context=llm_result.location_context,
            )
            source = "FAST_ACTION+LLM" if fast_action else "FULL_LLM"
            debug = f"Biology NLU ({source}):\n{json.dumps(result.model_dump(), indent=2, ensure_ascii=False)}"
            return result, debug
        except Exception as e:
            logger.error(f"BiologyWorker error: {e}")
            fallback = BiologyAnalysis(action=fast_action or "describe", attributes=python_attributes)
            return fallback, "Biology NLU: ERROR, fallback to python rules"
