# DockerEcoBot — Архитектурная документация

> Telegram-бот эко-ассистент по флоре и фауне Байкальского региона.  
> Мультисервисная система на Docker Compose: 6 микросервисов, PostgreSQL/PostGIS, Redis, FAISS, LLM.

---

## Оглавление

1. [Топология системы](#1-топология-системы)
2. [Модуль: Telegram Bot](#2-модуль-telegram-bot)
   - 2.1 [Точка входа — `bot.py`](#21-точка-входа--botpy)
   - 2.2 [Dialogue System — оркестратор диалога](#22-dialogue-system--оркестратор-диалога)
   - 2.3 [Workers — NLU-анализаторы](#23-workers--nlu-анализаторы)
   - 2.4 [Action Handlers — исполнители запросов](#24-action-handlers--исполнители-запросов)
   - 2.5 [Utils — вспомогательный слой](#25-utils--вспомогательный-слой)
3. [Модуль: Backend API (`salut_bot`)](#3-модуль-backend-api-salut_bot)
   - 3.1 [SearchService — векторный поиск](#31-searchservice--векторный-поиск)
   - 3.2 [RelationalService — реляционная БД](#32-relationalservice--реляционная-бд)
   - 3.3 [GeoService — пространственные запросы](#33-geoservice--пространственные-запросы)
   - 3.4 [REST-маршруты](#34-rest-маршруты)
4. [Модуль: LLM-провайдеры](#4-модуль-llm-провайдеры)
5. [Модуль: База данных](#5-модуль-база-данных)
6. [Модуль: Инфраструктура (Redis · Nginx)](#6-модуль-инфраструктура-redis--nginx)
7. [Межсервисное взаимодействие](#7-межсервисное-взаимодействие)
8. [Pipeline: полный путь запроса](#8-pipeline-полный-путь-запроса)
   - 8.1 [Сценарий A — биологический объект](#81-сценарий-a--биологический-объект-покажи-фото-лиственницы-зимой)
   - 8.2 [Сценарий B — инфраструктурный запрос](#82-сценарий-b--инфраструктурный-запрос-какие-музеи-есть-в-иркутске)
   - 8.3 [Сценарий C — кореферентный запрос](#83-сценарий-c--кореферентный-запрос-а-где-он-обитает)
9. [Схема базы данных](#9-схема-базы-данных)
10. [Переменные окружения](#10-переменные-окружения)
11. [Ключевые архитектурные паттерны](#11-ключевые-архитектурные-паттерны)

---

## 1. Топология системы

```
┌─────────────────────────────────────────────────────────────────┐
│                        Docker Network: ecobot_net               │
│                                                                 │
│  ┌──────────┐    ┌──────────────┐    ┌───────────────────────┐  │
│  │ telegram │───▶│  backend     │───▶│  PostgreSQL/PostGIS   │  │
│  │  :bot    │    │  :5555       │    │  :5432                │  │
│  └────┬─────┘    └──────────────┘    └───────────────────────┘  │
│       │               │                                         │
│       │          ┌────▼─────┐                                   │
│       │          │  redis   │                                   │
│       │          │  :6379   │                                   │
│       │          └──────────┘                                   │
│       │                                                         │
│  ┌────▼──────────────────┐    ┌──────────────┐                  │
│  │  rasa        :5005    │    │  gigachat    │                  │
│  │  rasa-actions:5055    │    │  :5556       │                  │
│  └───────────────────────┘    └──────────────┘                  │
│                                                                 │
│  ┌──────────────────────────────────────────┐                   │
│  │  nginx :80  →  backend / admin / static  │                   │
│  └──────────────────────────────────────────┘                   │
└─────────────────────────────────────────────────────────────────┘

External: Ollama LLM (host.docker.internal:11434) | Telegram API | Sber GigaChat
```

| Сервис | Путь | Порт | Стек |
|--------|------|------|------|
| Telegram Bot | `EcoBotProject/TelegramBot/` | — | Python 3.10, aiogram 2.25 |
| Backend API | `salut_bot/` | 5555 | Python 3.10, Flask 3.1 |
| NLU (Rasa) | `EcoBotProject/RasaProject/` | 5005/5055 | Python 3.9, Rasa 3.9 |
| GigaChat Fallback | `EcoBotProject/GigaChatAPI/` | 5556 | Flask |
| Database | `db_custom/` | 5432 | PostgreSQL 14 + PostGIS 3.2 + pgvector 0.8 |
| Cache / Proxy | — | 6379 / 80 | Redis Alpine, Nginx Alpine |

---

## 2. Модуль: Telegram Bot

### 2.1 Точка входа — `bot.py`

**Назначение**: Точка приёма Telegram-событий, инициализация всех внутренних сервисов, финальный рендеринг ответа.

```
EcoBotProject/TelegramBot/
├── bot.py                          ← main entry point
├── config.py                       ← env vars, API_URLS mapping
└── logic/
    ├── DialogSystem/
    │   ├── orchestrator.py         ← DialogueSystem class
    │   ├── router.py               ← SemanticRouter
    │   ├── rewriter.py             ← QueryRewriter
    │   ├── state_manager.py        ← DialogueStateManager
    │   ├── schemas.py              ← UserRequest / SystemResponse / DialogueState
    │   └── workers/
    │       ├── biology.py          ← BiologyWorker
    │       ├── infrastructure.py   ← InfrastructureWorker
    │       └── knowledge.py        ← KnowledgeWorker
    └── action_handlers/
        ├── biological.py
        ├── geospatial.py
        └── sevices.py
```

**Ключевые функции `bot.py`**:

| Функция | Описание |
|---------|----------|
| `on_startup(dp)` | Инициализация: Redis → `RedisContextManager`, `DialogueSystem`, `RasaHandler`, heartbeat |
| `handle_main_logic(message)` | Главный handler: загружает контекст из Redis, создаёт `UserRequest`, вызывает `DialogueSystem.process_request()` |
| `render_system_response(message, response)` | Конвертация `SystemResponse` в Telegram-сообщение: текст / фото / карта / кнопки |
| `on_shutdown(dp)` | Закрытие aiohttp-сессий, Redis-соединений |

**Типы данных (schemas.py)**:

```python
UserRequest(
    user_id: int,
    query: str,
    context: List[Dict],   # история сообщений из Redis
    settings: UserSettings
)

SystemResponse(
    text: str,
    intent: str,           # BIOLOGY | INFRASTRUCTURE | KNOWLEDGE | CHITCHAT
    response_type: str,    # text | image | map | clarification_map
    buttons: List[List[Dict]],
    media_url: str | None,
    debug_info: str | None
)

DialogueState(
    intent: str,
    object_name: str,      # "лиственница сибирская"
    category: str,         # Flora | Fauna | Infrastructure
    location: str,
    attributes: Dict,      # {season, habitat, flowering, ...}
    last_action: str       # describe | show_map | show_image | list_items
)
```

---

### 2.2 Dialogue System — оркестратор диалога

#### `orchestrator.py` — `DialogueSystem`

Центральный конвейер обработки запроса. Вызывается из `bot.py` для каждого входящего сообщения.

```python
DialogueSystem.process_request(request: UserRequest) → List[SystemResponse]
```

**Внутренний pipeline** (линейный, с ранним выходом):

```
UserRequest
    │
    ▼ (1) QueryRewriter.rewrite()         — восстановление контекста
    │
    ▼ (2) SemanticRouter.get_intent()     — классификация интента
    │
    ├── BIOLOGY      → _run_biology_flow()
    ├── INFRASTRUCTURE → _run_infra_flow()
    ├── KNOWLEDGE    → _run_knowledge_flow()
    └── CHITCHAT     → прямой LLM-ответ
    │
    ▼ (3) Worker.analyze()                — NLU-анализ
    │
    ▼ (4) StateManager.merge_state()      — слияние с предыдущим состоянием
    │
    ▼ (5) ActionHandler.handle_*()        — HTTP-запрос к backend
    │
    ▼ List[SystemResponse]
```

**Инициализация**:
```python
DialogueSystem(
    provider="qwen",               # LLM: "qwen" | "gigachat"
    session=aiohttp.ClientSession,
    context_manager=RedisContextManager
)
```

---

#### `router.py` — `SemanticRouter`

**Назначение**: Определить домен запроса с минимальными затратами.

```python
SemanticRouter.get_intent(query: str, last_intent: str) → tuple[str, str]
# Returns: (intent, source)  # source = "fast_path" | "llm"
```

**Двухуровневая классификация**:

| Уровень | Метод | Примеры триггеров |
|---------|-------|-------------------|
| **1. Python fast path** | Regex / set lookup | "музей", "памятник" → INFRASTRUCTURE |
| | | слово из `biological_entity.txt` (1000+ видов) → BIOLOGY |
| | | "билет", "цена", "выставка" → KNOWLEDGE |
| **2. LLM fallback** | Qwen JSON-mode | Сложные семантически неоднозначные запросы |

LLM получает минимальную схему `Route(intent, confidence)` для экономии токенов.

---

#### `rewriter.py` — `QueryRewriter`

**Назначение**: Восстановить полный смысл запроса из фрагмента, опирающегося на историю диалога.

```python
QueryRewriter.rewrite(query: str, history: List[Dict]) → str
```

**Логика**:
1. Детектирует маркеры кореференции (24 русских местоимения и указательные: "он", "она", "этот", "там", "туда" …)
2. Извлекает упомянутый объект из последних ходов истории
3. Подставляет объект, формируя самодостаточный запрос

```
"А где он обитает?" + history[{query: "омуль"}]
    → "Где обитает омуль?"
```

Если маркеров нет — возвращает запрос без изменений.

---

#### `state_manager.py` — `DialogueStateManager`

**Назначение**: Сохранять когерентность диалога между ходами — не терять объект или контекст при уточняющих вопросах.

```python
DialogueStateManager.merge_state(
    current_nlu: WorkerAnalysis,
    previous_state: DialogueState,
    intent: str
) → DialogueState
```

**Правила слияния**:
- Если `object_name` изменился → новая тема, сбросить атрибуты
- Если `object_name` пустой → унаследовать от предыдущего состояния
- `location`, `attributes` — накапливаются и уточняются
- `last_action` — перезаписывается текущим действием

Хранение: `state:{user_id}` в Redis (TTL 900 с).

---

### 2.3 Workers — NLU-анализаторы

Каждый worker получает raw-текст запроса и возвращает структурированный анализ.

#### `workers/biology.py` — `BiologyWorker`

```python
BiologyWorker.analyze(query: str) → tuple[BiologyAnalysis, DebugTrace]
```

**BiologyAnalysis**:
```python
{
    action: "show_image" | "show_map" | "describe" | "list_items" | "find_nearby",
    species_name: str,
    category: "Flora" | "Fauna",
    attributes: {
        season: str,      # "Зима" | "Лето" | ...
        habitat: str,     # "Болото" | "Лес" | ...
        flowering: str
    }
}
```

**Гибридная стратегия**:

| Шаг | Метод | Что определяет |
|-----|-------|----------------|
| 1 | Python regex | `action` по словам: "фото/выглядит" → show_image, "карт/где" → show_map |
| 2 | Python regex | `attributes` по словам: "зим" → season:Зима, "болот" → habitat:Болото |
| 3 | LLM (Qwen) | `species_name`, `category` — семантическое извлечение сущностей |

LLM видит только минимальную схему `LLMBiologyExtraction(species_name, category)`.

---

#### `workers/infrastructure.py` — `InfrastructureWorker`

```python
InfrastructureWorker.analyze(query: str) → tuple[InfraAnalysis, DebugTrace]
```

**InfraAnalysis**:
```python
{
    action: "list_items" | "count_items" | "show_map" | "describe",
    object_name: str,       # "Байкальский музей"
    entity_type: str,       # "modern_human_made"
    category: str,          # "Достопримечательности"
    subcategory: List[str], # ["Музеи"]
    area_name: str          # "Иркутск"
}
```

---

#### `workers/knowledge.py` — `KnowledgeWorker`

```python
KnowledgeWorker.analyze(query: str) → KnowledgeAnalysis
# KnowledgeAnalysis(search_query: str, topic: str)
```

Обрабатывает FAQ, исторические справки, информацию о ценах/режимах работы.

---

### 2.4 Action Handlers — исполнители запросов

Принимают `DialogueState` + `WorkerAnalysis`, делают HTTP-запросы к backend, возвращают `CoreResponse`.

#### `action_handlers/biological.py`

| Функция | HTTP-вызов | Назначение |
|---------|-----------|-----------|
| `handle_get_picture()` | `POST /search_images_by_features` | Найти фото вида с фильтром по атрибутам |
| `handle_get_description()` | `GET /object/description/` | Получить описание вида |
| `handle_draw_locate_map()` | `POST /coords_to_map` | Построить карту ареала |
| `handle_nearest()` | `GET /get_coords` | Найти ближайшие объекты |
| `handle_objects_in_polygon()` | `POST /objects_in_polygon_simply` | Виды в границах области |

#### `action_handlers/geospatial.py`

| Функция | HTTP-вызов | Назначение |
|---------|-----------|-----------|
| `handle_geo_request()` | `POST /objects_in_area_by_type` | Поиск объектов в районе |
| `handle_draw_map_of_infrastructure()` | `POST /coords_to_map` | Карта инфраструктуры |

**CoreResponse** (унифицированный формат между handlers и `bot.py`):
```python
{
    type: "text" | "image" | "map" | "clarification_map" | "debug",
    content: str,
    static_map: str | None,      # URL PNG-карты
    interactive_map: str | None, # URL HTML-карты (Folium)
    buttons: List[List[Dict]],
    used_objects: List[Dict]
}
```

---

### 2.5 Utils — вспомогательный слой

#### `utils/context_manager.py` — `RedisContextManager`

Асинхронное хранилище контекста пользователя в Redis.

```python
get_context(user_id: int) → Dict        # история + состояние
set_context(user_id: int, data: Dict)   # сохранить с TTL=900с
delete_context(user_id: int)            # сбросить сессию
```

**Ключи Redis**:
- `gigachat_context:{user_id}` — история сообщений (список ходов)
- `state:{user_id}` — `DialogueState` (сериализованный JSON)
- `clarify_options:{user_id}` — варианты уточнения (кнопки)

#### `utils/error_logger.py`

Структурированное логирование ошибок → `POST /log_error` → PostgreSQL `error_log`.

| Функция | Severity | Когда |
|---------|----------|-------|
| `log_critical()` | CRITICAL | Python exceptions, падение сервисов |
| `log_api_fail()` | ERROR | HTTP >= 400 от backend |
| `log_nlu_miss()` | WARNING | LLM вернул невалидный JSON |
| `log_zero_results()` | INFO | HTTP 200, но результатов нет |

#### `utils/bot_utils.py`

- `send_long_message()` — разбивка текста для лимита Telegram (4096 символов)
- `convert_llm_markdown_to_html()` — конвертация Markdown → Telegram HTML

#### `utils/settings_manager.py`

Загружает пользовательские настройки из JSON-файла: режим LLM (`gigachat` / `rasa`), `debug_mode`.

#### `utils/heartbeat.py`

Ping Redis каждые 60 секунд. Логирует потерю соединения.

---

## 3. Модуль: Backend API (`salut_bot`)

```
salut_bot/
├── api.py                      ← точка входа Flask
├── app/
│   ├── __init__.py             ← create_app(), DI-контейнер
│   └── routes/
│       ├── description.py      ← /object/description/
│       ├── area.py             ← /objects_in_area_by_type
│       ├── polygon.py          ← /objects_in_polygon_simply
│       ├── coordinates.py      ← /get_coords, /coords_to_map
│       ├── images.py           ← /search_images_by_features
│       ├── faiss.py            ← /vector_search
│       ├── database.py         ← /database_search
│       └── error_log.py        ← /log_error
└── core/
    ├── search_service.py       ← SearchService (фасад)
    ├── relational_service.py   ← RelationalService (PostgreSQL)
    └── geo_service.py          ← GeoService (PostGIS + Shapely)
```

**`create_app()`** инициализирует три singleton-сервиса, регистрирует blueprints, подключает Redis и CORS.

---

### 3.1 SearchService — векторный поиск

**Назначение**: Фасад, агрегирующий FAISS, реляционный поиск и генерацию LLM-ответа.

```python
SearchService.search_in_faiss(
    query: str,
    k: int = 10,
    threshold: float = 0.35
) → List[Dict]
```
Загружает FAISS-индекс при старте из `knowledge_base_scripts/Vector/faiss_index/`. Кодирует запрос через HuggingFace BGE-M3. Опционально применяет CrossEncoder reranking (если доступен CUDA).

```python
SearchService.resolve_object_synonym(
    object_name: str,
    object_type: str
) → Dict   # {main_form, object_type, resolved: bool}
```
Нормализация: "лапчатка ольхонская" → канонический вид из `object_synonyms.json`.

```python
SearchService.search_images_by_features(
    species_name: str,
    features: Dict   # {season, habitat, cloudiness, location, date}
) → Dict
```

```python
SearchService._generate_llm_answer(
    question: str,
    context: List[str]
) → Dict   # {content, finish_reason, success}
```
RAG-генерация: контекст из FAISS/реляционных результатов → Qwen / GigaChat.

---

### 3.2 RelationalService — реляционная БД

**Назначение**: Все SQL-запросы к PostgreSQL. Не содержит бизнес-логики.

```python
RelationalService.search_images_by_features(
    species_name: str,
    features: Dict,
    synonyms_data: Dict
) → Dict
# SQL: biological_entity → entity_relation → image_content (WHERE feature_data @> filters)
```

```python
RelationalService.get_object_descriptions(
    object_name: str,
    entity_type: str,
    in_stoplist: int   # 1=включить стоп-лист, 0=исключить
) → List[str]
```

```python
RelationalService.get_objects_in_area_by_type(
    area_geometry: GeoJSON,
    object_type: str,
    object_subtype: str,
    object_name: str,
    limit: int,
    search_around: bool,
    buffer_radius_km: float
) → List[Dict]
# SQL: ST_Contains(area.geometry, obj.geometry) | ST_DWithin для буфера
```

```python
RelationalService.log_error_to_db(
    user_query: str,
    error_message: str,
    context: Dict,
    additional_info: Dict
) → tuple[bool, int, str]   # (success, error_id, message)
```

---

### 3.3 GeoService — пространственные запросы

**Назначение**: PostGIS-запросы + геометрические операции через Shapely.

```python
GeoService.get_nearby_objects(
    lat: float, lon: float,
    radius_km: float,
    limit: int,
    object_type: str,
    species_name: str
) → List[Dict]
# SQL: ST_DWithin(geometry, ST_MakePoint(lon, lat)::geography, radius_m)
# Кэш: @lru_cache(maxsize=1000)
```

```python
GeoService.get_objects_in_polygon(
    polygon_geojson: Dict,
    buffer_radius_km: float,
    object_type: str,
    limit: int
) → List[Dict]
```

```python
GeoService.clip_geometries_to_buffer(
    geometries: List[Dict],
    buffer_geometry: Dict
) → List[Dict]
# Оптимизация: Shapely prepared geometry вместо SQL-клиппинга
# ~10–50ms vs 500–2000ms через PostGIS для 100 геометрий
```

---

### 3.4 REST-маршруты

| Метод | Endpoint | Назначение | Параметры |
|-------|----------|-----------|-----------|
| GET/POST | `/object/description/` | Описание объекта (текст + RAG) | `object_name`, `query`, `limit`, `use_gigachat_answer` |
| POST | `/search_images_by_features` | Поиск фото по атрибутам | `species_name`, `features` |
| GET | `/get_coords` | Координаты вида | `query` |
| POST | `/coords_to_map` | Построить карту (Folium) | `lat`, `lon`, `species_name`, `attributes` |
| POST | `/objects_in_area_by_type` | Объекты в районе | `area_name`, `object_type`, `object_subtype` |
| POST | `/objects_in_polygon_simply` | Объекты в полигоне | `name`, `buffer_radius_km`, `object_type` |
| POST | `/vector_search` | Сырой FAISS-поиск | `query`, `k`, `threshold` |
| POST | `/database_search` | Сырой SQL-поиск | `object_name`, `object_type` |
| POST | `/log_error` | Логирование ошибок | `user_query`, `error_message`, `context` |

**Кэширование маршрутов** (Redis):
- `/object/description/` → ключ `cache:description:{object_name}:{filters_hash}`
- `/objects_in_polygon_simply` → ключ `cache:polygon_simply:{name}:{buffer}`
- `/objects_in_area_by_type` → ключ `cache:area_search:{area}:{type}`

---

## 4. Модуль: LLM-провайдеры

### Qwen (Ollama) — основной

- Запущен локально на хосте: `host.docker.internal:11434`
- Интерфейс: OpenAI-совместимый REST (`/v1/chat/completions`)
- Режимы: текстовая генерация, JSON-mode для структурированного извлечения
- Переключение: `LLM_PROVIDER=qwen` в `.env`

### GigaChat — fallback

```
EcoBotProject/GigaChatAPI/giga_api.py
Flask :5556

POST /ask_simple
  {question: str} → {answer: str}
```

Используется: при недоступности Qwen или в режиме `LLM_PROVIDER=gigachat`.  
Провайдер: `langchain_gigachat`, ключ `SBER_KEY_ENTERPRICE`.

### Rasa NLU — legacy

```
EcoBotProject/RasaProject/
  rasa:5005      — Core (NLU + dialogue policies)
  rasa-actions:5055 — Action server

POST rasa:5005/webhooks/rest/webhook
  {sender: user_id, message: query}
```

Используется в `RasaHandler` как альтернативный путь обработки. Actions выполняют HTTP-запросы к тем же endpoint'ам backend.

---

## 5. Модуль: База данных

```
db_custom/
├── Dockerfile              ← postgres:14-alpine + PostGIS 3.2 + pgvector 0.8
└── init/                   ← SQL-скрипты инициализации
```

### Ключевые таблицы

```sql
-- Биологические объекты
biological_entity (
    id              SERIAL PRIMARY KEY,
    common_name_ru  TEXT,           -- "лиственница сибирская"
    scientific_name TEXT,           -- "Larix sibirica"
    category        TEXT,           -- "Flora" | "Fauna"
    in_stoplist     BOOLEAN         -- исключить из публичных результатов
)

-- Медиафайлы
image_content (
    id          SERIAL PRIMARY KEY,
    file_path   TEXT,
    title       TEXT,
    description TEXT,
    feature_data JSONB              -- {season, habitat, cloudiness, location, date}
)

-- Географические объекты
geographical_entity (
    id       SERIAL PRIMARY KEY,
    name     TEXT,
    geometry GEOMETRY(MultiPolygon, 4326)  -- PostGIS
)

-- Инфраструктурные объекты
modern_human_made (
    id          SERIAL PRIMARY KEY,
    name        TEXT,
    description TEXT,
    geometry    GEOMETRY(Point, 4326),
    category    TEXT,               -- "Достопримечательности"
    subcategory TEXT[]              -- ["Музеи", "Памятники"]
)

-- Связи между объектами
entity_relation (
    source_id   INT,
    source_type TEXT,
    target_id   INT,
    target_type TEXT,
    relation_type TEXT              -- "изображение объекта", "описание"
)

-- Ресурсы (тексты, PDF)
resource (
    id              SERIAL PRIMARY KEY,
    type            TEXT,           -- "Текст" | "Изображение"
    title           TEXT,
    content         TEXT,
    structured_data JSONB,
    identificator   JSONB
)

-- Лог ошибок бота
error_log (
    id              SERIAL PRIMARY KEY,
    user_query      TEXT,
    error_message   TEXT,
    context         JSONB,
    additional_info JSONB,
    created_at      TIMESTAMP DEFAULT NOW()
)
```

**Расширения PostgreSQL**:
- `PostGIS 3.2` — ST_Contains, ST_DWithin, ST_Buffer, ST_Intersection
- `pgvector 0.8` — хранение эмбеддингов (опционально)

---

## 6. Модуль: Инфраструктура (Redis · Nginx)

### Redis (:6379)

| Паттерн ключа | TTL | Содержимое |
|---------------|-----|-----------|
| `gigachat_context:{uid}` | 900с | История сообщений пользователя |
| `state:{uid}` | 900с | `DialogueState` (JSON) |
| `clarify_options:{uid}` | 300с | Варианты уточнения |
| `cache:description:{hash}` | 3600с | Результат `/object/description/` |
| `cache:polygon_simply:{hash}` | 3600с | Результат `/objects_in_polygon_simply` |
| `cache:area_search:{hash}` | 3600с | Результат `/objects_in_area_by_type` |

### Nginx (:80)

```nginx
/api/*    → backend:5555
/admin/*  → admin:5000
/maps/*   → /data/maps/ (статические Folium-карты)
/images/* → /data/images/ (фото объектов)
```

---

## 7. Межсервисное взаимодействие

### Граф зависимостей сервисов

```
telegram
  ├── redis               (context r/w, state r/w)
  ├── backend:5555        (HTTP/aiohttp — все запросы данных)
  ├── rasa:5005           (HTTP — legacy mode)
  └── gigachat:5556       (HTTP — LLM fallback)

backend:5555
  ├── postgres:5432       (psycopg2 — CRUD + PostGIS)
  ├── redis:6379          (результирующий кэш)
  └── ollama:11434        (HTTP — LLM RAG-генерация)

rasa-actions:5055
  └── backend:5555        (HTTP — данные для action-ответов)

nginx:80
  ├── backend:5555
  └── admin:5000
```

### Полная таблица HTTP-вызовов Bot → Backend

| Действие | Метод | Endpoint | Тело запроса |
|---------|-------|----------|-------------|
| Описание вида | GET | `/object/description/?object_name=&limit=` | — |
| Поиск фото | POST | `/search_images_by_features` | `{species_name, features}` |
| Координаты | GET | `/get_coords?query=` | — |
| Карта ареала | POST | `/coords_to_map` | `{lat, lon, species_name, attributes}` |
| Объекты в районе | POST | `/objects_in_area_by_type` | `{area_name, object_type, object_subtype}` |
| Объекты в полигоне | POST | `/objects_in_polygon_simply` | `{name, buffer_radius_km, object_type}` |
| Лог ошибки | POST | `/log_error` | `{user_query, error_message, context}` |

---

## 8. Pipeline: полный путь запроса

### 8.1 Сценарий A — биологический объект: "Покажи фото лиственницы зимой"

```
[1] Telegram → bot.py
    Событие: Message(user_id=42, text="Покажи фото лиственницы зимой")
    │
    ▼
[2] bot.py::handle_main_logic()
    Загрузить контекст: Redis.get("gigachat_context:42")
    Создать: UserRequest(user_id=42, query="...", context=[...])
    │
    ▼
[3] DialogueSystem.process_request(request)
    │
    ▼ [3.1] QueryRewriter.rewrite()
    Маркеры кореференции не найдены → запрос не изменён
    query = "Покажи фото лиственницы зимой"
    │
    ▼ [3.2] SemanticRouter.get_intent()
    Fast path: "лиственница" ∈ biological_entity.txt
    → intent = "BIOLOGY", source = "fast_path"
    │
    ▼ [3.3] BiologyWorker.analyze()
    Python:  "фото" → action = "show_image"
    Python:  "зим"  → attributes.season = "Зима"
    LLM:    species_name = "лиственница", category = "Flora"
    → BiologyAnalysis(action="show_image", species_name="лиственница",
                      attributes={season:"Зима"})
    │
    ▼ [3.4] DialogueStateManager.merge_state()
    previous_state = Redis.get("state:42") → None (первый запрос)
    → DialogueState(intent="BIOLOGY", object_name="лиственница",
                    category="Flora", attributes={season:"Зима"},
                    last_action="show_image")
    Redis.set("state:42", state, ex=900)
    │
    ▼ [3.5] action_handlers/biological.py::handle_get_picture()
    │
    ▼ HTTP POST backend:5555/search_images_by_features
    Body: {
        "species_name": "лиственница",
        "features": {"season": "Зима"}
    }
    │
    ▼ [4] SearchService.search_images_by_features()
    SearchService.resolve_object_synonym("лиственница") → "лиственница сибирская"
    RelationalService.search_images_by_features(
        species_name="лиственница сибирская",
        features={season:"Зима"},
        synonyms_data={...}
    )
    │
    ▼ SQL (PostgreSQL):
    SELECT ic.file_path, ic.title, ic.description
    FROM biological_entity be
    JOIN entity_relation er ON be.id = er.source_id
    JOIN image_content ic ON ic.id = er.target_id
    WHERE (be.common_name_ru ILIKE '%лиственница%'
           OR be.scientific_name ILIKE '%larix%')
      AND ic.feature_data->>'season' = 'Зима'
    LIMIT 5
    │
    ▼ Response: [{file_path: "/images/larix_winter_1.jpg", title: "...", ...}]
    │
    ▼ [5] CoreResponse(
        type="image",
        content="Лиственница сибирская зимой:\n...",
        static_map=None,
        media_url="/images/larix_winter_1.jpg",
        buttons=[[{text:"Описание", callback_data:"describe:лиственница"}]]
    )
    │
    ▼ [6] bot.py::render_system_response()
    type="image" → bot.send_photo(
        photo="http://nginx/images/larix_winter_1.jpg",
        caption="Лиственница сибирская зимой:\n...",
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    │
    ▼ [7] Telegram API → Пользователь получает фото с подписью и кнопкой
```

**Характерное время**: ~1.5–3 с (SQL ~100мс + Telegram API ~300мс + LLM entity extraction ~1–2с)

---

### 8.2 Сценарий B — инфраструктурный запрос: "Какие музеи есть в Иркутске?"

```
[1–2] bot.py → DialogueSystem (аналогично сценарию A)
    │
    ▼ [3.1] QueryRewriter → запрос не изменён
    │
    ▼ [3.2] SemanticRouter
    Fast path: "музей" → intent = "INFRASTRUCTURE"
    │
    ▼ [3.3] InfrastructureWorker.analyze()
    Python:  "какие" → action = "list_items"
    LLM:    object_name="музеи", category="Достопримечательности",
             subcategory=["Музеи"], area_name="Иркутск"
    │
    ▼ [3.4] StateManager → сохранить DialogueState в Redis
    │
    ▼ [3.5] action_handlers/geospatial.py::handle_geo_request()
    │
    ▼ HTTP POST backend:5555/objects_in_area_by_type
    Body: {
        "area_name": "Иркутск",
        "object_type": "modern_human_made",
        "object_subtype": "Музеи"
    }
    │
    ▼ [4] SearchService.get_objects_in_area_by_type()
    RelationalService.find_geometry("Иркутск")
    → SELECT geometry FROM geographical_entity WHERE name = 'Иркутск'
    → GeoJSON полигон города
    │
    GeoService.get_objects_in_area_by_type(area_geometry, "modern_human_made", "Музеи")
    → SQL:
    SELECT m.name, m.description, ST_AsGeoJSON(m.geometry) as geom,
           ST_Distance(m.geometry::geography, area.centroid) as distance
    FROM modern_human_made m
    WHERE ST_Contains(
        ST_GeomFromGeoJSON($area_geometry),
        m.geometry
    )
    AND m.subcategory @> ARRAY['Музеи']
    ORDER BY distance
    LIMIT 10
    │
    ▼ [{name:"Байкальский музей", description:"...", geom:{...}, distance:1200}, ...]
    │
    ▼ [5] CoreResponse(
        type="text",
        content="Найдено 5 музеев в Иркутске:\n1. Байкальский музей (1.2 км)\n2. ...",
        buttons=[[{text:"Показать на карте", callback_data:"map:Иркутск:музеи"}]]
    )
    │
    ▼ [6] bot.py::render_system_response()
    type="text" → bot_utils.send_long_message(text, parse_mode="HTML")
```

---

### 8.3 Сценарий C — кореферентный запрос: "А где он обитает?"

*Предыдущий ход пользователя: "Что такое омуль?"*

```
[1] Redis: gigachat_context:42 = [
    {role:"user",      content:"Что такое омуль?"},
    {role:"assistant", content:"Омуль — пресноводная рыба семейства..."}
]

[2] UserRequest(query="А где он обитает?", context=[...])
    │
    ▼ [3.1] QueryRewriter.rewrite(query, context)
    Детектировать маркер: "он" ∈ pronouns
    Извлечь объект из контекста: "омуль" (из последнего user-хода)
    Перезаписать: query = "Где обитает омуль?"
    │
    ▼ [3.2] SemanticRouter
    Fast path: "омуль" ∈ biological_entity.txt → intent = "BIOLOGY"
    │
    ▼ [3.3] BiologyWorker.analyze("Где обитает омуль?")
    Python: "где" → action = "show_map"
    LLM:   species_name = "омуль", category = "Fauna"
    │
    ▼ [3.4] StateManager.merge_state()
    previous_state.object_name = "омуль" (тот же объект)
    → объединить, обновить last_action = "show_map"
    │
    ▼ [3.5] handle_draw_locate_map()
    GET backend:5555/get_coords?query=омуль
    → coordinates: [{lat:53.5, lon:108.2, name:"озеро Байкал"}, ...]
    │
    POST backend:5555/coords_to_map
    Body: {species_name:"омуль", coordinates:[...], attributes:{}}
    │
    ▼ GeoService → Folium HTML-карта
    Nginx сохраняет: /data/maps/map_uuid.html
    │
    ▼ CoreResponse(type="map", static_map="/maps/map_uuid.png",
                   interactive_map="/maps/map_uuid.html")
    │
    ▼ bot.py → send_photo(map_png) + кнопка "Интерактивная карта" (URL)
```

---

## 9. Схема базы данных

```
biological_entity ──────────────────────┐
    id, common_name_ru, scientific_name  │ entity_relation
    category, in_stoplist                │ (source_id, source_type,
                                         │  target_id, target_type,
image_content ───────────────────────────┤  relation_type)
    id, file_path, title                 │
    feature_data (JSONB)                 │
                                         │
geographical_entity ─────────────────────┤
    id, name                             │
    geometry (PostGIS MultiPolygon)      │
                                         │
modern_human_made ───────────────────────┘
    id, name, geometry (PostGIS Point)
    category, subcategory[]

resource
    id, type, title, content
    structured_data (JSONB)

error_log
    id, user_query, error_message
    context (JSONB), created_at
```

---

## 10. Переменные окружения

### `EcoBotProject/TelegramBot/.env`

| Переменная | Назначение |
|-----------|-----------|
| `BOT_TOKEN` | Telegram Bot API ключ |
| `LLM_PROVIDER` | `qwen` \| `gigachat` |
| `LLM_BASE_URL` | `http://host.docker.internal:11434/v1` |
| `ECOBOT_API_BASE_URL` | `http://backend:5555` |
| `REDIS_HOST` | `redis` |
| `CONTEXT_TTL_SECONDS` | `900` |
| `RASA_WEBHOOK_URL` | `http://rasa:5005/webhooks/rest/webhook` |
| `GIGACHAT_FALLBACK_URL` | `http://gigachat:5556` |

### `salut_bot/.env`

| Переменная | Назначение |
|-----------|-----------|
| `DB_HOST`, `DB_USER`, `DB_PASSWORD` | PostgreSQL |
| `REDIS_HOST`, `REDIS_PORT` | Redis |
| `MAPS_DIR` | Путь для Folium-карт |
| `PUBLIC_BASE_URL` | `https://testecobot.ru` |
| `DOMAIN` | Публичный домен |

### `EcoBotProject/GigaChatAPI/.env`

| Переменная | Назначение |
|-----------|-----------|
| `SBER_KEY_ENTERPRICE` | GigaChat API ключ (Sber) |

---

## 11. Ключевые архитектурные паттерны

### Паттерн 1: Hybrid Python + LLM (экономия токенов)

```
Запрос
  │
  ├── Python fast path (regex/set lookup)  → действие за ~0мс
  │   Детерминировано: action, attributes
  │
  └── LLM (только если нужна семантика)   → ~1–2с
      Минимальная схема: {field1, field2}
      Не гоняем через LLM то, что можно через Python
```

### Паттерн 2: Event-driven State Machine через Redis

Каждый ход диалога — это операция read-modify-write над `DialogueState` в Redis.  
StateManager гарантирует когерентность: новый объект сбрасывает контекст, тот же объект накапливает атрибуты.

### Паттерн 3: Многоуровневый поиск

```
Запрос объекта
  1. Нормализация через synonym resolver
  2. Реляционный поиск (точное совпадение)
  3. FAISS fallback (семантическое совпадение, если реляционный пуст)
  4. RAG: LLM генерирует ответ по найденным документам
```

### Паттерн 4: Пространственная оптимизация

- **PostGIS** для тяжёлых spatial JOIN (`ST_Contains`, `ST_DWithin`)
- **Shapely prepared geometry** для клиппинга в памяти (~10–50мс vs ~500–2000мс в SQL)
- **LRU cache** на `get_nearby_objects` (1000 записей)

### Паттерн 5: Многоуровневый кэш

```
L1: In-process LRU (GeoService.get_nearby_objects)
L2: Redis (результаты поиска, TTL 3600с)
L3: FAISS (загружен в RAM при старте, не перезагружается)
```

### Паттерн 6: Структурированное логирование ошибок

Все ошибки бота сохраняются в PostgreSQL через `POST /log_error` с полным контекстом (запрос пользователя, трейс, состояние диалога) для последующего анализа через Admin Panel.

---

*Документ описывает состояние системы на апрель 2026. Актуальные endpoint'ы — в `salut_bot/app/routes/`. Актуальная конфигурация деплоя — в `docker-compose.yml`.*
