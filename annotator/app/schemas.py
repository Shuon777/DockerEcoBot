from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class AnnotateRequest(BaseModel):
    image_url: str = Field(..., description="http(s)-ссылка или относительный путь /images/...")
    features: Optional[List[str]] = Field(None, description="Имена признаков; пусто — все подходящие")
    executors: Optional[List[str]] = Field(None, description="Id моделей; пусто — все загруженные")
    lifeform: Optional[str] = Field(None, description="Флора/Фауна — отсекает неподходящие признаки")
    resource_id: Optional[int] = Field(None, description="Вернётся в ответе как есть")


class TaskInfo(BaseModel):
    task_id: str
    status: TaskStatus
    progress: int = 0
    resource_id: Optional[int] = None
    created_at: str
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    error: Optional[str] = None
    queue_position: Optional[int] = None


class ExecutorAnswer(BaseModel):
    executor: str
    value: Optional[str]
    confidence: Optional[float]
    note: Optional[str] = None
    error: Optional[str] = None


class FeatureResult(BaseModel):
    verdict: Optional[str]
    confidence: float
    agreement: str
    top_value: Optional[str]
    by_executor: List[ExecutorAnswer]


class AnnotationResult(BaseModel):
    task_id: str
    resource_id: Optional[int]
    status: TaskStatus
    executors: List[str]
    threshold: float
    features: Dict[str, FeatureResult]
    features_for_db: Dict[str, str]
    skipped_features: Dict[str, str] = {}
    caption: Optional[str] = None
    timing_sec: Dict[str, float] = {}
    meta: Dict[str, Any] = {}
