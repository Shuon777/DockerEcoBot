import os
import asyncio
import logging
import aiohttp
import redis.asyncio as redis

from utils.logging_config import setup_logging
from infrastructure.max_bot.setup import bot, dp
from infrastructure.max_bot.context import ctx
from application.search.slot_classifier import SlotClassifier
from application.search.slot_search_executor import SlotSearchExecutor
from application.search.context_manager import ConversationHistory
from application.search.dialogue_orchestrator import DialogueOrchestrator
from adapters.max.handlers.commands import register_command_handlers
from adapters.max.handlers.messages import register_message_handlers
from adapters.max.handlers.callbacks import register_callback_handlers
from adapters.max.handlers.attachments import register_attachment_handlers

setup_logging()
logger = logging.getLogger("MaxBotApp")


async def main() -> None:
    logger.info("Запуск MAX эко-бота...")

    llm_provider = os.getenv("LLM_PROVIDER", "qwen")
    redis_host = os.getenv("REDIS_HOST", "localhost")
    redis_port = int(os.getenv("REDIS_PORT", "6379"))

    ctx.session = aiohttp.ClientSession()
    ctx.redis_client = redis.Redis(host=redis_host, port=redis_port, db=0, decode_responses=True)
    ctx.classifier = SlotClassifier(provider=llm_provider)
    ctx.executor = SlotSearchExecutor(session=ctx.session)
    ctx.history = ConversationHistory(redis_client=ctx.redis_client)
    ctx.orchestrator = DialogueOrchestrator(
        classifier=ctx.classifier,
        executor=ctx.executor,
        history=ctx.history,
        redis_client=ctx.redis_client,
    )

    register_command_handlers(dp, bot)
    register_message_handlers(dp, bot)
    register_callback_handlers(dp, bot)
    register_attachment_handlers(dp, bot)

    use_webhook = os.getenv("MAX_USE_WEBHOOK", "").lower() == "true"

    try:
        if use_webhook:
            host = os.getenv("MAX_WEBHOOK_HOST", "0.0.0.0")
            port = int(os.getenv("MAX_WEBHOOK_PORT", "8080"))
            logger.info(f"Режим webhook: {host}:{port}")
            path = os.getenv("MAX_WEBHOOK_PATH", "/")
            webhook_url = os.getenv("MAX_WEBHOOK_URL", "")
            webhook_secret = os.getenv("MAX_WEBHOOK_SECRET")
            if webhook_url:
                await bot.subscribe_webhook(url=webhook_url, secret=webhook_secret)
            await dp.handle_webhook(bot=bot, host=host, port=port, path=path, secret=webhook_secret)
        else:
            logger.info("Режим polling")
            subscriptions = await bot.get_subscriptions()
            for sub in subscriptions.subscriptions:
                await bot.unsubscribe_webhook(url=sub.url)
            await dp.start_polling(bot)
    finally:
        await ctx.session.close()
        await ctx.redis_client.aclose()
        logger.info("MAX-бот остановлен")


if __name__ == "__main__":
    asyncio.run(main())
