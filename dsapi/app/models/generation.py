from pydantic import BaseModel, Field
from typing import List, Optional


class GenerationParams(BaseModel):
    """Параметры для алгоритмической и LLM генерации."""
    template_question: str = Field(..., description="Шаблонный вопрос")
    count: int = Field(default=3, ge=1, le=10, description="Количество вариантов")

    # Параметры для Rule-based (без LLM)
    add_typos: bool = Field(default=False, description="Добавлять опечатки")
    change_cases: bool = Field(default=False, description="Менять падежи/роды")

    # Параметры для LLM
    temperature: float = Field(default=0.7, description="Креативность LLM")


class GeneratedQuestionsResponse(BaseModel):
    """Список сгенерированных вопросов."""
    source_template: str
    generated_questions: List[str]
    method: str  # "rule-based" или "llm-based"