"""Скачивает веса всех моделей аннотатора в MODELS_DIR (по умолчанию ./models).

    python scripts/download_models.py                 # все
    python scripts/download_models.py clip phenovision # выборочно

Нужен доступ к huggingface.co. Дальше сервис работает офлайн.
Если у вас уже есть папки от images-extractor (local_owlv2_model и т.п.) —
можно не качать, а указать путь через OWLV2_PATH=... в .env.
"""
import os
import sys
from pathlib import Path

from huggingface_hub import HfApi, snapshot_download

MODELS = {
    "clip": "openai/clip-vit-base-patch32",
    "grounding_dino": "IDEA-Research/grounding-dino-tiny",
    "owlv2": "google/owlv2-base-patch16",
    "phenovision": "phenobase/phenovision",
    "blip": "Salesforce/blip-image-captioning-base",
}

target = Path(os.getenv("MODELS_DIR", Path(__file__).resolve().parents[1] / "models"))
names = sys.argv[1:] or list(MODELS)
for name in names:
    repo = MODELS[name]
    dest = target / name
    print(f"→ {repo}  ->  {dest}")
    # Берём safetensors, если есть; иначе pytorch_model.bin (так у CLIP и BLIP)
    files = HfApi().list_repo_files(repo)
    weights = ["*.safetensors"] if any(f.endswith(".safetensors") for f in files) else ["pytorch_model.bin"]
    snapshot_download(repo_id=repo, local_dir=dest,
                      allow_patterns=["*.json", "*.txt", "*.model", "*.csv", *weights])
print("Готово.")
