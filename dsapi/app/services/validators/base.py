from abc import ABC, abstractmethod
from typing import Dict, Any


class BaseValidator(ABC):

    @abstractmethod
    async def validate(self, template: str, query: str, bot_res: Dict[str, Any], mode: str) -> Dict[str, Any]:
        pass

    def _format_status(self, is_passed: bool, success_msg: str, error_msg: str) -> str:
        """Вспомогательный метод для унификации ✅/❌."""
        return f"✅ {success_msg}" if is_passed else f"❌ {error_msg}"