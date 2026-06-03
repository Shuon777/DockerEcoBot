import json
import logging
from dataclasses import dataclass, asdict
from typing import Any

logger = logging.getLogger(__name__)

_KEY_PREFIX = "dialogue:"
_MAX_TURNS = 5
_DEFAULT_TTL = 1800  # 30 минут


@dataclass
class DialogueTurn:
    query: str
    slots: dict[str, Any]
    had_results: bool


class ConversationHistory:
    """Хранит последние N диалоговых turn'ов в Redis."""

    def __init__(self, redis_client, ttl: int = _DEFAULT_TTL):
        self._redis = redis_client
        self._ttl = ttl

    def _key(self, user_id: str) -> str:
        return f"{_KEY_PREFIX}{user_id}"

    async def get_turns(self, user_id: str) -> list[DialogueTurn]:
        try:
            raw = await self._redis.get(self._key(user_id))
            if not raw:
                return []
            return [DialogueTurn(**t) for t in json.loads(raw)]
        except Exception as e:
            logger.error(f"ConversationHistory.get_turns [{user_id}]: {e}")
            return []

    async def add_turn(self, user_id: str, turn: DialogueTurn) -> None:
        try:
            turns = await self.get_turns(user_id)
            turns.append(turn)
            await self._redis.set(
                self._key(user_id),
                json.dumps([asdict(t) for t in turns[-_MAX_TURNS:]], ensure_ascii=False),
                ex=self._ttl,
            )
        except Exception as e:
            logger.error(f"ConversationHistory.add_turn [{user_id}]: {e}")

    async def clear(self, user_id: str) -> None:
        try:
            await self._redis.delete(self._key(user_id))
        except Exception as e:
            logger.error(f"ConversationHistory.clear [{user_id}]: {e}")
