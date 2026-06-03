#!/usr/bin/env bash
# Инициализация БД начальными данными.
# Использование: bash scripts/init_db.sh [--incremental]
# По умолчанию --full (сброс и пересоздание схемы).
set -euo pipefail

MODE="${1:---full}"

# Читаем PUBLIC_BASE_URL из shared.env на хосте
PUBLIC_BASE_URL=$(grep "^PUBLIC_BASE_URL=" shared.env 2>/dev/null | cut -d= -f2- | tr -d '"' | tr -d "'")
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
