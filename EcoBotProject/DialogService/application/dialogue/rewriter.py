import logging
from infrastructure.llm.factory import LLMFactory

logger = logging.getLogger("QueryRewriter")


class QueryRewriter:
    def __init__(self, provider: str = "qwen"):
        self.llm = LLMFactory.get_model(provider)
        self.context_markers = [
            "он", "она", "оно", "они",
            "его", "ее", "её", "их", "им", "ими",
            "него", "нее", "неё", "них", "ним", "ними", "нем", "нём", "ней",
            "этот", "эта", "это", "эти", "этого", "этой", "этим", "этих", "этом",
            "там", "тут", "туда", "оттуда",
        ]

    def _needs_rewriting(self, query: str) -> bool:
        words = query.lower().split()
        has_markers = any(m in words for m in self.context_markers)
        starts_with_conjunction = query.lower().startswith(("а ", "и ", "но ", "еще ", "ещё "))
        return has_markers or starts_with_conjunction

    async def rewrite(self, query: str, history: list) -> str:
        if not history or not self._needs_rewriting(query):
            logger.info("Rewriter skipped")
            return query

        logger.info("Rewriter triggered")
        history_text = "".join(f"{m['role'].upper()}: {m['content']}\n" for m in history[-3:])

        prompt = f"""
        Ты — лингвистический модуль. Восстанови обрывочный запрос пользователя, используя историю.

        ПРАВИЛА:
        1. Если запрос содержит местоимения или начинается с "А ..." — замени местоимения объектами из истории.
        2. Если запрос полноценный и содержит новый объект — верни его как есть.

        ПРИМЕРЫ:
        История: USER: Расскажи про омуля. ASSISTANT: Омуль - это рыба...
        Запрос: А где он обитает? -> Где обитает омуль?

        История: USER: Как выглядит кедр? ASSISTANT: Вот фото...
        Запрос: А осенью? -> Как выглядит кедр осенью?

        ИСТОРИЯ:
        {history_text}
        ЗАПРОС: {query}
        ПЕРЕПИСАННЫЙ ЗАПРОС (только текст):"""
        try:
            response = await self.llm.ainvoke(prompt)
            rewritten = response.content.strip().strip('"')
            logger.info(f"Rewriter result: '{rewritten}'")
            return rewritten
        except Exception as e:
            logger.error(f"Rewriter LLM error: {e}")
            return query
