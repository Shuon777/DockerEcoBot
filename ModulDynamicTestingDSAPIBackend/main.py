import os
import uvicorn
import sys
from fastapi import FastAPI
from app.api.v1.api import api_router
from app.core.config import settings
from contextlib import asynccontextmanager
from app.services.text_validation.neural_checkers import NeuralValidator
from app.services.pipeline.dynamic_pipeline import IntegratedDynamicPipeline
import asyncio
from app.core.logging_config import setup_logging

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Действия при старте: инициализируем тяжелые модели один раз
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
    # 1. Фикс для работы Natasha и Pymorphy3 на Python 3.12
    try:
        import pymorphy3
        sys.modules['pymorphy2'] = pymorphy3
    except:
        pass

    # 2. Запуск пайплайна
    pipeline = IntegratedDynamicPipeline(domain=os.getenv("PUBLIC_BASE_URL", "https://testecobot.ru"))

    # Можно выбрать режим: "rasa" или "gigachat"
    #await pipeline.process_testing(mode="rasa")
    #await pipeline.process_from_file("doc/tests.xlsx")
    await pipeline.process_dynamic_testing("doc/tests.xlsx")


if __name__ == "__main__":
    # Запуск сервера на порту 5050
    uvicorn.run("main:app", host="127.0.0.1", port=5050, reload=True)
    #asyncio.run(main())