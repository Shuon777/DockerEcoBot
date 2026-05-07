import os
from langchain_openai import ChatOpenAI
from langchain_gigachat import GigaChat
from domain.interfaces.llm import ILLMProvider


class LLMFactory(ILLMProvider):
    def __init__(self, provider: str = "qwen"):
        self._provider = provider

    def get_llm(self):
        return LLMFactory.get_model(self._provider)

    @staticmethod
    def get_model(provider: str = "qwen"):
        if provider == "qwen":
            return ChatOpenAI(
                base_url=os.getenv("LLM_BASE_URL", "http://host.docker.internal:11434/v1"),
                api_key="ollama",
                model="qwen2.5:14b",
                temperature=0.1,
            )
        if provider == "gigachat":
            return GigaChat(
                credentials=os.getenv("GIGACHAT_CREDENTIALS"),
                model="GigaChat-2-Max",
                verify_ssl_certs=False,
            )
        raise ValueError(f"Unknown provider: {provider}")
