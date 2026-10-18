"""Итоговый вердикт по признаку из ответов нескольких моделей.

Взвешенное голосование:
  балл(значение) = Σ вес_модели × уверенность_модели  (по моделям, выбравшим это значение)
                   ─────────────────────────────────────
                   Σ веса всех моделей, которые РАБОТАЛИ с признаком

- Модель, которая воздержалась (value=None), остаётся в знаменателе: её сомнение снижает итог.
- Модель, которая упала (error), из знаменателя исключается: поломка не должна штрафовать итог.
- LLM без вероятности голосует с фиксированной уверенностью settings.llm_confidence.
- Если лучший балл ниже порога — вердикт None («не определено»), в БД не пишется.
"""
from dataclasses import dataclass
from typing import Dict, List, Optional

from app.executors.base import Prediction


@dataclass
class Vote:
    executor_id: str
    weight: float
    prediction: Prediction


@dataclass
class Verdict:
    value: Optional[str]
    confidence: float
    agreement: str
    top_value: Optional[str]

    def to_dict(self) -> dict:
        return {"verdict": self.value, "confidence": round(self.confidence, 4),
                "agreement": self.agreement, "top_value": self.top_value}


def aggregate(votes: List[Vote], threshold: float, llm_confidence: float) -> Verdict:
    working = [v for v in votes if v.prediction.error is None]
    total_weight = sum(v.weight for v in working)
    if not working or total_weight <= 0:
        return Verdict(None, 0.0, "0/0", None)

    scores: Dict[str, float] = {}
    for v in working:
        p = v.prediction
        if p.value is None:
            continue
        conf = llm_confidence if p.confidence is None else max(0.0, min(1.0, p.confidence))
        scores[p.value] = scores.get(p.value, 0.0) + v.weight * conf

    if not scores:
        return Verdict(None, 0.0, f"0/{len(working)}", None)

    top_value = max(scores, key=scores.get)
    confidence = scores[top_value] / total_weight
    agree = sum(1 for v in working if v.prediction.value == top_value)
    return Verdict(
        value=top_value if confidence >= threshold else None,
        confidence=confidence,
        agreement=f"{agree}/{len(working)}",
        top_value=top_value,
    )
