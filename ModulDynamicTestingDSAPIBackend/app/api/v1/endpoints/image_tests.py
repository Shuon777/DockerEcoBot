from fastapi import APIRouter, Body
from app.services.image_validation.checkers import ImageChecker
from app.services.image_validation.nsfw_checker import ImageSafetyValidator

router = APIRouter()
img_checker = ImageChecker()
safety_validator = ImageSafetyValidator()

@router.post("/detect-and-validate")
async def detect_images(json_data: Dict = Body(...)):
    """Поиск картинок в JSON и проверка их размеров и доступности."""
    urls = img_checker.extract_image_urls(json_data)
    results = []
    for url in urls:
        val = await img_checker.validate_url_and_size(url)
        results.append({"url": url, "validation": val})
    return {"found_images": len(urls), "results": results}

@router.post("/check-nsfw")
async def check_nsfw(url: str):
    """Нейронная проверка картинки по URL на нежелательный контент."""
    return await safety_validator.analyze_image_safety(url)

@router.post("/validate-geo-links")
async def validate_geo(json_data: Dict = Body(...)):
    """Поиск и проверка валидности ссылок на карты (2GIS, Google, Yandex)."""
    links = await img_checker.check_geo_links(json_data)
    return {"geo_links": links}