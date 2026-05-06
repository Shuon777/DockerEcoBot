import logging

from aiogram import Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from utils.settings_manager import get_user_settings, update_user_settings
from utils.stand_manager import start_stand_session, end_stand_session, is_stand_session_active
from config import STAND_SESSION_TIMEOUT

logger = logging.getLogger(__name__)

main_keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
main_keyboard.add(types.KeyboardButton("⚙ Настройки"))


def create_settings_keyboard(user_id: str) -> InlineKeyboardMarkup:
    user_settings = get_user_settings(user_id)
    debug_enabled = user_settings.get("debug_mode", False)
    fallback_enabled = user_settings.get("gigachat_fallback", False)
    stoplist_enabled = user_settings.get("stoplist_enabled", True)

    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton(
            f"Дополнять GigaChat: {'✅ Вкл' if fallback_enabled else '❌ Выкл'}",
            callback_data="toggle_fallback",
        )
    )
    keyboard.add(
        InlineKeyboardButton(
            f"Стоп-лист: {'✅ Вкл' if stoplist_enabled else '❌ Выкл'}",
            callback_data="toggle_stoplist",
        )
    )
    keyboard.add(
        InlineKeyboardButton(
            f"Debug Mode: {'✅ Вкл' if debug_enabled else '❌ Выкл'}",
            callback_data="toggle_debug",
        )
    )
    if is_stand_session_active(user_id):
        keyboard.add(InlineKeyboardButton("❌ Отвязаться от стенда", callback_data="stand_detach"))
    return keyboard


def register_command_handlers(dp: Dispatcher):
    @dp.message_handler(commands=["start"])
    async def handle_start(message: types.Message):
        user_id = str(message.from_user.id)
        args = message.get_args()
        logger.info(f"[{user_id}] /start args='{args}'")

        if args and args.startswith("stand_"):
            session = Dispatcher.get_current().get("aiohttp_session")
            started = await start_stand_session(user_id, message.bot, session)
            if started:
                minutes = STAND_SESSION_TIMEOUT // 60
                text = (
                    f"✅ *Вы подключились к интерактивному стенду!*\n\n"
                    f"Сессия продлится *{minutes} минут*.\n\n"
                    "Примеры запросов:\n"
                    " • `Расскажи о музеях на Ольхоне`\n"
                    " • `Покажи на карте музеи Иркутска`\n"
                )
                kb = InlineKeyboardMarkup().add(
                    InlineKeyboardButton("❌ Отвязаться от стенда", callback_data="stand_detach")
                )
                await message.answer(text, reply_markup=kb, parse_mode="Markdown")
            else:
                await message.answer(
                    "❗️Стенд занят. Попробуйте отсканировать QR-код через несколько минут."
                )
        else:
            await message.answer(
                "Здравствуйте! Я ваш эко-ассистент по Байкалу 🌿\n\n"
                "Для поиска с подсказками используйте команду /search.",
                reply_markup=main_keyboard,
                parse_mode="Markdown",
            )

    @dp.message_handler(commands=["search"])
    async def handle_search(message: types.Message):
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton(
            text="Начать поиск с автодополнением",
            switch_inline_query_current_chat="",
        ))
        await message.answer("Нажмите кнопку ниже для поиска с подсказками:", reply_markup=kb)

    @dp.message_handler(commands=["help"])
    async def handle_help(message: types.Message):
        await message.answer(
            "Я эко-ассистент по Байкалу. Вот что я умею:\n\n"
            "📖 *Описания:* `Расскажи про нерпу`\n"
            "🖼️ *Изображения:* `пихта сибирская зимой`\n"
            "🗺️ *Карта:* `где растет эдельвейс`\n"
            "🐾 *Списки видов:* `животные на Ольхоне`\n\n"
            "Для удобного поиска используйте /search.",
            parse_mode="Markdown",
        )

    @dp.message_handler(lambda m: m.text == "⚙ Настройки")
    async def handle_settings(message: types.Message):
        user_id = str(message.from_user.id)
        await message.answer("Меню настроек:", reply_markup=create_settings_keyboard(user_id))

    @dp.callback_query_handler(lambda c: c.data == "stand_detach")
    async def handle_stand_detach(cq: types.CallbackQuery):
        user_id = str(cq.from_user.id)
        session = Dispatcher.get_current().get("aiohttp_session")
        await end_stand_session(user_id, session)
        await cq.answer("Сессия со стендом завершена.")
        await cq.message.edit_text("Вы отвязались от стенда. Ответы будут приходить только сюда.")

    @dp.callback_query_handler(lambda c: c.data in ["toggle_fallback", "toggle_stoplist", "toggle_debug"])
    async def process_settings_callback(cq: types.CallbackQuery):
        user_id = str(cq.from_user.id)
        if cq.data == "toggle_fallback":
            val = not get_user_settings(user_id).get("gigachat_fallback", False)
            update_user_settings(user_id, {"gigachat_fallback": val})
            await cq.answer(f"Дополнение GigaChat {'включено' if val else 'выключено'}")
        elif cq.data == "toggle_stoplist":
            val = not get_user_settings(user_id).get("stoplist_enabled", True)
            update_user_settings(user_id, {"stoplist_enabled": val})
            await cq.answer(f"Стоп-лист {'включён' if val else 'выключен'}")
        elif cq.data == "toggle_debug":
            val = not get_user_settings(user_id).get("debug_mode", False)
            update_user_settings(user_id, {"debug_mode": val})
            await cq.answer(f"Debug Mode {'включён' if val else 'выключен'}")
        try:
            await cq.message.edit_reply_markup(create_settings_keyboard(user_id))
        except Exception:
            pass
