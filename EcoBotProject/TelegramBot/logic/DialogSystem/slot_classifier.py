import logging
import re
from typing import Optional, Dict, Any, Literal
from pydantic import BaseModel, Field, ConfigDict, field_validator
from .llm_factory import LLMFactory

logger = logging.getLogger("SlotClassifier")

CLASSIFICATION_PROMPT = """
Ты — классификатор запросов эко-бота о Байкальском регионе (флора, фауна, географические объекты, услуги).

ЗАДАЧА: Извлечь из запроса пользователя слоты и вернуть JSON.

═══ СЛОТ 1: object_type (обязательный) ═══
Ровно одна из трёх фраз (без сокращений!):
• "Объект флоры и фауны" — живые существа: растения, деревья, цветы, животные, рыбы, птицы, насекомые, грибы
• "Географический объект" — места с координатами: музей, заповедник, остров, гора, памятник, маяк, пещера, город, посёлок, турбаза, санаторий, горнолыжная база
• "Услуга" — информационные запросы: расписание, правила посещения, цена, билеты, контакты, часы работы, режим работы, как добраться, телефон
  Примеры Услуги: "Режим работы музея", "Как купить билет", "Как добраться до Байкала", "Контакты заповедника"
ЗАПРЕЩЕНО сокращать: "Объект фауны" и "Объект флоры" — не допустимые значения. Только полная фраза "Объект флоры и фауны".

═══ СЛОТ 2: synonym (null если нет конкретного названия) ═══
Конкретное название вида или объекта из запроса в именительном падеже.
null — если пользователь ищет класс объектов (без конкретного вида/места).
ВАЖНО: Общие категориальные слова НЕ являются synonym:
  × Неверно: "животные", "растения", "рыбы", "птицы", "музеи", "турбазы", "заповедники"
  ✓ Верно: "нерпа", "омуль", "Байкальский музей СО РАН", "Баргузинский заповедник", "Pandion haliaetus"
Для Услуги synonym — объект, к которому относится запрос:
  "Как купить билет в Байкальский музей?" → synonym="Байкальский музей СО РАН"
  "Режим работы Баргузинского заповедника" → synonym="Баргузинский заповедник"
  "Как добраться до Байкала?" → synonym=null (Байкал это location, не объект услуги)

═══ СЛОТ 3: modality (обязательный) ═══
В какой форме нужен ответ:
• "Текст"       — цель запроса: описание, рассказ, история, список объектов
• "Изображение" — маркеры: "покажи", "фото", "картинку", "как выглядит"
• "Геоданные"   — маркеры: "на карте", "где растёт", "где обитает", "ареал", "рядом с", "около", "поблизости"

═══ СЛОТ 4: features (словарь, {{}} если нет) ═══
ПРАВИЛО 1: Ключ "location" — топоним (город, остров, река) — заполняется для ЛЮБОЙ modality.
ПРАВИЛО 2: Остальные ключи features — ТОЛЬКО при modality="Изображение".

РАЗГРАНИЧЕНИЕ location vs habitat vs baikal_relation:
• "на побережье", "в горах", "в лесу" → features.habitat (тип среды, НЕ топоним)
• "в Иркутске", "на острове Ольхон", "из Иркутска" → features.location
• "в Байкале", "на Байкале", "рядом с Байкалом" → НЕ features.location — это properties.baikal_relation

Разрешённые ключи (кроме location) и точные значения:
  season: ["Осень", "Зима", "Весна", "Лето"]
  habitat: ["Сад", "Море", "Пустыня", "Луг", "Болото", "Городская среда", "Поле", "Лес", "Озеро", "Горы", "Побережье", "Река"]
  fauna_type: ["Рыба", "Ёж", "Птица", "Паукообразное", "Млекопитающее", "Земноводное"]
  flora_type: ["Травянистое растение", "Кустарник", "Мох", "Папоротник", "Сибирский Кедр", "Цветущее растение"]
  flowering: ["Да", "Нет"]
  fruits_present: ["Шишка", "Нет"]
  cloudiness: ["Ясно", "Переменная облачность", "Пасмурно"]

═══ СЛОТ 5: properties (словарь, {{}} если нет явных фильтров) ═══
Постоянные атрибуты объекта в базе данных.

Для "Объект флоры и фауны":
  "тип офф": ["Объект флоры", "Объект фауны"]
    ОБЯЗАТЕЛЬНО заполнять, если в запросе упоминается класс организмов вместо конкретного вида:
    → "Объект флоры": слова растения, растение, цветы, цветок, деревья, дерево, флора, трава, мох, гриб
    → "Объект фауны": слова животные, животное, зверь, птицы, птица, рыбы, рыба, насекомые, фауна
    Примеры: "Какие растения на Ольхоне" → тип офф = "Объект флоры"
             "Редкие птицы Байкала" → тип офф = "Объект фауны"
             "Расскажи о лиственнице" → тип офф НЕ заполнять (есть конкретный вид = synonym)

  "baikal_relation": ["в/на Байкале", "рядом/около Байкала", "неизвестно"]
    ОБЯЗАТЕЛЬНО заполнять если в запросе явно написано слово "Байкал" или "байкальский".
    НЕ заполнять если упомянут Ольхон, Листвянка, Баргузин и другие места — они идут в features.location.
    Примеры:
      "Какая флора есть на Байкале?" → тип офф="Объект флоры" + baikal_relation="в/на Байкале"
      "Какие животные живут на Байкале?" → тип офф="Объект фауны" + baikal_relation="в/на Байкале"
      "Заповедники рядом с Байкалом" → subtypes="Заповедник" + baikal_relation="рядом/около Байкала"
      "растения на Ольхоне" → baikal_relation НЕ заполнять, Ольхон → features.location

Для "Географический объект":
  "subtypes": категория объекта — одно из: Музей, Заповедник, Заказник, Нацпарк,
    природоохранная территория, Памятник, Маяк, Достопримечательность, Храм,
    Гора, Хребет, Залив, Озеро, Река, Пещера, Скала, Остров, Мыс,
    Турбаза, Горнолыжная база, Санаторий, Горячие источники,
    образовательное учреждение, Наука, Государственное учреждение,
    Населённый пункт, Город, Посёлок, Село, Этнографические музеи

  "baikal_relation": ["в/на Байкале", "рядом/около Байкала", "неизвестно"]
    ОБЯЗАТЕЛЬНО при явном слове "Байкал". subtypes и baikal_relation совместимы!
    Примеры:
      "Заповедники рядом с Байкалом" → subtypes="Заповедник" + baikal_relation="рядом/около Байкала"
      "Достопримечательности Байкала" → subtypes="Достопримечательность" + baikal_relation="в/на Байкале"
      "Музеи в Иркутске" → subtypes="Музей" + features.location="Иркутск" (НЕ baikal_relation)

═══ СЛОТ 6: extra (словарь, {{}} если нет) ═══
Свойства из запроса, которых нет в словарях properties выше. Свободная форма.
  "редкие растения" → extra: {{"редкость": "редкие"}}
  "краснокнижные птицы" → extra: {{"охранный статус": "краснокнижные"}}
  "эндемичные виды" → extra: {{"эндемизм": "эндемичные"}}
Не дублировать то, что уже попало в properties.

═══ ВАЖНЫЕ ПРАВИЛА ═══
1. object_type — РОВНО одна из трёх допустимых фраз, без сокращений
2. synonym — только конкретное имя собственное, null для классов/категорий
3. Не выдумывай топонимы и атрибуты — только то, что явно есть в запросе
4. baikal_relation — ОБЯЗАТЕЛЬНО при слове "Байкал"; subtypes и baikal_relation совместимы
5. тип офф — ВСЕГДА заполнять при словах-классах (растения, животные, птицы, рыбы и т.д.)
6. Верни ТОЛЬКО JSON без пояснений, обёрток и комментариев

ЗАПРОС: {query}

Ответь строго JSON:
{{"object_type": "...", "synonym": "...", "properties": {{}}, "features": {{}}, "extra": {{}}, "modality": "..."}}
"""

# ── Нормализация галлюцинаций LLM ─────────────────────────────────────────────

_OBJECT_TYPE_ALIASES = {
    "Объект фауны": "Объект флоры и фауны",
    "Объект флоры": "Объект флоры и фауны",
    "Объект фауны и флоры": "Объект флоры и фауны",
    "Флора и фауна": "Объект флоры и фауны",
    "Фауна": "Объект флоры и фауны",
    "Флора": "Объект флоры и фауны",
}

_BAIKAL_NEAR_RE = re.compile(
    r"рядом\s+с\s+байкал|около\s+байкал|возле\s+байкал|у\s+байкал", re.IGNORECASE
)
_BAIKAL_RE = re.compile(r"байкал", re.IGNORECASE)

_FLORA_WORDS = {"растения", "растение", "цветы", "цветок", "деревья", "дерево", "флора", "трава", "мох", "грибы", "гриб"}
_FAUNA_WORDS = {"животные", "животное", "зверь", "звери", "птицы", "птица", "рыбы", "рыба", "насекомые", "насекомое", "фауна"}

_SERVICE_MARKERS = {
    "режим работы", "часы работы", "расписание", "стоимость посещения",
    "как купить билет", "купить билет", "как добраться", "правила посещения",
    "контакты", "телефон", "как проехать",
}

_HABITAT_WORDS = {
    "побережье", "берег", "горы", "гора", "лес", "болото", "луг",
    "река", "озеро", "море", "поле", "степь", "сад", "пустыня"
}


def _detect_ambiguity(query: str, modality: str) -> bool:
    """
    Лингвистические правила двусмысленности модальности.
    LLM этот флаг не выставляет — ненадёжна в мета-рефлексии.
    """
    q = query.lower()
    has_map_marker = any(w in q for w in ["карт", "на карте"])
    has_near_marker = any(w in q for w in ["рядом", "около", "возле", "в районе", "поблизости"])

    if modality == "Геоданные" and "где" in q and not has_map_marker:
        return True

    if modality == "Изображение" and has_near_marker and not has_map_marker:
        if not any(h in q for h in _HABITAT_WORDS):
            return True

    return False


def _post_process_slots(query: str, slots: dict) -> dict:
    """
    Детерминированные поправки к выводу LLM:
    1. Определение Услуги по ключевым маркерам запроса
    2. Fallback тип офф из ключевых слов для ОФФ без синонима
    3. Fallback baikal_relation при явном слове "Байкал"
    4. Очистка baikal_relation когда "байкал" часть синонима, а не локация
    5. Перенос properties.location → features.location (LLM иногда путает)
    """
    q_lower = query.lower()
    props = dict(slots.get("properties") or {})
    features = dict(slots.get("features") or {})
    synonym = (slots.get("synonym") or "").lower()

    # ── 1. Определение Услуги по маркерам ────────────────────────────────────
    if slots.get("object_type") != "Услуга":
        for marker in _SERVICE_MARKERS:
            if marker in q_lower:
                slots["object_type"] = "Услуга"
                break

    # ── 2. Fallback тип офф (только для ОФФ, только без синонима) ────────────
    if slots.get("object_type") == "Объект флоры и фауны" and not slots.get("synonym"):
        if "тип офф" not in props:
            q_words = set(re.findall(r'\w+', q_lower))
            has_flora = bool(q_words & _FLORA_WORDS)
            has_fauna = bool(q_words & _FAUNA_WORDS)
            if has_flora and not has_fauna:
                props["тип офф"] = "Объект флоры"
            elif has_fauna and not has_flora:
                props["тип офф"] = "Объект фауны"
            # Оба → не устанавливаем (запрос о флоре И фауне одновременно)

    # ── 3. Очистка baikal_relation если "байкал" — часть синонима ────────────
    # Пример: "Байкальский музей" содержит "байкал", но это имя объекта, не озеро
    if "байкал" in synonym and "baikal_relation" in props:
        del props["baikal_relation"]

    # ── 4. Fallback baikal_relation при явном упоминании Байкала ─────────────
    if "baikal_relation" not in props and _BAIKAL_RE.search(query) and "байкал" not in synonym:
        if _BAIKAL_NEAR_RE.search(query):
            props["baikal_relation"] = "рядом/около Байкала"
        else:
            props["baikal_relation"] = "в/на Байкале"

    # ── 5. LLM иногда кладёт location в properties — переносим в features ────
    if "location" in props and not features.get("location"):
        features["location"] = props.pop("location")

    slots["properties"] = props
    slots["features"] = features
    return slots


class SlotResult(BaseModel):
    model_config = ConfigDict(extra='forbid')
    object_type: Optional[Literal["Объект флоры и фауны", "Географический объект", "Услуга"]] = None
    synonym: Optional[str] = None
    properties: Dict[str, Any] = Field(default_factory=dict)
    features: Dict[str, Any] = Field(default_factory=dict)
    extra: Dict[str, Any] = Field(default_factory=dict)
    modality: Literal["Текст", "Изображение", "Геоданные"] = "Текст"

    @field_validator('object_type', mode='before')
    @classmethod
    def normalize_object_type(cls, v):
        """Исправляет типичные сокращения LLM до канонического значения."""
        return _OBJECT_TYPE_ALIASES.get(v, v)


def _determine_template(slots: dict) -> Optional[str]:
    obj_type = slots.get("object_type")
    synonym = slots.get("synonym")
    properties = slots.get("properties") or {}
    features = slots.get("features") or {}
    extra = slots.get("extra") or {}
    modality = slots.get("modality", "Текст")

    feat_location = features.get("location")
    baikal_rel = properties.get("baikal_relation")
    # baikal_relation ("в/на Байкале", "рядом/около Байкала") засчитывается как location
    effective_location = feat_location or (baikal_rel if baikal_rel and baikal_rel != "неизвестно" else None)

    image_features = {k: v for k, v in features.items() if k != "location"}
    tipo_off = properties.get("тип офф")
    subtypes = properties.get("subtypes")
    # baikal_relation и тип офф — служебные поля, не "дополнительные фильтры"
    other_props = {k: v for k, v in properties.items() if k not in {"тип офф", "baikal_relation"}}

    # has_any_props: есть ли какие-то фильтры помимо базовой локации и типа
    # тип офф учитывается только при отсутствии синонима (с синонимом тип избыточен)
    if synonym:
        has_any_props = bool(other_props) or bool(extra)
    else:
        has_any_props = bool(tipo_off) or bool(other_props) or bool(extra)

    if obj_type == "Объект флоры и фауны":
        if synonym:
            if modality == "Текст":
                return "О2" if has_any_props else "О1"
            elif modality == "Изображение":
                return "О3" if image_features else "О4"
            elif modality == "Геоданные":
                # О5 — показать ареал конкретного вида в конкретном месте
                return "О5" if effective_location else "О6"
        else:
            if modality == "Геоданные" and effective_location:
                return "О11"
            if modality == "Изображение":
                # Фото категории объектов — всегда О9 (habitat опционален)
                return "О9"
            if effective_location:
                if tipo_off and not other_props and not extra:
                    return "О12"
                if has_any_props:
                    return "О8"
                return "О10"
            if has_any_props:
                return "О7"

    elif obj_type == "Географический объект":
        if synonym:
            if modality == "Геоданные":
                return "Г3"
            if effective_location:
                return "Г2"
            return "Г1"
        else:
            if subtypes and effective_location:
                return "Г5" if modality == "Геоданные" else "Г4"
            if subtypes:
                return "Г6"
            if effective_location:
                return "Г7"

    elif obj_type == "Услуга":
        if synonym:
            return "У2" if effective_location else "У1"
        if effective_location:
            return "У3"

    return None


class SlotClassifier:
    def __init__(self, provider: str = "qwen"):
        llm = LLMFactory.get_model(provider)
        self.parser = llm.with_structured_output(SlotResult, method="json_mode")

    async def classify(self, query: str) -> dict:
        prompt = CLASSIFICATION_PROMPT.format(query=query)
        logger.info(f"🔍 Classifying: '{query}'")
        try:
            result: SlotResult = await self.parser.ainvoke(prompt)
            slots = result.model_dump()
            slots = _post_process_slots(query, slots)
            slots["template"] = _determine_template(slots)
            slots["modality_ambiguous"] = _detect_ambiguity(query, slots["modality"])
            logger.info(f"🔍 Classification result: {slots}")
            return slots
        except Exception as e:
            logger.error(f"SlotClassifier error: {e}")
            return {
                "object_type": None,
                "synonym": None,
                "properties": {},
                "features": {},
                "extra": {},
                "modality": "Текст",
                "modality_ambiguous": False,
                "template": None,
                "error": str(e)
            }
