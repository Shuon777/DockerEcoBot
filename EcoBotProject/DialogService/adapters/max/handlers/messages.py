import logging
import hashlib
import time
import asyncio

from maxapi import Dispatcher, Bot, F
from maxapi.types import MessageCreated

from infrastructure.max_bot.context import ctx
from adapters.max.presenter import render_pipeline_result
from utils.error_logger import log_critical
from utils.bot_messages import ERR_REQUEST

logger = logging.getLogger("MaxMessageHandler")


def register_message_handlers(dp: Dispatcher, bot: Bot) -> None:
    
    @dp.message_created(F.message.body.text)
    async def handle_text(event: MessageCreated) -> None:
        try:
            text: str = event.message.body.text
            if not text or text.startswith("/"):
                return

            try:
                chat_id: int = event.message.recipient.chat_id
            except AttributeError:
                chat_id, _ = event.get_ids()
                
            logger.info(f"[{chat_id}] Message: '{text}'")

            try:
                await bot.send_action(chat_id=chat_id, action="typing_on")
            except Exception:
                pass

            # сохраняем переменные для фоновой задачи, чтобы избежать проблем с областями видимости
            current_text = text
            current_chat_id = chat_id

            async def process_in_background():
                try:
                    promo_val = await ctx.redis_client.get("settings:promo_enabled")
                    promo_enabled = promo_val != "0"
                    result = await ctx.orchestrator.process(
                        current_text, user_id=str(current_chat_id), promo_enabled=promo_enabled
                    )
                    await render_pipeline_result(bot, current_chat_id, result, ctx.session)
                except Exception as e:
                    logger.error(f"Background processing error [{current_chat_id}]: {e}", exc_info=True)
                    try:
                        await bot.send_message(chat_id=current_chat_id, text="Произошла ошибка. Попробуйте ещё раз.")
                    except Exception:
                        pass

            # запускаем параллельную задачу
            asyncio.create_task(process_in_background())

            # сразу же отправляем 200
            return

        except Exception as e:
            logger.error(f"Message handler error: {e}", exc_info=True)
            await log_critical(ctx.session, text, str(chat_id), e)
            try:
                await bot.send_message(
                    chat_id=chat_id,
                    text=ERR_REQUEST,
                )
            except Exception:
                pass
