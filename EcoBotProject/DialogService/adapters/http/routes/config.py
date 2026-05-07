import logging
from pathlib import Path
from fastapi import APIRouter, Body
from dotenv import dotenv_values, set_key

logger = logging.getLogger(__name__)
router = APIRouter()

ENV_PATH = Path(__file__).parent.parent.parent.parent / ".env"


@router.get("/config")
async def get_config():
    if ENV_PATH.exists():
        return dotenv_values(ENV_PATH)
    return {}


@router.post("/config")
async def update_config(data: dict = Body(...)):
    if not ENV_PATH.exists():
        ENV_PATH.touch()
    for key, value in data.items():
        set_key(str(ENV_PATH), key, str(value))
    return {"status": "success", "message": "Конфигурация обновлена"}
