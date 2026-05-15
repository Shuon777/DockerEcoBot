import logging
from pathlib import Path
from fastapi import APIRouter, Body
from dotenv import dotenv_values, set_key

logger = logging.getLogger(__name__)
router = APIRouter()

ENV_PATH = Path(__file__).parent.parent.parent.parent / ".env"
PROMPTS_DIR = Path(__file__).parent.parent.parent.parent / "prompts"


@router.get("/prompts")
async def get_prompts():
    if not PROMPTS_DIR.exists():
        return {}
    return {f.name: f.read_text(encoding="utf-8") for f in sorted(PROMPTS_DIR.glob("*.txt"))}


@router.post("/prompts")
async def update_prompts(data: dict = Body(...)):
    PROMPTS_DIR.mkdir(exist_ok=True)
    for filename, content in data.items():
        (PROMPTS_DIR / filename).write_text(content, encoding="utf-8")
    return {"status": "success", "message": "Промпты обновлены"}


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
