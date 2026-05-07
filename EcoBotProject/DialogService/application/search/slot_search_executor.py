import os
import re
import aiohttp
from typing import Any, Dict, List, Optional

_NEAR_RE = re.compile(r"рядом|около|возле|недалеко|поблизости|близ", re.IGNORECASE)
_MD_IMG_RE = re.compile(r'!\[[^\]]*\]\([^)]*\)')           # ![alt](url) → удалить
_MD_LINK_RE = re.compile(r'\[([^\]]+)\]\([^)]+\)')          # [text](url) → text
_EXCESS_NL_RE = re.compile(r'\n{3,}')


class SlotSearchExecutor:
    """Исполнительная часть пайплайна нового классификатора.
    Преобразует слоты в параметры запроса к /search или /search/place/objects
    и возвращает результат.
    """

    def __init__(self, session: aiohttp.ClientSession = None):
        self._session = session
        self._backend_url = os.getenv("ECOBOT_API_BASE_URL", "http://backend:5555")

    async def execute(self, query: str, slots: Dict[str, Any]) -> Dict[str, Any]:
        if self._use_place_endpoint(slots):
            search_body = self._build_place_params(slots, query)
            search_data = await self._call_place(search_body)
        else:
            search_body = self._build_search_params(slots, query)
            search_data = await self._call_search(search_body)
        result = self._format_result(slots, search_data)
        return {"slots": slots, "search_request": search_body, "search": search_data, "result": result}

    # ── Форматирование результата ─────────────────────────────────────────────

    def _format_result(self, slots: Dict[str, Any], search_data: dict) -> dict:
        llm = search_data.get("llm_answer") or {}
        llm_raw = (llm.get("content") or "").strip() if isinstance(llm, dict) else ""

        resources: List[dict] = search_data.get("resources") or []
        text_res  = [r for r in resources if r.get("modality_type") == "Текст"]
        image_res = [r for r in resources if r.get("modality_type") == "Изображение"]
        geo_res   = [r for r in resources if r.get("modality_type") == "Геоданные"]

        objects: List[dict] = search_data.get("objects") or []

        result: dict = {}

        # ── Текст ──
        if llm_raw:
            result["answer"] = self._clean_text(llm_raw)
        elif text_res:
            result["answer"] = self._extract_text(text_res[0])
        elif not objects:
            result["answer"] = "По вашему запросу ничего не найдено."

        # ── Изображения ──
        images = [
            r["content"]["file_path"]
            for r in image_res
            if isinstance(r.get("content"), dict) and r["content"].get("file_path")
        ]
        if images:
            result["images"] = images[:5]

        # ── Карта из geo-ресурсов (/search) ──
        for r in geo_res:
            links = (r.get("content") or {}).get("map_links")
            if links:
                result["map"] = links
                break

        # ── Карта из свойств объектов (place-поиск) ──
        if "map" not in result:
            for obj in objects:
                props = obj.get("properties") or {}
                if props.get("static_map") or props.get("interactive_map"):
                    result["map"] = {
                        "static": props.get("static_map"),
                        "interactive": props.get("interactive_map"),
                    }
                    break

        # ── Найденные объекты ──
        if objects:
            result["objects"] = [
                {
                    "id": obj.get("id"),
                    "name": obj["synonyms"][0].title() if obj.get("synonyms") else "—",
                }
                for obj in objects
            ]

        # ── Мета place-поиска ──
        if "total_objects" in search_data:
            result["total_found"] = search_data["total_objects"]
        if "place_name" in search_data:
            result["place"] = search_data["place_name"]

        return result

    @staticmethod
    def _clean_text(text: str) -> str:
        """Убирает markdown-медиа из LLM-ответа, оставляет читаемый текст."""
        text = _MD_IMG_RE.sub("", text)                                  # удаляем ![alt](url)
        text = _MD_LINK_RE.sub(r"\1", text)                              # [text](url) → text
        text = re.sub(r"^\s*[-*]\s*$", "", text, flags=re.MULTILINE)    # пустые list-items
        text = _EXCESS_NL_RE.sub("\n\n", text)
        return text.strip()

    @staticmethod
    def _extract_text(resource: dict) -> str:
        """Извлекает текст из структуры контента текстового ресурса."""
        c = resource.get("content") or {}
        if isinstance(c, dict):
            sd = c.get("structured_data") or {}
            if isinstance(sd, dict):
                return (sd.get("content") or sd.get("text") or "").strip()
            return (c.get("text") or c.get("content") or "").strip()
        return str(c).strip()

    # ── Роутинг ───────────────────────────────────────────────────────────────

    def _use_place_endpoint(self, slots: Dict[str, Any]) -> bool:
        """Геопоиск по месту: Геоданные + нет конкретного объекта + есть топоним."""
        if slots.get("modality") != "Геоданные":
            return False
        if slots.get("synonym"):
            return False
        props = slots.get("properties") or {}
        return bool(props.get("Детальное расположение") or props.get("Расположение относительно Байкала"))

    # ── Геопоиск по месту (/search/place/objects) ─────────────────────────────

    def _build_place_params(self, slots: Dict[str, Any], user_query: str) -> dict:
        props = slots.get("properties") or {}
        is_baikal = bool(props.get("Расположение относительно Байкала"))

        place_name = "озеро байкал" if is_baikal else (props.get("Детальное расположение") or "").lower()
        search_type = self._resolve_search_type(user_query, is_baikal)
        buffer_km = 1.0 if is_baikal else 10.0

        body: dict = {
            "place_name": place_name,
            "buffer_radius_km": buffer_km,
            "limit": 20,
            "offset": 0,
            "search_type": search_type,
        }

        subtypes = props.get("Подтип объекта")
        if subtypes:
            body["Подтип объекта"] = [subtypes] if isinstance(subtypes, str) else subtypes

        return body

    @staticmethod
    def _resolve_search_type(query: str, is_baikal: bool) -> str:
        if is_baikal:
            return "both"
        if _NEAR_RE.search(query):
            return "near"
        return "inside"

    async def _call_place(self, body: dict) -> dict:
        own_session = self._session is None
        sess = self._session or aiohttp.ClientSession()
        try:
            async with sess.post(f"{self._backend_url}/search/place/objects", json=body) as resp:
                return await resp.json()
        finally:
            if own_session:
                await sess.close()

    # ── Стандартный поиск (/search) ───────────────────────────────────────────

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
                "debug": True,
                "user_query": user_query,
                "clean_user_query": user_query,
                "use_llm_answer": True,
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
