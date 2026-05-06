import logging
import os
from pathlib import Path
import sys
from flask import Flask
from flask_cors import CORS
from dotenv import load_dotenv

from app.config import BASE_DIR, RESOURCES_DIST_PATH, IMAGES_DIR, MAPS_DIR, DOMAIN, REDIS_HOST, REDIS_PORT, REDIS_DB
from app.services import geo, slot_val, search_service, relational_service
from app.utils import init_redis
from app.routes import register_blueprints
from search_api import all_blueprints  # <-- импортируем все blueprints из search_api
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

# Импортируем из search_api - больше не нужно импортировать конкретные blueprints
from search_api.config import SearchConfig
from search_api.infrastructure import RedisCache

# В create_app() добавьте после создания config:

def create_app():
    app = Flask(__name__)
    CORS(app)
    
    # Регистрация ВСЕХ blueprints из search_api
    for bp in all_blueprints:
        app.register_blueprint(bp)
        app.logger.info(f"Registered blueprint: {bp.name}")
    
    # Инициализация Redis
    init_redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True)
    
    # Создание конфигурации для search_api
    search_config = SearchConfig.from_env()
    search_redis = RedisCache(host=search_config.redis_host, port=search_config.redis_port, db=search_config.redis_db)
    if not search_redis.ping():
        app.logger.warning("Search API Redis connection failed")
    
    # ВАЖНО: Инициализация БД для search_api
    from search_api.infrastructure.database import init_db
    init_db(search_config)
    app.logger.info("Database initialized for search_api")
    
    app.config['SEARCH_CONFIG'] = search_config
    app.config['SEARCH_REDIS'] = search_redis

    # Регистрация остальных blueprints из app/routes
    register_blueprints(app)

    @app.route("/")
    def home():
        return "SalutBot API works!"

    return app