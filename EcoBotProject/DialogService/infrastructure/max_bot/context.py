from __future__ import annotations
import aiohttp
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from application.search.slot_classifier import SlotClassifier
    from application.search.slot_search_executor import SlotSearchExecutor


class _MaxBotContext:
    """Shared runtime dependencies для MAX-бота. Заполняется при старте в main_max.py."""
    session: aiohttp.ClientSession | None = None
    classifier: "SlotClassifier | None" = None
    executor: "SlotSearchExecutor | None" = None
    redis_client: Any | None = None


ctx = _MaxBotContext()
