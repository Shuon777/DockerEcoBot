from fastapi import APIRouter, Depends, HTTPException
from app.models.text_validation import TextValidationRequest, ValidationResponse, ComprehensiveTextTestResponse
from app.services.text_validation.checkers import TextChecker, TextCheckerPiiFIO
from app.services.llm_evaluator.evaluator import LLMService

router = APIRouter()
checker = TextChecker()
checker_pii_fio = TextCheckerPiiFIO()
llm_service = LLMService()

@router.post("/validate-heuristics", response_model=ComprehensiveTextTestResponse)
async def run_heuristic_tests(request: TextValidationRequest):
    """Эндпоинт для быстрых формальных проверок (ссылки, PII, кодировка)."""
    if not request.text:
        raise HTTPException(status_code=400, detail="Text is required")

    results = []
    # 1. Проверка на пустоту
    results.append(checker.check_not_empty(request.text))
    # 2. Проверка кодировки
    results.append(checker.check_encoding_and_markup(request.text))
    # 3. Проверка PII
    results.append(checker_pii_fio.check_pii_and_fio(request.text))
    # 4. Проверка языка
    results.append(checker.check_language(request.text, request.expected_lang))
    # 5. Проверка ссылок (асинхронно)
    results.append(await checker.check_links(request.text))

    overall = all(r["is_passed"] for r in results)
    return {"overall_passed": overall, "results": results}

@router.post("/test-relevance")
async def test_relevance(question: str, answer: str):
    """Тест на соответствие ответа вопросу (LLM)."""
    return await llm_service.check_relevance(question, answer)

@router.post("/test-ethics")
async def test_ethics(answer: str):
    """Тест на этику, тональность и оскорбления (LLM)."""
    return await llm_service.check_sentiment_and_ethics(answer)

@router.post("/test-safety")
async def test_safety(question: str, answer: str):
    """Тест на утечку системной информации (LLM)."""
    return await llm_service.check_safety_leakage(question, answer)