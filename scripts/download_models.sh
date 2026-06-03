#!/usr/bin/env bash
# =============================================================
# download_models.sh — скачивание ML-моделей через Docker
# Запускать из корня репозитория: bash scripts/download_models.sh
# =============================================================
set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

log() { echo "[download_models] $*"; }
die() { echo "[download_models] ERROR: $*" >&2; exit 1; }

# Базовые флаги для backend: переопределяем embedding_models без :ro
BACKEND_RUN="docker compose run --rm --no-deps
    -v ${REPO_ROOT}/salut_bot/embedding_models:/app/embedding_models
    backend"

# -----------------------------------------------------------
# 1. salut_bot — embedding модели (sentence-transformers)
# -----------------------------------------------------------
log "=== salut_bot: embedding models ==="

$BACKEND_RUN python scripts/download_embedding_model_from_HF.py "BAAI/bge-m3" \
    || die "failed to download bge-m3"

$BACKEND_RUN python scripts/download_embedding_model_from_HF.py "sergeyzh/BERTA" \
    || die "failed to download BERTA"

$BACKEND_RUN python scripts/download_embedding_model_from_HF.py "BAAI/bge-reranker-v2-m3" \
    || die "failed to download bge-reranker-v2-m3"

$BACKEND_RUN python scripts/download_embedding_model_from_HF.py "DiTy/cross-encoder-russian-msmarco" \
    || die "failed to download cross-encoder-russian-msmarco"

log "salut_bot: done"

# -----------------------------------------------------------
# 2. dsapi — классификаторы (transformers)
# -----------------------------------------------------------
log "=== dsapi: local models ==="

docker compose run --rm --no-deps dsapi python setup_models.py \
    || die "dsapi setup_models.py failed"

log "dsapi: done"

# -----------------------------------------------------------
# 3. Ollama (LLM) — ручной шаг
# -----------------------------------------------------------
log "=== Ollama: выполните вручную на хосте ==="
log "  ollama pull qwen2.5:14b"
log "  ollama pull qwen3-vl:32b"

log ""
log "=== Всё готово ==="
log "Следующий шаг (если нужно пересобрать FAISS-индекс):"
log "  bash scripts/build_faiss.sh"
