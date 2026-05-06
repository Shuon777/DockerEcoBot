import logging
from typing import List
from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from domain.entities import SystemResponse
from utils.bot_utils import send_long_message, convert_llm_markdown_to_html

logger = logging.getLogger(__name__)


def build_keyboard(buttons_data: list) -> InlineKeyboardMarkup | None:
    if not buttons_data:
        return None
    kb = InlineKeyboardMarkup()
    for row in buttons_data:
        kb.row(*[
            InlineKeyboardButton(text=b["text"], callback_data=b.get("callback_data"), url=b.get("url"))
            for b in row
        ])
    return kb


async def render_responses(message: types.Message, responses: List[SystemResponse]):
    for response in responses:
        keyboard = build_keyboard(response.buttons)

        if response.response_type == "debug":
            debug_text = f"<b>Debug</b>\n<code>{response.text}</code>"
            await message.answer(debug_text, parse_mode="HTML")

        elif response.response_type == "image" and response.media_url:
            await message.answer_photo(
                photo=response.media_url,
                caption=response.text or None,
                reply_markup=keyboard,
            )

        elif response.response_type in ["map", "clarification_map"] and response.media_url:
            caption = convert_llm_markdown_to_html(response.text) if response.text else None
            await message.answer_photo(
                photo=response.media_url,
                caption=caption,
                reply_markup=keyboard,
                parse_mode="HTML",
            )

        else:
            html_text = convert_llm_markdown_to_html(response.text)
            await send_long_message(message, html_text, parse_mode="HTML", reply_markup=keyboard)
