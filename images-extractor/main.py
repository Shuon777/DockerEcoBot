from init_pipeline import Pipeline
# from Test import GigaChatModelLoader
import requests
from gigachat import GigaChat


if __name__ == '__main__':
    """main блок"""
    path = input("Введите путь к файлу (.json), где находятся описание признаков (или objects/feature.json): ")
    path = path if len(path) else 'objects/feature.json'

    path_name_object = input("Введите путь к файлу (.xlsx), где находится список ОФФ (или objects/OFF_actual.xlsx): ")
    path_name_object = path_name_object if len(path_name_object) else 'objects/OFF_actual.xlsx'

    path_yolo_object = input("Введите путь к файлу (.json), где находится список классов для YOLO (или objects/flora_fauna_classes.json): ")
    path_yolo_object = path_yolo_object if len(path_yolo_object) else 'objects/flora_fauna_classes.json'

    path_all_objects = input("Введите путь к файлу (.xlsx), где находится список ОФФ (или objects/All_Objects.xlsx): ")
    path_all_objects = path_all_objects if len(path_all_objects) else 'objects/All_Objects.xlsx'

    pipeline = Pipeline(file_path=path, file_yolo_path=path_yolo_object, file_promt_path="objects/Промт2.txt")
    pipeline.run(excel_path=path_all_objects,off=path_name_object)

    #'objects/feature.json'
    #'objects/All_Objects.xlsx'
    """Для тестирования работы GigaChat"""
    # Используйте ключ авторизации, полученный в личном кабинете, в проекте GigaChat API.
    #with GigaChat(credentials="OTU2MTMyMDEtZjhkNy00Mzc5LWIzZDYtNWRjMTkzYWE2NjExOmEyYjMyMzY3LTJhYzItNGQ4Ny05ZDE4LWI4ZWFhYzU3N2YyOQ==", ca_bundle_file="russian_trusted_root_ca.cer", scope="GIGACHAT_API_CORP") as giga:
        #response = giga.chat("Какие факторы влияют на стоимость страховки на дом?")
      #  print(response.choices[0].message.content)

    # giga = GigaChatModelLoader()
    # result = giga.process_image("photos\Pusa\large (1).jpeg", "")
    # print(result)
