"""Реестр исполнителей: id из ANNOTATOR_EXECUTORS -> класс."""
import logging
from typing import Dict, List, Optional, Tuple

from app.executors.base import Executor

log = logging.getLogger("annotator")


def _classes() -> Dict[str, type]:
    # Импорт внутри функции: модули не тянут torch при импорте, тесты работают без него
    from app.executors.clip_executor import ClipExecutor
    from app.executors.detectors import GroundingDinoExecutor, Owlv2Executor
    from app.executors.gigachat_executor import GigaChatExecutor
    from app.executors.phenovision import PhenoVisionExecutor

    return {cls.id: cls for cls in (
        ClipExecutor, GroundingDinoExecutor, Owlv2Executor, PhenoVisionExecutor, GigaChatExecutor)}


def load_executors(settings) -> Tuple[List[Executor], Dict[str, str]]:
    """Грузит включённые модели. Упавшая модель не роняет сервис — попадает в failed."""
    classes = _classes()
    loaded: List[Executor] = []
    failed: Dict[str, str] = {}
    for executor_id in settings.executors:
        cls = classes.get(executor_id)
        if cls is None:
            failed[executor_id] = "неизвестный исполнитель"
            continue
        try:
            log.info("Загрузка %s…", executor_id)
            executor = cls(settings)
            executor.load()
            loaded.append(executor)
            log.info("%s загружен (%s)", executor_id, executor.device)
        except Exception as exc:  # noqa: BLE001
            failed[executor_id] = f"{type(exc).__name__}: {exc}"
            log.exception("Не удалось загрузить %s", executor_id)
    return loaded, failed


def load_captioner(settings) -> Tuple[Optional[object], Optional[str]]:
    if not settings.enable_caption:
        return None, None
    try:
        from app.executors.blip_captioner import BlipCaptioner
        captioner = BlipCaptioner(settings)
        captioner.load()
        return captioner, None
    except Exception as exc:  # noqa: BLE001
        log.exception("Не удалось загрузить BLIP")
        return None, f"{type(exc).__name__}: {exc}"
