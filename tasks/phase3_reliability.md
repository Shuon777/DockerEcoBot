# Фаза 3 — Надёжность

## Описание

Устранена гонка при старте: все сервисы теперь ждут реальной готовности БД и Redis. Добавлено монтирование логов для backend. Создан шаблон .env для AdminPanel.

## Изменения

- `docker-compose.yml` — добавлены healthcheck для `redis` (redis-cli ping) и `db` (pg_isready)
- `docker-compose.yml` — `backend`, `core-api`, `admin` переведены на `depends_on: condition: service_healthy` для db/redis
- `docker-compose.yml` — добавлен volume `./logs:/app/logs` для сервиса `backend`
- `.gitignore` — правило `logs/` заменено на `logs/*` + `!logs/.gitkeep`
- `logs/.gitkeep` — создан, чтобы папка существовала после `git clone`
- `AdminPanel/.env.example` — создан шаблон с документированными переменными

## Что уже было сделано (не потребовало изменений)

- `settings.html` AdminPanel уже содержит `restart-notice` блоки и toast-уведомления — пользователь информируется что настройки применяются после перезапуска

## Архитектура depends_on

- `backend` ← `db (healthy)`, `redis (healthy)`
- `core-api` ← `db (healthy)`, `redis (healthy)`, `backend (started)`
- `admin` ← `db (healthy)`, `redis (healthy)`, `backend (started)`
- `nginx` ← `backend (started)`, `admin (started)`, `core-api (started)`
