from fastapi import APIRouter, HTTPException
from app.models.map_validation import MapImageRequest, MapContextRequest, MapValidationResponse
from app.services.image_validation.map_classifier import MapClassifier
from app.services.image_validation.map_semantic_validator import MapSemanticValidator

router = APIRouter()

# Инициализация сервисов (загрузка моделей при первом вызове)
map_classifier = MapClassifier()
semantic_validator = MapSemanticValidator()


@router.post("/is-it-map", response_model=MapValidationResponse)
async def check_is_it_map(request: MapImageRequest):
    """
    Эндпоинт для визуальной проверки изображения.
    Определяет, является ли картинка по ссылке картой или схемой.
    Использует нейросеть CLIP (Zero-shot classification).
    """
    try:
        # Вызываем метод нашего классификатора
        result = await map_classifier.is_it_a_map(request.image_url)

        return MapValidationResponse(
            is_passed=result["is_passed"],
            details=result["details"],
            confidence=result.get("confidence")
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка визуального анализа: {str(e)}")


@router.post("/validate-context", response_model=MapValidationResponse)
async def validate_map_context(request: MapContextRequest):
    """
    Эндпоинт для семантической проверки соответствия карты запросу.
    Проверяет через LLM Qwen, подходит ли описание карты под вопрос пользователя.
    """
    try:
        # Вызываем LLM-валидатор контекста
        result = await semantic_validator.validate_map_context(
            request.query,
            request.map_description
        )

        return MapValidationResponse(
            is_passed=result.get("is_passed", False),
            details="Анализ контекста завершен",
            reasoning=result.get("reasoning", "Нет обоснования")
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка LLM анализа: {str(e)}")