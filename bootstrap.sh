#!/usr/bin/env bash
# =============================================================
# bootstrap.sh — точка входа для установки EcoBot на новый сервер
#
# Использование (одна команда на сервере):
#   curl -fsSL https://raw.githubusercontent.com/Shuon777/DockerEcoBot/master/bootstrap.sh | sudo bash
#
# Или скопировать файл и запустить:
#   sudo bash bootstrap.sh
# =============================================================
set -euo pipefail

# Переключаем stdin на терминал (нужно при запуске через curl | bash)
exec < /dev/tty

REPO_URL="https://github.com/Shuon777/DockerEcoBot.git"
DEFAULT_INSTALL_DIR="/opt/ecoassistant"


RED='\033[0;31m'; YELLOW='\033[1;33m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'; NC='\033[0m'
log()  { echo -e "${GREEN}[bootstrap]${NC} $*"; }
warn() { echo -e "${YELLOW}[bootstrap]${NC} $*"; }
die()  { echo -e "${RED}[bootstrap] ERROR:${NC} $*" >&2; exit 1; }
ask()  { echo -e "${CYAN}[bootstrap]${NC} $*"; }

# -----------------------------------------------------------
# 1. Зависимости
# -----------------------------------------------------------
log "Проверка зависимостей..."
command -v git    >/dev/null 2>&1 || die "git не установлен. Установите: apt install git"
command -v docker >/dev/null 2>&1 || die "docker не установлен. См: https://docs.docker.com/engine/install/"
docker compose version >/dev/null 2>&1 || die "docker compose plugin не установлен"
log "Зависимости ОК"

# -----------------------------------------------------------
# 2. Директория установки
# -----------------------------------------------------------
echo ""
ask "Директория установки [${DEFAULT_INSTALL_DIR}]:"
read -r -p "Install dir: " INSTALL_DIR < /dev/tty
INSTALL_DIR="${INSTALL_DIR:-$DEFAULT_INSTALL_DIR}"

if [[ -d "$INSTALL_DIR/.git" ]]; then
    warn "Репозиторий уже существует в $INSTALL_DIR"
    ask "Обновить (git pull) существующую установку? [y/N]:"
    read -r -p "Обновить? " UPDATE < /dev/tty
    if [[ "$UPDATE" =~ ^[Yy]$ ]]; then
        log "Обновление репозитория..."
        git -C "$INSTALL_DIR" pull origin master
    else
        log "Используем существующий репозиторий без обновления"
    fi
elif [[ -d "$INSTALL_DIR" && "$(ls -A "$INSTALL_DIR")" ]]; then
    die "Директория $INSTALL_DIR уже существует и не пустая. Укажите другую директорию."
else
    # -----------------------------------------------------------
    # 3. Клонирование
    # -----------------------------------------------------------
    log "Клонирование репозитория в $INSTALL_DIR..."
    git clone "$REPO_URL" "$INSTALL_DIR"
    log "Репозиторий склонирован"
fi

# -----------------------------------------------------------
# 4. Запуск основного установщика
# -----------------------------------------------------------
cd "$INSTALL_DIR"
log "Запуск install.sh..."
bash install.sh
