import logging
import aiohttp
from contextlib import asynccontextmanager
from fastapi import FastAPI

from adapters.http.routes.dialogue import router as dialogue_router
from adapters.http.routes.search import router as search_router
from adapters.http.routes.config import router as config_router
from infrastructure.db_feature_loader import load_valid_features

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.session = aiohttp.ClientSession()
    app.state.valid_features = await load_valid_features()
    logger.info("Core API: сессия открыта.")
    yield
    await app.state.session.close()
    logger.info("Core API: сессия закрыта.")


app = FastAPI(title="EcoBot Core API", lifespan=lifespan)
app.include_router(dialogue_router)
app.include_router(search_router)
app.include_router(config_router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5001)
