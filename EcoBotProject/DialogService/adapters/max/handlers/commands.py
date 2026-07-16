import logging
from maxapi import Dispatcher, Bot
from maxapi.types import BotStarted, MessageCreated, Command
from maxapi.utils.inline_keyboard import InlineKeyboardBuilder
from maxapi.types.attachments.buttons import CallbackButton

from infrastructure.max_bot.context import ctx
from utils.stand_manager import start_stand_session, end_stand_session, is_stand_session_active
from utils.bot_messages import (
    START_TEXT, HELP_TEXT,
    STAND_BUTTON_DETACH, STAND_CONNECTED, STAND_BUSY,
)

STAND_SESSION_TIMEOUT_MIN = 5

logger = logging.getLogger(__name__)


def register_command_handlers(dp: Dispatcher, bot: Bot) -> None:

    @dp.bot_started()
    async def handle_bot_started(event: BotStarted) -> None:
        chat_id = event.chat_id
        payload = event.payload or ""
        logger.info(f"[{chat_id}] bot_started, payload='{payload}'")

        if payload.startswith("stand_"):
            user_id = str(chat_id)
            started = await start_stand_session(user_id, bot, ctx.session, ctx.redis_client)
            if started:
                builder = InlineKeyboardBuilder()
                builder.row(CallbackButton(text=STAND_BUTTON_DETACH, payload="stand_detach"))
                await bot.send_message(
                    chat_id=chat_id,
                    text=STAND_CONNECTED.format(timeout_min=STAND_SESSION_TIMEOUT_MIN),
                    attachments=[builder.as_markup()],
                )
            else:
                await bot.send_message(chat_id=chat_id, text=STAND_BUSY)
            return

        await bot.send_message(chat_id=chat_id, text=START_TEXT)

    @dp.message_created(Command("start"))
    async def handle_start(event: MessageCreated) -> None:
        chat_id = event.message.recipient.chat_id
        await bot.send_message(chat_id=chat_id, text=START_TEXT)

    @dp.message_created(Command("help"))
    async def handle_help(event: MessageCreated) -> None:
        chat_id = event.message.recipient.chat_id
        await bot.send_message(chat_id=chat_id, text=HELP_TEXT)
