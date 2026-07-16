from transformers import (BlipProcessor, BlipForConditionalGeneration,
                          CLIPProcessor, CLIPModel,
                          Owlv2Processor, Owlv2ForObjectDetection,
                          AutoProcessor, AutoModelForZeroShotObjectDetection, AutoModelForCausalLM)
import open_clip
import torch
from huggingface_hub import snapshot_download
# Скачиваем и сохраняем в папку ./local_blip_model
# print("Начало скачивания модели blip-image-captioning-base!")
# processor = BlipProcessor.from_pretrained("Salesforce/blip-image-captioning-base")
# model = BlipForConditionalGeneration.from_pretrained("Salesforce/blip-image-captioning-base")
#
# processor.save_pretrained("./local_blip_model")
# model.save_pretrained("./local_blip_model")
#
# print("Модель blip-image-captioning-base сохранена локально!")

# Скачиваем и сохраняем в папку ./local_blip_model
# print("Начало скачивания модели bioclip!")
# Загружаем процессор от OpenAI
# processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch16")
# Загружаем модель от Imageomics
# model = CLIPModel.from_pretrained("hf-hub:imageomics/bioclip")
# model, _, processor = open_clip.create_model_and_transforms('hf-hub:imageomics/bioclip')
# processor.save_pretrained("./local_bioclip_model")
# model.save_pretrained("./local_bioclip_model")
# Скачиваем только нужные файлы (веса модели и конфиг)
# snapshot_download(
#     repo_id="imageomics/bioclip",
#     local_dir="./local_bioclip_model",
#     allow_patterns=["*.bin", "*.json", "*.txt"], # Качаем только бинарники и конфиги
#     local_dir_use_symlinks=False # Важно: качаем реальные файлы, а не ссылки
# )
# print("Модель bioclip сохранена локально!")

# Скачиваем и сохраняем в папку ./local_blip_model
# print("Начало скачивания модели owlv2-base-patch16!")
# processor = Owlv2Processor.from_pretrained("google/owlv2-base-patch16")
# model = Owlv2ForObjectDetection.from_pretrained("google/owlv2-base-patch16")
#
# processor.save_pretrained("./local_owlv2_model")
# model.save_pretrained("./local_owlv2_model")
#
# print("Модель owlv2-base-patch16 сохранена локально!")

# Скачиваем и сохраняем в папку ./local_blip_model
# print("Начало скачивания модели grounding-dino-tiny!")
# processor = AutoProcessor.from_pretrained("IDEA-Research/grounding-dino-tiny")
# model = AutoModelForZeroShotObjectDetection.from_pretrained("IDEA-Research/grounding-dino-tiny")
#
# processor.save_pretrained("./local_grounding_dino_tiny_model")
# model.save_pretrained("./local_grounding_dino_tiny_model")
#
# print("Модель grounding-dino-tiny сохранена локально!")

output_dir = "./local_florence_model"

print(f"Скачивание Florence-2 в {output_dir}...")
# trust_remote_code=True обязателен для Florence
torch_dtype = torch.float16 if torch.cuda.is_available() else torch.float32
processor = AutoProcessor.from_pretrained("microsoft/Florence-2-large", trust_remote_code=True )
model = AutoModelForCausalLM.from_pretrained("microsoft/Florence-2-large", torch_dtype=torch_dtype, trust_remote_code=True)

processor.save_pretrained(output_dir)
model.save_pretrained(output_dir)
print("Готово.")



print("Модели сохранены все локально!")