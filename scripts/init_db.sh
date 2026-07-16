#!/usr/bin/env bash
# Инициализация БД начальными данными.
# Использование: bash scripts/init_db.sh [--incremental]
# По умолчанию --full (сброс и пересоздание схемы).
set -euo pipefail

MODE="${1:---full}"

# Загружаем shared.env через встроенный source (без внешних утилит)
set -a
# shellcheck disable=SC1091
source shared.env 2>/dev/null || true
set +a

PUBLIC_BASE_URL="${PUBLIC_BASE_URL:-http://localhost}"

echo "[init_db] Режим: $MODE"
echo "[init_db] PUBLIC_BASE_URL: $PUBLIC_BASE_URL"

# Вся замена и запуск происходит внутри контейнера
docker compose exec -T backend bash -c "
    sed 's|{{PUBLIC_BASE_URL}}|${PUBLIC_BASE_URL}|g' \
        /app/json_files/resources.json \
        > /app/json_files/resources_deploy.json

    cd knowledge_base_scripts/Relational
    python -m db_importer.main ${MODE} \
        --resources-file /app/json_files/resources_deploy.json

    rm -f /app/json_files/resources_deploy.json
"

echo "[init_db] Готово"
