from app.infrastructure.ffmpeg import FfmpegAudioNormalizer
from app.infrastructure.whisper import WhisperTranscriber
"""
Реализации  ffmpeg и faster-whisper:
    ffmpeg - превращает звуковой файл любого формата в wav 16 кГц, моно, 16 бит
    fast-whisper - распознает текст по wav
"""
__all__ = ["FfmpegAudioNormalizer", "WhisperTranscriber"] # Для импорта формата *

