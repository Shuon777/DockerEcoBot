#!/usr/bin/env bash
# Инициализация БД начальными данными.
# Использование: bash scripts/init_db.sh [--incremental]
# По умолчанию --full (сброс и пересоздание схемы).
set -euo pipefail

REPO_ROOT="$(cd "${BASH_SOURCE[0]%/*}/.." && pwd)"
MODE="${1:---full}"

source "$REPO_ROOT/shared.env" 2>/dev/null || true
PUBLIC_BASE_URL="${PUBLIC_BASE_URL:-http://localhost}"

echo "[init_db] Режим: $MODE"
echo "[init_db] PUBLIC_BASE_URL: $PUBLIC_BASE_URL"

# Генерируем временный resources_deploy.json с реальным URL
sed "s|{{PUBLIC_BASE_URL}}|$PUBLIC_BASE_URL|g" \
    "$REPO_ROOT/salut_bot/json_files/resources.json" \
    > "$REPO_ROOT/salut_bot/json_files/resources_deploy.json"

cd "$REPO_ROOT"
docker compose exec -T backend bash -c "
    cd knowledge_base_scripts/Relational &&
    python -m db_importer.main $MODE \
        --resources-file /app/json_files/resources_deploy.json
"

rm -f "$REPO_ROOT/salut_bot/json_files/resources_deploy.json"
echo "[init_db] Готово"
