from typing import Dict, Any
from .base import BaseValidator

from app.services.validators.image_validator import ImageValidator
from app.services.validators.map_validator import MapValidator
from app.services.validators.text_validator import TextValidator

class ValidatorFactory:
    def __init__(self, services: Dict[str, Any]):
        self.services = services

    def get_validator(self, t_id: int) -> BaseValidator:
        if t_id == 3:
            return TextValidator(
                self.services['speller'], self.services['pii'],
                self.services['neural'], self.services['llm'],
                self.services['text_checker']
            )
        if t_id == 2:
            return ImageValidator(
                self.services['img_checker'], self.services['nsfw'],
                self.services['vlm'], self.services['text_checker']
            )
        if t_id == 1:
            return MapValidator(
                self.services['img_checker'], self.services['map_classifier'],
                self.services['map_semantic'], self.services['text_checker']
            )
        raise ValueError(f"Unknown Type ID: {t_id}")