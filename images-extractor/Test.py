
import torch, json
from langchain.schema import HumanMessage
from langchain_gigachat import GigaChat
#from gigachat import GigaChat


class BaseModelLoader:
    def __init__(self):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")


class GigaChatModelLoader():
    def __init__(self, file_path=""):

        # url = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
        #
        # payload = {
        #  'scope': 'GIGACHAT_API_PERS'
        # }
        # headers = {
        #   'Content-Type': 'application/x-www-form-urlencoded',
        #   'Accept': 'application/json',
        #   'RqUID': 'a58b61f8-dbc1-496b-bf85-5a20c4deafde',
        #   'Authorization': 'Basic MzA4ZTBjMTktMTdhOS00OTZmLTkyNjUtYzEzZmFhY2JjZTg2OjBhYmMwZmM1LTA2NjItNDk4Ny1hNzE4LTMzMmU1NDZmZDdjNg=='
        # }

        # response = requests.request("POST", url, headers=headers, data=payload, verify=False)

        self.AUTH_TOKEN = "OTU2MTMyMDEtZjhkNy00Mzc5LWIzZDYtNWRjMTkzYWE2NjExOmI5YTU3MjZhLTYwZGEtNGFiZS1iNGNiLTAyYmJkZjQzYmQ3Mw=="
        # print(response.text)
        self.giga = GigaChat(
            credentials=self.AUTH_TOKEN,
            # access_token=self.AUTH_TOKEN,
            # base_url="https://gigachat.devices.sberbank.ru/api/v1",
            model='GigaChat-Pro',
            verify_ssl_certs=False,
            scope='GIGACHAT_API_CORP',
            timeout=120
        )
        # with open(file_path, "r", encoding="utf-8") as file:
        #   self.ANNOTATION_PROMPT = file.read()
        self.ANNOTATION_PROMPT = """Вы — эксперт по визуальному распознаванию природы.
У вас есть изображение.
Нужно проанализировать его и вернуть **строго валидный JSON** (без поясняющего текста, без комментариев, без лишних пробелов), полностью соответствующий схемe ниже.
Если признак определить нельзя — выводите наименование признака со значением пустой строки (""), например "season": "".

ФОРМАТ ВЫВОДА
{
    "season": "",                    // Один из: ["Весна","Лето","Осень","Зима"]
    "sex": "",                       // ["Мужской","Женский"]
    "behavior": "",                  // ["Сидит","Стоит","Летит","Идёт","Бежит","Плавает","Лазит","Отдыхает","Ест","Охотится","Играет"]
    "habitat": "",                   // ["Лес","Поле","Луг","Пустыня","Болото","Горы","Городская среда","Деревня","Побережье","Река","Озеро","Море","Сад","Парк"]
    "surface_type": "",              // ["Кора","Трава","асфальт","Песок","Снег","Почва","Камень","Лист","Вода","Бетон","Дерево (доски)","Металл","Пластик"]
    "placed": "",                    // Расположение объекта (LOCATION): ["На земле","На дереве","На ветке","На камне","В воде","В небе","На траве","На песке","На снегу","На стене","На здании"]
    "interaction": "",               // ["Один","В группе","С человеком","С другим животным","С потомством"]
    "mood": "",                      // ["Спокоен","Агрессивен","Насторожен","Испуган","Любопытен","Спит","Ранен","Играет"]
    "lifeform": "",                  // ["Фауна","Флора"]
    "fauna_type": "",            // Если lifeform="Фауна": ["Млекопитающее","Птица","Рептилия","Земноводное","Рыба","Насекомое","Паукообразное","Моллюск","Ракообразное","Червь"]
    "flora_type": "",            // Если lifeform="Флора": ["Дерево","Кустарник","Травянистое растение","Цветущее растение","Папоротник","Мох","Водоросль"]
    "age": "",                       // ["Детеныш","Молодая особь","Взрослая особь","Старая особь"]
    "precipitation": "",             // ["Без осадков","Дождь","Снег","Морось","Град","Гроза","Туман"]
    "cloudiness": "",                // ["Ясно","Переменная облачность","Пасмурно"]
    "temperature": "",               // ["Жарко","Тепло","Прохладно","Холодно","Мороз"]
    "wind": "",                      // ["Штиль","Лёгкий ветер","Ветрено","Штормовой ветер"]
    "classification_info": {
        "name": "",                  // Вид (пример: "Нерпа")
        "genus": "",                 // Род  (пример: "Нeрпы")
        "family": "",                // Семейство (пример: "Настоящие тюлени")
    },
    "image_caption": "",             // Одно короткое описательное предложение на русском
    "flowering": "",                 // Есть ли признаки цветения? "Да" | "Нет" | "" (если неприменимо)
    "flower_color": "",              // Цвет лепестков (свободная строка) или ""
    "fruits_present": ""             // Есть ли плод на изображении? "Да" | "Нет" | "" (если неприменимо)
}

ПРАВИЛА
1. Используйте **только** указанные значения. Не добавляйте «Undefined» — вместо этого ставьте "".
2. Если lifeform="Фауна", поле flora_type должно быть "". Если lifeform="Флора", fauna_type — "".
3. Выводите ровно один объект JSON без обёрток, префиксов, суффиксов и пояснений.
4. Детализация: Указывай только те признаки, которые можно достоверно определить по фото. Если информация неочевидна, оставляй поле пустым ("").
5. Точность: Используй научные названия для флоры и фауны (например, "Байкальский омуль", а не просто "рыба").
      """

    def process_image(self, image_path: str, filename: str) -> dict:
        """Обрабатывает одно изображение и возвращает аннотацию"""
        # try:
        # load_dotenv(find_dotenv())
        print(image_path)
        file_info = self.giga.upload_file(open(image_path, "rb"))
        file_id = file_info.id_
        messages = [
            HumanMessage(
                content=self.ANNOTATION_PROMPT,
                additional_kwargs={"attachments": [file_id]}
            )
        ]

        response = self.giga.invoke(messages)

        content = response.content.strip()
        try:
            json_start = content.find('{')
            json_end = content.rfind('}') + 1
            result = json.loads(content[json_start:json_end])
            return result

        except json.JSONDecodeError:
            return {"error": "Invalid JSON format", "response": content}

        # except Exception as e:
        #     return {"error": str(e), "filename": filename}
        # finally:
        #     time.sleep(1.5)

    def process_all_images(self, image_path, filename):
        """Обрабатывает все изображения в директории"""
        result = self.process_image(image_path, filename)

        if "error" in result:
            print(f"  Ошибка: {result['error']}")
        else:
            print("  Успешно!")

        print(f"\nРезультаты сохранены")
        return result