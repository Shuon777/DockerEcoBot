import httpx
BASE_URL = "http://localhost:5050/api/v1/pipeline_testing"
TOKEN = "B4QGDhFk79yME2m1malbLqGnxDk2373GTNkEbBWAc31"

# Настройка заголовков для всех запросов
headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json"
}

client = httpx.Client(headers=headers, timeout=60.0)


def check_status(session_id: str):
    response = client.get(f"{BASE_URL}/status/{session_id}")
    data = response.json()

    status = data['status']  # pending, running, completed, failed
    progress = data['progress']  # 0-100%

    print(f"📊 Статус: {status} | Прогресс: {progress}%")
    return data

def start_test(objs, mode: str = "llm"):
    response = client.post(f"{BASE_URL}/start", params={"mode": mode, "objs": objs})
    if response.status_code == 200:
        data = response.json()
        print(f"✅ Тест запущен. ID сессии: {data['session_id']}")
        return data['session_id']
    else:
        print(f"❌ Ошибка старта: {response.text}")


if __name__ == "__main__":
    start_test(objs=["Эдельвейс"], mode="no llm")