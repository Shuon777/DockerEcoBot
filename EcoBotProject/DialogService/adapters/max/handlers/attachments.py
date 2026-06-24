import io
import logging
import aiohttp
from PIL import Image as PILImage
from maxapi import Dispatcher, Bot, F
from maxapi.enums.attachment import AttachmentType
from maxapi.types import MessageCreated

from config import PLANTNET_API_KEY
from infrastructure.max_bot.context import ctx
from application.naturalist.plant_identifier import identify_plant, format_plant_info
from utils.bot_messages import (
    PLANT_UNAVAILABLE, PLANT_NO_FILE, PLANT_IMAGE_ONLY, PLANT_IDENTIFYING,
    PLANT_IMAGE_LOAD_ERROR, PLANT_IMAGE_DOWNLOAD_ERROR, PLANT_IMAGE_FORMAT_ERROR,
    PLANT_NOT_FOUND,
)

logger = logging.getLogger(__name__)


def register_attachment_handlers(dp: Dispatcher, bot: Bot) -> None:

    @dp.message_created(F.message.body.attachments)
    async def handle_attachments(event: MessageCreated) -> None:
        try:
            try:
                chat_id: int = event.message.recipient.chat_id
            except AttributeError:
                chat_id, _ = event.get_ids()

            if not PLANTNET_API_KEY:
                await bot.send_message(chat_id=chat_id, text=PLANT_UNAVAILABLE)
                return

            attachments = event.message.body.attachments if event.message.body else []
            if not attachments:
                await bot.send_message(chat_id=chat_id, text=PLANT_NO_FILE)
                return

            attachment = attachments[0]

            if attachment.type != AttachmentType.IMAGE or not attachment.payload or not getattr(attachment.payload, "url", None):
                await bot.send_message(chat_id=chat_id, text=PLANT_IMAGE_ONLY)
                return

            image_url = attachment.payload.url
            logger.info(f"[{chat_id}] Plant identification request, image URL: {image_url}")

            await bot.send_message(chat_id=chat_id, text=PLANT_IDENTIFYING)

            try:
                async with ctx.session.get(image_url) as resp:
                    if resp.status == 200:
                        image_bytes = await resp.read()
                        content_type = resp.headers.get("content-type", "image/jpeg")
                    else:
                        await bot.send_message(chat_id=chat_id, text=PLANT_IMAGE_LOAD_ERROR)
                        return
            except aiohttp.ClientError as e:
                logger.error(f"[{chat_id}] Failed to download image: {e}")
                await bot.send_message(chat_id=chat_id, text=PLANT_IMAGE_DOWNLOAD_ERROR)
                return

            if content_type not in ("image/jpeg", "image/png"):
                try:
                    buf = io.BytesIO()
                    PILImage.open(io.BytesIO(image_bytes)).convert("RGB").save(buf, format="JPEG")
                    image_bytes = buf.getvalue()
                except Exception as e:
                    logger.error(f"[{chat_id}] Image conversion failed: {e}")
                    await bot.send_message(chat_id=chat_id, text=PLANT_IMAGE_FORMAT_ERROR)
                    return

            plant_data = await identify_plant(image_bytes, PLANTNET_API_KEY, ctx.session)

            if plant_data:
                result_text = format_plant_info(plant_data)
                await bot.send_message(chat_id=chat_id, text=result_text)
            else:
                await bot.send_message(chat_id=chat_id, text=PLANT_NOT_FOUND)

        except Exception as e:
            logger.error(f"Attachment handler error: {e}", exc_info=True)
