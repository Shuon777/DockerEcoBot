from abc import ABC, abstractmethod


class ILLMProvider(ABC):
    @abstractmethod
    def get_llm(self):
        """Возвращает инстанс LangChain BaseChatModel."""
