import os
from transformers import (
    AutoTokenizer,
    AutoModelForSequenceClassification,
    AutoProcessor,
    CLIPModel,
    AutoModelForImageClassification
)

# Список всех моделей, которые мы используем в проекте
MODELS_TO_DOWNLOAD = {
    "sentiment": "cointegrated/rubert-tiny2-sentence-sentiment",
    "toxicity": "SkolkovoInstitute/russian_toxicity_classifier",
    "emotions": "fyaronskiy/ruRoberta-large-ru-go-emotions",
    "nsfw": "Falconsai/nsfw_image_detection",
    "map_clip": "openai/clip-vit-base-patch32"
}

def download_and_save_models(base_path: str = "./local_models"):
    """
    Скачивает модели и сохраняет их локально для работы без интернета.
    """
    os.makedirs(base_path, exist_ok=True)
    print(f"📁 Начинаю загрузку моделей в {os.path.abspath(base_path)}...")

    for key, model_id in MODELS_TO_DOWNLOAD.items():
        print(f"\n--- Загрузка {key} ({model_id}) ---")
        target_dir = os.path.join(base_path, key)
        os.makedirs(target_dir, exist_ok=True)

        try:
            # 1. Текстовые классификаторы (BERT/RoBERTa)
            if key in ["sentiment", "toxicity", "emotions"]:
                tokenizer = AutoTokenizer.from_pretrained(model_id)
                model = AutoModelForSequenceClassification.from_pretrained(model_id)
                tokenizer.save_pretrained(target_dir)
                model.save_pretrained(target_dir)

            # 2. Vision Transformer (NSFW)
            elif key == "nsfw":
                processor = AutoProcessor.from_pretrained(model_id)
                model = AutoModelForImageClassification.from_pretrained(model_id)
                processor.save_pretrained(target_dir)
                model.save_pretrained(target_dir)

            # 3. Мультимодальный CLIP (Карты)
            elif key == "map_clip":
                processor = AutoProcessor.from_pretrained(model_id)
                model = CLIPModel.from_pretrained(model_id)
                processor.save_pretrained(target_dir)
                model.save_pretrained(target_dir)

            print(f"✅ Модель {key} сохранена в {target_dir}")
        except Exception as e:
            print(f"❌ Ошибка при загрузке {model_id}: {e}")

if __name__ == "__main__":
    download_and_save_models()
    print("\n🚀 Все модели готовы для Offline работы!")
    print("ВАЖНО: Не забудьте выполнить 'ollama pull qwen2.5:72b' и 'ollama pull qwen3-vl:32b' на сервере!")