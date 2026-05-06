import logging
from aiogram import Dispatcher, types

from domain.entities import UserRequest
from application.dialogue.orchestrator import DialogueSystem
from infrastructure.storage.redis_storage import RedisContextManager
from infrastructure.bot.setup import bot
from utils.settings_manager import get_user_settings
from adapters.telegram.presenter import render_responses

logger = logging.getLogger("MessageHandler")


def register_message_handlers(dp: Dispatcher):
    @dp.message_handler(content_types=types.ContentTypes.TEXT)
    async def handle_main_logic(message: types.Message):
        if message.text.startswith("/"):
            return

        user_id = str(message.from_user.id)
        user_settings = get_user_settings(user_id)

        ds: DialogueSystem = dp["ds"]
        context_manager: RedisContextManager = dp["context_manager"]

        history_data = await context_manager.get_context(user_id)
        history = history_data.get("history", [])

        formatted_context = []
        for entry in history[-5:]:
            formatted_context.append({"role": "user", "content": entry.get("query", "")})
            resps = entry.get("response", [])
            if resps:
                formatted_context.append({"role": "assistant", "content": resps[0].get("content", "")})

        request = UserRequest(
            user_id=user_id,
            query=message.text,
            context=formatted_context,
            settings=user_settings,
        )

        await bot.send_chat_action(user_id, types.ChatActions.TYPING)
        responses = await ds.process_request(request)

        await render_responses(message, responses)

        # Сохраняем ответ в историю (исправление: раньше не сохранялось)
        final_text = responses[0].text if responses else ""
        new_entry = {"query": message.text, "response": [{"content": final_text}]}
        updated_history = [new_entry] + history[:10]
        history_data["history"] = updated_history
        await context_manager.set_context(user_id, history_data)
