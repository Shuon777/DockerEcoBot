from abc import ABC, abstractmethod
from pydantic import BaseModel
from typing import List

class QuestionTemplate(BaseModel):
    id: int
    text: str

class ITemplateRepository(ABC):
    """Интерфейс для загрузки шаблонов"""
    @abstractmethod
    def get_all_templates(self) -> List[QuestionTemplate]:
        pass