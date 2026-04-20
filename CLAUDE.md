# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**DockerEcoBot** is a Telegram chatbot eco-assistant about flora and fauna of the Lake Baikal region. It is a multi-service system orchestrated via Docker Compose.

## Services Architecture

Six microservices communicate over a Docker network:

| Service | Path | Port | Stack |
|---------|------|------|-------|
| Telegram Bot | `EcoBotProject/TelegramBot/` | — | Python 3.10, aiogram 2.25 |
| Backend API | `salut_bot/` | 5555 | Python 3.10, Flask 3.1 / FastAPI 0.110 |
| NLU | `EcoBotProject/RasaProject/` | 5005 | Python 3.9, Rasa 3.9 |
| GigaChat Fallback | `EcoBotProject/GigaChatAPI/` | — | Flask |
| Database | `db_custom/` | 5432 | PostgreSQL 14 + PostGIS 3.2 + pgvector 0.8 |
| Cache / Proxy | Redis + Nginx | 6379 / 80 | Alpine images |

## Commands

### Run everything
```bash
docker-compose up --build
docker-compose down
```

### Run single service
```bash
docker-compose up --build telegram
docker-compose up --build backend
```

### Backend tests (from `salut_bot/`)
```bash
pytest                          # all tests
pytest -m unit
pytest -m regression
pytest -m integration
pytest tests/unit/search_api/test_use_cases.py -v
```

### Manual start (without Docker)
```bash
# Backend
cd salut_bot && pip install -r requirements.txt && python api.py

# Bot
cd EcoBotProject/TelegramBot && pip install -r requirements.txt && python bot.py
```

## Data Flow

```
Telegram User
     │
     ▼
bot.py (aiogram)
     │
     ▼
Dialogue System (logic/DialogSystem/)
  ├─ rewriter.py   — LLM-based context-aware query rewriting (history from Redis)
  ├─ router.py     — semantic routing → BIOLOGY / INFRASTRUCTURE / KNOWLEDGE / CHITCHAT
  └─ workers/      — biology.py, infrastructure.py, knowledge.py
     │
     ▼ HTTP (aiohttp)
salut_bot Backend API (port 5555)
  ├─ search_service.py   — FAISS vector search (BGE-M3 embeddings)
  ├─ relational_service.py — PostgreSQL species/distributions
  └─ geo_service.py      — PostGIS geospatial + Folium map generation
     │
     ▼
PostgreSQL + PostGIS + pgvector  ←→  Redis (session state, TTL 900s)
Nginx (serves generated maps at port 80)
```

Optional fallback path: Router → Rasa (structured intents) → GigaChat LLM.

## Key Subsystems

### Dialogue System (`EcoBotProject/TelegramBot/logic/DialogSystem/`)
Event-driven orchestrator pattern introduced as the main request dispatcher:
- `orchestrator.py` — entry point, calls rewriter → router → worker
- `state_manager.py` — Redis-backed slot state per user (`intent`, `object_name`, `location`, etc.)
- `router.py` — semantic classification of user query into one of four intents

### Backend Search (`salut_bot/core/search_service.py`)
FAISS indices loaded at startup from `salut_bot/knowledge_base_scripts/Vector/faiss_index`. Embeddings generated with BGE-M3 (`salut_bot/embedding_models/`).

### Context Manager (`EcoBotProject/TelegramBot/utils/context_manager.py`)
Stores per-user conversation history and state in Redis. Used by `rewriter.py` to inject recent turns before routing.

### Backend API routes (`salut_bot/app/routes/`)
- `/api/species/description/` — species details
- `/api/get_coords` — coordinates lookup
- `/api/coords_to_map` — map generation
- `/api/objects_in_polygon_simply` — area queries
- `/api/ask` — knowledge base semantic search

## Environment Variables

Each service has its own `.env` file:

| File | Variables |
|------|-----------|
| `EcoBotProject/TelegramBot/.env` | `BOT_TOKEN`, `RASA_WEBHOOK_URL`, `GIGACHAT_FALLBACK_URL`, `ECOBOT_API_BASE_URL` |
| `salut_bot/.env` | `DB_HOST`, `DB_USER`, `DB_PASSWORD`, `REDIS_HOST`, `REDIS_PORT`, `MAPS_DIR`, `PUBLIC_BASE_URL` |
| `salut_bot/.env.test` | Test DB config used by pytest |
| `db_custom/.env` | `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` |

LLM provider is selected via `LLM_PROVIDER` (`qwen` for local Ollama, `gigachat` for Sber API). Sber key: `SBER_KEY_ENTERPRICE`.

## Testing Strategy

Tests live in `salut_bot/tests/` with pytest markers: `unit`, `integration`, `regression`, `e2e`, `smoke`. Configuration in `salut_bot/pytest.ini`. Use `.env.test` for isolated DB access.
