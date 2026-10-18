import io
import sys
from pathlib import Path

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Settings  # noqa: E402
from app.executors.base import Executor, Prediction  # noqa: E402


class FakeExecutor(Executor):
    """Отвечает заранее заданными значениями — чтобы тестировать сервис без моделей."""

    def __init__(self, settings, executor_id, answers, universal=True, fail_on=()):
        super().__init__(settings)
        self.id = executor_id
        self.title = executor_id
        self.answers = answers
        self.universal = universal
        self.fail_on = set(fail_on)

    def load(self):
        pass

    def predict(self, image, feature):
        if feature.name in self.fail_on:
            raise RuntimeError("boom")
        value, conf = self.answers.get(feature.name, (None, None))
        return Prediction(value=value, confidence=conf)


@pytest.fixture
def settings(monkeypatch):
    monkeypatch.setenv("ANNOTATOR_API_TOKEN", "secret")
    monkeypatch.setenv("EXECUTOR_WEIGHTS", "a=1.0,b=0.8,pheno=2.0")
    monkeypatch.setenv("CONFIDENCE_THRESHOLD", "0.4")
    return Settings()


@pytest.fixture
def jpeg_bytes():
    buf = io.BytesIO()
    Image.new("RGB", (64, 48), (120, 160, 200)).save(buf, format="JPEG")
    return buf.getvalue()
