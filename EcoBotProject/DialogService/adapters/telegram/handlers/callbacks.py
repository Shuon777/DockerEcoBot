import logging
from aiogram import types, Dispatcher
from uuid import uuid4

from utils.inline_search import find_suggestions

logger = logging.getLogger(__name__)


async def process_inline_query(inline_query: types.InlineQuery):
    query_text = inline_query.query
    found_items = find_suggestions(query_text)

    results = []
    for item_name in found_items:
        results.append(types.InlineQueryResultArticle(
            id=str(uuid4()),
            title=f"📖 {item_name}",
            description="Узнать описание и факты",
            input_message_content=types.InputTextMessageContent(
                message_text=f"Расскажи про {item_name}"
            ),
        ))
        results.append(types.InlineQueryResultArticle(
            id=str(uuid4()),
            title=f"🖼️ {item_name}",
            description="Посмотреть, как выглядит",
            input_message_content=types.InputTextMessageContent(
                message_text=f"Как выглядит {item_name}"
            ),
        ))
        results.append(types.InlineQueryResultArticle(
            id=str(uuid4()),
            title=f"🗺️ {item_name}",
            description="Найти ареал обитания на карте",
            input_message_content=types.InputTextMessageContent(
                message_text=f"Где растет {item_name}"
            ),
        ))

    await inline_query.bot.answer_inline_query(inline_query.id, results=results, cache_time=1)


def register_inline_handlers(dp: Dispatcher):
    dp.register_inline_handler(process_inline_query)
