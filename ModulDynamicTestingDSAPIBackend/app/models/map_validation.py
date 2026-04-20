from pydantic import BaseModel, Field
from typing import Optional

class MapImageRequest(BaseModel):
    image_url: str = Field(..., description="URL изображения для проверки на наличие карты")

class MapContextRequest(BaseModel):
    query: str = Field(..., description="Исходный запрос пользователя (например, 'Где растет нерпа?')")
    map_description: str = Field(..., description="Описание карты, присланное ботом (например, 'Карта глубин Байкала')")

class MapValidationResponse(BaseModel):
    is_passed: bool
    details: str
    confidence: Optional[float] = None
    reasoning: Optional[str] = None