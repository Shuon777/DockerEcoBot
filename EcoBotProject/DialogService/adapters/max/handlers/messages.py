import logging
from maxapi import Dispatcher, Bot, F
from maxapi.types import MessageCreated

from infrastructure.max_bot.context import ctx
from adapters.max.presenter import render_pipeline_result

logger = logging.getLogger("MaxMessageHandler")


def register_message_handlers(dp: Dispatcher, bot: Bot) -> None:

    @dp.message_created(F.message.body.text)
    async def handle_text(event: MessageCreated) -> None:
        try:
            text: str = event.message.body.text
            if not text or text.startswith("/"):
                return

            # chat_id: пробуем recipient, fallback — get_ids()
            try:
                chat_id: int = event.message.recipient.chat_id
            except AttributeError:
                chat_id, _ = event.get_ids()

            logger.info(f"[{chat_id}] Message: '{text}'")

            try:
                await bot.send_action(chat_id=chat_id, action="typing_on")
            except Exception:
                pass

            result = await ctx.orchestrator.process(text, user_id=str(chat_id))
            await render_pipeline_result(bot, chat_id, result, ctx.session)

        except Exception as e:
            logger.error(f"Message handler error: {e}", exc_info=True)
            try:
                await bot.send_message(
                    chat_id=chat_id,
                    text="Произошла ошибка при обработке запроса. Попробуйте ещё раз.",
                )
            except Exception:
                pass
