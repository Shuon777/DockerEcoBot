import logging
from maxapi import Dispatcher, Bot
from maxapi.types import MessageCallback

from infrastructure.max_bot.context import ctx
from adapters.max.presenter import render_pipeline_result
from utils.stand_manager import end_stand_session

logger = logging.getLogger("MaxCallbackHandler")

# payload-префикс → шаблон запроса для пайплайна
_PAYLOAD_QUERIES: dict[str, str] = {
    "desc":  "Расскажи о {}",
    "photo": "Покажи фото {}",
}


def register_callback_handlers(dp: Dispatcher, bot: Bot) -> None:

    @dp.message_callback()
    async def handle_callback(event: MessageCallback) -> None:
        payload: str = event.callback.payload or ""
        chat_id, _ = event.get_ids()
        logger.info(f"[{chat_id}] Callback: '{payload}'")

        try:
            await event.ack()
        except Exception:
            pass

        if payload == "stand_detach":
            await end_stand_session(str(chat_id), ctx.session, ctx.redis_client)
            await bot.send_message(
                chat_id=chat_id,
                text="Вы отключились от стенда.",
            )
            return

        prefix, _, name = payload.partition(":")
        query_template = _PAYLOAD_QUERIES.get(prefix)
        if not query_template or not name:
            logger.warning(f"Unknown callback payload: '{payload}'")
            return

        query = query_template.format(name)

        try:
            await bot.send_action(chat_id=chat_id, action="typing_on")
        except Exception:
            pass

        try:
            slots = await ctx.classifier.classify(query)
            result = await ctx.executor.execute(query, slots, user_id=str(chat_id))
            await render_pipeline_result(bot, chat_id, result, ctx.session)
        except Exception as e:
            logger.error(f"Callback pipeline error [{chat_id}]: {e}", exc_info=True)
            await bot.send_message(
                chat_id=chat_id,
                text="Произошла ошибка. Попробуйте ещё раз.",
            )
