import logging
from maxapi import Dispatcher, Bot
from maxapi.types import BotStarted, MessageCreated, Command
from maxapi.utils.inline_keyboard import InlineKeyboardBuilder
from maxapi.types.attachments.buttons import CallbackButton

from infrastructure.max_bot.context import ctx
from utils.stand_manager import start_stand_session, end_stand_session, is_stand_session_active

STAND_SESSION_TIMEOUT_MIN = 5

logger = logging.getLogger(__name__)

_START_TEXT = (
    "Здравствуйте! Я ваш эко-ассистент по Байкалу 🌿\n\n"
    "Задавайте вопросы о флоре, фауне и географии Байкальского региона.\n\n"
    "Примеры:\n"
    "• «Расскажи про байкальскую нерпу»\n"
    "• «Покажи фото пихты сибирской»\n"
    "• «Где обитает байкальский омуль»\n"
    "• «Животные на Ольхоне»\n\n"
    "Напишите /help чтобы узнать больше."
)

_HELP_TEXT = (
    "Я эко-ассистент по Байкалу. Вот что я умею:\n\n"
    "📖 Описания: «Расскажи про нерпу»\n"
    "🖼 Изображения: «Покажи пихту сибирскую»\n"
    "🗺 Карта: «Где растёт байкальский омуль»\n"
    "🐾 Списки видов: «Животные на Ольхоне»\n"
    "🏛 Объекты: «Музеи в Иркутске»\n"
    "📋 Услуги: «Режим работы Байкальского музея»"
)


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
                builder.row(CallbackButton(text="Отвязаться от стенда", payload="stand_detach"))
                await bot.send_message(
                    chat_id=chat_id,
                    text=(
                        "Вы успешно подключились к интерактивному стенду!\n\n"
                        "Теперь объекты, которые я нахожу по вашим запросам, "
                        "будут автоматически отображаться на стенде.\n\n"
                        f"Сессия активна {STAND_SESSION_TIMEOUT_MIN} минут. "
                        "Вы можете завершить её досрочно кнопкой ниже."
                    ),
                    attachments=[builder.as_markup()],
                )
            else:
                await bot.send_message(
                    chat_id=chat_id,
                    text=(
                        "Стенд сейчас занят другим пользователем.\n"
                        "Пожалуйста, попробуйте позже."
                    ),
                )
            return

        await bot.send_message(chat_id=chat_id, text=_START_TEXT)

    @dp.message_created(Command("start"))
    async def handle_start(event: MessageCreated) -> None:
        chat_id = event.message.recipient.chat_id
        await bot.send_message(chat_id=chat_id, text=_START_TEXT)

    @dp.message_created(Command("help"))
    async def handle_help(event: MessageCreated) -> None:
        chat_id = event.message.recipient.chat_id
        await bot.send_message(chat_id=chat_id, text=_HELP_TEXT)
