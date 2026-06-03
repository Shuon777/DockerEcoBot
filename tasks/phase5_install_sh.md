# Фаза 5 — install.sh

## Описание

Единый скрипт установки EcoBot на новый сервер с нуля.

## Созданные файлы

- `install.sh` — основной установщик
- `scripts/init_db.sh` — инициализация БД (можно запускать отдельно)

## Что делает install.sh

1. Проверяет зависимости (docker, docker compose, python3, git)
2. Спрашивает PUBLIC_BASE_URL, DB_PASSWORD, BOT_TOKEN
3. Генерирует/обновляет `shared.env` с введёнными значениями
4. Генерирует случайный `SESSION_SECRET_KEY` для AdminPanel если не задан
5. Копирует нужный nginx конфиг (http или https в зависимости от URL)
6. Создаёт все необходимые директории
7. Опционально скачивает ML-модели (`scripts/download_models.sh`)
8. Запускает `docker compose up -d --build`
9. Ждёт готовности backend
10. Опционально инициализирует БД (`db_importer --full`)

## Решение проблемы URL в resources.json

- `resources.json` хранится в git с плейсхолдером `{{PUBLIC_BASE_URL}}`
- При инициализации БД `install.sh` создаёт временный `resources_deploy.json` с реальным URL через sed
- Передаёт его в `db_importer --resources-file`
- Удаляет временный файл после импорта

## Что нужно сделать вручную после install.sh (SSL)

```bash
docker run --rm \
  -v $(pwd)/certbot/www:/var/www/certbot \
  -v $(pwd)/certbot/conf:/etc/letsencrypt \
  certbot/certbot certonly --webroot \
  -w /var/www/certbot -d YOUR_DOMAIN \
  --email your@email.com --agree-tos
docker compose restart nginx
```
