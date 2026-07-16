from pydantic import BaseModel
from typing import Optional, Any, Dict
from enum import Enum
import uuid

class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

class TaskInfo(BaseModel):
    session_id: str
    status: TaskStatus
    progress: int = 0  # Процент выполнения
    result_file: Optional[str] = None
    error: Optional[str] = None

# Глобальный реестр задач (в памяти)
ACTIVE_JOBS: Dict[str, TaskInfo] = {}