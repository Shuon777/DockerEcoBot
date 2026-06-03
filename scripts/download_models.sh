#!/usr/bin/env bash
# =============================================================
# download_models.sh — скачивание ML-моделей для всех сервисов
# Запускать из корня репозитория: bash scripts/download_models.sh
# =============================================================
set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

log() { echo "[download_models] $*"; }
die() { echo "[download_models] ERROR: $*" >&2; exit 1; }

# -----------------------------------------------------------
# 1. salut_bot — embedding модели (sentence-transformers)
# -----------------------------------------------------------
log "=== salut_bot: embedding models ==="

EMBED_DIR="$REPO_ROOT/salut_bot/embedding_models"
EMBED_SCRIPT="$REPO_ROOT/salut_bot/scripts/download_embedding_model_from_HF.py"

cd "$REPO_ROOT/salut_bot"
python "$EMBED_SCRIPT" "BAAI/bge-m3"                          || die "failed to download bge-m3"
python "$EMBED_SCRIPT" "sergeyzh/BERTA"                       || die "failed to download BERTA"
python "$EMBED_SCRIPT" "BAAI/bge-reranker-v2-m3"              || die "failed to download bge-reranker-v2-m3"
python "$EMBED_SCRIPT" "DiTy/cross-encoder-russian-msmarco"   || die "failed to download cross-encoder-russian-msmarco"

log "salut_bot: embedding models done ($(du -sh "$EMBED_DIR" | cut -f1))"

# -----------------------------------------------------------
# 2. dsapi — классификаторы (transformers)
# -----------------------------------------------------------
log "=== dsapi: local models ==="

cd "$REPO_ROOT/dsapi"
python setup_models.py || die "dsapi setup_models.py failed"

log "dsapi: local models done ($(du -sh "$REPO_ROOT/dsapi/local_models" | cut -f1))"

# -----------------------------------------------------------
# 3. Ollama модели (LLM)
# -----------------------------------------------------------
log "=== Ollama: LLM models ==="
log "Убедитесь что Ollama запущена на хосте, затем выполните:"
log "  ollama pull qwen2.5:14b"
log "  ollama pull qwen3-vl:32b     (для dsapi vision)"
log "(пропускаем автоматическое скачивание — требует работающей Ollama)"

# -----------------------------------------------------------
# 4. Итог
# -----------------------------------------------------------
log ""
log "=== Готово ==="
log "salut_bot/embedding_models: $(du -sh "$REPO_ROOT/salut_bot/embedding_models" | cut -f1)"
log "dsapi/local_models:         $(du -sh "$REPO_ROOT/dsapi/local_models" | cut -f1)"
log ""
log "Следующий шаг — собрать FAISS-индекс:"
log "  cd salut_bot && python knowledge_base_scripts/Vector/faiss_adapter.py"
