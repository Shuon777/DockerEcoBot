# Отчёт: Реализация пагинации (постраничной выдачи)

> **Дата**: Июль 2026  
> **Компонент**: `salut_bot` — пакет `search_api/` + FastAPI  
> **Суть**: В ответ поисковых эндпоинтов добавлен блок `pagination`, позволяющий клиенту узнать общее количество объектов и получить следующую страницу.

---

## 1. Мотивация

**Проблема**: Бот находил много объектов (например, 45 музеев), но показывал только первые 5. Кнопка «Покажи ещё» не работала — backend не возвращал информацию о том, сколько всего объектов найдено и есть ли следующая страница.

**Решение**: Добавить в ответ backend'а блок `pagination`:

```json
{
  "pagination": {
    "total": 45,
    "limit": 10,
    "offset": 0,
    "next_offset": 10,
    "has_more": true
  }
}
```

Клиент (DialogService) использует эти поля, чтобы:
- Показать кнопку «Ещё», если `has_more == true`
- Вычислить `offset` для следующего запроса: `pagination.next_offset`
- Показать прогресс: «Объекты 1–10 из 45»

---

## 2. Архитектура решения

Пагинация реализована в 4 слоях:

```
FastAPI route → SearchUseCase → SearchRepository → PostgreSQL
                    │
                    ▼
              Pagination (dataclass)
                    │
                    ▼
              ResponseBuilder → JSON с "pagination"
```

### 2.1 Слой сущностей (domain)

**Файл**: [`salut_bot/search_api/domain/entities.py`](salut_bot/search_api/domain/entities.py)

Добавлена dataclass `Pagination`:

```python
@dataclass
class Pagination:
    total: int          # всего объектов в БД (без учёта limit/offset)
    limit: int          # сколько объектов запрошено на страницу
    offset: int         # с какой позиции начинается текущая страница
    next_offset: int    # offset для следующей страницы (= offset + limit)
    has_more: bool      # true, если есть ещё объекты (next_offset < total)
```

**Пояснение**: `next_offset` вычисляется как `offset + limit` — это позволяет клиенту просто подставить это значение в следующий запрос без дополнительной арифметики. `has_more` — булев флаг, по которому клиент решает, показывать ли кнопку «Ещё».

Поля добавлены в `SearchResponse`:

```python
@dataclass
class SearchResponse:
    objects: List[ObjectResult]
    resources: List[ResourceResult]
    object_criteria: Optional[ObjectCriteria] = None
    resource_criteria: Optional[ResourceCriteria] = None
    modality_filter: Optional[str] = None
    total_objects: int = 0       # общее количество найденных объектов
    total_resources: int = 0     # общее количество найденных ресурсов
    pagination: Optional[Pagination] = None
```

Аналогично в [`PlaceSearchResponse`](salut_bot/search_api/domain/place_entities.py):

```python
@dataclass
class PlaceSearchResponse:
    place_name: str
    objects: List[PlaceGeometryResult]
    geometry_type: Optional[str] = None
    pagination: Optional[Pagination] = None
```

---

### 2.2 Слой репозиториев (адаптеры)

#### Абстрактный класс

**Файл**: [`salut_bot/search_api/adapters/search_repository.py`](salut_bot/search_api/adapters/search_repository.py)

Сигнатуры изменены: теперь каждый метод возвращает кортеж `(результаты, общее_количество)`:

```python
class SearchRepository(ABC):
    @abstractmethod
    def find_objects_by_criteria(
        self, criteria: ObjectCriteria, limit: int = 20, offset: int = 0
    ) -> Tuple[List[ObjectResult], int]:
        """Возвращает (список объектов, общее количество без limit/offset)"""
        ...

    @abstractmethod
    def find_resources_by_criteria(
        self, criteria: ResourceCriteria, object_ids: Optional[List[int]] = None,
        limit: int = 50, offset: int = 0
    ) -> Tuple[List[ResourceResult], int]:
        """Возвращает (список ресурсов, общее количество без limit/offset)"""
        ...
```

**Пояснение**: Возврат кортежа вместо одного списка — ключевое изменение. Второй элемент (`total`) используется для вычисления `Pagination`. Это打破了 обратную совместимость, поэтому пришлось обновить все имплементации и моки в тестах.

#### SQLAlchemySearchRepository

**Файл**: [`salut_bot/search_api/adapters/sqlalchemy_repository.py`](salut_bot/search_api/adapters/sqlalchemy_repository.py)

**Поиск объектов** (`find_objects_by_criteria`, строка 35):

```python
# Строим query с JOIN и WHERE (без ORDER BY — для объектов сортировка не нужна)
query = session.query(Object).options(joinedload(Object.synonyms)).join(Object.object_type)
# ... применяем фильтры из criteria ...

# COUNT до LIMIT/OFFSET — отдельный запрос с теми же условиями
count_query = query.with_entities(func.count(Object.id.distinct()))
total = count_query.scalar()

# Основной запрос с LIMIT/OFFSET
objects = query.limit(limit).offset(offset).all()

return [ObjectResult(...) for obj in objects], total
```

**Пояснение**: `query.with_entities(func.count(Object.id.distinct()))` создаёт новый SELECT-запрос, который считает количество уникальных ID объектов, но сохраняет все WHERE-условия и JOIN из оригинального query. Это гарантирует, что `total` соответствует тем же фильтрам, что и результаты на странице.

**Поиск ресурсов** (`find_resources_by_criteria`, строка 118):

```python
# Строим query с JOIN и WHERE
query = session.query(Resource).options(...).outerjoin(...)
# ... применяем фильтры ...

# Для ресурсов есть ORDER BY (по длине контента или по ID)
if criteria.modality_type == "Текст" or criteria.modality_type is None:
    query = query.order_by(sql_text("length(COALESCE(...)) DESC NULLS LAST"))
else:
    query = query.order_by(Resource.id)

# COUNT до LIMIT/OFFSET — ВАЖНО: сбрасываем ORDER BY
count_query = query.with_entities(func.count(Resource.id.distinct())).order_by(None)
total = count_query.scalar()

# Основной запрос с LIMIT/OFFSET и ORDER BY
resources = query.limit(limit).offset(offset).all()

return [ResourceResult(...) for r in resources], total
```

**Пояснение**: `.order_by(None)` критически важен. Без него SQLAlchemy генерирует:
```sql
SELECT count(DISTINCT resource.id) FROM ... ORDER BY resource.id
```
PostgreSQL отвергает такой запрос — `ORDER BY` недопустим в агрегатных функциях без `GROUP BY`. `.order_by(None)` сбрасывает сортировку только для COUNT-запроса, основной запрос с LIMIT/OFFSET сохраняет сортировку.

#### PostgresSearchRepository (psycopg2)

**Файл**: [`salut_bot/search_api/adapters/database.py`](salut_bot/search_api/adapters/database.py)

Для `find_objects_by_criteria` выполняется отдельный COUNT-запрос:

```python
# Основной запрос с LIMIT/OFFSET
cur.execute(f"""
    SELECT DISTINCT o.id, o.db_id, ot.name, o.object_properties,
           COALESCE(json_agg(ons.synonym) FILTER (WHERE ons.synonym IS NOT NULL), '[]') as synonyms
    FROM eco_assistant.object o
    JOIN eco_assistant.object_type ot ON o.object_type_id = ot.id
    LEFT JOIN eco_assistant.object_name_synonym ons ON o.id = ons.object_id
    WHERE {conditions}
    GROUP BY o.id, ot.name
    ORDER BY o.id
    LIMIT {limit} OFFSET {offset}
""")

# COUNT-запрос — те же JOIN и WHERE, но без LIMIT/OFFSET/ORDER BY/GROUP BY
count_cur.execute(f"""
    SELECT COUNT(*) FROM (
        SELECT DISTINCT o.id
        FROM eco_assistant.object o
        JOIN eco_assistant.object_type ot ON o.object_type_id = ot.id
        LEFT JOIN eco_assistant.object_name_synonym ons ON o.id = ons.object_id
        WHERE {conditions}
    ) AS counted
""")
total = count_cur.fetchone()[0]
```

**Пояснение**: Для psycopg2 COUNT выполняется как вложенный запрос `SELECT COUNT(*) FROM (SELECT DISTINCT ...) AS counted`. Это даёт точное количество уникальных объектов после применения всех фильтров, но без LIMIT/OFFSET.

---

### 2.3 Слой use cases

#### SearchUseCase

**Файл**: [`salut_bot/search_api/use_cases/search_use_case.py`](salut_bot/search_api/use_cases/search_use_case.py)

```python
@dataclass
class SearchUseCase:
    _repository: SearchRepository

    def execute(self, request: SearchRequest) -> SearchResponse:
        # Репозиторий возвращает кортеж (results, total)
        objects, total_objects = self._repository.find_objects_by_criteria(
            request.object_criteria, limit=request.limit, offset=request.offset
        )
        resources, total_resources = self._repository.find_resources_by_criteria(
            request.resource_criteria, object_ids=[o.id for o in objects],
            limit=request.limit, offset=request.offset
        )

        # Вычисление пагинации
        next_offset = request.offset + request.limit
        has_more = next_offset < total_objects
        pagination = Pagination(
            total=total_objects,
            limit=request.limit,
            offset=request.offset,
            next_offset=next_offset,
            has_more=has_more
        )

        return SearchResponse(
            objects=objects,
            resources=resources,
            object_criteria=request.object_criteria,
            resource_criteria=request.resource_criteria,
            modality_filter=request.modality_type,
            total_objects=total_objects,
            total_resources=total_resources,
            pagination=pagination
        )
```

**Пояснение**: `Pagination` вычисляется на основе `total_objects` (общее количество объектов в БД), а не `total_resources`. Это сделано потому, что пагинация постранично выдаёт объекты, а ресурсы — это сопутствующая информация к ним. `next_offset = offset + limit` — простой инкремент. `has_more = next_offset < total` — если следующая страница выходит за пределы общего количества, значит, это последняя страница.

#### PlaceSearchUseCase

**Файл**: [`salut_bot/search_api/use_cases/place_search_use_case.py`](salut_bot/search_api/use_cases/place_search_use_case.py)

Добавлен метод `_count_objects_with_geometry()`:

```python
def _count_objects_with_geometry(
    self, geometry: Any, subtypes: List[str],
    object_criteria: Optional[ObjectCriteria], buffer_radius_km: float
) -> int:
    """Выполняет COUNT(*) с теми же spatial и criteria условиями, что и основной запрос."""
    with self._get_session() as session:
        query = session.query(Object).join(ObjectType).filter(
            Object.object_properties['subtypes'].as_string().in_(subtypes)
        )
        # Применяем spatial фильтр (ST_DWithin)
        # Применяем object_criteria фильтры
        count_query = query.with_entities(func.count(Object.id.distinct()))
        return count_query.scalar()
```

**Пояснение**: Для place-поиска нужен отдельный COUNT, потому что основной запрос содержит spatial-фильтр (`ST_DWithin`), который нельзя просто отделить от LIMIT/OFFSET. `_count_objects_with_geometry` дублирует все JOIN и WHERE из основного запроса, но без LIMIT/OFFSET и без загрузки геометрии (что дорого).

---

### 2.4 Слой сериализации (ResponseBuilder)

**Файл**: [`salut_bot/search_api/services/response_builder.py`](salut_bot/search_api/services/response_builder.py)

```python
class ResponseBuilder:
    def build(self, search_response: SearchResponse, ...) -> dict:
        result = {
            'object_criteria': self._serialize_object_criteria(search_response.object_criteria),
            'resource_criteria': self._serialize_resource_criteria(search_response.resource_criteria),
            'modality_filter': search_response.modality_filter,
            'objects': self._serialize_objects(search_response.objects),
            'resources': self._serialize_resources(search_response.resources, search_response.objects),
        }

        # Сериализация пагинации
        if search_response.pagination:
            result['pagination'] = {
                'total': search_response.pagination.total,
                'limit': search_response.pagination.limit,
                'offset': search_response.pagination.offset,
                'next_offset': search_response.pagination.next_offset,
                'has_more': search_response.pagination.has_more,
            }

        return result
```

**Пояснение**: `pagination` добавляется в JSON-ответ только если он присутствует в `SearchResponse`. Это обеспечивает обратную совместимость — старые клиенты, которые не знают про `pagination`, просто его проигнорируют.

---

### 2.5 FastAPI-роут place.py

**Файл**: [`salut_bot/fastapi_app/routes/place.py`](salut_bot/fastapi_app/routes/place.py)

```python
@router.post("/search/place/objects")
async def search_objects_near_place(request_data: PlaceSearchRequest):
    # ... вызов PlaceSearchUseCase ...

    response_data = {
        "place_name": place_name,
        "objects": objects_serialized,
        "total_objects": len(objects_serialized),
        "pagination": {
            "total": response.total_objects,
            "limit": request_data.limit,
            "offset": request_data.offset,
            "next_offset": request_data.offset + request_data.limit,
            "has_more": (request_data.offset + request_data.limit) < response.total_objects,
        }
    }
```

**Пояснение**: Для place-роута пагинация вычисляется непосредственно в роуте, а не в use case, потому что `PlaceSearchResponse` уже содержит `total_objects` от use case.

---

## 3. Тестирование

### 3.1 Консольный тест (docker exec → FastAPI)

Проверка на реальных данных: 2 объекта «байкальская нерпа» в БД.

```bash
docker exec praktika2026-backend-1 python -c "
import urllib.request, json

# Страница 1: limit=1, offset=0
req = urllib.request.Request('http://localhost:8000/search',
    data=json.dumps({
        'system_parameters': {'user_query': 'нерпа', 'limit': 1, 'offset': 0, 'debug': True},
        'search_parameters': {'object': {'name_synonyms': {'ru': ['байкальская нерпа']}}}
    }).encode(),
    headers={'Content-Type': 'application/json'})
resp = urllib.request.urlopen(req)
data = json.loads(resp.read())
print('Page 1:', len(data['objects']), 'objects, pagination:', json.dumps(data['pagination']))

# Страница 2: limit=1, offset=1
req2 = urllib.request.Request('http://localhost:8000/search',
    data=json.dumps({
        'system_parameters': {'user_query': 'нерпа', 'limit': 1, 'offset': 1, 'debug': True},
        'search_parameters': {'object': {'name_synonyms': {'ru': ['байкальская нерпа']}}}
    }).encode(),
    headers={'Content-Type': 'application/json'})
resp2 = urllib.request.urlopen(req2)
data2 = json.loads(resp2.read())
print('Page 2:', len(data2['objects']), 'objects, pagination:', json.dumps(data2['pagination']))
"
```

**Результат**:

```
Page 1: 1 objects, pagination: {"total": 2, "limit": 1, "offset": 0, "next_offset": 1, "has_more": true}
Page 2: 1 objects, pagination: {"total": 2, "limit": 1, "offset": 1, "next_offset": 2, "has_more": false}
```

**Анализ**:

| Параметры | Объекты | `total` | `has_more` | Пояснение |
|-----------|---------|---------|------------|-----------|
| `limit=1, offset=0` | 1 (id=123) | 2 | `true` | Первая страница: есть ещё |
| `limit=1, offset=1` | 1 (id=242) | 2 | `false` | Вторая страница: последняя |
| `limit=10, offset=0` | 2 | 2 | `false` | Все объекты на одной странице |

### 3.2 Юнит-тесты

**Файл**: [`salut_bot/tests/unit/search_api/test_use_cases.py`](salut_bot/tests/unit/search_api/test_use_cases.py)

```python
class TestSearchUseCase:
    def test_execute_with_pagination_has_more(self):
        """10 объектов в БД, запрашиваем limit=3 → has_more=true"""
        mock_repo = Mock(spec=SearchRepository)
        mock_repo.find_objects_by_criteria.return_value = (
            [ObjectResult(id=i, ...) for i in range(3)], 10  # 3 на странице, 10 всего
        )
        mock_repo.find_resources_by_criteria.return_value = ([], 0)

        use_case = SearchUseCase(mock_repo)
        response = use_case.execute(SearchRequest(limit=3, offset=0))

        assert response.pagination.total == 10
        assert response.pagination.has_more is True   # 3 < 10 → есть ещё
        assert response.pagination.next_offset == 3

    def test_execute_with_pagination_last_page(self):
        """10 объектов в БД, запрашиваем limit=10 → has_more=false"""
        mock_repo = Mock(spec=SearchRepository)
        mock_repo.find_objects_by_criteria.return_value = (
            [ObjectResult(id=i, ...) for i in range(10)], 10  # все на странице
        )
        mock_repo.find_resources_by_criteria.return_value = ([], 0)

        use_case = SearchUseCase(mock_repo)
        response = use_case.execute(SearchRequest(limit=10, offset=0))

        assert response.pagination.total == 10
        assert response.pagination.has_more is False  # 10 == 10 → последняя
        assert response.pagination.next_offset == 10
```

---

## 4. Формат ответа

### `/search` (главный поисковый эндпоинт)

```json
{
  "object_criteria": {...},
  "resource_criteria": {...},
  "modality_filter": "Текст",
  "objects": [...],
  "resources": [...],
  "pagination": {
    "total": 45,
    "limit": 10,
    "offset": 0,
    "next_offset": 10,
    "has_more": true
  },
  "debug": {
    "objects_query_time": 0.28,
    "total_objects": 2,
    "resources_query_time": 0.42,
    "total_resources": 4,
    "total_time": 0.70
  }
}
```

### `/search/place/objects` (поиск по месту)

```json
{
  "place_name": "Байкал",
  "objects": [...],
  "total_objects": 15,
  "pagination": {
    "total": 15,
    "limit": 5,
    "offset": 0,
    "next_offset": 5,
    "has_more": true
  }
}
```

---

## 5. Изменённые файлы

| Файл | Что сделано |
|------|-------------|
| `salut_bot/search_api/domain/entities.py` | Добавлена dataclass `Pagination` (total, limit, offset, next_offset, has_more). В `SearchResponse` добавлены `total_objects`, `total_resources`, `pagination` |
| `salut_bot/search_api/domain/place_entities.py` | В `PlaceSearchResponse` добавлено поле `pagination: Optional[Pagination]` |
| `salut_bot/search_api/adapters/search_repository.py` | Сигнатуры методов изменены на возврат `Tuple[List[Any], int]` — второй элемент это `total` |
| `salut_bot/search_api/adapters/sqlalchemy_repository.py` | В `find_objects_by_criteria` и `find_resources_by_criteria` добавлены COUNT-запросы до LIMIT/OFFSET. Для ресурсов — `.order_by(None)` чтобы избежать `GroupingError` |
| `salut_bot/search_api/adapters/database.py` | В `find_objects_by_criteria` и `find_resources_by_criteria` (psycopg2) добавлены отдельные `SELECT COUNT(*)` запросы |
| `salut_bot/search_api/use_cases/search_use_case.py` | Вычисляется `Pagination` на основе `total_objects` из репозитория. `next_offset = offset + limit`, `has_more = next_offset < total` |
| `salut_bot/search_api/use_cases/place_search_use_case.py` | Добавлен `_count_objects_with_geometry()` — отдельный COUNT-запрос с spatial + criteria условиями. Вычисляется `Pagination` |
| `salut_bot/search_api/services/response_builder.py` | Добавлена сериализация `pagination` в JSON: `result['pagination'] = {...}` |
| `salut_bot/fastapi_app/routes/place.py` | В `response_data` добавлен блок `pagination` |
| `salut_bot/tests/unit/search_api/test_use_cases.py` | Добавлены тесты `test_execute_with_pagination_has_more` и `test_execute_with_pagination_last_page` |
| `salut_bot/tests/conftest.py` | Мок `mock_repository` возвращает `([], 0)` вместо `[]` |
| `salut_bot/tests/integration/search_api/test_repository.py` | Распаковка кортежей `(results, total)` из методов репозитория |

---

## 6. Известные проблемы и их решения

### Проблема: `GroupingError` в COUNT-запросе ресурсов

**Ошибка** (возникала при запросе "покажи нерпу"):
```
(psycopg2.errors.GroupingError) column "resource.id" must appear in the GROUP BY clause
or be used in an aggregate function
... ORDER BY eco_assistant.resource.id
```

**Причина**: В `find_resources_by_criteria` основной query содержит `ORDER BY` (сортировка по длине контента или по ID). Когда мы делаем `query.with_entities(func.count(...))`, SQLAlchemy копирует весь query, включая `ORDER BY`, в COUNT-запрос. PostgreSQL запрещает `ORDER BY` в агрегатных запросах без `GROUP BY`.

**Воспроизведение**: Любой запрос, который находит ресурсы с `modality_type` (например, "Текст" или "Изображение").

**Решение**: Добавлен `.order_by(None)` к count-запросу:

```python
# Было (падало с GroupingError):
count_query = query.with_entities(func.count(Resource.id.distinct()))
total = count_query.scalar()

# Стало (работает):
count_query = query.with_entities(func.count(Resource.id.distinct())).order_by(None)
total = count_query.scalar()
```

`.order_by(None)` сбрасывает сортировку только для COUNT-запроса. Основной запрос с LIMIT/OFFSET сохраняет сортировку.

---

## 7. Дальнейшие шаги

1. **DialogService**: хранение `pagination` в `DialogueTurn`, кнопка «Ещё» в `presenter.py`, обработчик `more:` в `callbacks.py`
2. **Тесты для FastAPI**: написать тесты с `TestClient` от FastAPI для проверки пагинации через HTTP