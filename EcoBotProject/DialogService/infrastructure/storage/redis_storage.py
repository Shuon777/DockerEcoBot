import json
import logging
import redis.asyncio as redis
from typing import Dict, Any

from config import CONTEXT_TTL_SECONDS
from domain.interfaces.storage import IContextStorage

logger = logging.getLogger(__name__)


class RedisContextManager(IContextStorage):
    def __init__(self, host: str = "localhost", port: int = 6379, db: int = 0):
        try:
            self.redis_client = redis.Redis(host=host, port=port, db=db, decode_responses=True)
            logger.info(f"Redis инициализирован: {host}:{port}/{db}")
        except Exception as e:
            logger.critical(f"Не удалось инициализировать Redis: {e}")
            self.redis_client = None

    def _key(self, user_id: str) -> str:
        if ":" in str(user_id):
            return str(user_id)
        return f"gigachat_context:{user_id}"

    async def check_connection(self) -> bool:
        if not self.redis_client:
            return False
        try:
            await self.redis_client.ping()
            return True
        except Exception as e:
            logger.critical(f"Redis недоступен: {e}")
            return False

    async def get_context(self, key: str) -> Dict[str, Any]:
        if not self.redis_client:
            return {}
        try:
            data = await self.redis_client.get(self._key(key))
            return json.loads(data) if data else {}
        except Exception as e:
            logger.error(f"get_context({key}): {e}")
            return {}

    async def set_context(self, key: str, data: Dict[str, Any]) -> None:
        if not self.redis_client:
            return
        try:
            await self.redis_client.set(
                self._key(key), json.dumps(data, ensure_ascii=False), ex=CONTEXT_TTL_SECONDS
            )
        except Exception as e:
            logger.error(f"set_context({key}): {e}")

    async def delete_context(self, key: str) -> None:
        if not self.redis_client:
            return
        try:
            await self.redis_client.delete(self._key(key))
        except Exception as e:
            logger.error(f"delete_context({key}): {e}")
