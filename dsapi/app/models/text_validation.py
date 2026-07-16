from pydantic import BaseModel, Field, HttpUrl
from typing import List, Optional, Dict

class TextValidationRequest(BaseModel):
    """Модель входящего запроса для тестирования текста."""
    text: Optional[str] = Field(None, description="Текст ответа бота для проверки")
    expected_lang: str = Field("ru", description="Ожидаемый язык ответа (ISO код)")

class LinkCheckResult(BaseModel):
    """Результат проверки одной ссылки."""
    url: str
    status_code: Optional[int]
    is_valid: bool
    error: Optional[str] = None

class ValidationResponse(BaseModel):
    """Общая модель ответа для всех тестов валидации."""
    test_name: str
    is_passed: bool
    details: Optional[str] = None
    data: Optional[Dict] = None  # Дополнительные данные (найденные ссылки, PII и т.д.)

class ComprehensiveTextTestResponse(BaseModel):
    """Результат комплексного тестирования текста."""
    overall_passed: bool
    results: List[ValidationResponse]