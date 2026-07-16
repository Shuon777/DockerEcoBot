from fastapi import APIRouter, Body
from app.services.llm_evaluator.vision_service import VisionLLMService

router = APIRouter()
vision_service = VisionLLMService()


@router.post("/describe-image")
async def describe_image(image_url: str):
    """Описание изображения через Qwen3-VL."""
    description = await vision_service.describe_image(image_url)
    return {"image_url": image_url, "description": description}


@router.post("/verify-metadata-match")
async def verify_metadata(
        image_url: str = Body(...),
        expected_entity: str = Body(...)
):
    """
    Сравнение объекта на фото с метаданными бота.
    Пример: Бот сказал что на фото 'Эдельвейс', VLM проверяет так ли это.
    """
    result = await vision_service.verify_object_match(image_url, expected_entity)
    is_passed = result.get("found", False)

    return {
        "test_name": "vision_metadata_sync",
        "is_passed": is_passed,
        "expected": expected_entity,
        "vlm_analysis": result
    }