# app/__init__.py
# ВНИМАНИЕ: Это Flask-приложение больше не используется.
# Вся функциональность перенесена в FastAPI (fastapi_app/).
# Файл оставлен, чтобы не сломать импорты app.config, app.services, app.utils,
# которые используются в fastapi_app/.
import logging
import os
from pathlib import Path
import sys
from dotenv import load_dotenv

from app.config import BASE_DIR, RESOURCES_DIST_PATH, IMAGES_DIR, MAPS_DIR, DOMAIN, REDIS_HOST, REDIS_PORT, REDIS_DB, EMBEDDING_MODEL_PATH, FAISS_INDEX_PATH
from app.services import geo, slot_val, search_service, relational_service
from app.utils import init_redis

load_dotenv()

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout,
    force=True
)
matplotlib_logger = logging.getLogger('matplotlib')
matplotlib_logger.setLevel(logging.WARNING)
logging.getLogger('search_api').setLevel(logging.DEBUG)
logging.getLogger('search_api.adapters').setLevel(logging.DEBUG)
logging.getLogger('search_api.use_cases').setLevel(logging.DEBUG)
logging.getLogger('search_api.services').setLevel(logging.DEBUG)
logging.getLogger('search_api.infrastructure').setLevel(logging.DEBUG)