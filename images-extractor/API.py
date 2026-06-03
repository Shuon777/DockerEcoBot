import requests
from abc import ABC, abstractmethod
import base64
from typing import Optional
import os
import mimetypes
import json

class ApiClientBase(ABC):
    """Интерфейс API клиента"""

    # @abstractmethod
    # def post(self, endpoint: str, body: dict, headers: dict = None):
    #     pass
    #
    # @abstractmethod
    # def post_files(self, endpoint: str, files: dict, data: dict = None, headers: dict = None):
    #     pass

    @abstractmethod
    def post_form(self, endpoint: str, data: dict, files: dict | None = None):
        pass


class ApiClient(ApiClientBase):
    """Реализация API клиента"""

    def __init__(self, base_url: str, default_headers: dict = None):
        self.base_url = base_url.rstrip("/")
        self.default_headers = default_headers or {}

    def _build_url(self, endpoint: str):
        return f"{self.base_url}/{endpoint.lstrip('/')}"

    def _merge_headers(self, headers):
        return {**self.default_headers, **(headers or {})}

    def post(self, endpoint: str, body: dict, headers: dict = None):
        url = self._build_url(endpoint)
        headers = self._merge_headers(headers)

        response = requests.post(url, json=body, headers=headers)
        response.raise_for_status()
        return response.json()

    def post_form(self, endpoint: str, data: dict, files: Optional[dict] = None):
        """
        Универсальный метод отправки multipart/form-data
        data — текстовые поля
        files — файлы
        """
        url = self._build_url(endpoint)
        headers = self.default_headers

        response = requests.post(
            url=url,
            headers=headers,
            data=data,
            files=files
        )

        response.raise_for_status()
        return response.json()

    def upload_both_archives(self, json_path: str, images_path: str):
        """
        Загрузка двух архивов:
        - json_archive
        - images_archive
        + перезагрузка БД + инкрементальное обновление
        """
        data = {
            "reload_database": "true",
            "incremental_update": "true",
            "use_stubs": "true"
        }

        with open(json_path, "rb") as json_file, open(images_path, "rb") as images_file:
            files = {
                "json_archive": ("json_archive.zip", json_file, "application/zip"),
                "images_archive": ("images_archive.zip", images_file, "application/zip")
            }

            return self.post_form("upload_resources", data=data, files=files)

    # =========================
    #       СЦЕНАРИИ API
    # =========================

    def reload_database_only(self):
        """Только перезагрузка БД (без файлов)"""
        data = {
            "reload_database": "true",
            "incremental_update": "false",
            "use_stubs": "true"
        }
        return self.post_form("upload_resources", data=data)

    def upload_json_only(self, json_path: str):
        """Только JSON архив"""
        data = {
            "reload_database": "true",
            "incremental_update": "true",
            "use_stubs": "true"
        }

        with open(json_path, "rb") as json_file:
            files = {
                "json_archive": ("json_archive.zip", json_file, "application/zip")
            }
            return self.post_form("upload_resources", data=data, files=files)

    def upload_images_only(self, images_path: str):
        """Только архив с картинками"""
        data = {
            "reload_database": "false",
            "incremental_update": "true",
            "use_stubs": "true"
        }

        with open(images_path, "rb") as images_file:
            files = {
                "images_archive": ("images_archive.zip", images_file, "application/zip")
            }
            return self.post_form("upload_resources", data=data, files=files)

    def upload_same_archives_again(self, json_path: str, images_path: str):
        """Повторная загрузка + обновление БД"""
        data = {
            "reload_database": "true",
            "incremental_update": "true",
            "use_stubs": "true"
        }

        with open(json_path, "rb") as json_file, open(images_path, "rb") as images_file:
            files = {
                "json_archive": ("json_archive.zip", json_file, "application/zip"),
                "images_archive": ("images_archive.zip", images_file, "application/zip"),
            }
            return self.post_form("upload_resources", data=data, files=files)

    def upload_single_resource(self, json_list: {}, images_path: str):
        """Повторная загрузка + обновление БД"""
        json_data = json.dumps(json_list)
        data = {
            "reload_database": "true",
            "incremental_update": "true",
            "use_stubs": "true",
            "json_date": json_data
        }

        with open(images_path, "rb") as images_file:
            files = {
                "images_file": (os.path.basename(images_path), images_file, mimetypes.guess_type(images_path)[0] or "application/octet-stream"),
            }
            return self.post_form("upload_single_resource", data=data, files=files)

    def add_resources_only(self, json_path: str):
        """Добавление ресурсов без обновления БД"""
        data = {
            "reload_database": "false"
        }

        with open(json_path, "rb") as json_file:
            files = {
                "json_archive": ("json_archive.zip", json_file, "application/zip"),
            }
            return self.post_form("upload_resources", data=data, files=files)

# ===== Пример использования =====
if __name__ == "__main__":
    client = ApiClient(base_url="https://testecobot.ru", default_headers={"X-Admin-Password": "ecobotadminpass"})

    # result = client.upload_both_archives(
    #     json_path="Siberian fir_features1.zip",
    #     images_path="data.zip"
    # )
    # print(result)
    # print(client.reload_database_only())
    # print(client.upload_json_only("Siberian fir_features1.zip"))
    # print(client.upload_images_only("data.zip"))
    print(client.upload_single_resource("Siberian fir_features1.zip", "data.zip"))
    # print(client.upload_same_archives_again("Siberian fir_features1.zip", "data.zip"))
    # print(client.add_resources_only("Siberian fir_features1.zip"))
    #
    # # открываем файлы безопасно
    # with open("Siberian fir_features1.zip", "rb") as json_file, \
    #         open("data.zip", "rb") as images_file:
    #     files = {
    #         "json_archive": ("Siberian fir_features1.zip", json_file, "application/zip"),
    #         "images_archive": ("data.zip", images_file, "application/zip")
    #     }
    #
    #     response = client.post_files(
    #     endpoint="upload_resources",
    #     files=files,
    #     data={"database_reloaded":"true", "reload_database": "true", "incremental_update": "true","use_stubs": "true" }
    #     )
    #     print(response)
    # отправляем два архива
    # files = {
    #     "archive1": ("Siberian fir_features1.zip", open("Siberian fir_features1.zip", "rb"), "application/zip"),
    #     "archive2": ("data.zip", open("data.zip", "rb"), "application/zip"),
    # }
    #
    # result = client.post_files(
    #     endpoint="upload_resources",
    #     files=files,
    #     data={"database_reloaded":"true", "reload_database": "true", "incremental_update": "true","use_stubs": "true" }
    # )

