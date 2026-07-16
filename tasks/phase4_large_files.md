# Фаза 4 — Большие файлы

## Описание

Инвентаризация ML-моделей по результатам сравнения с продакшн сервером (194.156.118.21:/opt/ecoassistant).
Создан единый скрипт скачивания. images-extractor вынесен в опциональный профиль.

## Инвентарь моделей (~11GB)

| Папка | Размер | Источник |
|-------|--------|----------|
| `salut_bot/embedding_models/` | 2.7G | HuggingFace (sentence-transformers) |
| `dsapi/local_models/` | 4.6G | HuggingFace (transformers) |
| `images-extractor/` | ~3.4G | HuggingFace + Meta SAM + timm ViT + Ultralytics YOLO |

## Изменения

- `scripts/download_models.sh` — единый скрипт: качает embedding-модели salut_bot и классификаторы dsapi
- `dsapi/setup_models.py` — добавлена модель `safety` (`protectai/deberta-v3-base-prompt-injection-v2`), которая была на сервере но отсутствовала в скрипте
- `docker-compose.yml` — `images-extractor` переведён в `profiles: [extractor]`, по умолчанию не запускается

## Что НЕ автоматизировано (намеренно)

- **images-extractor**: модуль одноразовый (`restart: "no"`), запускать только явно через `docker compose --profile extractor up images-extractor`. Скрипт скачивания не написан — ~3.4GB моделей нужно перенести вручную или через отдельный скрипт позже.
- **Ollama LLM**: требует работающей Ollama на хосте — инструкция в download_models.sh
- **faiss_index**: строится из данных, не скачивается. Команда: `python salut_bot/knowledge_base_scripts/Vector/faiss_adapter.py`
