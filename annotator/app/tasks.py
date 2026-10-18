"""Очередь задач и сам пайплайн аннотации.

Модели живут на одной GPU, поэтому задачи выполняет ОДИН фоновый поток по очереди.
Реестр задач — в памяти (как в dsapi). При перезапуске сервиса незавершённые задачи теряются;
для продакшена реестр можно вынести в Redis, интерфейс TaskManager при этом не меняется.
"""
import logging
import queue
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

from app.aggregator import Vote, aggregate
from app.executors.base import Executor
from app.features import FeatureCatalog, FeatureSpec, normalize_lifeform
from app.images import ImageError, download, open_image, resolve_url
from app.schemas import TaskStatus

log = logging.getLogger("annotator")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Job:
    image_url: Optional[str] = None
    image_bytes: Optional[bytes] = None
    features: Optional[List[str]] = None
    executors: Optional[List[str]] = None
    lifeform: Optional[str] = None
    resource_id: Optional[int] = None


@dataclass
class Task:
    task_id: str
    job: Job
    status: TaskStatus = TaskStatus.PENDING
    progress: int = 0
    created_at: str = field(default_factory=_now)
    created_ts: float = field(default_factory=time.time)
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    error: Optional[str] = None
    result: Optional[dict] = None


class ValidationError(ValueError):
    pass


class AnnotationPipeline:
    def __init__(self, settings, catalog: FeatureCatalog, executors: List[Executor], captioner=None):
        self.settings = settings
        self.catalog = catalog
        self.executors = {e.id: e for e in executors}
        self.captioner = captioner

    # ---------- проверка запроса (до постановки в очередь) ----------
    def plan(self, job: Job):
        lifeform = normalize_lifeform(job.lifeform)
        if job.executors:
            unknown = [e for e in job.executors if e not in self.executors]
            if unknown:
                raise ValidationError(f"исполнители не загружены: {', '.join(unknown)}")
            executors = [self.executors[e] for e in job.executors]
        else:
            executors = list(self.executors.values())
        if not executors:
            raise ValidationError("нет ни одной загруженной модели")

        if job.features:
            unknown = [f for f in job.features if self.catalog.get(f) is None]
            if unknown:
                raise ValidationError(f"неизвестные признаки: {', '.join(unknown)}")
            requested = [self.catalog.get(f) for f in job.features]
        else:
            requested = self.catalog.all()

        features, skipped = [], {}
        for f in requested:
            if not f.applies(lifeform):
                skipped[f.name] = f"не применяется к {job.lifeform}"
            elif not any(e.supports(f) for e in executors):
                skipped[f.name] = "ни одна из выбранных моделей не умеет этот признак"
            else:
                features.append(f)
        if not features:
            raise ValidationError("нет признаков, которые можно посчитать выбранными моделями")
        return executors, features, skipped

    # ---------- выполнение ----------
    def run(self, task: Task, on_progress) -> dict:
        timings: Dict[str, float] = {}
        executors, features, skipped = self.plan(task.job)
        work = {e.id: [f for f in features if e.supports(f)] for e in executors}
        total = 1 + sum(len(v) for v in work.values()) + (1 if self.captioner else 0)
        done = 0

        def step(n: int = 1):
            nonlocal done
            done += n
            on_progress(min(99, int(done * 100 / total)))

        t0 = time.time()
        if task.job.image_bytes is not None:
            image = open_image(task.job.image_bytes)
        else:
            url = resolve_url(task.job.image_url, self.settings.image_base_url,
                              self.settings.image_url_rewrite)
            image = open_image(download(url, self.settings.max_image_bytes,
                                        self.settings.image_timeout_sec))
        task.job.image_bytes = None  # не держим байты в памяти после загрузки
        timings["image"] = round(time.time() - t0, 2)
        step()

        answers: Dict[str, Dict[str, object]] = {f.name: {} for f in features}
        for executor in executors:
            feats = work[executor.id]
            if not feats:
                continue
            t0 = time.time()
            try:
                preds = executor.predict_many(image, feats, on_progress=step)
            except Exception as exc:  # noqa: BLE001 — модель целиком упала
                log.exception("%s упал", executor.id)
                from app.executors.base import Prediction
                preds = {f.name: Prediction(error=f"{type(exc).__name__}: {exc}") for f in feats}
                step(len(feats))
            for name, pred in preds.items():
                answers[name][executor.id] = pred
            timings[executor.id] = round(time.time() - t0, 2)

        caption = None
        if self.captioner:
            t0 = time.time()
            try:
                caption = self.captioner.caption(image)
            except Exception as exc:  # noqa: BLE001
                log.warning("BLIP упал: %s", exc)
            timings["caption"] = round(time.time() - t0, 2)
            step()

        features_out, for_db = {}, {}
        for f in features:
            votes = [Vote(eid, self.settings.weight(eid), pred) for eid, pred in answers[f.name].items()]
            verdict = aggregate(votes, self.settings.confidence_threshold, self.settings.llm_confidence)
            features_out[f.name] = {
                **verdict.to_dict(),
                "by_executor": [{"executor": v.executor_id, **v.prediction.to_dict()} for v in votes],
            }
            if verdict.value is not None:
                for_db[f.name] = verdict.value

        return {
            "task_id": task.task_id,
            "resource_id": task.job.resource_id,
            "status": TaskStatus.COMPLETED.value,
            "executors": [e.id for e in executors],
            "threshold": self.settings.confidence_threshold,
            "features": features_out,
            "features_for_db": for_db,
            "skipped_features": skipped,
            "caption": caption,
            "timing_sec": timings,
            "meta": {"image_size": list(image.size), "lifeform": normalize_lifeform(task.job.lifeform)},
        }


class TaskManager:
    def __init__(self, pipeline: AnnotationPipeline, settings):
        self.pipeline = pipeline
        self.settings = settings
        self._tasks: Dict[str, Task] = {}
        self._order: List[str] = []
        self._lock = threading.Lock()
        self._queue: "queue.Queue[str]" = queue.Queue()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._worker, name="annotator-worker", daemon=True)

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._queue.put("")  # разбудить поток

    # ---------- API ----------
    def submit(self, job: Job) -> Task:
        self.pipeline.plan(job)  # ошибки запроса — сразу, а не через статус failed
        self._cleanup()
        with self._lock:
            waiting = sum(1 for t in self._tasks.values() if t.status == TaskStatus.PENDING)
            if waiting >= self.settings.max_queue:
                raise OverflowError("очередь переполнена, попробуйте позже")
            task = Task(task_id=str(uuid.uuid4()), job=job)
            self._tasks[task.task_id] = task
            self._order.append(task.task_id)
        self._queue.put(task.task_id)
        return task

    def get(self, task_id: str) -> Optional[Task]:
        with self._lock:
            return self._tasks.get(task_id)

    def queue_position(self, task: Task) -> Optional[int]:
        if task.status != TaskStatus.PENDING:
            return None
        with self._lock:
            pending = [tid for tid in self._order if self._tasks[tid].status == TaskStatus.PENDING]
        return pending.index(task.task_id) + 1 if task.task_id in pending else None

    def stats(self) -> dict:
        with self._lock:
            counts: Dict[str, int] = {}
            for t in self._tasks.values():
                counts[t.status.value] = counts.get(t.status.value, 0) + 1
        return counts

    # ---------- внутреннее ----------
    def _cleanup(self):
        cutoff = time.time() - self.settings.task_ttl_sec
        with self._lock:
            old = [tid for tid, t in self._tasks.items()
                   if t.status in (TaskStatus.COMPLETED, TaskStatus.FAILED) and t.created_ts < cutoff]
            for tid in old:
                self._tasks.pop(tid, None)
            self._order = [tid for tid in self._order if tid in self._tasks]

    def _worker(self):
        while not self._stop.is_set():
            task_id = self._queue.get()
            task = self.get(task_id) if task_id else None
            if task is None:
                continue
            task.status, task.started_at = TaskStatus.RUNNING, _now()

            def on_progress(p: int):
                task.progress = p

            try:
                task.result = self.pipeline.run(task, on_progress)
                task.progress, task.status = 100, TaskStatus.COMPLETED
            except (ImageError, ValidationError) as exc:
                task.status, task.error = TaskStatus.FAILED, str(exc)
            except Exception as exc:  # noqa: BLE001
                log.exception("Задача %s упала", task_id)
                task.status, task.error = TaskStatus.FAILED, f"{type(exc).__name__}: {exc}"
            finally:
                task.finished_at = _now()
                task.job.image_bytes = None
