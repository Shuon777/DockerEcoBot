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

## Запуск

```bash
cd annotator
cp .env.example .env                 # задать ANNOTATOR_API_TOKEN
pip install huggingface_hub
python scripts/download_models.py    # ~3 ГБ в ./models, нужен доступ к huggingface.co
cd .. && docker compose up -d --build annotator admin
```

В `AdminPanel/.env` добавить `ANNOTATOR_TOKEN` = тот же токен.
Для GPU добавить к команде `docker-compose.gpu.yml`:
`docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build annotator admin`
(на сервере нужен nvidia-container-toolkit).

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
