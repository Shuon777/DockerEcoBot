#!/usr/bin/env bash
# =============================================================
# setup_local.sh — подготовка к локальному запуску (демо админки и аннотатора).
# Создаёт все .env из шаблонов с согласованными паролями и токенами, и нужные папки.
# Уже существующие .env НЕ перезаписывает (кроме синхронизации токена аннотатора).
#
# Запуск из корня репозитория:  bash scripts/setup_local.sh
# =============================================================
set -euo pipefail
cd "$(dirname "$0")/.."

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
log()  { echo -e "${GREEN}[setup]${NC} $*"; }
warn() { echo -e "${YELLOW}[setup]${NC} $*"; }

rand() { python3 -c "import secrets; print(secrets.token_hex($1))" 2>/dev/null || openssl rand -hex "$1"; }

# set_kv FILE KEY VALUE — заменить строку KEY=... или дописать, если её нет
set_kv() {
    local file="$1" key="$2" value="$3"
    if grep -q "^${key}=" "$file"; then
        python3 - "$file" "$key" "$value" <<'PY'
import sys, re
path, key, value = sys.argv[1:]
text = open(path, encoding="utf-8").read()
text = re.sub(rf"^{re.escape(key)}=.*$", lambda m: f"{key}={value}", text, flags=re.M)
open(path, "w", encoding="utf-8").write(text)
PY
    else
        printf '\n%s=%s\n' "$key" "$value" >> "$file"
    fi
}

get_kv() { grep -E "^$2=" "$1" 2>/dev/null | head -1 | cut -d= -f2- || true; }

# create FILE_FROM_EXAMPLE -> 0 если создан, 1 если уже был
create() {
    local target="$1"
    if [[ -f "$target" ]]; then
        warn "уже есть: $target — не трогаю"
        return 1
    fi
    cp "${target}.example" "$target"
    log "создан: $target"
    return 0
}

DB_PASS="$(get_kv shared.env DB_PASSWORD)"
if [[ -z "$DB_PASS" || "$DB_PASS" == "changeme" ]]; then DB_PASS="local_$(rand 8)"; fi

# --- shared.env ---
if create shared.env; then
    set_kv shared.env DB_PASSWORD "$DB_PASS"
    set_kv shared.env PUBLIC_BASE_URL "http://localhost:8080"
    set_kv shared.env BASE_URL_MAPS "http://localhost:8080/maps/"
fi

# --- db_custom/.env (пароль Postgres должен совпадать с DB_PASSWORD) ---
if create db_custom/.env; then
    set_kv db_custom/.env POSTGRES_PASSWORD "$DB_PASS"
fi

# --- annotator/.env ---
if create annotator/.env; then
    set_kv annotator/.env ANNOTATOR_API_TOKEN "$(rand 16)"
fi
ANN_TOKEN="$(get_kv annotator/.env ANNOTATOR_API_TOKEN)"

# --- AdminPanel/.env ---
if create AdminPanel/.env; then
    set_kv AdminPanel/.env SESSION_SECRET_KEY "$(rand 32)"
    set_kv AdminPanel/.env DB_PASSWORD "$DB_PASS"
fi
# токен админки всегда приводим к токену аннотатора
set_kv AdminPanel/.env ANNOTATOR_URL "http://annotator:8010"
set_kv AdminPanel/.env ANNOTATOR_TOKEN "$ANN_TOKEN"

# --- остальные сервисы: нужны только для полного запуска, но compose проверяет наличие файлов ---
for f in salut_bot/.env EcoBotProject/DialogService/.env dsapi/.env images-extractor/.env; do
    create "$f" || true
done

# --- папки для volume ---
mkdir -p data/postgres_data data/admin_db logs maps salut_bot/images \
         salut_bot/embedding_models dsapi/local_models dsapi/logs dsapi/results \
         annotator/models salut_bot/knowledge_base_scripts/Vector/faiss_index

# --- проверка согласованности паролей ---
for pair in "shared.env:DB_PASSWORD" "db_custom/.env:POSTGRES_PASSWORD" "AdminPanel/.env:DB_PASSWORD"; do
    file="${pair%%:*}"; key="${pair##*:}"
    val="$(get_kv "$file" "$key")"
    if [[ "$val" != "$DB_PASS" ]]; then
        warn "ВНИМАНИЕ: $file: $key отличается от DB_PASSWORD в shared.env — выровняйте вручную"
    fi
done

log "Готово. Логин в админку по умолчанию: admin / admin"
