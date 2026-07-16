import torch
import json
import os
import numpy as np
import pandas as pd
import cv2
import clip
import timm
import requests
from PIL import Image, ExifTags
from datetime import datetime
from collections import Counter
from transformers import ( BlipProcessor, BlipForConditionalGeneration,
                          AutoProcessor, AutoModelForZeroShotObjectDetection, Owlv2ForObjectDetection)
# CLIPModel, CLIPProcessor,
from timm.data import resolve_data_config
from timm.data.transforms_factory import create_transform
import open_clip
from ultralytics import YOLO
from transformers.utils.constants import OPENAI_CLIP_MEAN, OPENAI_CLIP_STD
import time
import openpyxl
from tqdm import tqdm
from bs4 import BeautifulSoup
from langchain_core.messages import HumanMessage
#from langchain_gigachat import GigaChat
from pathlib import Path
from API import ApiClient

class BaseModelLoader:
    def __init__(self):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        #self.device = torch.device("cpu")


class CLIPModelLoader(BaseModelLoader):
    def __init__(self):
        super().__init__()
        # self.model = CLIPModel.from_pretrained("patrickjohncyh/fashion-clip") #openai/clip-vit-base-patch32
        # self.processor = CLIPProcessor.from_pretrained("patrickjohncyh/fashion-clip")
        self.model, self.processor = clip.load("ViT-B/32", device=self.device)

    # def extract(self, image: Image.Image, candidates, type_action=0):
    #     inputs = self.processor(text=list(candidates.keys()), images=image, return_tensors="pt", padding=True).to(
    #         self.device)
    #     with torch.no_grad():
    #         outputs = self.model(**inputs)
    #         logits_per_image = outputs.logits_per_image
    #         probs = logits_per_image.softmax(dim=1)
    #     best_idx = torch.argmax(probs[0]).item()
    #     if type_action:
    #         return list(candidates.keys())[best_idx], float(probs[0][best_idx].item())
    #     return candidates.get(list(candidates.keys())[best_idx], ""), float(probs[0][best_idx].item())
    def extract(self, image: Image.Image, candidates, type_action=0):
        # 1. Подготовка текста (используем clip.tokenize вместо processor)
        text_list = [class_can for class_can in candidates.keys() if "Undefined" not in class_can]
        text_inputs = clip.tokenize(text_list).to(self.device)

        # 2. Подготовка изображения
        # self.processor возвращает тензор (C, H, W), нужно добавить размерность батча -> (1, C, H, W)
        image_input = self.processor(image).unsqueeze(0).to(self.device)

        with torch.no_grad():
            # 3. Вызов модели (принимает image и text как отдельные аргументы)
            logits_per_image, logits_per_text = self.model(image_input, text_inputs)
            probs = logits_per_image.softmax(dim=-1)

        best_idx = torch.argmax(probs[0]).item()

        if type_action:
            return text_list[best_idx], float(probs[0][best_idx].item())
        return candidates.get(text_list[best_idx], ""), float(probs[0][best_idx].item())

class BLIPModelLoader(BaseModelLoader):
    def __init__(self):
        super().__init__()
        self.model = BlipForConditionalGeneration.from_pretrained("./local_blip_model")#("Salesforce/blip-image-captioning-base")
        self.processor = BlipProcessor.from_pretrained("./local_blip_model")#("Salesforce/blip-image-captioning-base")
        self.model.to(self.device)

    def extract_caption(self, image: Image.Image):
        inputs = self.processor(image, return_tensors="pt").to(self.device)
        out = self.model.generate(**inputs, max_length=100, num_beams=5, early_stopping=True)
        return self.processor.decode(out[0], skip_special_tokens=True)


class YOLOModelLoader:
    def __init__(self, file_yolo_path: str, classes: list[str], model_path="yolov8s-world.pt"):
        self.model = YOLO(model_path)
        add_class = self.load_yolo_classes(json_path=file_yolo_path)
        self.model.set_classes(classes+add_class)

    def extract(self, path: str):
        res = self.model(path)[0]
        return list({res.names[int(b.cls.cpu().numpy())] for b in res.boxes})

    @staticmethod
    def load_yolo_classes(json_path: str | Path) -> list[str]:
        """
        Загружает список классов YOLO из JSON-файла
        """
        json_path = Path(json_path)

        with json_path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        classes = data.get("YOLO_CLASSES")
        if not isinstance(classes, list):
            raise ValueError("Некорректная структура JSON: отсутствует YOLO_CLASSES")

        return classes


class GroundingDINOModelLoader(BaseModelLoader):
    def __init__(self, model_id="IDEA-Research/grounding-dino-tiny"):
        super().__init__()
        self.processor = AutoProcessor.from_pretrained("./local_grounding_dino_tiny_model") #(model_id)
        self.model = AutoModelForZeroShotObjectDetection.from_pretrained("./local_grounding_dino_tiny_model").to(self.device)

    def extract(self, image: Image.Image, candidates, type_action=0):
        text = " ".join(word.lower().replace("a photo of ", "", 1) + "." for word in candidates.keys() if "Undefined" not in word)
        inputs = self.processor(images=image, text=text, return_tensors="pt").to(self.device)
        with torch.no_grad():
            outputs = self.model(**inputs)
        results = self.processor.post_process_grounded_object_detection(
            outputs, inputs.input_ids, text_threshold=0.2, target_sizes=[image.size[::-1]]
        )
        best_idx = None
        for result in results:
            scores = result["scores"]
            if scores.numel() == 0:
                continue
            best_idx = torch.argmax(scores)

        if best_idx is None:
            return candidates.get("Undefined", ""), 0
        # print(results)
        # print(result["labels"][best_idx])
        text_copy = [word.strip() for word in text.split(".") if word != ""]
        # print(text_copy)
        text_id = None
        for i, word in enumerate(text_copy):
            if word == result["labels"][best_idx]:
                text_id = i
        if text_id is None:
            return candidates.get("Undefined", ""), 0
        if type_action:
            return list(candidates.keys())[text_id], float(scores[best_idx].item())
        return candidates.get(list(candidates.keys())[text_id], ""), float(scores[best_idx].item())


class OWLv2ModelLoader(BaseModelLoader):
    def __init__(self):
        super().__init__()
        self.processor = AutoProcessor.from_pretrained("./local_owlv2_model") #("google/owlv2-base-patch16")
        self.model = Owlv2ForObjectDetection.from_pretrained("./local_owlv2_model") #("google/owlv2-base-patch16")
        self.model.eval().to(self.device)

    def extract(self, image: Image.Image, candidates, type_action=0):
        texts = [word.lower() for word in candidates.keys() if "Undefined" not in word]
        inputs = self.processor(text=texts, images=image, return_tensors="pt").to(self.device)
        with torch.no_grad():
            outputs = self.model(**inputs)
        arr = inputs.pixel_values.squeeze().cpu().numpy()
        unnorm = (arr * np.array(OPENAI_CLIP_STD)[:, None, None]) + np.array(OPENAI_CLIP_MEAN)[:, None, None]
        unnorm = (unnorm * 255).astype(np.uint8)
        unnorm = np.moveaxis(unnorm, 0, -1)
        im = Image.fromarray(unnorm)
        target_sizes = torch.Tensor([im.size[::-1]]).to(self.device)
        results = self.processor.post_process_grounded_object_detection(
            outputs=outputs, threshold=0.2, target_sizes=target_sizes
        )
        best_idx = None
        for result in results:
            scores = result["scores"]
            if scores.numel() == 0:
                continue
            best_idx = torch.argmax(scores)

        # print(texts)
        # print("best_idx", best_idx)
        # print("result", result)
        # print("result[\"labels\"][best_idx]][best_idx]",result["labels"][best_idx].item())
        if best_idx is None:
            return candidates.get("Undefined", ""), 0
        if type_action:
            return list(candidates.keys())[result["labels"][best_idx].item()], float(scores[best_idx].item())

        return candidates.get(list(candidates.keys())[result["labels"][best_idx].item()], ""), float(
            scores[best_idx].item())


class BioCLIPModelLoader(BaseModelLoader):
    def __init__(self):
        super().__init__()
        self.model, _, self.preprocess = open_clip.create_model_and_transforms(model_name='ViT-B-16',
                                                                               pretrained="./local_bioclip_model")#('hf-hub:imageomics/bioclip')
        self.tokenizer = open_clip.get_tokenizer('ViT-B-16')
        self.model.to(self.device)

    def extract(self, image: Image.Image, candidates, type_action=0):
        img = self.preprocess(image).unsqueeze(0).to(self.device)
        classes = [word.lower() for word in candidates.keys() if "Undefined" not in word]
        text_inputs = self.tokenizer(classes).to(self.device)
        with torch.no_grad():
            image_embed = self.model.encode_image(img)
            text_embed = self.model.encode_text(text_inputs)
        image_embed = image_embed / image_embed.norm(dim=-1, keepdim=True)
        text_embed = text_embed / text_embed.norm(dim=-1, keepdim=True)
        logits = image_embed @ text_embed.T
        probs = logits.softmax(dim=-1)
        best_idx = torch.argmax(probs[0]).item()
        if type_action:
            return list(candidates.keys())[best_idx], float(probs[0][best_idx].item())
        return candidates.get(list(candidates.keys())[best_idx], ""), float(probs[0][best_idx].item())

class ViTImageNetClassifierModelLoader:
    def __init__(self, model_name: str, weights_path: str, classes_file: str):
        """
        model_name: название модели в timm, например 'vit_base_patch16_224'
        weights_path: путь к файлу с сохранёнными весами (.pth)
        classes_file: путь к файлу imagenet_classes.txt
        """
        # Загружаем имена классов
        with open(classes_file, "r") as f:
            self.class_names = [line.strip().split()[1] for line in f.readlines()]

        # Создаём модель, загружаем веса, переводим в eval
        self.model = timm.create_model(model_name, pretrained=False)
        self.model.load_state_dict(torch.load(weights_path))
        self.model.eval()

        # Конфиг препроцессинга и трансформ
        config = resolve_data_config({}, model=self.model)
        self.transform = create_transform(**config)

    def extract(self, image: Image.Image):
        """
        Выполняет предсказание для одного изображения.
        Возвращает кортеж (id класса, имя класса, вероятность).
        """
        # Препроцессинг
        tensor = self.transform(image).unsqueeze(0)

        # Инференс
        with torch.no_grad():
            output = self.model(tensor)
            probs = torch.nn.functional.softmax(output[0], dim=0)
            top_prob, top_catid = torch.topk(probs, 1)

        idx = top_catid.item()
        label = self.class_names[idx] if idx < len(self.class_names) else "Unknown"

        return label, top_prob.item()


# class GigaChatModelLoader():
#     def __init__(self, file_path=""):
#
#         # url = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
#         #
#         # payload = {
#         #  'scope': 'GIGACHAT_API_PERS'
#         # }
#         # headers = {
#         #   'Content-Type': 'application/x-www-form-urlencoded',
#         #   'Accept': 'application/json',
#         #   'RqUID': 'a58b61f8-dbc1-496b-bf85-5a20c4deafde',
#         #   'Authorization': 'Basic MzA4ZTBjMTktMTdhOS00OTZmLTkyNjUtYzEzZmFhY2JjZTg2OjBhYmMwZmM1LTA2NjItNDk4Ny1hNzE4LTMzMmU1NDZmZDdjNg=='
#         # }
#
#         # response = requests.request("POST", url, headers=headers, data=payload, verify=False)
#
#         self.AUTH_TOKEN = "OTU2MTMyMDEtZjhkNy00Mzc5LWIzZDYtNWRjMTkzYWE2NjExOmI5YTU3MjZhLTYwZGEtNGFiZS1iNGNiLTAyYmJkZjQzYmQ3Mw=="
#         # print(response.text)
#         self.giga = GigaChat(
#             credentials=self.AUTH_TOKEN,
#             # access_token=self.AUTH_TOKEN,
#             # base_url="https://gigachat.devices.sberbank.ru/api/v1",
#             model='GigaChat-Pro',
#             verify_ssl_certs=False,
#             scope='GIGACHAT_API_CORP',
#             timeout=120
#         )
#         # with open(file_path, "r", encoding="utf-8") as file:
#         #   self.ANNOTATION_PROMPT = file.read()
#         self.ANNOTATION_PROMPT = """Ты — эксперт по визуальному распознаванию природы.
# У вас есть изображение.
# Нужно проанализировать его и вернуть **строго валидный JSON** (без поясняющего текста, без комментариев, без лишних пробелов), полностью соответствующий схемe ниже.
# Если признак определить нельзя — выводите наименование признака со значением пустой строки (""), например "season": "".
#
# ФОРМАТ ВЫВОДА
# {
#     "season": "",                    // Один из: ["Весна","Лето","Осень","Зима"]
#     "sex": "",                       // ["Мужской","Женский"]
#     "behavior": "",                  // ["Сидит","Стоит","Летит","Идёт","Бежит","Плавает","Лазит","Отдыхает","Ест","Охотится","Играет"]
#     "habitat": "",                   // ["Лес","Поле","Луг","Пустыня","Болото","Горы","Городская среда","Деревня","Побережье","Река","Озеро","Море","Сад","Парк"]
#     "surface_type": "",              // ["Кора","Трава","асфальт","Песок","Снег","Почва","Камень","Лист","Вода","Бетон","Дерево (доски)","Металл","Пластик"]
#     "placed": "",                    // Расположение объекта (LOCATION): ["На земле","На дереве","На ветке","На камне","В воде","В небе","На траве","На песке","На снегу","На стене","На здании"]
#     "interaction": "",               // ["Один","В группе","С человеком","С другим животным","С потомством"]
#     "mood": "",                      // ["Спокоен","Агрессивен","Насторожен","Испуган","Любопытен","Спит","Ранен","Играет"]
#     "lifeform": "",                  // ["Фауна","Флора"]
#     "fauna_type": "",            // Если lifeform="Фауна": ["Млекопитающее","Птица","Рептилия","Земноводное","Рыба","Насекомое","Паукообразное","Моллюск","Ракообразное","Червь"]
#     "flora_type": "",            // Если lifeform="Флора": ["Дерево","Кустарник","Травянистое растение","Цветущее растение","Папоротник","Мох","Водоросль"]
#     "age": "",                       // ["Детеныш","Молодая особь","Взрослая особь","Старая особь"]
#     "precipitation": "",             // ["Без осадков","Дождь","Снег","Морось","Град","Гроза","Туман"]
#     "cloudiness": "",                // ["Ясно","Переменная облачность","Пасмурно"]
#     "temperature": "",               // ["Жарко","Тепло","Прохладно","Холодно","Мороз"]
#     "wind": "",                      // ["Штиль","Лёгкий ветер","Ветрено","Штормовой ветер"]
#     "classification_info": {
#         "name": "",                  // Вид (пример: "Нерпа")
#         "genus": "",                 // Род  (пример: "Нeрпы")
#         "family": "",                // Семейство (пример: "Настоящие тюлени")
#     },
#     "detected_objects": [],          // Объекты которые были обнаружены на изображении через запятую списком, н-р ["Дерево", "Нерпа"]
#     "image_caption": "",             // Одно короткое описательное предложение на русском
#     "flowering": "",                 // Есть ли признаки цветения? "Да" | "Нет" | "" (если неприменимо)
#     "flower_color": "",              // Цвет лепестков (свободная строка) или ""
#     "fruits_present": ""             // Есть ли плод на изображении? "Да" | "Нет" | "" (если неприменимо)
# }
#
# ПРАВИЛА
# 1. Используйте **только** указанные значения. Не добавляйте «Undefined» — вместо этого ставьте "".
# 2. Если lifeform="Фауна", поле flora_type должно быть "". Если lifeform="Флора", fauna_type — "".
# 3. Выводите ровно один объект JSON без обёрток, префиксов, суффиксов и пояснений.
# 4. Детализация: Указывай только те признаки, которые можно достоверно определить по фото. Если информация неочевидна, оставляй поле пустым ("").
# 5. Точность: Используй научные названия для флоры и фауны (например, "Байкальский омуль", а не просто "рыба").
#       """
#
#     def process_image(self, image_path: str, filename: str) -> dict:
#         """Обрабатывает одно изображение и возвращает аннотацию"""
#         # try:
#         # load_dotenv(find_dotenv())
#         # print(image_path)
#         file_info = self.giga.upload_file(open(image_path, "rb"))
#         file_id = file_info.id_
#         messages = [
#             HumanMessage(
#                 content=self.ANNOTATION_PROMPT,
#                 additional_kwargs={"attachments": [file_id]}
#             )
#         ]
#
#         response = self.giga.invoke(messages)
#
#         content = response.content.strip()
#         try:
#             json_start = content.find('{')
#             json_end = content.rfind('}') + 1
#             result = json.loads(content[json_start:json_end])
#             return result
#
#         except json.JSONDecodeError:
#             return {"error": "Invalid JSON format", "response": content}
#
#         # except Exception as e:
#         #     return {"error": str(e), "filename": filename}
#         # finally:
#         #     time.sleep(1.5)
#
#     def process_all_images(self, image_path, filename):
#         """Обрабатывает все изображения в директории"""
#         result = self.process_image(image_path, filename)
#
#         if "error" in result:
#             print(f"  Ошибка: {result['error']}")
#         else:
#             print("  Успешно!")
#
#         print(f"\nРезультаты сохранены")
#         return result

WIKI_HEADERS = {
    "User-Agent": "iNaturalistTaxonomyBot/1.0 (contact: your_email@example.com)"
}

class iNaturalistTaxonomy:
    def __init__(self, json_path:str, wiki_headers: dict = None, timeout: int = 15):
        """
        wiki_headers: заголовки для запросов к Wikipedia
        timeout: таймаут для HTTP-запросов
        """
        self.wiki_headers = wiki_headers or WIKI_HEADERS
        self.timeout = timeout
        self.json_path = json_path

    def _fetch_json(self, url: str):
        resp = requests.get(url, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def _parse_family_genus_from_wikipedia(self, wiki_url: str) -> dict:
        """Парсит Family и Genus из таксобокса Wikipedia."""
        response = requests.get(wiki_url, headers=self.wiki_headers, timeout=self.timeout)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        taxobox = soup.find("table", class_="infobox biota")
        if not taxobox:
            return {"family": None, "genus": None}

        family = genus = None
        for row in taxobox.find_all("tr", class_="taxonrow"):
            cells = row.find_all("td")
            if len(cells) != 2:
                continue

            label = cells[0].get_text(strip=True).lower()
            value = cells[1].get_text(" ", strip=True)

            if label.startswith("family"):
                family = value.split()[0]
            elif label.startswith("genus"):
                genus = value.split()[0]

        return {"family": family, "genus": genus}

    def extract(self, observation_id: int) -> dict:
        """
        Возвращает таксономическую информацию по observation_id iNaturalist.
        """
        # 1) Получаем наблюдение
        obs_url = f"https://api.inaturalist.org/v1/observations/{observation_id}"
        data = self._fetch_json(obs_url)

        if not data["results"]:
            raise ValueError("Наблюдение не найдено")

        taxon = data["results"][0].get("taxon")
        if not taxon:
            raise ValueError("У наблюдения нет таксона")

        family = genus = species = None

        # 2) Пробуем ancestors
        for ancestor in taxon.get("ancestors", []):
            if ancestor.get("rank") == "family":
                family = ancestor.get("name")
            elif ancestor.get("rank") == "genus":
                genus = ancestor.get("name")

        if taxon.get("rank") == "species":
            species = taxon.get("name")

        # 3) Если не всё нашли — парсим Wikipedia
        if (family is None or genus is None) and taxon.get("wikipedia_url"):
            wiki_data = self._parse_family_genus_from_wikipedia(taxon["wikipedia_url"])
            family = family or wiki_data.get("family")
            genus = genus or wiki_data.get("genus")

        # Собираем результат
        return {
            "observation_id": observation_id,
            "scientific_name": taxon.get("name"),
            "species": species,
            "genus": genus,
            "family": family,
            "common_name": taxon.get("preferred_common_name"),
            "wikipedia_url": taxon.get("wikipedia_url"),
            "taxon_id": taxon.get("id")
        }

    def add_taxonomy_to_json(
            self,
            key: str,
            genus: str,
            family: str,
            name: str
    ) -> None:
        """
        Добавляет или обновляет запись в разделе TAXONOMY JSON-файла

        :param json_path: путь к JSON файлу
        :param key: ключ (например "A photo of a seal")
        :param genus: род
        :param family: семейство
        :param name: название объекта
        """
        json_path = Path(self.json_path)

        # Если файла нет — создаём пустую структуру
        if not json_path.exists():
            data = {"TAXONOMY": {}}
        else:
            with json_path.open("r", encoding="utf-8") as f:
                data = json.load(f)

        # Гарантируем наличие TAXONOMY
        data.setdefault("TAXONOMY", {})

        # Добавляем / обновляем запись
        data["TAXONOMY"][key] = {
            "genus": genus or "",
            "family": family or "",
            "name": name or ""
        }

        # Сохраняем обратно
        with json_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)


class FeatureExtractor:
    def __init__(self, extractors, extractors_classification):
        self.extractors = extractors  # list of model instances with .extract()
        self.extractors_classification = extractors_classification  # list of model instances with .extract()

    def extract_info(self, image: Image.Image, candidates: dict, result_chatgpt: dict, meta_inform=""):
        results = [model.extract(image, candidates) for model in self.extractors]
        # print(results)
        if isinstance(meta_inform, dict) :
            results.append((meta_inform, 1.0))
        results.append((result_chatgpt, 0.0))
        # Подсчет частоты слов
        word_counts = Counter([dict_class.get('name', "") if dict_class else "" for dict_class, pos in results])
        # Нахождение самого частого слова
        most_common_class, count = word_counts.most_common(1)[0]
        # Поиск данных в results, соответствующих самому частому классу
        matching_entry = next(((d, p) for d, p in results if d.get("name", "") == most_common_class), ({}, 0.0))
        return {
            "meta_inform": self._format_result(results[3]),
            "clip": self._format_result(results[0]),
            "dino": self._format_result(results[1]),
            "owlv2": self._format_result(results[2]),
            "giga_chat":  ("",0.0), #self._format_result(results[3]),
            "result": {
                "name": most_common_class,
                'genus': matching_entry[0].get('genus', ""),
                'family': matching_entry[0].get('family', "")
            }
        }

    def extract_feature_classification(self, image: Image.Image):
        results = [model.extract(image) for model in self.extractors_classification]
        word_counts = Counter([res[0] for res in results])
        most_common_class, _ = word_counts.most_common(1)[0]
        return {
            "vit": results[0],
            "result": most_common_class
        }

    def extract_feature(self, image: Image.Image, candidates: dict, result_chatgpt):
        results = [model.extract(image, candidates) for model in self.extractors]
        results.append((result_chatgpt, 0.0))
        word_counts = Counter([res[0] for res in results])
        most_common_class, _ = word_counts.most_common(1)[0]
        return {
            "clip": results[0],
            "dino": results[1],
            "owlv2": results[2],
            "giga_chat": ("",0.0), #results[3],
            "result": most_common_class
        }

    @staticmethod
    def _format_result(result_tuple):
        class_info, prob = result_tuple
        return {
            "name": class_info.get("name", ""),
            "genus": class_info.get("genus", ""),
            "family": class_info.get("family", ""),
            "possibels": prob
        }


class FloraDetector:
    @staticmethod
    def detect_flora_info(img: Image.Image, yolo_objs):
        # Конвертация в HSV
        arr = np.array(img)
        hsv = cv2.cvtColor(arr, cv2.COLOR_RGB2HSV)
        mask = cv2.inRange(hsv, (0, 50, 50), (180, 255, 255))  # оттенок, насыщенность, яркость
        flowering = "Да" if mask.mean() > 50 else "Нет"

        if flowering == "Да":
            pixels = arr[mask > 0]
            avg = pixels.mean(axis=0).astype(int)
            color = "#{:02X}{:02X}{:02X}".format(avg[0], avg[1], avg[2])
        else:
            color = "Не определён"

        fruits_present = "Да" if any(o in yolo_objs for o in {"flower", "cone"}) else "Нет"
        return flowering, color, fruits_present


class EXIFExtractor:
    @staticmethod
    def extract(path: str):
        data = {
            "author": "", "country": "", "region": "",
            "coords": (None, None), "datetime_original": None
        }
        try:
            img = Image.open(path)
            exif_raw = img._getexif() or {}
            exif = {ExifTags.TAGS.get(k): v for k, v in exif_raw.items() if k in ExifTags.TAGS}

            data["author"] = exif.get('Artist', "")

            gps = exif.get('GPSInfo')
            if gps:
                def _dms_to_dd(dms, ref):
                    deg, minute, sec = dms
                    dd = deg + minute / 60 + sec / 3600
                    return dd * (-1 if ref in ['S', 'W'] else 1)

                lat = _dms_to_dd(gps[2], gps[1])
                lon = _dms_to_dd(gps[4], gps[3])
                data["coords"] = (lat, lon)

            for tag in ('DateTimeOriginal', 'DateTimeDigitized', 'DateTime'):
                val = exif.get(tag)
                if val:
                    try:
                        data["datetime_original"] = datetime.strptime(val, "%Y:%m:%d %H:%M:%S")
                    except ValueError:
                        pass
                    break
        except Exception:
            pass

        return data


class ImageProcessor:
    def __init__(self, extractor: FeatureExtractor, inaturalist:iNaturalistTaxonomy, blip_loader: BLIPModelLoader, yolo_loader: YOLOModelLoader,
                 gigachatmodel_loader, taxonomy: dict):
        self.extractor = extractor
        self.inaturalist = inaturalist
        self.blip = blip_loader
        self.yolo = yolo_loader
        self.gigachat = gigachatmodel_loader
        self.taxonomy = taxonomy

    def process_folder(self, excel_path: str, off_path: str, out_json: str = 'features_results.json'):
        output = {}
        folder_name = ""
        client = ApiClient(base_url=os.getenv("ECOBOT_API_BASE_URL", ""), default_headers={"X-Admin-Password": os.getenv("ADMIN_PASSWORD", "")})
        df = pd.read_excel(excel_path)
        df_off = pd.read_excel(off_path)
        start = time.time()
        # df = df[:1]
        try:
            for idx, row in tqdm(df.iterrows(), total=len(df), desc="Аннотирование ОФФ:"):
                image_path = row['Путь к файлу']  # Замените, если имя столбца отличается
                if not isinstance(image_path, str):
                    continue

                if not image_path.lower().endswith(('.jpg', '.jpeg', '.png', '.bmp', '.tiff', 'gif')):
                    continue

                abs_path = os.path.abspath(image_path)

                if not os.path.exists(image_path):
                    print(f"Файл не найден: {image_path}")
                    continue

                try:
                    img = Image.open(image_path).convert('RGB')
                    folder_name = os.path.basename(os.path.dirname(image_path))
                    print(
                        'image:', img,
                        'folder:', folder_name,
                        'image_path:', image_path,
                        'abs_path:', image_path
                    )
                except Exception as e:
                    print(f"Ошибка при открытии {image_path}: {e}")
                    continue

                meta = EXIFExtractor.extract(image_path)
                matched_key = next(
                    (key for key in self.taxonomy.get("TAXONOMY", {}) if folder_name.lower() in key.lower()), None)
                matched_taxonomy=""
                if matched_key:
                    matched_taxonomy = self.taxonomy.get("TAXONOMY", {}).get(matched_key)
                else:
                    taxonomy_response = self.inaturalist.extract(int(row['id наблюдения']))
                    russion_name = df_off.loc[
                        df_off["Латинское"] == row['Идентификатор ОФФ'],
                        "Русское"
                    ]
                    self.inaturalist.add_taxonomy_to_json(
                        key="A photo of a "+taxonomy_response.get("scientific_name", "None"),
                        genus=taxonomy_response.get("genus", "None"),
                        family=taxonomy_response.get("family", "None"),
                        name=russion_name.iloc[0]
                    )
                    matched_taxonomy = {
                        "genus": taxonomy_response.get("genus", "None"),
                        "family": taxonomy_response.get("family", "None"),
                        "name": russion_name.iloc[0]
                    }

                # Основная информация
                # json_result_GigaChat = self.gigachat.process_image(image_path, folder_name)
                json_result_GigaChat={}
                class_info_object = self.extractor.extract_info(img, self.taxonomy.get("TAXONOMY", {}),
                                                                json_result_GigaChat.get("classification_info", {}),
                                                                matched_taxonomy)
                classification_object = self.extractor.extract_feature_classification(img)
                # Побочные признаки json_result_GigaChat[key.lower()]
                features = {key.lower(): self.extractor.extract_feature(img, self.taxonomy.get(key, {}),
                                                                        json_result_GigaChat.get(key.lower(), ""))
                            for key in ["SEASONS", "SEXES", "AGES", "PRECIPITATION", "CLOUDINESS", "TEMPERATURE",
                                        "WIND", "BEHAVIOR", "HABITAT", "SURFACE_TYPE", "INTERACTION", "MOOD",
                                        "LIFEFORM", "FAUNA_TYPE", "FLORA_TYPE", "LOCATION"]}

                caption = self.blip.extract_caption(img)
                yolo_objs = self.yolo.extract(image_path)
                flowering, flower_color, fruits_present = FloraDetector.detect_flora_info(img, yolo_objs)
                entry = {
                    "observation_id": row["id наблюдения"],
                    "name_photo": image_path,
                    "parent": folder_name,
                    "author_photo": meta['author'] if meta['author'] else row['Автор'],
                    "rights": row['Права'],
                    "season": features['seasons'],
                    "sex": features['sexes'],
                    "behavior": features['behavior'],
                    "habitat": features['habitat'],
                    "surface_type": features['surface_type'],
                    "placed": features['location'],
                    "interaction": features['interaction'],
                    "mood": features['mood'],
                    "lifeform": features['lifeform'],
                    "class_type": {
                        "fauna_type": features['fauna_type'],
                        "flora_type": features['flora_type']
                    },
                    "age": features['ages'],
                    "precipitation": features['precipitation'],
                    "cloudiness": features['cloudiness'],
                    "temperature": features['temperature'],
                    "wind": features['wind'],
                    "classification_info": class_info_object,
                    "date_shooting_time": meta["datetime_original"].strftime("%Y-%m-%d") if meta[
                        "datetime_original"] else row['Время съёмки'],
                    "date_loading_time": row['время загрузки'],
                    "location": {
                        "location": meta['country'] + "," + meta['region'] if meta['country'] or meta['region'] else
                        row['Место съёмки'],
                        "coordinates": {
                            "latitude": meta['coords'][0] if meta['coords'][0] else
                            row['Координаты съёмки'].split(", ")[0],
                            "longitude": meta['coords'][1] if meta['coords'][1] else
                            row['Координаты съёмки'].split(", ")[1]
                        }
                    },
                    "image_caption": {"blip": caption,
                                      "giga_chat": json_result_GigaChat.get("image_caption", "")
                                      },
                    "classification_objects": classification_object,
                    "detected_objects":{
                        "yolo": yolo_objs,
                        "giga_chat": json_result_GigaChat.get("detected_objects", [])
                    },
                    "flowering": {"flora_detector": flowering,
                                  "giga_chat": json_result_GigaChat.get("flowering", "")},
                    "flower_color": {"flora_detector": flower_color,
                                     "giga_chat": json_result_GigaChat.get("flower_color", "")},
                    "fruits_present": {"flora_detector": fruits_present,
                                       "giga_chat": json_result_GigaChat.get("fruits_present", "")},
                }
                if folder_name not in output.keys():
                    output[folder_name] = {}
                output[folder_name][f"featurePhoto{idx}"] = entry
            # except Exception as e:
            #   print(f"Ошибка при обработке {abs_path}: {e}")
            # finally:
            output_dir = Path("results")
            output_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            if output:
                for key in output.keys():
                    # client.upload_single_resource(json_list=output[key], images_path=image_path)
                    filename_path = output_dir/f"{key}_{out_json}_{timestamp}.json"
                    with filename_path.open('w', encoding='utf-8') as f:
                        json.dump(output[key], f, ensure_ascii=False, indent=4)
                    print(f"Saved to {filename_path}")
            end = time.time()
            print(f"Время выполнения: {end - start} секунд")
        except KeyboardInterrupt:
            output_dir = Path("results/errors")
            output_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            if output:
                for key in output.keys():
                    filename_path = output_dir/f"{key}_{out_json}_{timestamp}.json"
                    with filename_path.open('w', encoding='utf-8') as f:
                        json.dump(output[key], f, ensure_ascii=False, indent=4)
                    print(f"Saved to {filename_path}")
            end = time.time()
            print(f"Время выполнения: {end - start} секунд")


class Pipeline:
    def __init__(self, file_path, file_yolo_path, file_promt_path, custom_models=None):
        self.clip_loader = CLIPModelLoader()
        self.dino_loader = GroundingDINOModelLoader()
        self.owlv2_loader = OWLv2ModelLoader()
        # self.bioclip_loader = BioCLIPModelLoader()
        self.vit_loader = ViTImageNetClassifierModelLoader(
            model_name="vit_base_patch16_224",
            weights_path="ViT/vit_model.pth",
            classes_file="imagenet_classes.txt"
        )
        # self.giga_loader = GigaChatModelLoader(file_promt_path)

        self.access_functions_zero_shot = [
            self.clip_loader,
            self.dino_loader,
            self.owlv2_loader,
            # self.bioclip_loader
        ]

        self.access_functions_zero_shot_classification = [
            self.vit_loader
        ]

        if custom_models:
            self.access_functions_zero_shot.extend(custom_models)

        self.extractor = FeatureExtractor(self.access_functions_zero_shot, self.access_functions_zero_shot_classification)
        self.inaturalist = iNaturalistTaxonomy(json_path=file_path)
        self.yolo_loader = YOLOModelLoader(file_yolo_path=file_yolo_path, classes=self.get_taxonomy_keys_without_prefix(json_path=file_path))
        self.blip_loader = BLIPModelLoader()
        # self.flora_detector = FloraDetector(self.yolo_loader)

        # Путь к файлу
        with open(file_path, 'r', encoding='utf-8') as file:
            feature_data_classification = json.load(file)

        self.processor = ImageProcessor(
            extractor=self.extractor,
            inaturalist=self.inaturalist,
            blip_loader=self.blip_loader,
            yolo_loader=self.yolo_loader,
            gigachatmodel_loader=None, #
            taxonomy=feature_data_classification
        )

    @staticmethod
    def get_taxonomy_keys_without_prefix(
            json_path: str | Path,
            prefix: str = "A photo of a "
    ) -> list[str]:
        """
        Возвращает список ключей TAXONOMY без префикса
        'A photo of a ' и без ключа 'Undefined'
        """
        json_path = Path(json_path)

        with json_path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        taxonomy = data.get("TAXONOMY", {})

        result = []

        for key in taxonomy.keys():
            if key == "Undefined":
                continue

            if key.startswith(prefix):
                result.append(key[len(prefix):].lower())
            else:
                result.append(key.lower())

        return result

    def run(self, excel_path:str, off:str, output_json="features_results.json"):
        self.processor.process_folder(excel_path=excel_path, off_path=off, out_json=output_json)

    def add_model(self, model):
        self.access_functions_zero_shot.append(model)
        self.extractor = FeatureExtractor(self.access_functions_zero_shot)
        self.processor.extractor = self.extractor