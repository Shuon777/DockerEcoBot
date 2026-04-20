from fastapi import APIRouter, BackgroundTasks, HTTPException, Depends,Query
from app.api.deps import validate_token
from fastapi.responses import FileResponse
import uuid
import json
import os
from app.models.testing_status import ACTIVE_JOBS, TaskInfo, TaskStatus
from app.services.pipeline.dynamic_pipeline import IntegratedDynamicPipeline
from app.models.pipeline_model import FullTestResult
from typing import Dict, Any, List, Optional
router = APIRouter()
pipeline = IntegratedDynamicPipeline()


@router.post("/start", response_model=TaskInfo)
async def start_testing(background_tasks: BackgroundTasks, objs: Optional[list[str]] = Query(
        default=None,
        description="Список ОФФ для тестирования. Можно передать один или несколько: ?objs=Нерпа&objs=Омуль"
    ), mode: str = "llm", token: str = Depends(validate_token)):
    """
    Запуск тестирования. Генерирует ID сессии
    """
    session_id = str(uuid.uuid4())
    objs = objs if objs else []
    # Инициализируем статус
    task_info = TaskInfo(session_id=session_id, status=TaskStatus.PENDING)
    ACTIVE_JOBS[session_id] = task_info

    # Запускаем фоновую задачу
    background_tasks.add_task(pipeline.process_dynamic_testing, session_id, mode, objs)

    return task_info


@router.get("/status/{session_id}", response_model=TaskInfo)
async def get_status(session_id: str, token: str = Depends(validate_token)):
    """
    Получение текущего прогресса и статуса задачи.
    """
    if session_id not in ACTIVE_JOBS:
        raise HTTPException(status_code=404, detail="Session ID not found")
    return ACTIVE_JOBS[session_id]


@router.get("/result/{session_id}")
async def get_result(session_id: str, token: str = Depends(validate_token)):
    """
    Скачивание или получение содержимого результирующего JSON.
    """
    if session_id not in ACTIVE_JOBS:
        raise HTTPException(status_code=404, detail="Session ID not found")

    job = ACTIVE_JOBS[session_id]

    if job.status != TaskStatus.COMPLETED:
        raise HTTPException(status_code=400, detail=f"Result not ready. Current status: {job.status}")

    if job.result_file and os.path.exists(job.result_file):
        # Возвращаем файл для скачивания
        return FileResponse(
            path=job.result_file,
            media_type='application/json',
            filename=f"result_{session_id}.json"
        )

    raise HTTPException(status_code=404, detail="Result file missing on server")


@router.get("/result/{session_id}/json", response_model=FullTestResult)
async def get_json_result(
        session_id: str,
        token: str = Depends(validate_token)
):
    """
    Возвращает содержимое результатов тестирования в формате JSON.
    """
    if session_id not in ACTIVE_JOBS:
        raise HTTPException(status_code=404, detail="Сессия не найдена")

    job = ACTIVE_JOBS[session_id]

    if job.status != TaskStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="Результат еще не готов")

    try:
        with open(job.result_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка чтения данных: {e}")