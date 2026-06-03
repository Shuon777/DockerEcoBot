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

# HF_TOKEN — опционально, ускоряет скачивание с HuggingFace
# Передать: HF_TOKEN=hf_xxx bash scripts/download_models.sh
HF_TOKEN="${HF_TOKEN:-}"
if [[ -n "$HF_TOKEN" ]]; then
    log "HuggingFace токен найден — используем авторизованные запросы"
    HF_ENV="-e HF_TOKEN=$HF_TOKEN"
else
    warn() { echo "[download_models] WARN: $*"; }
    warn "HF_TOKEN не задан — скачивание может быть медленным"
    warn "Для ускорения: HF_TOKEN=hf_xxx bash scripts/download_models.sh"
    HF_ENV=""
fi

# -----------------------------------------------------------
# 1. salut_bot — embedding модели (sentence-transformers)
# -----------------------------------------------------------
log "=== salut_bot: embedding models ==="

for MODEL in "BAAI/bge-m3" "sergeyzh/BERTA" "BAAI/bge-reranker-v2-m3" "DiTy/cross-encoder-russian-msmarco"; do
    log "Скачивание: $MODEL"
    docker compose run --rm --no-deps $HF_ENV backend \
        python scripts/download_embedding_model_from_HF.py "$MODEL" \
        || die "failed to download $MODEL"
done

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
log ""
log "=== Ollama: выполните вручную на хосте ==="
log "  ollama pull qwen2.5:14b"
log "  ollama pull qwen3-vl:32b"
log ""
log "=== Всё готово ==="
log "Следующий шаг (пересборка FAISS-индекса при необходимости):"
log "  bash scripts/build_faiss.sh"
