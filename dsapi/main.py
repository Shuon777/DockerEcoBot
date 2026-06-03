import uvicorn
import sys
from fastapi import FastAPI
from app.api.v1.api import api_router
from app.core.config import settings
from contextlib import asynccontextmanager
from app.services.text_validation.neural_checkers import NeuralValidator
#from app.services.pipeline._dynamic_pipeline import IntegratedDynamicPipeline
from app.services.pipeline.dynamic_pipeline import IntegratedDynamicPipeline
import asyncio
import uuid
from app.core.logging_config import setup_logging
from app.models.testing_status import ACTIVE_JOBS, TaskInfo, TaskStatus
from app.services.clients.bot_client import EcobotHttpClient
from app.services.generation.strategies import MorphologicalGenerator, TyposGenerator, SimpleGenerator
from app.services.llm_evaluator.generation_q import LLMServiceGenerationQuestions
from app.services.files_repositories.excel_repo import ExcelTemplateRepository

@asynccontextmanager
async def lifespan(app: FastAPI):
    # инициализируем тяжелые модели один раз
    print("🚀 Инициализация нейронных моделей...")
    NeuralValidator()
    yield
    # Действия при выключении
    print("🛑 Отключение системы...")

setup_logging()

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Модуль статического и динамического тестирования диалоговых систем",
    version="1.0.0",
    lifespan=lifespan
)

# Подключаем все маршруты API версии 1
app.include_router(api_router, prefix=settings.API_V1_STR)


async def main():
    # для работы Natasha и Pymorphy3 на Python 3.12
    try:
        import pymorphy3
        sys.modules['pymorphy2'] = pymorphy3
    except:
        pass

    # Инициализируем статус
    session_id = str(uuid.uuid4())
    print(session_id)
    task_info = TaskInfo(session_id=session_id, status=TaskStatus.PENDING)
    ACTIVE_JOBS[session_id] = task_info
    current_client = EcobotHttpClient(domain=settings.BOT_DOMAIN)
    current_gen = SimpleGenerator()
    current_file_repo = ExcelTemplateRepository(settings.PATH_TEMPLATES_EXCEL)
    # Запуск пайплайн
    pipeline = IntegratedDynamicPipeline(bot_client=current_client,
                                         generator=current_gen,
                                         template_repo=current_file_repo)
    
    await pipeline.process_dynamic_testing(session_id, "no llm", ["эдельвейс"])


if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=5050, reload=True)
    #asyncio.run(main())