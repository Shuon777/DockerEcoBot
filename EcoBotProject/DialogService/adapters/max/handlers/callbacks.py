import logging
from maxapi import Dispatcher, Bot
from maxapi.types import MessageCallback

from infrastructure.max_bot.context import ctx
from adapters.max.presenter import render_pipeline_result
from utils.stand_manager import end_stand_session
from utils.error_logger import log_critical
from utils.bot_messages import STAND_DISCONNECTED, ERR_SEARCH_OUTDATED, ERR_GENERIC

logger = logging.getLogger("MaxCallbackHandler")

# payload-префикс → шаблон запроса, отправляемого в оркестратор
_PAYLOAD_QUERIES: dict[str, str] = {
    "desc":  "Расскажи о {}",
    "photo": "Покажи фото {}",
    "map":   "Где обитает {}",
    "text":  "Расскажи о {}",
}


def register_callback_handlers(dp: Dispatcher, bot: Bot) -> None:

    @dp.message_callback()
    async def handle_callback(event: MessageCallback) -> None:
        payload: str = event.callback.payload or ""
        chat_id, _ = event.get_ids()
        user_id = str(chat_id)
        logger.info(f"[{chat_id}] Callback: '{payload}'")

        try:
            await event.ack()
        except Exception:
            pass

        # ── Стенд ────────────────────────────────────────────────────────────
        if payload == "stand_detach":
            await end_stand_session(user_id, ctx.session, ctx.redis_client)
            await bot.send_message(chat_id=chat_id, text=STAND_DISCONNECTED)
            return

        # ── Упрощение поиска (Сценарий 4) ────────────────────────────────────
        if payload.startswith("simplify:"):
            idx_str = payload.removeprefix("simplify:")
            try:
                idx = int(idx_str)
            except ValueError:
                return
            item = await ctx.orchestrator.load_simplification(user_id, idx)
            if not item:
                await bot.send_message(chat_id=chat_id, text=ERR_SEARCH_OUTDATED)
                return
            try:
                await bot.send_action(chat_id=chat_id, action="typing_on")
            except Exception:
                pass
            try:
                result = await ctx.orchestrator.process_with_slots(
                    item["query"], item["slots"], user_id=user_id
                )
                await render_pipeline_result(bot, chat_id, result, ctx.session)
            except Exception as e:
                logger.error(f"Simplify callback error [{chat_id}]: {e}", exc_info=True)
                await log_critical(ctx.session, payload, user_id, e)
                await bot.send_message(chat_id=chat_id, text=ERR_GENERIC)
            return

        # ── Стандартные проактивные кнопки ────────────────────────────────────
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
            promo_val = await ctx.redis_client.get("settings:promo_enabled")
            result = await ctx.orchestrator.process(query, user_id=user_id, promo_enabled=promo_val != "0")
            await render_pipeline_result(bot, chat_id, result, ctx.session)
        except Exception as e:
            logger.error(f"Callback pipeline error [{chat_id}]: {e}", exc_info=True)
            await log_critical(ctx.session, query, user_id, e)
            await bot.send_message(chat_id=chat_id, text="Произошла ошибка. Попробуйте ещё раз.")
