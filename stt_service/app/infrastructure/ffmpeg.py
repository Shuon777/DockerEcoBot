from __future__ import annotations

import asyncio
import logging
import wave
from pathlib import Path

from app.domain.exceptions import AudioValidationError, UnsupportedAudioFormatError
from app.domain.models import NormalizedAudio
from app.domain.ports import IAudioNormalizer

logger = logging.getLogger(__name__)

class FfmpegAudioNormalizer(IAudioNormalizer):
    def __init__(self, *, sample_rate: int = 16_000, timeout_seconds: float = 120.0) -> None:
        self._sample_rate = sample_rate
        self._timeout = timeout_seconds

    async def normalize(self, source_path: Path, destination_path: Path) -> NormalizedAudio:
        # Конвертация файла в wav
        command = (
            "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(source_path),
            "-ac", "1",
            "-ar", str(self._sample_rate),
            "-c:a", "pcm_s16le",
            "-f", "wav",
            str(destination_path),
        )
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            _, stderr = await asyncio.wait_for(process.communicate(), timeout=self._timeout)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            raise AudioValidationError(f"ffmpeg не уложился в {self._timeout:.0f} с") from None

        if process.returncode != 0 or not destination_path.exists():
            reason = (stderr or b"").decode("utf-8", "replace").strip()[:300]
            logger.warning("ffmpeg не смог декодировать файл: %s", reason)
            raise UnsupportedAudioFormatError(
                "Не удалось прочитать аудиофайл",
                details={"ffmpeg": reason},
            )
        return NormalizedAudio(
            path=destination_path,
            duration_seconds=_wav_duration(destination_path),
        )
def _wav_duration(path: Path) -> float | None:
    # Длительность WAV
    try:
        with wave.open(str(path), "rb") as wav_file:
            frames = wav_file.getnframes()
            rate = wav_file.getframerate()
            return round(frames / rate, 3) if rate else None
    except (wave.Error, OSError):
        return None