import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# Импортируем Base из models.models, чтобы использовать единый базовый класс
from models.models import Base

DATABASE_URL = (
    f"postgresql+asyncpg://{os.getenv('DB_USER', 'postgres')}:"
    f"{os.getenv('DB_PASSWORD')}@{os.getenv('DB_HOST', 'db')}:"
    f"{os.getenv('DB_PORT', '5432')}/{os.getenv('DB_NAME', 'eco')}"
)

engine = create_async_engine(
    DATABASE_URL,
    echo=True,
    pool_pre_ping=True,  # Проверять соединение перед использованием
    pool_recycle=3600,   # Пересоздавать соединения каждые 3600 секунд
    pool_size=10,
    max_overflow=20,
    connect_args={
        "command_timeout": 30,
        "server_settings": {"application_name": "admin_panel"}
    }
)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# Зависимость для FastAPI
async def get_db():
    async with AsyncSessionLocal() as session:
        yield session