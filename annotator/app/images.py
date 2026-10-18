"""Получение картинки: по http(s)-ссылке, относительному пути или из загруженных байтов."""
import io
from urllib.parse import urljoin, urlparse

import httpx
from PIL import Image, ImageOps

MAX_PIXELS = 60_000_000  # защита от «бомб» распаковки
Image.MAX_IMAGE_PIXELS = MAX_PIXELS


class ImageError(ValueError):
    pass


def resolve_url(raw: str, base_url: str, rewrite=()) -> str:
    raw = (raw or "").strip()
    for src, dst in rewrite:
        if src and raw.startswith(src):
            raw = dst + raw[len(src):]
            break
    if not raw:
        raise ImageError("пустой image_url")
    if raw.startswith("/"):
        if not base_url:
            raise ImageError("относительный путь, но IMAGE_BASE_URL не задан")
        raw = urljoin(base_url.rstrip("/") + "/", raw.lstrip("/"))
    scheme = urlparse(raw).scheme
    if scheme not in ("http", "https"):
        raise ImageError(f"поддерживаются только http/https, получено: {scheme or 'нет схемы'}")
    return raw


def download(url: str, max_bytes: int, timeout: float) -> bytes:
    with httpx.Client(timeout=timeout, follow_redirects=True,
                      headers={"User-Agent": "EcoBaikalAnnotator/1.0 (research)"}) as client:
        with client.stream("GET", url) as resp:
            if resp.status_code != 200:
                raise ImageError(f"не удалось скачать изображение: HTTP {resp.status_code}")
            chunks, size = [], 0
            for chunk in resp.iter_bytes():
                size += len(chunk)
                if size > max_bytes:
                    raise ImageError(f"изображение больше {max_bytes // (1024 * 1024)} МБ")
                chunks.append(chunk)
    return b"".join(chunks)


def open_image(data: bytes) -> Image.Image:
    try:
        img = Image.open(io.BytesIO(data))
        img = ImageOps.exif_transpose(img)  # фото с телефона бывают повёрнуты через EXIF
        return img.convert("RGB")
    except Exception as exc:  # noqa: BLE001
        raise ImageError(f"файл не является изображением: {exc}") from exc
