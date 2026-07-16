# План исправлений: векторный поиск (FAISS)

## Задача

Внести два изменения в код по заданию Александра Столбова:

1. Убрать проверку `request.modality_type == "Текст"` из условия активации векторного поиска
2. Заменить `config.embedding_model_path` и `config.faiss_index_path` на прямые пути через `pathlib`

---

## Изменение 1: `salut_bot/search_api/use_cases/search_use_case.py`

### Текущий код (строка 75)

```python
if (request.modality_type == "Текст" and not resources and
    self._vector_search and request.user_query):
```

### Что нужно сделать

Убрать проверку `request.modality_type == "Текст"`, оставив только:

```python
if (not resources and self._vector_search and request.user_query):
```

**Обоснование:** Векторный поиск должен использоваться как fallback, когда не найдено никаких ресурсов, независимо от modality_type. Сейчас он срабатывает только при `modality_type == "Текст"`, что ограничивает его применение.

---

## Изменение 2: `salut_bot/search_api/routes/search.py`

### Текущий код (строка 30)

```python
vector_search = VectorSearchAdapter(config.embedding_model_path, config.faiss_index_path)
```

### Что нужно сделать

Заменить на прямые пути через `pathlib`, аналогично тому, как это сделано в `salut_bot/fastapi_app/config.py`:

```python
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent.parent  # salut_bot/

vector_search = VectorSearchAdapter(
    str(BASE_DIR / "embedding_models" / "bge-m3"),
    str(BASE_DIR / "knowledge_base_scripts" / "Vector" / "faiss_index")
)
```

**Обоснование:** `config.embedding_model_path` и `config.faiss_index_path` берутся из переменных окружения с fallback-значениями. Прямые пути гарантируют, что используется правильная локальная модель и индекс, независимо от настроек окружения.

---

## Зависимости

- Модель эмбеддингов `bge-m3` должна быть скачана в `salut_bot/embedding_models/bge-m3/`
- FAISS индекс должен быть создан в `salut_bot/knowledge_base_scripts/Vector/faiss_index/`
  - Сейчас там только `index_stats.json` — нужны файлы `index.faiss` и `index.pkl`

---

## Порядок выполнения

1. Внести изменение в `search_use_case.py` (убрать проверку modality_type)
2. Внести изменение в `routes/search.py` (заменить пути)
3. Убедиться, что модель `bge-m3` присутствует в `embedding_models/bge-m3/`
4. Убедиться, что FAISS индекс создан (есть `index.faiss` и `index.pkl`)
5. Протестировать векторный поиск через API