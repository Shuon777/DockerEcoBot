"""Сервис-аннотатор изображений ЭкоБайкал.

POST /annotate            — поставить задачу (фото по ссылке), сразу вернуть task_id
POST /annotate/upload     — то же, но файлом (multipart)
GET  /tasks/{id}          — статус: pending / running / completed / failed, прогресс
GET  /tasks/{id}/result   — результат (когда completed)
GET  /features            — какие признаки умеет искать сервис
GET  /executors           — какие модели загружены
GET  /health
"""
import logging
from contextlib import asynccontextmanager
from typing import List, Optional

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from app.config import Settings
from app.features import FeatureCatalog, normalize_lifeform
from app.schemas import AnnotateRequest, AnnotationResult, TaskInfo, TaskStatus
from app.tasks import AnnotationPipeline, Job, TaskManager, ValidationError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def create_app(settings: Optional[Settings] = None, executors=None, captioner=None,
               failed: Optional[dict] = None) -> FastAPI:
    """executors/captioner можно передать готовыми (тесты). Иначе грузятся при старте."""
    settings = settings or Settings()
    catalog = FeatureCatalog.load(settings.features_path)
    state = {"failed": dict(failed or {}), "caption_error": None}

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        nonlocal executors, captioner
        if executors is None:
            from app.executors.registry import load_captioner, load_executors
            executors, state["failed"] = load_executors(settings)
            captioner, state["caption_error"] = load_captioner(settings)
        pipeline = AnnotationPipeline(settings, catalog, executors, captioner)
        manager = TaskManager(pipeline, settings)
        manager.start()
        app.state.manager, app.state.pipeline = manager, pipeline
        yield
        manager.stop()

    app = FastAPI(title="EcoBaikal Annotator", version="0.1.0", lifespan=lifespan)

    def check_token(x_api_token: Optional[str] = Header(None)):
        if settings.api_token and x_api_token != settings.api_token:
            raise HTTPException(status_code=401, detail="неверный X-API-Token")

    def manager() -> TaskManager:
        return app.state.manager

    def task_info(task) -> TaskInfo:
        return TaskInfo(
            task_id=task.task_id, status=task.status, progress=task.progress,
            resource_id=task.job.resource_id, created_at=task.created_at,
            started_at=task.started_at, finished_at=task.finished_at, error=task.error,
            queue_position=manager().queue_position(task),
        )

    def submit(job: Job):
        try:
            task = manager().submit(job)
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        except OverflowError as exc:
            raise HTTPException(status_code=503, detail=str(exc))
        return JSONResponse(status_code=202, content=task_info(task).model_dump(mode="json"))

    @app.get("/health")
    def health():
        pipeline = app.state.pipeline
        return {"status": "ok", "executors": list(pipeline.executors), "failed": state["failed"],
                "caption": pipeline.captioner is not None, "tasks": manager().stats()}

    @app.get("/features", dependencies=[Depends(check_token)])
    def features(lifeform: Optional[str] = None):
        lf = normalize_lifeform(lifeform)
        loaded = list(app.state.pipeline.executors.values())
        return [{
            "name": f.name, "values": f.value_names, "applies_to": f.applies_to,
            "executors": [e.id for e in loaded if e.supports(f)],
        } for f in catalog.all() if f.applies(lf)]

    @app.get("/executors", dependencies=[Depends(check_token)])
    def list_executors():
        loaded = [{**e.describe(), "loaded": True} for e in app.state.pipeline.executors.values()]
        broken = [{"id": eid, "loaded": False, "error": err} for eid, err in state["failed"].items()]
        return loaded + broken

    @app.post("/annotate", status_code=202, response_model=TaskInfo, dependencies=[Depends(check_token)])
    def annotate(req: AnnotateRequest):
        return submit(Job(image_url=req.image_url, features=req.features, executors=req.executors,
                          lifeform=req.lifeform, resource_id=req.resource_id))

    @app.post("/annotate/upload", status_code=202, response_model=TaskInfo,
              dependencies=[Depends(check_token)])
    async def annotate_upload(
        file: UploadFile = File(...),
        features: Optional[str] = Form(None, description="через запятую"),
        executors: Optional[str] = Form(None, description="через запятую"),
        lifeform: Optional[str] = Form(None),
        resource_id: Optional[int] = Form(None),
    ):
        data = await file.read(settings.max_image_bytes + 1)
        if len(data) > settings.max_image_bytes:
            raise HTTPException(status_code=413, detail="файл слишком большой")

        def split(raw: Optional[str]) -> Optional[List[str]]:
            items = [x.strip() for x in (raw or "").split(",") if x.strip()]
            return items or None

        return submit(Job(image_bytes=data, features=split(features), executors=split(executors),
                          lifeform=lifeform, resource_id=resource_id))

    @app.get("/tasks/{task_id}", response_model=TaskInfo, dependencies=[Depends(check_token)])
    def get_task(task_id: str):
        task = manager().get(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="задача не найдена")
        return task_info(task)

    @app.get("/tasks/{task_id}/result", response_model=AnnotationResult,
             dependencies=[Depends(check_token)])
    def get_result(task_id: str):
        task = manager().get(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="задача не найдена")
        if task.status == TaskStatus.FAILED:
            raise HTTPException(status_code=500, detail=f"задача завершилась с ошибкой: {task.error}")
        if task.status != TaskStatus.COMPLETED:
            raise HTTPException(status_code=409, detail=f"результат ещё не готов: {task.status.value}")
        return task.result

    return app


app = create_app()
