import os
import logging
import aiohttp
import redis.asyncio as redis
from fastapi import APIRouter, Body, HTTPException, Request

from application.search.slot_classifier import SlotClassifier
from application.search.slot_search_executor import SlotSearchExecutor
from application.search.context_manager import ConversationHistory
from application.search.dialogue_orchestrator import DialogueOrchestrator

logger = logging.getLogger(__name__)
router = APIRouter()


def _make_orchestrator(request: Request) -> DialogueOrchestrator:
    provider = os.getenv("LLM_PROVIDER", "qwen")
    redis_host = os.getenv("REDIS_HOST", "redis")
    redis_port = int(os.getenv("REDIS_PORT", "6379"))
    redis_client = redis.Redis(host=redis_host, port=redis_port, db=0, decode_responses=True)
    classifier = SlotClassifier(provider=provider, valid_features=request.app.state.valid_features)
    executor = SlotSearchExecutor(session=request.app.state.session)
    history = ConversationHistory(redis_client=redis_client)
    return DialogueOrchestrator(
        classifier=classifier,
        executor=executor,
        history=history,
        redis_client=redis_client,
    )


@router.post("/classify")
async def classify_query(request: Request, data: dict = Body(...)):
    query = data.get("query", "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="query required")
    provider = os.getenv("LLM_PROVIDER", "qwen")
    classifier = SlotClassifier(provider=provider, valid_features=request.app.state.valid_features)
    return await classifier.classify(query)


@router.post("/search_pipeline")
async def search_pipeline(request: Request, data: dict = Body(...)):
    query = data.get("query", "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="query required")
    user_id: str | None = data.get("user_id") or None
    orchestrator = _make_orchestrator(request)
    return await orchestrator.process(query, user_id=user_id)
