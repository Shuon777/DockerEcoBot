#!/usr/bin/env bash
# =============================================================
# install.sh — установка EcoBot на новый сервер
# Использование: sudo bash install.sh
# =============================================================
set -euo pipefail

REPO_ROOT="$(cd "${BASH_SOURCE[0]%/*}" && pwd)"

RED='\033[0;31m'; YELLOW='\033[1;33m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'; NC='\033[0m'
log()  { echo -e "${GREEN}[install]${NC} $*"; }
warn() { echo -e "${YELLOW}[install]${NC} $*"; }
die()  { echo -e "${RED}[install] ERROR:${NC} $*" >&2; exit 1; }
ask()  { echo -e "${CYAN}[install]${NC} $*"; }

# -----------------------------------------------------------
# 1. Проверка зависимостей
# -----------------------------------------------------------
log "Проверка зависимостей..."
command -v docker       >/dev/null 2>&1 || die "docker не установлен"
docker compose version  >/dev/null 2>&1 || die "docker compose plugin не установлен"
command -v python3      >/dev/null 2>&1 || die "python3 не установлен"
command -v git          >/dev/null 2>&1 || die "git не установлен"
log "Зависимости ОК"

# -----------------------------------------------------------
# 2. Сбор конфигурации
# -----------------------------------------------------------
echo ""
ask "=== Настройка сервера ==="

ask "Публичный адрес сервера (домен или IP, без слэша в конце)."
ask "Примеры: https://ecobot.example.com  |  http://192.168.1.10"
read -r -p "PUBLIC_BASE_URL: " PUBLIC_BASE_URL
PUBLIC_BASE_URL="${PUBLIC_BASE_URL%/}"
[[ -n "$PUBLIC_BASE_URL" ]] || die "PUBLIC_BASE_URL не может быть пустым"

USE_SSL=false
DOMAIN=""
if [[ "$PUBLIC_BASE_URL" == https://* ]]; then
    USE_SSL=true
    DOMAIN="${PUBLIC_BASE_URL#https://}"
    log "Режим HTTPS, домен: $DOMAIN"
else
    log "Режим HTTP-only"
fi

ask "Пароль PostgreSQL (Enter = оставить из shared.env):"
read -r -s -p "DB_PASSWORD: " DB_PASSWORD_INPUT
echo ""

ask "Telegram Bot Token (Enter = оставить из shared.env):"
read -r -s -p "BOT_TOKEN: " BOT_TOKEN_INPUT
echo ""

echo ""

# -----------------------------------------------------------
# 3. Генерация shared.env
# -----------------------------------------------------------
log "Настройка shared.env..."

if [[ ! -f "$REPO_ROOT/shared.env" ]]; then
    cp "$REPO_ROOT/shared.env.example" "$REPO_ROOT/shared.env"
    warn "shared.env создан из шаблона — заполните оставшиеся секреты вручную"
fi

# Подставляем введённые значения
sed -i "s|^PUBLIC_BASE_URL=.*|PUBLIC_BASE_URL=$PUBLIC_BASE_URL|" "$REPO_ROOT/shared.env"
sed -i "s|^BASE_URL_MAPS=.*|BASE_URL_MAPS=$PUBLIC_BASE_URL/maps/|" "$REPO_ROOT/shared.env"

if [[ -n "$DB_PASSWORD_INPUT" ]]; then
    sed -i "s|^DB_PASSWORD=.*|DB_PASSWORD=$DB_PASSWORD_INPUT|" "$REPO_ROOT/shared.env"
    sed -i "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$DB_PASSWORD_INPUT|" "$REPO_ROOT/db_custom/.env" 2>/dev/null || true
fi

if [[ -n "$BOT_TOKEN_INPUT" ]]; then
    sed -i "s|^BOT_TOKEN=.*|BOT_TOKEN=$BOT_TOKEN_INPUT|" "$REPO_ROOT/shared.env"
fi

log "shared.env готов"

# -----------------------------------------------------------
# 4. AdminPanel — генерация SESSION_SECRET_KEY
# -----------------------------------------------------------
if [[ ! -f "$REPO_ROOT/AdminPanel/.env" ]]; then
    cp "$REPO_ROOT/AdminPanel/.env.example" "$REPO_ROOT/AdminPanel/.env"
fi

# Если ключ не задан (заглушка) — генерируем случайный
if grep -q "replace-with-random-secret" "$REPO_ROOT/AdminPanel/.env"; then
    SESSION_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    sed -i "s|replace-with-random-secret|$SESSION_SECRET|" "$REPO_ROOT/AdminPanel/.env"
    log "SESSION_SECRET_KEY сгенерирован"
fi

# -----------------------------------------------------------
# 5. Nginx — выбор конфига
# -----------------------------------------------------------
log "Настройка nginx..."
mkdir -p "$REPO_ROOT/certbot/www" "$REPO_ROOT/certbot/conf"

if [[ "$USE_SSL" == true ]]; then
    sed "s/\${DOMAIN}/$DOMAIN/g" "$REPO_ROOT/nginx/nginx.https.conf" > "$REPO_ROOT/nginx/nginx.conf"
    log "nginx: HTTPS режим (домен: $DOMAIN)"

    warn "Для получения сертификата Let's Encrypt выполните ПОСЛЕ первого запуска:"
    warn "  docker run --rm -v \$(pwd)/certbot/www:/var/www/certbot -v \$(pwd)/certbot/conf:/etc/letsencrypt certbot/certbot certonly --webroot -w /var/www/certbot -d $DOMAIN --email your@email.com --agree-tos"
else
    cp "$REPO_ROOT/nginx/nginx.http.conf" "$REPO_ROOT/nginx/nginx.conf"
    log "nginx: HTTP-only режим"
fi

# -----------------------------------------------------------
# 6. Создание необходимых директорий
# -----------------------------------------------------------
log "Создание директорий..."
mkdir -p \
    "$REPO_ROOT/data/postgres_data" \
    "$REPO_ROOT/data/admin_db" \
    "$REPO_ROOT/logs" \
    "$REPO_ROOT/maps" \
    "$REPO_ROOT/salut_bot/images" \
    "$REPO_ROOT/salut_bot/embedding_models" \
    "$REPO_ROOT/dsapi/local_models" \
    "$REPO_ROOT/dsapi/logs" \
    "$REPO_ROOT/dsapi/results"

# -----------------------------------------------------------
# 7. Скачивание ML-моделей
# -----------------------------------------------------------
echo ""
ask "Скачать ML-модели сейчас? (salut_bot ~2.7GB + dsapi ~4.6GB)"
ask "Можно пропустить и запустить позже: bash scripts/download_models.sh"
read -r -p "Скачать? [y/N]: " DOWNLOAD_MODELS
if [[ "$DOWNLOAD_MODELS" =~ ^[Yy]$ ]]; then
    log "Скачивание моделей (это займёт время)..."
    bash "$REPO_ROOT/scripts/download_models.sh"
else
    warn "Пропущено. Перед запуском выполните: bash scripts/download_models.sh"
fi

# -----------------------------------------------------------
# 8. Запуск сервисов
# -----------------------------------------------------------
echo ""
log "Запуск docker compose..."
cd "$REPO_ROOT"
docker compose up -d --build

# -----------------------------------------------------------
# 9. Ожидание готовности backend
# -----------------------------------------------------------
log "Ожидание запуска backend..."
RETRIES=30
until docker compose exec -T backend python -c "import sys; sys.exit(0)" 2>/dev/null; do
    RETRIES=$((RETRIES - 1))
    [[ $RETRIES -le 0 ]] && die "backend не запустился за 60 секунд"
    sleep 2
done
log "backend готов"

# -----------------------------------------------------------
# 10. Инициализация БД
# -----------------------------------------------------------
echo ""
ask "Инициализировать БД начальными данными?"
ask "(--full удаляет и пересоздаёт схему; пропустите если БД уже заполнена)"
read -r -p "Инициализировать? [y/N]: " INIT_DB
if [[ "$INIT_DB" =~ ^[Yy]$ ]]; then
    log "Генерация resources_deploy.json с адресом $PUBLIC_BASE_URL..."
    sed "s|{{PUBLIC_BASE_URL}}|$PUBLIC_BASE_URL|g" \
        "$REPO_ROOT/salut_bot/json_files/resources.json" \
        > "$REPO_ROOT/salut_bot/json_files/resources_deploy.json"

    log "Запуск db_importer..."
    docker compose exec -T backend bash -c "
        cd knowledge_base_scripts/Relational &&
        python -m db_importer.main --full \
            --resources-file /app/json_files/resources_deploy.json
    "

    rm -f "$REPO_ROOT/salut_bot/json_files/resources_deploy.json"
    log "БД инициализирована"
else
    warn "Пропущено. Для инициализации позже:"
    warn "  bash scripts/init_db.sh"
fi

# -----------------------------------------------------------
# 11. Итог
# -----------------------------------------------------------
echo ""
log "========================================"
log "  EcoBot установлен!"
log "========================================"
log "Адрес:       $PUBLIC_BASE_URL"
log "AdminPanel:  $PUBLIC_BASE_URL/admin/"
echo ""
if grep -q "changeme\|your_.*_here\|your_sber_key" "$REPO_ROOT/shared.env" 2>/dev/null; then
    warn "В shared.env остались незаполненные значения (changeme / your_*_here)"
    warn "Отредактируйте shared.env и перезапустите: docker compose restart"
fi
