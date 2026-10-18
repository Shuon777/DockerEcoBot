"""Справочник признаков: что можно искать на фото и какими промптами."""
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

LIFEFORM_ALIASES = {
    "flora": "flora", "флора": "flora",
    "fauna": "fauna", "фауна": "fauna",
}


@dataclass(frozen=True)
class FeatureSpec:
    name: str                      # «Время года» — как в resource.features
    values: Dict[str, str]         # «Зима» -> "a photo taken in winter"
    applies_to: str = "any"        # any | flora | fauna
    executors: Optional[tuple] = None  # если задано — только эти модели

    @property
    def value_names(self) -> List[str]:
        return list(self.values.keys())

    @property
    def prompts(self) -> List[str]:
        return list(self.values.values())

    def value_by_prompt(self, prompt: str) -> Optional[str]:
        for value, p in self.values.items():
            if p == prompt:
                return value
        return None

    def applies(self, lifeform: Optional[str]) -> bool:
        if self.applies_to == "any" or not lifeform:
            return True
        return self.applies_to == lifeform


def normalize_lifeform(raw: Optional[str]) -> Optional[str]:
    """«Флора», «flora», «Объект флоры» -> flora; то же для фауны; иначе None (все признаки)."""
    if not raw:
        return None
    text = raw.strip().lower()
    if text in LIFEFORM_ALIASES:
        return LIFEFORM_ALIASES[text]
    if "флор" in text:
        return "flora"
    if "фаун" in text:
        return "fauna"
    return None


class FeatureCatalog:
    def __init__(self, specs: Dict[str, FeatureSpec]):
        self._specs = specs

    @classmethod
    def load(cls, path: Path) -> "FeatureCatalog":
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        specs = {}
        for name, item in raw.items():
            if name.startswith("_"):
                continue
            if not item.get("values"):
                raise ValueError(f"Признак «{name}»: пустой список значений")
            execs = item.get("executors")
            specs[name] = FeatureSpec(
                name=name,
                values=dict(item["values"]),
                applies_to=item.get("applies_to", "any"),
                executors=tuple(execs) if execs else None,
            )
        return cls(specs)

    def all(self) -> List[FeatureSpec]:
        return list(self._specs.values())

    def get(self, name: str) -> Optional[FeatureSpec]:
        return self._specs.get(name)

    def names(self) -> List[str]:
        return list(self._specs.keys())
