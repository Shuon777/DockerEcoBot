import logging
import aiohttp
from maxapi import Bot
from maxapi.utils.inline_keyboard import InlineKeyboardBuilder
from maxapi.types.attachments.buttons import LinkButton, CallbackButton
from maxapi.types import InputMediaBuffer

logger = logging.getLogger(__name__)

_MAX_IMAGES = 3


async def _fetch_image(session: aiohttp.ClientSession, url: str) -> bytes | None:
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
            if r.status == 200:
                return await r.read()
    except Exception as e:
        logger.warning(f"Image download failed ({url}): {e}")
    return None


async def render_pipeline_result(
    bot: Bot,
    chat_id: int,
    pipeline_result: dict,
    session: aiohttp.ClientSession,
) -> None:
    result = pipeline_result.get("result", {})
    answer: str = result.get("answer", "")
    images: list = result.get("images") or []
    map_data: dict = result.get("map") or {}
    total = result.get("total_found")
    place = result.get("place")

    proactive: dict = pipeline_result.get("proactive") or {}
    modality_ambiguous: bool = pipeline_result.get("modality_ambiguous", False)
    simplifications: list = pipeline_result.get("simplifications") or []
    slots: dict = pipeline_result.get("slots") or {}

    for url in images[:_MAX_IMAGES]:
        data = await _fetch_image(session, url)
        if data:
            try:
                await bot.send_message(
                    chat_id=chat_id,
                    attachments=[InputMediaBuffer(buffer=data, filename="photo.jpg")],
                )
            except Exception as e:
                logger.error(f"Image send failed: {e}")

    # ── Статическая карта как изображение ────────────────────────────────────
    static_url = map_data.get("static") if isinstance(map_data, dict) else None
    if static_url:
        data = await _fetch_image(session, static_url)
        if data:
            try:
                await bot.send_message(
                    chat_id=chat_id,
                    attachments=[InputMediaBuffer(buffer=data, filename="map.jpg")],
                )
            except Exception as e:
                logger.error(f"Static map send failed: {e}")

    builder = InlineKeyboardBuilder()
    has_buttons = False

    # ── Интерактивная карта как кнопка ────────────────────────────────────────
    interactive_url = map_data.get("interactive") if isinstance(map_data, dict) else None
    if interactive_url:
        builder.row(LinkButton(text="Открыть интерактивную карту", url=interactive_url))
        has_buttons = True

    # ── Проактивные предложения ───────────────────────────────────────────────
    if proactive.get("photo"):
        builder.row(CallbackButton(text="🖼 Фото", payload=f"photo:{proactive['photo'][:50]}"))
        has_buttons = True
    if proactive.get("map"):
        builder.row(CallbackButton(text="🗺 Карта ареала", payload=f"map:{proactive['map'][:50]}"))
        has_buttons = True
    if proactive.get("text"):
        builder.row(CallbackButton(text="📖 Подробнее", payload=f"text:{proactive['text'][:50]}"))
        has_buttons = True

    # ── Неопределённая модальность (Сценарий 2) ───────────────────────────────
    if modality_ambiguous and slots.get("synonym") and not proactive.get("map") and not map_data:
        builder.row(CallbackButton(
            text="🗺 Показать на карте",
            payload=f"map:{slots['synonym'][:50]}",
        ))
        has_buttons = True

    # ── Текст ответа ──────────────────────────────────────────────────────────
    text = answer or "По вашему запросу ничего не найдено."
    if total is not None and place:
        text += f"\n\nНайдено объектов: {total} (место: {place})"

    # ── Упрощения поиска (Сценарий 4) ────────────────────────────────────────
    if simplifications:
        text += "\n\nМожно расширить поиск:"
        for i, s in enumerate(simplifications):
            builder.row(CallbackButton(text=s["label"], payload=f"simplify:{i}"))
            has_buttons = True

    await bot.send_message(
        chat_id=chat_id,
        text=text,
        attachments=[builder.as_markup()] if has_buttons else None,
    )

    # ── Промо: связанные услуги/экспозиции ───────────────────────────────────
    for item in (result.get("promo") or []):
        promo_text = item.get("promo_text") or item.get("name", "")
        if promo_text:
            try:
                await bot.send_message(chat_id=chat_id, text=f"💡 {promo_text}")
            except Exception as e:
                logger.error(f"Promo send failed: {e}")
