from pydantic import BaseModel, Field, HttpUrl
from typing import List, Optional, Dict, Any

class ImageCheckRequest(BaseModel):
    json_data: Dict[str, Any] = Field(..., description="JSON ответ бота целиком")

class ImageValidationResponse(BaseModel):
    test_name: str
    is_passed: bool
    details: str
    data: Optional[Dict[str, Any]] = None

class GeoLinkResponse(BaseModel):
    url: str
    provider: str # 2GIS, Google, Yandex
    is_valid: bool
    status_code: Optional[int]