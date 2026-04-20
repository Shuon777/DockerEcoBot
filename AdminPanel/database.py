import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = (
    f"postgresql+asyncpg://{os.getenv('DB_USER', 'postgres')}:"
    f"{os.getenv('DB_PASSWORD')}@{os.getenv('DB_HOST', 'db')}:"
    f"{os.getenv('DB_PORT', '5432')}/{os.getenv('DB_NAME', 'eco')}"
)

engine = create_async_engine(DATABASE_URL, echo=True)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()

# Зависимость для FastAPI
async def get_db():
    async with AsyncSessionLocal() as session:
        yield session