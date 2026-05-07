import os
import logging
import asyncio
import aiohttp
from aiogram import executor

from utils.logging_config import setup_logging
from infrastructure.bot.setup import dp, bot
from infrastructure.storage.redis_storage import RedisContextManager
from utils.heartbeat import BotHeartbeat
from application.dialogue.orchestrator import DialogueSystem
from adapters.telegram.handlers.commands import register_command_handlers
from adapters.telegram.handlers.callbacks import register_inline_handlers
from adapters.telegram.handlers.messages import register_message_handlers

setup_logging()
logger = logging.getLogger("BotApp")


async def on_startup(dispatcher):
    logger.info("Запуск Эко-бота...")

    session = aiohttp.ClientSession()
    dispatcher["aiohttp_session"] = session

    redis_host = os.getenv("REDIS_HOST", "redis")
    context_manager = RedisContextManager(host=redis_host, port=6379, db=0)
    if not await context_manager.check_connection():
        raise ConnectionError("Не удалось подключиться к Redis")
    dispatcher["context_manager"] = context_manager

    llm_provider = os.getenv("LLM_PROVIDER", "qwen")
    ds = DialogueSystem(provider=llm_provider, session=session, context_manager=context_manager)
    dispatcher["ds"] = ds

    register_command_handlers(dispatcher)
    register_inline_handlers(dispatcher)
    register_message_handlers(dispatcher)

    hb = BotHeartbeat(host=redis_host, port=6379, db=2)

    async def heartbeat_loop():
        while True:
            try:
                await hb.ping()
            except Exception as e:
                logger.error(f"Heartbeat error: {e}")
            await asyncio.sleep(60)

    asyncio.create_task(heartbeat_loop())
    logger.info(f"Система готова. Провайдер: {llm_provider}")


async def on_shutdown(dispatcher):
    logger.info("Остановка бота...")
    await dispatcher["aiohttp_session"].close()


if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup, on_shutdown=on_shutdown)
