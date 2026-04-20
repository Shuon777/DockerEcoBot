from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.api.v1.endpoints.text_tests import checker
from app.services.text_validation.spelling import SpellingChecker
from app.services.text_validation.neural_checkers import NeuralValidator
from app.services.text_validation.checkers import TextCheckerPiiFIO

router = APIRouter()
spelling_service = SpellingChecker()
# Инициализация нейронного валидатора (загрузка моделей произойдет при первом вызове)
neural_service = NeuralValidator()
checker_pii_fio = TextCheckerPiiFIO()

class SimpleTextRequest(BaseModel):
    text: str = Field(..., min_length=1, description="Текст ответа бота для анализа")

@router.post("/check-spelling")
async def check_spelling(request: SimpleTextRequest):
    """
    Эндпоинт для проверки орфографии.
    Использует Yandex Speller для поиска ошибок и предложения исправлений.
    """
    return await  spelling_service.check_spelling(request.text)

@router.post("/neural-sentiment")
async def neural_sentiment(request: SimpleTextRequest):
    """
    Нейронный анализ тональности и эмпатии.
    Определяет, является ли ответ позитивным, нейтральным или негативным.
    """
    return neural_service.analyze_sentiment_and_tone(request.text)

@router.post("/neural-toxicity")
async def neural_toxicity(request: SimpleTextRequest):
    """
    Нейронная проверка на токсичность и оскорбления.
    Выявляет агрессию, мат или предвзятость в ответе бота.
    """
    return neural_service.analyze_toxicity(request.text)

@router.post("/neural-safety")
async def neural_safety(request: SimpleTextRequest):
    """
    Нейронная проверка на утечку системного промпта (Safety).
    Определяет, не выдал ли бот технические инструкции или секретные данные.
    """
    return neural_service.check_prompt_leakage(request.text)

@router.post("/check-pii-fio")
async def check_pii_fio(request: SimpleTextRequest):
    """Поиск Email, Телефонов и ФИО через Natasha NLP."""
    return checker_pii_fio.check_pii_and_fio(request.text)

@router.post("/advanced-empathy")
async def advanced_empathy(request: SimpleTextRequest):
    """Глубокий анализ эмоций и эмпатии (28 классов)."""
    return neural_service.analyze_detailed_toxicity(request.text)

@router.post("/complex-toxicity")
async def complex_toxicity(request: SimpleTextRequest):
    """Проверка на угрозы, маты, оскорбления и хейтспич."""
    return neural_service.analyze_detailed_toxicity(request.text)