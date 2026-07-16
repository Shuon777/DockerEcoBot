# Фаза 2 — Параметризация

## Описание

Убраны все хардкодированные IP-адреса, домены и учётные данные из кода и конфигов. Создана двойная конфигурация nginx для HTTP/HTTPS. Очищены дублирующиеся переменные в per-service .env файлах.

## Изменения

- `dsapi/app/services/pipeline/_dynamic_pipeline.py` — дефолт `"https://testecobot.ru"` заменён на `os.getenv("BOT_DOMAIN", "")`
- `salut_bot/core/resource_update_service.py` — убран хардкод домена из fallback `PUBLIC_BASE_URL`
- `salut_bot/core/coordinates_finder.py` — User-Agent `TestEcoBot (testecobot.ru)` заменён на `EcoBot`
- `EcoBotProject/DialogService/config.py` — убран хардкод IP `84.237.20.90` из дефолта `STAND_ENDPOINT`
- `images-extractor/init_pipeline.py` — `ApiClient` читает `ECOBOT_API_BASE_URL` и `ADMIN_PASSWORD` из env
- `images-extractor/API.py` — аналогично в `__main__` блоке
- `docker-compose.yml` — секрет `MAX_WEBHOOK_SECRET` заменён на `${MAX_WEBHOOK_SECRET}`, хардкод URL убран; certbot volumes исправлены (`/etc/letsencrypt` → `./certbot/conf`)
- `nginx/nginx.conf` — `server_name` заменён на `_`, убран закомментированный HTTPS-блок с хардкодом домена
- `nginx/nginx.http.conf` — новый: HTTP-only шаблон для install.sh
- `nginx/nginx.https.conf` — новый: HTTPS шаблон с `${DOMAIN}` для install.sh
- `certbot/www/.gitkeep`, `certbot/conf/.gitkeep` — созданы чтобы папки существовали
- `.gitignore` — правило `certbot/` заменено на `certbot/conf/*` / `certbot/www/*` с исключением `.gitkeep`
- `salut_bot/.env` — убраны дубли из shared.env (LLM_*, GIGACHAT_*, DB_*, REDIS_*, PUBLIC_BASE_URL и другие)
- `EcoBotProject/DialogService/.env` — убраны дубли из shared.env, оставлены только уникальные пути и PLANTNET_API_KEY

## Проблемы

- `shared.env:STAND_ENDPOINT` содержит IP `84.237.20.90` — это корректно: это значение конфига, не хардкод в коде. Пользователь меняет при переносе.
- `salut_bot/.env:ADMIN_PASSWORD` содержит `ecobotadminpass` — файл в .gitignore, не попадает в git.

## Архитектура env (итог)

- `shared.env` — всё общее (ключи API, LLM, DB кроме хоста, Redis кроме хоста, публичные URL)
- Per-service `.env` — только уникальное для сервиса
- `docker-compose environment:` — только docker-инфраструктурное (DB_HOST, REDIS_HOST, PYTHONUNBUFFERED)
