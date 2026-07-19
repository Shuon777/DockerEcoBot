# DockerEcoBot — Архитектурная документация

> Эко-ассистент по флоре и фауне Байкальского региона.  
> Мультисервисная система на Docker Compose: 9 сервисов, PostgreSQL/PostGIS, Redis, FAISS, LLM.

---

## Оглавление

1. [Топология системы](#1-топология-системы)
2. [Модуль: DialogService](#2-модуль-dialogservice)
   - 2.1 [Clean Architecture — слои](#21-clean-architecture--слои)
   - 2.2 [SlotClassifier — классификация запроса](#22-slotclassifier--классификация-запроса)
   - 2.3 [DialogueOrchestrator — оркестратор диалога](#23-dialogueorchestrator--оркестратор-диалога)
   - 2.4 [SlotSearchExecutor — исполнитель поиска](#24-slotsearchexecutor--исполнитель-поиска)
   - 2.5 [Точки входа: core-api и max](#25-точки-входа-core-api-и-max)
   - 2.6 [Utils — вспомогательный слой](#26-utils--вспомогательный-слой)
3. [Модуль: Backend API (`salut_bot`)](#3-модуль-backend-api-salut_bot)
   - 3.1 [FastAPI — основной API-слой](#31-fastapi--основной-api-слой)
   - 3.2 [search_api — бизнес-логика поиска](#32-search_api--бизнес-логика-поиска)
   - 3.3 [Пагинация (Pagination)](#33-пагинация-pagination)
   - 3.4 [REST-маршруты](#34-rest-маршруты)
4. [Модуль: LLM-провайдеры](#4-модуль-llm-провайдеры)
5. [Модуль: База данных](#5-модуль-база-данных)
6. [Модуль: AdminPanel](#6-модуль-adminpanel)
7. [Модуль: DSAPI — тестирование и валидация](#7-модуль-dsapi--тестирование-и-валидация)
8. [Модуль: Images Extractor](#8-модуль-images-extractor)
9. [Модуль: Инфраструктура (Redis · Nginx)](#9-модуль-инфраструктура-redis--nginx)
10. [Межсервисное взаимодействие](#10-межсервисное-взаимодействие)
11. [Pipeline: полный путь запроса](#11-pipeline-полный-путь-запроса)
    - 11.1 [Сценарий A — биологический объект](#111-сценарий-a--биологический-объект-покажи-фото-лиственницы-зимой)
    - 11.2 [Сценарий B — географический объект](#112-сценарий-b--географический-объект-где-находится-байкальский-музей)
    - 11.3 [Сценарий C — кореферентный запрос](#113-сценарий-c--кореферентный-запрос-а-где-он-обитает)
12. [Схема базы данных](#12-схема-базы-данных)
13. [Переменные окружения](#13-переменные-окружения)
14. [Ключевые архитектурные паттерны](#14-ключевые-архитектурные-паттерны)

---

## 1. Топология системы

```
┌──────────────────────────────────────────────────────────────────────┐
│                         Docker Network: ecobot_net                   │
│                                                                      │
│  ┌──────────┐    ┌──────────────┐    ┌────────────────────────────┐  │
│  │   max    │───▶│  core-api    │───▶│  backend :8000             │  │
│  │ (Max bot)│    │  :5001       │    │  (salut_bot, FastAPI)      │  │
│  └──────────┘    └──────┬───────┘    └─────────────┬──────────────┘  │
│                         │                          │                  │
│                    ┌────▼─────┐         ┌──────────▼──────────────┐  │
│                    │  redis   │         │  db (PostgreSQL/PostGIS) │  │
│                    │  :6379   │         │  :5432                  │  │
│                    └──────────┘         └─────────────────────────┘  │
│                                                                      │
│  ┌──────────┐    ┌──────────────┐    ┌────────────────────────────┐  │
│  │  admin   │    │    dsapi     │    │   images-extractor         │  │
│  │  :5000   │    │    :5050     │    │   (profile: extractor)     │  │
│  └──────────┘    └──────────────┘    └────────────────────────────┘  │
│                                                                      │
│  ┌───────────────────────────────────────────────────────────────┐   │
│  │  nginx :80/:443 → core-api / backend / admin / static         │   │
│  └───────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────┘

External: Ollama LLM (host.docker.internal:11434) | Max API (VK) | GigaChat API
```

| Сервис | Путь | Порт | Стек |
|--------|------|------|------|
| Max Bot | `EcoBotProject/DialogService/` | — | Python 3.10, max-bot SDK |
| Core API | `EcoBotProject/DialogService/` | 5001 | Python 3.10, FastAPI |
| Backend API | `salut_bot/` | **8000** | Python 3.10, **FastAPI** (uvicorn) |
| Admin Panel | `AdminPanel/` | 5000 | Python 3.10, FastAPI |
| DS API | `dsapi/` | 5050 | Python 3.10, FastAPI |
| Database | `db_custom/` | 5432 | PostgreSQL 14 + PostGIS 3.2 + pgvector 0.8 |
| Cache | — | 6379 | Redis Alpine |
| Proxy | — | 80 / 443 | Nginx Alpine + Let's Encrypt |
| Images Extractor | `images-extractor/` | — | Python, YOLO/SAM/BioCLIP (profile: extractor) |

> **Важно**: Backend API работает на **FastAPI** (порт **8000**). Flask-приложение (`app/`) и Flask-роуты (`search_api/routes/`) удалены. Вся бизнес-логика находится в пакете `search_api/`.

---

## 2. Модуль: DialogService

`EcoBotProject/DialogService/` — центральный сервис диалоговой логики. Реализован по принципам Clean Architecture и запускается в двух режимах: как HTTP API (`core-api`) и как бот Max (`max`).

### 2.1 Clean Architecture — слои

```
EcoBotProject/DialogService/
├── domain/                         ← Доменные сущности и интерфейсы
│   ├── entities.py                 ← UserRequest, SystemResponse, DialogueState, CoreResponse
│   └── interfaces/
│       ├── llm.py                  ← Интерфейс LLM-провайдера
│       └── storage.py              ← Интерфейс хранилища
├── application/                    ← Бизнес-логика
│   └── search/
│       ├── slot_classifier.py      ← SlotClassifier (LLM + fast-path)
│       ├── dialogue_orchestrator.py← DialogueOrchestrator (полный цикл)
│       ├── slot_search_executor.py ← SlotSearchExecutor (HTTP к backend)
│       └── context_manager.py      ← ConversationHistory (Redis)
├── infrastructure/                 ← Инфраструктурные адаптеры
│   ├── llm/factory.py              ← LLMFactory (Qwen / GigaChat)
│   ├── storage/redis_storage.py    ← RedisStorage
│   ├── db_feature_loader.py        ← Загрузка valid_features из БД при старте
│   └── max_bot/
│       ├── setup.py                ← bot, dp (max-bot SDK)
│       └── context.py              ← ctx (singleton runtime-контекст)
├── adapters/                       ← Интерфейсные адаптеры
│   ├── http/routes/
│   │   ├── search.py               ← POST /classify, POST /search_pipeline
│   │   └── config.py               ← GET /config (управление настройками)
│   └── max/
│       ├── handlers/
│       │   ├── messages.py         ← Обработчик текстовых сообщений
│       │   ├── commands.py         ← Обработчик команд (/start, /help …)
│       │   ├── callbacks.py        ← Обработчик callback-кнопок
│       │   └── attachments.py      ← Обработчик вложений (фото → naturalist)
│       └── presenter.py            ← Форматирование ответов для Max
├── utils/                          ← Утилиты
│   ├── error_logger.py
│   ├── entity_normalizer.py
│   ├── bot_utils.py
│   ├── history_helper.py
│   ├── inline_search.py
│   ├── feedback_manager.py
│   ├── stand_manager.py
│   └── baikal_context.py
├── api.py                          ← Точка входа core-api (FastAPI)
└── main_max.py                     ← Точка входа Max-бота
```

**Типы данных (domain/entities.py)**:

```python
UserRequest(user_id, query, context, settings)

SystemResponse(text, intent, response_type, buttons, media_url, debug_info)

DialogueState(intent, object_name, category, location, attributes, last_action, timestamp)

CoreResponse(type, content, buttons, static_map, interactive_map, used_objects, debug_info)
```

---

### 2.2 SlotClassifier — классификация запроса

**Назначение**: Извлечь из текста пользователя структурированные слоты для поиска.

```python
SlotClassifier.classify(query: str, prev_query: str | None, prev_promo: list) → dict
```

**Слоты**:

| Слот | Тип | Описание |
|------|-----|---------|
| `object_type` | str | `"Объект флоры и фауны"` / `"Географический объект"` / `"Услуга"` |
| `synonym` | str \| null | Конкретное название вида или объекта в именительном падеже |
| `modality` | str | `"Текст"` / `"Изображение"` / `"Геоданные"` |
| `features` | dict | Атрибуты изображения: `{"Время года": "Лето", "Среда обитания": "Лес"}` |
| `properties` | dict | Пространственные свойства: `{"Детальное расположение": "Иркутск"}` |
| `extra` | dict | Прочие параметры |
| `template` | str | Имя шаблона запроса к backend |

**Двухуровневая классификация**:

| Уровень | Метод | Применение |
|---------|-------|-----------|
| **1. Python fast-path** | Regex / словари | Очевидные маркеры: "фото" → Изображение, "где" → Геоданные |
| **2. LLM (JSON-mode)** | Qwen / GigaChat | Семантически сложные запросы, извлечение `synonym`, `object_type` |

LLM получает только минимальную схему слотов, что сокращает расход токенов.

---

### 2.3 DialogueOrchestrator — оркестратор диалога

Центральный конвейер. Вызывается для каждого входящего сообщения.

```python
DialogueOrchestrator.process(query: str, user_id: str | None, promo_enabled: bool | None) → dict
```

**Внутренний pipeline**:

```
query
  │
  ▼ (1) ConversationHistory.get_turns()   — история из Redis
  │
  ▼ (2) SlotClassifier.classify()         — извлечение слотов
  │
  ▼ (3) _merge_with_context()             — наследование слотов из предыдущего хода
  │       • synonym пустой → наследуем из предыдущего хода
  │       • synonym изменился → новая тема, сбросить features
  │       • features: предыдущие + новые (если нет явной отмены)
  │
  ▼ (4) _resolve_promo_ref()              — разрешение ссылок на промо-объекты
  │
  ▼ (5) SlotSearchExecutor.execute()      — HTTP-запрос к backend
  │
  ▼ (6) _try_simplifications()            — если нет результатов: снимаем фильтры
  │       параллельная проверка вариантов, кэш в Redis (TTL 300с)
  │
  ▼ (7) _build_proactive()               — что предложить после ответа
  │
  ▼ (8) ConversationHistory.add_turn()    — сохранить ход в Redis
  │
  ▼ dict { result, proactive, simplifications, timing, ... }
```

**Хранение истории**:  
`ConversationHistory` хранит последние N ходов (`DialogueTurn`) в Redis как JSON-список. Каждый ход содержит: `query`, `slots`, `had_results`, `promo_objects`.

---

### 2.4 SlotSearchExecutor — исполнитель поиска

**Назначение**: По слотам сформировать HTTP-запрос к `backend:8000` и вернуть результат.

```python
SlotSearchExecutor.execute(query: str, slots: dict, user_id: str | None, promo_enabled: bool | None, context: dict) → dict
```

Выбирает `template` из слотов и маппит его на endpoint backend'а. Результат содержит `result` (данные для ответа) и `search` (сырые данные из БД).

---

### 2.5 Точки входа: core-api и max

#### `api.py` — Core API (FastAPI)

HTTP-интерфейс для DialogService. Используется клиентами (в т.ч. Max-ботом через HTTP или внешними системами).

```
POST /classify        — только классификация слотов (без поиска)
POST /search_pipeline — полный цикл: классификация → контекст → поиск → проактивность
GET  /config          — чтение/запись настроек бота
```

При старте загружает `valid_features` из БД (`db_feature_loader.py`), создаёт общую `aiohttp.ClientSession`.

#### `main_max.py` — Max Bot

Бот для Max. Режимы: polling или webhook (`MAX_USE_WEBHOOK=true`).

| Обработчик | Файл | Назначение |
|-----------|------|-----------|
| Команды | `adapters/max/handlers/commands.py` | `/start`, `/help` и т.п. |
| Сообщения | `adapters/max/handlers/messages.py` | Текстовые запросы → orchestrator |
| Callbacks | `adapters/max/handlers/callbacks.py` | Нажатие inline-кнопок |
| Вложения | `adapters/max/handlers/attachments.py` | Фото → `PlantIdentifier` (naturalist) |

**Натуралист** (`application/naturalist/plant_identifier.py`): распознавание растений по фото через vision-LLM.

---

### 2.6 Utils — вспомогательный слой

| Утилита | Назначение |
|---------|-----------|
| `error_logger.py` | Структурированное логирование ошибок → `POST /log_error` → PostgreSQL |
| `entity_normalizer.py` | Нормализация имён сущностей (регистр, синонимы) |
| `bot_utils.py` | Форматирование текста, разбивка длинных сообщений |
| `history_helper.py` | Вспомогательные операции над историей диалога |
| `inline_search.py` | Формирование inline-кнопок из результатов поиска |
| `feedback_manager.py` | Сбор и сохранение пользовательских оценок |
| `stand_manager.py` | Управление режимами стенда (prod/test) |
| `baikal_context.py` | Статический байкальский контекст для LLM |
| `heartbeat.py` | Ping Redis каждые 60 секунд |

---

## 3. Модуль: Backend API (`salut_bot`)

```
salut_bot/
├── main_fastapi.py             ← Точка входа FastAPI (uvicorn, порт 8000)
├── fastapi_app/                ← FastAPI-приложение
│   ├── main.py                 ← FastAPI app factory
│   ├── database.py             ← POST /reload_database
│   └── routes/
│       ├── search.py           ← POST /search (главный поиск)
│       ├── place.py            ← POST /search/place/objects
│       ├── related.py          ← POST /objects/related
│       └── description.py      ← GET/POST /object/description, /species/description
├── search_api/                 ← Бизнес-логика поиска (Clean Architecture)
│   ├── domain/
│   │   ├── entities.py         ← Pagination, SearchRequest, SearchResponse, ...
│   │   ├── place_entities.py   ← PlaceSearchRequest, PlaceSearchResponse
│   │   └── value_objects.py    ← ModalityType, GeoContent
│   ├── use_cases/
│   │   ├── search_use_case.py          ← SearchUseCase
│   │   ├── search_and_build_use_case.py← SearchAndBuildUseCase
│   │   └── place_search_use_case.py    ← PlaceSearchUseCase
│   ├── adapters/
│   │   ├── search_repository.py        ← SearchRepository (ABC)
│   │   ├── sqlalchemy_repository.py    ← SQLAlchemySearchRepository
│   │   ├── database.py                 ← PostgresSearchRepository (psycopg2)
│   │   └── vector_search_adapter.py    ← VectorSearchPort
│   └── services/
│       ├── response_builder.py         ← ResponseBuilder
│       ├── llm_answer_generator.py     ← LLMAnswerGenerator
│       └── geo_map_service.py          ← GeoMapService
├── app/                         ← Устаревшее Flask-приложение (не используется)
│   ├── config.py                ← Конфигурация (используется fastapi_app)
│   ├── services.py              ← Singleton-сервисы (используется fastapi_app)
│   └── utils.py                 ← Утилиты (используется fastapi_app)
└── core/                        ← Базовые сервисы
    ├── search_service.py        ← SearchService (фасад)
    ├── relational_service.py    ← RelationalService (PostgreSQL)
    └── geo_service.py           ← GeoService (PostGIS + Shapely)
```

### 3.1 FastAPI — основной API-слой

Backend API работает на **FastAPI** (uvicorn, порт **8000**). Запускается через:

```bash
uvicorn main_fastapi:app --host 0.0.0.0 --port 8000
```

**Основные эндпоинты FastAPI**:

| Метод | Endpoint | Назначение |
|-------|----------|-----------|
| POST | `/search` | Главный поиск: объекты + ресурсы по сложным критериям |
| POST | `/search/place/objects` | Поиск объектов вблизи именованного места |
| POST | `/objects/related` | Связанные / промо-объекты для списка ID |
| GET/POST | `/object/description` | Описание объекта (текст + RAG + FAISS fallback) |
| GET | `/species/description` | Описание биологического вида |
| POST | `/reload_database` | Перезагрузка БД из `resources_dist.json` |

### 3.2 search_api — бизнес-логика поиска

Пакет `search_api/` реализован по принципам Clean Architecture:

- **domain/** — сущности: `Pagination`, `SearchRequest`, `SearchResponse`, `ObjectCriteria`, `ResourceCriteria`, `PlaceSearchResponse`
- **use_cases/** — бизнес-логика: `SearchUseCase`, `PlaceSearchUseCase`, `SearchAndBuildUseCase`
- **adapters/** — репозитории: `SQLAlchemySearchRepository` (основной), `PostgresSearchRepository` (psycopg2, для тестов)
- **services/** — сервисы: `ResponseBuilder` (сериализация), `LLMAnswerGenerator`, `GeoMapService`

### 3.3 Пагинация (Pagination)

В ответ на поисковые запросы добавляется блок `pagination`:

```json
{
  "objects": [...],
  "pagination": {
    "total": 45,
    "limit": 10,
    "offset": 0,
    "next_offset": 10,
    "has_more": true
  }
}
```

**Поля**:

| Поле | Тип | Описание |
|------|-----|---------|
| `total` | int | Общее количество объектов (без учёта limit/offset) |
| `limit` | int | Максимум объектов на странице |
| `offset` | int | Смещение от начала |
| `next_offset` | int | Смещение для следующей страницы (`offset + limit`) |
| `has_more` | bool | Есть ли ещё объекты (`next_offset < total`) |

**Как работает**:

1. `SearchRequest` содержит `limit` (по умолчанию 20) и `offset` (по умолчанию 0)
2. Репозиторий выполняет два запроса:
   - `SELECT ... LIMIT {limit} OFFSET {offset}` — получение страницы
   - `SELECT COUNT(DISTINCT id) ...` — общее количество (без ORDER BY)
3. `SearchUseCase` вычисляет `Pagination` и добавляет в `SearchResponse`
4. `ResponseBuilder` сериализует `pagination` в JSON-ответ

**Пример запроса с пагинацией**:

```bash
curl -s -X POST http://backend:8000/search \
  -H "Content-Type: application/json" \
  -d '{
    "system_parameters": {
      "user_query": "нерпа",
      "limit": 1,
      "offset": 0,
      "debug": true
    },
    "search_parameters": {
      "object": {
        "name_synonyms": {"ru": ["байкальская нерпа"]}
      }
    }
  }'
```

**Результат тестирования** (2 объекта в БД):

| Параметры | objects | pagination |
|-----------|---------|------------|
| `limit=1, offset=0` | 1 (id=123) | `{"total": 2, "limit": 1, "offset": 0, "next_offset": 1, "has_more": true}` |
| `limit=1, offset=1` | 1 (id=242) | `{"total": 2, "limit": 1, "offset": 1, "next_offset": 2, "has_more": false}` |

### 3.4 REST-маршруты

#### FastAPI (`fastapi_app/routes/`)

| Метод | Endpoint | Назначение | Ключевые параметры |
|-------|----------|-----------|-------------------|
| POST | `/search` | Главный поиск: объекты + ресурсы | `system_parameters`, `search_parameters` |
| POST | `/search/place/objects` | Поиск объектов вблизи места | `place_name`, `subtypes`, `buffer_radius_km` |
| POST | `/objects/related` | Связанные / промо-объекты | `object_ids`, `relation_type` |
| GET/POST | `/object/description` | Описание объекта (RAG) | `object_name`, `query`, `use_gigachat_answer` |
| GET | `/species/description` | Описание биологического вида | `species_name`, `query` |
| POST | `/reload_database` | Перезагрузка БД | `reload_database`, `incremental` |

**Структура `/search`**:

```json
{
  "system_parameters": {
    "user_query": "string",
    "use_llm_answer": false,
    "limit": 20,
    "offset": 0,
    "debug": false
  },
  "search_parameters": {
    "modality_type": "Текст | Изображение | Геоданные",
    "object": {
      "identificator": { "db_id": 42 },
      "name_synonyms": { "ru_names": ["байкальская нерпа"] },
      "properties": { "Подтип объекта": "Музеи" },
      "object_type": "biological_entity | geographical_entity"
    },
    "resource": {
      "features": { "Время года": "Зима" },
      "modality": { "value": { "structured_data": { "taxonomy": {} } } }
    }
  }
}
```

**Общие соглашения**:
- Все поисковые ответы содержат `pagination` (см. [раздел 3.3](#33-пагинация-pagination))
- Параметр `debug=true` добавляет трассировку выполнения в поле `debug`
- Кэширование в Redis по хэшу параметров: TTL 30 мин – 1 ч

---

## 4. Модуль: LLM-провайдеры

### Qwen (Ollama) — основной

- Запущен локально на хосте: `host.docker.internal:11434`
- Интерфейс: OpenAI-совместимый REST (`/v1/chat/completions`)
- Режимы: текстовая генерация, JSON-mode для структурированного извлечения слотов
- Переключение: `LLM_PROVIDER=qwen` в `.env`

### GigaChat — fallback

- Интерфейс через `langchain_gigachat`, ключ `SBER_KEY_ENTERPRICE`
- Используется при `LLM_PROVIDER=gigachat` или недоступности Qwen
- Вызывается непосредственно из `LLMFactory` — отдельного контейнера нет

### LLMFactory (`infrastructure/llm/factory.py`)

Единая точка создания LLM-клиента. Принимает `provider: str` → возвращает имплементацию интерфейса `LLMProvider` из `domain/interfaces/llm.py`.

---

## 5. Модуль: База данных

```
db_custom/
├── Dockerfile              ← postgres:14-alpine + PostGIS 3.2 + pgvector 0.8
└── init.sql                ← SQL-скрипты инициализации
```

### Ключевые таблицы (схема `eco_assistant`)

```sql
-- Биологические объекты
biological_entity (
    id              SERIAL PRIMARY KEY,
    common_name_ru  TEXT,           -- "лиственница сибирская"
    scientific_name TEXT,           -- "Larix sibirica"
    category        TEXT,           -- "Flora" | "Fauna"
    in_stoplist     BOOLEAN
)

-- Медиафайлы
image_content (
    id           SERIAL PRIMARY KEY,
    file_path    TEXT,
    title        TEXT,
    description  TEXT,
    feature_data JSONB              -- {season, habitat, cloudiness, location, date}
)

-- Географические объекты
geographical_entity (
    id       SERIAL PRIMARY KEY,
    name     TEXT,
    geometry GEOMETRY(MultiPolygon, 4326)
)

-- Инфраструктурные объекты
modern_human_made (
    id          SERIAL PRIMARY KEY,
    name        TEXT,
    description TEXT,
    geometry    GEOMETRY(Point, 4326),
    category    TEXT,
    subcategory TEXT[]
)

-- Связи между объектами
entity_relation (
    source_id     INT,
    source_type   TEXT,
    target_id     INT,
    target_type   TEXT,
    relation_type TEXT
)

-- Ресурсы (тексты, PDF)
resource (
    id              SERIAL PRIMARY KEY,
    type            TEXT,
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
- `pgvector 0.8` — хранение эмбеддингов

---

## 6. Модуль: AdminPanel

```
AdminPanel/
├── main.py                     ← FastAPI-приложение
├── database.py                 ← Подключение к PostgreSQL
├── auth.py                     ← Авторизация администраторов
├── heartbeat.py                ← Мониторинг состояния сервисов
└── models/
    ├── models.py               ← ORM схема legacy (ErrorLog, BiologicalEntity…)
    ├── eco_assistant_models.py ← ORM схема eco_assistant (Object, Resource, Modality…)
    └── admin_models.py         ← ORM схема admin (AdminUser, TestSession)
```

**Функции**:
- Просмотр и редактирование объектов, ресурсов и их связей в схеме `eco_assistant`
- Управление синонимами объектов (`ObjectNameSynonym`)
- Просмотр лога ошибок бота
- Управление пользователями-администраторами

---

## 7. Модуль: DSAPI — тестирование и валидация

```
dsapi/
├── main.py                         ← FastAPI-приложение (:5050)
├── app/
│   ├── api/v1/endpoints/           ← REST-маршруты тестирования
│   ├── services/
│   │   ├── pipeline/               ← IntegratedDynamicPipeline
│   │   ├── generation/             ← Генераторы тестовых запросов (morph, typos, simple)
│   │   ├── text_validation/        ← Валидация текстовых ответов (нейронные + rule-based)
│   │   ├── image_validation/       ← Валидация изображений (NSFW, карта, семантика)
│   │   ├── llm_evaluator/          ← LLM-оценка качества ответов
│   │   └── clients/bot_client.py   ← HTTP-клиент к core-api
│   └── models/                     ← Pydantic-схемы запросов/ответов
└── setup_models.py                 ← Предзагрузка нейронных моделей
```

**Назначение**: Автоматическое тестирование диалоговой системы. Генерирует тестовые запросы (морфологические вариации, опечатки, шаблонные вопросы), отправляет их в Core API, валидирует ответы.

**Ключевые pipeline'ы**:
- **Static testing** — набор фиксированных тест-кейсов
- **Dynamic testing** — генерация запросов на лету из списка сущностей
- **LLM evaluation** — оценка качества ответа через отдельную LLM-модель

---

## 8. Модуль: Images Extractor

```
images-extractor/
├── Dockerfile
├── docker-compose.yml
├── objects/                    ← Описания объектов для поиска
├── photos/                     ← Входные фотографии
└── results/                    ← Результаты обработки
```

**Назначение**: Пайплайн извлечения и классификации изображений флоры и фауны для пополнения базы данных.

**Модели**:
- **YOLO + Grounding DINO** — детекция объектов на фото
- **SAM (Segment Anything Model)** — сегментация объектов
- **BioCLIP** — классификация биологических видов
- **BLIP** — генерация описаний изображений
- **OWLv2** — zero-shot детекция объектов

Запускается как отдельный профиль (`docker compose --profile extractor up images-extractor`), не входит в основной стек.

---

## 9. Модуль: Инфраструктура (Redis · Nginx)

### Redis (:6379)

| Паттерн ключа | TTL | Содержимое |
|---------------|-----|-----------|
| `history:{uid}` | 900с | История ходов диалога (JSON-список `DialogueTurn`) |
| `simplify:{uid}` | 300с | Варианты упрощения запроса (кнопки) |
| `cache:description:{hash}` | 3600с | Результат `/object/description/` |
| `cache:polygon_simply:{hash}` | 3600с | Результат `/objects_in_polygon_simply` |
| `cache:area_search:{hash}` | 3600с | Результат `/objects_in_area_by_type` |

### Nginx (:80 / :443)

```nginx
/api/*      → core-api:5001    (Core API / Dialog)
/backend/*  → backend:8000     (salut_bot, FastAPI)
/admin/*    → admin:5000
/maps/*     → /var/www/maps/   (статические Folium-карты)
/images/*   → /var/www/images/ (фото объектов)
```

SSL: Let's Encrypt через certbot (`/etc/letsencrypt`).

---

## 10. Межсервисное взаимодействие

### Граф зависимостей сервисов

```
max (bot)
  └── core-api:5001           (HTTP — search_pipeline, classify)

core-api / max (внутри DialogService)
  ├── redis:6379              (история диалога, упрощения)
  ├── backend:8000            (HTTP/aiohttp — все запросы данных)
  └── ollama:11434            (HTTP — LLM классификация и RAG)

backend:8000
  ├── postgres:5432           (psycopg2 — CRUD + PostGIS)
  ├── redis:6379              (результирующий кэш)
  └── ollama:11434            (HTTP — LLM RAG-генерация)

admin:5000
  └── postgres:5432           (asyncpg — чтение/запись eco_assistant)

dsapi:5050
  └── core-api:5001           (HTTP — запросы от bot_client)

nginx:80/443
  ├── core-api:5001
  ├── backend:8000
  └── admin:5000
```

### Таблица HTTP-вызовов core-api / max → backend

| Действие | Метод | Endpoint | Ключевые поля тела |
|---------|-------|----------|-------------------|
| Поиск текста / описаний | POST | `/search` | `modality_type="Текст"`, `object.name_synonyms`, `system_parameters.use_llm_answer` |
| Поиск изображений | POST | `/search` | `modality_type="Изображение"`, `object.name_synonyms`, `resource.features` |
| Геопоиск объекта | POST | `/search` | `modality_type="Геоданные"`, `object.name_synonyms` |
| Поиск вблизи места | POST | `/search/place/objects` | `place_name`, `subtypes`, `buffer_radius_km` |
| Связанные / промо | POST | `/objects/related` | `object_ids`, `relation_type="promo"` |
| Описание объекта (с RAG) | GET/POST | `/object/description` | `object_name`, `query`, `use_gigachat_answer` |

---

## 11. Pipeline: полный путь запроса

### 11.1 Сценарий A — биологический объект: "Покажи фото лиственницы зимой"

```
[1] Max Bot → adapters/max/handlers/messages.py
    Событие: Message(user_id="42", text="Покажи фото лиственницы зимой")
    │
    ▼
[2] DialogueOrchestrator.process(query, user_id="42")
    ConversationHistory: prev_turn = None (первый запрос)
    │
    ▼ [2.1] SlotClassifier.classify()
    Fast-path: "фото" → modality = "Изображение"
    LLM:  object_type = "Объект флоры и фауны"
          synonym     = "лиственница"
          features    = {"Время года": "Зима"}
    │
    ▼ [2.2] _merge_with_context() → нет предыдущего хода, наследовать нечего
    │
    ▼ [2.3] SlotSearchExecutor.execute()
    │
    ▼ HTTP POST backend:8000/search
    Body: {
      "system_parameters": { "limit": 10, "offset": 0 },
      "search_parameters": {
        "modality_type": "Изображение",
        "object": {
          "name_synonyms": { "ru_names": ["лиственница"] },
          "object_type": "biological_entity"
        },
        "resource": {
          "features": { "Время года": "Зима" }
        }
      }
    }
    │
    ▼ [3] SQLAlchemySearchRepository:
    JOIN Object → ObjectNameSynonym → ResourceValue (modality=Изображение)
    WHERE synonym ILIKE '%лиственница%'
      AND resource_feature.key = 'Время года' AND resource_feature.value = 'Зима'
    LIMIT 10 OFFSET 0
    │
    ▼ [4] Orchestrator → _build_proactive()
    Предложить: {"map": "лиственница", "text": "лиственница"}
    │
    ▼ [5] Presenter форматирует ответ для Max:
    Фото + подпись + кнопки "Описание" / "Показать на карте"
```

**Характерное время**: ~1.5–3 с (SQL ~100мс + Max API ~300мс + LLM ~1–2с)

---

### 11.2 Сценарий B — место вблизи: "Какие достопримечательности есть на Байкале?"

```
[1] Max Bot → DialogueOrchestrator.process()
    │
    ▼ [2.1] SlotClassifier.classify()
    LLM:  object_type = "Географический объект"
          synonym     = null  (класс объектов, не конкретный)
          modality    = "Текст"
          properties  = {"Подтип объекта": "Достопримечательности"}
          extra       = {"Расположение относительно Байкала": "на Байкале"}
    │
    ▼ [2.3] SlotSearchExecutor — шаблон place_search
    │
    ▼ HTTP POST backend:8000/search/place/objects
    Body: {
      "place_name": "Байкал",
      "subtypes": ["Достопримечательности"],
      "buffer_radius_km": 10.0,
      "limit": 20,
      "offset": 0
    }
    │
    ▼ backend: ищет геометрию "Байкал" → ST_DWithin по буферу → объекты с подтипом
    │
    ▼ Response: { "place_name": "Байкал", "total_objects": 15, "objects": [...], "pagination": {...} }
    │
    ▼ Presenter → список + кнопки "Показать на карте" для каждого объекта
```

---

### 11.3 Сценарий C — кореферентный запрос: "А где он обитает?"

*Предыдущий ход: "Что такое омуль?"*

```
[1] ConversationHistory: prev_turn = {
    query="Что такое омуль?",
    slots={synonym="омуль", object_type="Объект флоры и фауны", modality="Текст"},
    had_results=True
}

[2] SlotClassifier.classify("А где он обитает?", prev_query="Что такое омуль?")
    LLM получает prev_query и разрешает "он" → synonym = "омуль"
    modality = "Геоданные"
    │
    ▼ [3] _merge_with_context()
    synonym не изменился → наследуем object_type="Объект флоры и фауны"
    Итог: {synonym="омуль", modality="Геоданные", object_type="Объект флоры и фауны"}
    │
    ▼ [4] SlotSearchExecutor
    │
    ▼ HTTP POST backend:8000/search
    Body: {
      "search_parameters": {
        "modality_type": "Геоданные",
        "object": {
          "name_synonyms": { "ru_names": ["омуль"] },
          "object_type": "biological_entity"
        }
      }
    }
    │
    ▼ backend: находит геоданные (координаты ареала омуля)
    → строит Folium-карту
    │
    ▼ Presenter → карта ареала омуля + кнопка "Интерактивная карта"
```

---

## 12. Схема базы данных

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

## 13. Переменные окружения

### `EcoBotProject/DialogService/.env`

| Переменная | Назначение |
|-----------|-----------|
| `LLM_PROVIDER` | `qwen` \| `gigachat` |
| `LLM_BASE_URL` | `http://host.docker.internal:11434/v1` |
| `ECOBOT_API_BASE_URL` | `http://backend:8000` |
| `REDIS_HOST` | `redis` |
| `MAX_USE_WEBHOOK` | `true` \| `false` |
| `MAX_WEBHOOK_PORT` | `8080` |
| `MAX_WEBHOOK_PATH` | `/max-webhook` |
| `MAX_WEBHOOK_URL` | Публичный URL для подписки |
| `MAX_WEBHOOK_SECRET` | Секрет для проверки подписи |

### `shared.env`

Переменные, общие для нескольких сервисов (backend, core-api, admin).

| Переменная | Назначение |
|-----------|-----------|
| `PUBLIC_BASE_URL` | `https://testecobot.ru` |
| `DOMAIN` | Публичный домен |

### `salut_bot/.env`

| Переменная | Назначение |
|-----------|-----------|
| `DB_HOST`, `DB_USER`, `DB_PASSWORD` | PostgreSQL |
| `REDIS_HOST`, `REDIS_PORT` | Redis |
| `MAPS_DIR` | Путь для Folium-карт |
| `PUBLIC_BASE_URL` | Публичный домен |

### `AdminPanel/.env`

| Переменная | Назначение |
|-----------|-----------|
| `DB_HOST`, `DB_USER`, `DB_PASSWORD` | PostgreSQL |
| `SECRET_KEY` | Ключ сессий FastAPI |
| `ADMIN_PASSWORD_HASH` | Хэш пароля администратора |

---

## 14. Ключевые архитектурные паттерны

### Паттерн 1: Slot-filling NLU (вместо intent-based)

```
Запрос пользователя
  │
  ├── Fast-path (Python regex)   → modality, очевидные features (~0мс)
  └── LLM JSON-mode              → object_type, synonym, остальные слоты (~1–2с)

Слоты хранятся между ходами в Redis и наследуются — не нужно повторять контекст.
```

### Паттерн 2: Контекстный мёрдж слотов

Каждый ход — операция read-modify-write над `DialogueTurn` в Redis.  
Правила наследования: новый `synonym` → сброс `features`; тот же `synonym` → накопление `features`.

### Паттерн 3: Сценарий 4 — автоупрощение

Если поиск не вернул результатов, оркестратор параллельно проверяет варианты с уменьшенным набором `features` и предлагает пользователю кнопки упрощения. Результаты кэшируются в Redis (TTL 300с).

### Паттерн 4: Многоуровневый поиск

```
Запрос объекта
  1. Нормализация через synonym resolver
  2. Реляционный поиск (точное совпадение)
  3. FAISS fallback (семантическое совпадение, если реляционный пуст)
  4. RAG: LLM генерирует ответ по найденным документам
```

### Паттерн 5: Пространственная оптимизация

- **PostGIS** для тяжёлых spatial JOIN (`ST_Contains`, `ST_DWithin`)
- **Shapely prepared geometry** для клиппинга в памяти (~10–50мс vs ~500–2000мс в SQL)
- **LRU cache** на `GeoService.get_nearby_objects` (1000 записей)

### Паттерн 6: Многоуровневый кэш

```
L1: In-process LRU (GeoService.get_nearby_objects)
L2: Redis (результаты поиска, TTL 3600с; история диалога, TTL 900с)
L3: FAISS (загружен в RAM при старте backend, не перезагружается)
```

### Паттерн 7: Структурированное логирование ошибок

Все ошибки бота сохраняются в PostgreSQL через `POST /log_error` с полным контекстом (запрос пользователя, трейс, слоты) для анализа через Admin Panel.

### Паттерн 8: Проактивные предложения

После успешного ответа оркестратор детерминированно формирует `proactive`-словарь: что ещё может быть интересно (фото, карта, текст). Это реализуется без дополнительных HTTP-запросов — только на основе слотов и наличия данных в результате.

---

*Документ описывает состояние системы на июль 2026. Backend API работает на FastAPI (порт 8000). Актуальные endpoint'ы — в `salut_bot/fastapi_app/routes/`. Актуальная конфигурация деплоя — в `docker-compose.yml`.*
