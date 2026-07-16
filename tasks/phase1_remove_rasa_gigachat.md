# Фаза 1 — Удаление архаизмов: Rasa и GigaChat микросервис

## Описание

Rasa и микросервис GigaChatAPI больше не используются в проекте. `GIGACHAT_FALLBACK_URL` использовался только из Rasa actions. `salut_bot` работает с GigaChat напрямую через SDK, без микросервиса. Задача — удалить мёртвый код и очистить конфиги.

## Изменения

- `EcoBotProject/RasaProject/` — удалён полностью (27 файлов)
- `EcoBotProject/GigaChatAPI/` — удалён полностью (4 файла)
- `docker-compose.yml` — удалён сервис `gigachat:`
- `EcoBotProject/DialogService/config.py` — удалена переменная `GIGACHAT_FALLBACK_URL` (объявлялась, нигде не использовалась)
- `shared.env` — удалены `GIGACHAT_FALLBACK_URL` и `RASA_WEBHOOK_URL`, обновлён комментарий
- `shared.env.example` — удалены те же переменные
- `.env.example` — удалены `GIGACHAT_FALLBACK_URL` и `RASA_WEBHOOK_URL`
- `EcoBotProject/DialogService/.env` — удалены те же строки

## Проблемы

- В `dsapi/app/dynamic_testingDS/testing_answerBot.py` строки `"rasa"` и `"gigachat"` — это ключи словарей для хранения результатов тестирования, не внешние зависимости. Оставлены без изменений.

## Решения

- `GIGACHAT_CREDENTIALS`, `GIGACHAT_MODEL`, `SBER_KEY_ENTERPRICE` в `shared.env` оставлены — они используются `salut_bot` напрямую через `langchain-gigachat`, без микросервиса.
