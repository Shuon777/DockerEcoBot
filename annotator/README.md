# Annotator — сервис аннотации изображений

На вход: фото + список искомых признаков. На выход: по каждому признаку — ответ каждой модели
с уверенностью и итоговый вердикт (взвешенное голосование). Обработка асинхронная:
задача ставится в очередь, результат забирается по `task_id`.

ML-часть основана на загрузчиках из `images-extractor` (CLIP, Grounding DINO, OWLv2, BLIP),
добавлена PhenoVision для цветения и плодов.

## Модели

| id | Модель | Что делает | Признаки |
|---|---|---|---|
| `clip` | openai/clip-vit-base-patch32 | zero-shot классификация | все, кроме цветения/плодов |
| `grounding_dino` | IDEA-Research/grounding-dino-tiny | zero-shot детекция | все, кроме цветения/плодов |
| `owlv2` | google/owlv2-base-patch16 | zero-shot детекция | все, кроме цветения/плодов |
| `phenovision` | phenobase/phenovision (MIT) | цветки/плоды, ViT-L | «Цветение», «Наличие плодов» |
| `gigachat` | GigaChat Vision (платный) | LLM, все признаки одним запросом | любые |
| BLIP | Salesforce/blip-image-captioning-base | подпись к фото, не голосует | — |

Модели взаимозаменяемы: каждая — класс-наследник `Executor` (`app/executors/base.py`).
Добавить модель = один файл + строка в `registry.py` + id в `ANNOTATOR_EXECUTORS`.

## Итоговый вердикт

```
балл(значение) = Σ вес × уверенность (модели, выбравшие значение) / Σ веса моделей, работавших с признаком
```
- воздержавшаяся модель остаётся в знаменателе (снижает итог), упавшая — исключается;
- LLM без вероятности голосует с уверенностью `LLM_CONFIDENCE` (0.7);
- ниже `CONFIDENCE_THRESHOLD` (0.4) — «не определено», в `features_for_db` не попадает.

## API

| Метод | Путь | |
|---|---|---|
| POST | `/annotate` | JSON `{image_url, features?, executors?, lifeform?, resource_id?}` → `202 {task_id, status}` |
| POST | `/annotate/upload` | то же, multipart с файлом `file` |
| GET | `/tasks/{id}` | статус `pending/running/completed/failed`, `progress`, `queue_position` |
| GET | `/tasks/{id}/result` | результат; `409`, если ещё не готов |
| GET | `/features?lifeform=Флора` | признаки и допустимые значения |
| GET | `/executors` | загруженные модели и ошибки загрузки |
| GET | `/health` | |

Все, кроме `/health`, требуют заголовок `X-API-Token`, если задан `ANNOTATOR_API_TOKEN`.
Swagger: `http://<host>:8010/docs`.

Пример результата (сокращённо):
```json
{
  "features": {
    "Время года": {"verdict": "Лето", "confidence": 0.53, "agreement": "2/3", "top_value": "Лето",
                   "by_executor": [{"executor": "clip", "value": "Лето", "confidence": 0.62}, "..."]}
  },
  "features_for_db": {"Время года": "Лето"},
  "skipped_features": {"Цветение": "не применяется к Фауна"},
  "caption": "a group of seals laying on top of a rock"
}
```

## Запуск на сервере

Сервис вынесен в профиль `annotator` в `docker-compose.yml`: обычный `docker compose up -d`
и `docker compose build` его не собирают и не запускают. Пока он выключен, кнопка
«Аннотировать» в админке показывает «Сервис аннотации недоступен», остальное работает как обычно.

### Обновление кода без включения аннотатора

```bash
git pull origin version2
docker compose restart admin
```
Ничего больше не нужно: `annotator/.env`, токены и веса моделей не требуются.

### Включение

Все команды — из корня репозитория.

1. Настройки и токен:
   ```bash
   cp annotator/.env.example annotator/.env
   python3 -c "import secrets; print(secrets.token_hex(32))"
   ```
   Полученную строку вписать в `annotator/.env` как `ANNOTATOR_API_TOKEN=...`
   и в `AdminPanel/.env` как `ANNOTATOR_TOKEN=...` (значения должны совпадать).

2. Сборка образа (по умолчанию PyTorch для CPU):
   ```bash
   docker compose --profile annotator build annotator
   ```
   Сервер с видеокартой NVIDIA (нужны драйвер и nvidia-container-toolkit):
   ```bash
   docker compose --profile annotator build --build-arg TORCH_INDEX=https://download.pytorch.org/whl/cu124 annotator
   ```

3. Веса моделей (~4 ГБ в `annotator/models`, нужен доступ к huggingface.co):
   ```bash
   docker compose --profile annotator run --rm --no-deps -e HF_HUB_OFFLINE=0 annotator python scripts/download_models.py
   ```

4. Запуск аннотатора и перезапуск админки (чтобы она подхватила токен):
   ```bash
   docker compose --profile annotator up -d annotator
   docker compose up -d admin
   ```
   С видеокартой первая команда:
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.gpu.yml --profile annotator up -d annotator
   ```

5. Проверка: в логах должно появиться `Application startup complete` без `ERROR`,
   затем в админке нажать «Аннотировать» на любом фото.
   ```bash
   docker compose --profile annotator logs -f annotator
   ```

Мало памяти (меньше ~5 ГБ свободной RAM): перед шагом 4 оставить в `annotator/.env`
облегчённый набор и заполнить `GIGACHAT_CREDENTIALS`:
```bash
ANNOTATOR_EXECUTORS=clip,gigachat
ENABLE_CAPTION=false
```

### Выключение

```bash
docker compose --profile annotator stop annotator
```

Локально без Docker: `pip install -r requirements.txt && uvicorn app.main:app --port 8010`.

Тесты (без моделей и без torch): `pip install -r requirements-dev.txt && pytest -q`.

## Ресурсы

PhenoVision — ViT-Large (~304M параметров, ~1.2 ГБ в fp32). Вместе с остальными моделями
нужно порядка 3–4 ГБ памяти GPU или столько же RAM на CPU. На CPU одна задача — десятки секунд.

## Ограничения

- Реестр задач в памяти: при перезапуске незавершённые задачи теряются.
- PhenoVision — presence-only: «Нет» значит «на фото не видно», а не «растение не цветёт».
- Названия признаков в `app/features.json` должны совпадать с каталогом «Признаки ресурсов»
  в админке, иначе итог не перенесётся в описание (админка об этом предупреждает).
