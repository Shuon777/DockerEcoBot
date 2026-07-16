from abc import ABC, abstractmethod
from typing import Any


class IContextStorage(ABC):
    @abstractmethod
    async def get_context(self, key: str) -> dict:
        """Возвращает данные контекста по ключу (пустой dict если нет)."""

    @abstractmethod
    async def set_context(self, key: str, data: dict) -> None:
        """Сохраняет данные контекста по ключу."""

    @abstractmethod
    async def delete_context(self, key: str) -> None:
        """Удаляет контекст по ключу."""

    @abstractmethod
    async def check_connection(self) -> bool:
        """Проверяет доступность хранилища."""
