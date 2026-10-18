"""GigaChat Vision: LLM отвечает на все запрошенные признаки одним запросом.
Платный, поэтому по умолчанию не входит в ANNOTATOR_EXECUTORS.
Ключ — только из переменной окружения GIGACHAT_CREDENTIALS, в коде ключей нет."""
import io
import json
from typing import Dict, List, Optional

from PIL import Image

from app.executors.base import Executor, Prediction, ProgressCallback
from app.features import FeatureSpec

PROMPT_HEAD = (
    "Ты — эксперт по визуальному распознаванию природы Байкальского региона. "
    "Посмотри на изображение и определи признаки. Для каждого признака выбери РОВНО одно "
    "значение из списка или пустую строку, если по фото это достоверно определить нельзя. "
    "Верни только валидный JSON без пояснений и без markdown в формате "
    '{"признак": "значение"}.\n\nПризнаки и допустимые значения:\n'
)


class GigaChatExecutor(Executor):
    id = "gigachat"
    title = "GigaChat Vision"
    kind = "LLM (платный)"

    def load(self) -> None:
        if not self.settings.gigachat_credentials:
            raise RuntimeError("не задан GIGACHAT_CREDENTIALS")
        from gigachat import GigaChat

        self.client = GigaChat(
            credentials=self.settings.gigachat_credentials,
            scope=self.settings.gigachat_scope,
            model=self.settings.gigachat_model,
            verify_ssl_certs=False,
            timeout=120,
        )

    def predict(self, image: Image.Image, feature: FeatureSpec) -> Prediction:
        return self.predict_many(image, [feature])[feature.name]

    def predict_many(self, image: Image.Image, features: List[FeatureSpec],
                     on_progress: Optional[ProgressCallback] = None) -> Dict[str, Prediction]:
        try:
            answer = self._ask(image, features)
            out = {}
            for f in features:
                raw = str(answer.get(f.name, "") or "").strip()
                value = raw if raw in f.values else None
                note = None if value or not raw else f"вне списка: «{raw}»"
                out[f.name] = Prediction(value=value, note=note)
        except Exception as exc:  # noqa: BLE001
            out = {f.name: Prediction(error=f"{type(exc).__name__}: {exc}") for f in features}
        if on_progress:
            on_progress(len(features))
        return out

    def _ask(self, image: Image.Image, features: List[FeatureSpec]) -> dict:
        buf = io.BytesIO()
        image.save(buf, format="JPEG", quality=90)
        uploaded = self.client.upload_file(("image.jpg", buf.getvalue(), "image/jpeg"))
        schema = "\n".join(f'- "{f.name}": {json.dumps(f.value_names, ensure_ascii=False)}'
                           for f in features)
        response = self.client.chat({
            "messages": [{"role": "user", "content": PROMPT_HEAD + schema,
                          "attachments": [uploaded.id_]}],
            "temperature": 0.1,
        })
        content = response.choices[0].message.content
        start, end = content.find("{"), content.rfind("}") + 1
        return json.loads(content[start:end])
