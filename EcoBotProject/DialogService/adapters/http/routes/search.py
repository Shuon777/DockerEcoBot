import os
import logging
from fastapi import APIRouter, Body, HTTPException, Request

from application.search.slot_classifier import SlotClassifier
from application.search.slot_search_executor import SlotSearchExecutor

logger = logging.getLogger(__name__)
router = APIRouter()


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
    provider = os.getenv("LLM_PROVIDER", "qwen")
    classifier = SlotClassifier(provider=provider, valid_features=request.app.state.valid_features)
    slots = await classifier.classify(query)
    executor = SlotSearchExecutor(session=request.app.state.session)
    return await executor.execute(query, slots)
