from abc import ABC, abstractmethod
from typing import List

class IQuestionGenerator(ABC):
    """Общий интерфейс для всех генераторов вопросов."""
    @abstractmethod
    async def generate(self, query: str, count: int, error_rate: float = 0.1) -> List[str]:
        pass