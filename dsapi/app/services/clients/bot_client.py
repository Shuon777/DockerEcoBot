from abc import ABC, abstractmethod
from typing import Dict, Any
import httpx

class IBotClient(ABC):
    @abstractmethod
    async def send_query(self, query: str, debug_mode: bool = True) -> Dict[str, Any]:
        pass

class EcobotHttpClient(IBotClient):
    def __init__(self, domain: str):
        self.url = f"{domain}/test-api/test_query"

    async def send_query(self, query: str, debug_mode: bool = True) -> Dict[str, Any]:
        payload = {
            "query": query,
            "user_id": "test_user",
            "settings": {"debug_mode": debug_mode},
        }
        async with httpx.AsyncClient(timeout=40.0) as client:
            try:
                response = await client.post(self.url, json=payload)
                if response.status_code == 200:
                    return response.json()
                return {"error": f"Status {response.status_code}"}
            except Exception as e:
                return {"error": str(e)}