import time

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import FakeExecutor

H = {"X-API-Token": "secret"}


@pytest.fixture
def client(settings):
    execs = [
        FakeExecutor(settings, "a", {"Время года": ("Зима", 0.8), "Среда обитания": ("Озеро", 0.7)}),
        FakeExecutor(settings, "b", {"Время года": ("Зима", 0.6), "Среда обитания": ("Лес", 0.3)},
                     fail_on={"Облачность"}),
        FakeExecutor(settings, "phenovision", {"Цветение": ("Да", 0.95)}, universal=False),
    ]
    app = create_app(settings, executors=execs, captioner=None)
    with TestClient(app) as c:
        yield c


def wait(client, task_id, timeout=5):
    deadline = time.time() + timeout
    while time.time() < deadline:
        info = client.get(f"/tasks/{task_id}", headers=H).json()
        if info["status"] in ("completed", "failed"):
            return info
        time.sleep(0.05)
    raise AssertionError("задача не завершилась")


def test_token_required(client):
    assert client.get("/features").status_code == 401
    assert client.get("/features", headers=H).status_code == 200


def test_features_filtered_by_lifeform(client):
    fauna = {f["name"] for f in client.get("/features?lifeform=Фауна", headers=H).json()}
    assert "Поведение" in fauna and "Цветение" not in fauna
    flora = {f["name"]: f for f in client.get("/features?lifeform=flora", headers=H).json()}
    assert flora["Цветение"]["executors"] == ["phenovision"]


def test_full_cycle_upload(client, jpeg_bytes):
    r = client.post("/annotate/upload", headers=H,
                    files={"file": ("x.jpg", jpeg_bytes, "image/jpeg")},
                    data={"features": "Время года,Среда обитания,Облачность,Цветение",
                          "lifeform": "Флора", "resource_id": "1234"})
    assert r.status_code == 202, r.text
    task_id = r.json()["task_id"]
    assert wait(client, task_id)["status"] == "completed"

    res = client.get(f"/tasks/{task_id}/result", headers=H).json()
    assert res["resource_id"] == 1234
    f = res["features"]
    assert f["Время года"]["verdict"] == "Зима"
    assert f["Цветение"]["verdict"] == "Да"
    assert [x["executor"] for x in f["Цветение"]["by_executor"]] == ["phenovision"]
    # b упал на облачности, a не ответил -> не определено, но задача жива
    assert f["Облачность"]["verdict"] is None
    assert any(x["error"] for x in f["Облачность"]["by_executor"])
    assert res["features_for_db"]["Время года"] == "Зима"
    assert "Облачность" not in res["features_for_db"]


def test_validation_errors_are_immediate(client):
    r = client.post("/annotate", headers=H, json={"image_url": "http://x/y.jpg", "features": ["Нет такого"]})
    assert r.status_code == 422
    r = client.post("/annotate", headers=H, json={"image_url": "http://x/y.jpg", "executors": ["zzz"]})
    assert r.status_code == 422
    r = client.post("/annotate", headers=H, json={"image_url": "http://x/y.jpg",
                                                   "features": ["Цветение"], "executors": ["a"]})
    assert r.status_code == 422  # a не умеет цветение


def test_bad_url_fails_task_not_service(client):
    r = client.post("/annotate", headers=H, json={"image_url": "ftp://x/y.jpg", "features": ["Время года"]})
    info = wait(client, r.json()["task_id"])
    assert info["status"] == "failed" and "http" in info["error"]
    assert client.get(f"/tasks/{info['task_id']}/result", headers=H).status_code == 500


def test_result_not_ready_and_unknown(client):
    assert client.get("/tasks/nope", headers=H).status_code == 404
