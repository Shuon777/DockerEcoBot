import os
import aiohttp
from typing import Any, Dict


class SlotSearchExecutor:
    """Исполнительная часть пайплайна нового классификатора.
    Преобразует слоты в параметры запроса к /search и возвращает результат.
    """

    def __init__(self, session: aiohttp.ClientSession = None):
        self._session = session
        self._backend_url = os.getenv("ECOBOT_API_BASE_URL", "http://backend:5555")

    async def execute(self, query: str, slots: Dict[str, Any]) -> Dict[str, Any]:
        search_body = self._build_search_params(slots, query)
        search_data = await self._call_search(search_body)
        return {"slots": slots, "search_request": search_body, "search": search_data}

    def _build_search_params(self, slots: Dict[str, Any], user_query: str) -> dict:
        search_params = {}

        obj = {}
        synonym = slots.get("synonym")
        if synonym:
            # Синонимы в БД хранятся в нижнем регистре без ё (см. import_objects.py)
            normalized = synonym.lower().strip().replace("ё", "е")
            obj["name_synonyms"] = {"ru": [normalized]}
            # При конкретном синониме properties и object_type не передаём —
            # они фильтры для поиска класса объектов и добавляют лишние AND-условия
        else:
            merged_props = {**slots.get("properties", {}), **slots.get("extra", {})}
            if merged_props:
                obj["properties"] = merged_props
            if slots.get("object_type"):
                obj["object_type"] = slots["object_type"]
        if obj:
            search_params["object"] = obj

        if slots.get("features"):
            search_params["resource"] = {"features": slots["features"]}

        if slots.get("modality"):
            search_params["modality_type"] = slots["modality"]

        return {
            "system_parameters": {
                "user_query": user_query,
                "clean_user_query": user_query,
                "use_llm_answer": False,
            },
            "search_parameters": search_params,
        }

    async def _call_search(self, body: dict) -> dict:
        own_session = self._session is None
        sess = self._session or aiohttp.ClientSession()
        try:
            async with sess.post(f"{self._backend_url}/search", json=body) as resp:
                return await resp.json()
        finally:
            if own_session:
                await sess.close()
