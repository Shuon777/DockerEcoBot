# План тестирования FAISS

## Текущее состояние

### ✅ Что уже есть
- **Пакет `faiss-cpu==1.11.0`** — прописан в `salut_bot/requirements.txt`
- **Пакет `sentence-transformers==4.1.0`** — прописан в `requirements.txt`
- **Пакет `torch==2.7.1`** — прописан в `requirements.txt`
- **FAISS индекс** — директория `salut_bot/knowledge_base_scripts/Vector/faiss_index/` существует, но содержит **только `index_stats.json`** (без файлов индекса `.faiss` и `.pkl`)
- **JSON с данными** — `salut_bot/json_files/resources_dist.json` существует (9767 документов)
- **Тестовый эндпоинт** — `/test_faiss_search` в `salut_bot/app/routes/faiss.py`
- **Адаптер FAISS** — `salut_bot/knowledge_base_scripts/Vector/faiss_adapter.py`

### ❌ Чего не хватает
- **Директория `embedding_models/` — пуста** (модели не загружены)
- **FAISS индекс не содержит файлов** — нужна переиндексация
- **Модель реранкера** не загружена

## Пошаговый план

### Шаг 1: Проверить установку Python-пакетов
Выполнить команду проверки, что все нужные пакеты установлены:
- `faiss` (faiss-cpu)
- `sentence-transformers`
- `torch`
- `langchain-community` (для FAISS.load_local)
- `langchain-huggingface` или `langchain` (для HuggingFaceEmbeddings)

**Команда:** `python -c "import faiss; import sentence_transformers; import torch; print('OK')"`

### Шаг 2: Загрузить модель эмбеддингов BAAI/bge-m3
Использовать скрипт `salut_bot/scripts/download_embedding_model_from_HF.py`:
```bash
cd salut_bot
python scripts/download_embedding_model_from_HF.py "BAAI/bge-m3"
```
Модель сохранится в `salut_bot/embedding_models/bge-m3/`

### Шаг 3: Загрузить модель реранкера DiTy/cross-encoder-russian-msmarco
```bash
cd salut_bot
python scripts/download_embedding_model_from_HF.py "DiTy/cross-encoder-russian-msmarco"
```
Модель сохранится в `salut_bot/embedding_models/rerankers/DiTy_cross-encoder-russian-msmarco/`

### Шаг 4: Создать тестовый FAISS индекс
Запустить `faiss_adapter.py` как main-скрипт:
```bash
cd salut_bot
python knowledge_base_scripts/Vector/faiss_adapter.py
```
Этот скрипт:
1. Загрузит модель эмбеддингов из локальной директории
2. Прочитает `resources_dist.json`
3. Разобьёт тексты на чанки
4. Создаст FAISS индекс
5. Сохранит его в `faiss_index/`
6. Выполнит тестовый поиск по 5 запросам

### Шаг 5: Проверить работу тестового поиска
После создания индекса скрипт сам выполнит тестовый поиск по запросам:
- "байкальская нерпа"
- "земляника лесная"
- "археологические находки Шалино"
- "растения Байкала"
- "животные озера Байкал"

### Шаг 6: Проверить эндпоинт /test_faiss_search (опционально)
Если Flask-приложение запущено, проверить HTTP-эндпоинт:
```bash
curl "http://localhost:5555/test_faiss_search?query=Байкал&k=5&similarity_threshold=0.7"
```

### Шаг 7: Написать отчёт
Зафиксировать результаты:
- Какие модели загружены и их размер
- Размер FAISS индекса (количество векторов)
- Результаты тестового поиска (найдено ли что-то по запросам)
- Время загрузки модели и создания индекса

## Ожидаемые результаты

| Проверка | Ожидаемый результат |
|----------|---------------------|
| `faiss` package | Установлен, версия 1.11.0 |
| `sentence-transformers` | Установлен, версия 4.1.0 |
| `torch` | Установлен, версия 2.7.1 |
| Модель bge-m3 | Загружена в `embedding_models/bge-m3/` |
| Модель реранкера | Загружена в `embedding_models/rerankers/` |
| FAISS индекс | Создан, содержит ~9767 документов |
| Тестовый поиск | Возвращает результаты по всем запросам |

## Схема взаимодействия компонентов

```mermaid
flowchart TD
    A[resources_dist.json] --> B[faiss_adapter.py]
    C[embedding_models/bge-m3] --> B
    B --> D[faiss_index/]
    D --> E[SearchService.search_in_faiss]
    E --> F[Результаты поиска]
    C --> E
    G[embedding_models/rerankers/] --> H[SearchService._load_reranker]
    H --> I[Реренкинг результатов]
    F --> I
    I --> J[Финальные результаты]