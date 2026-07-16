import logging
import os
from logging.handlers import RotatingFileHandler


def setup_logging():
    """
    Настройка глобального логирования для проекта.
    """
    log_dir = "logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    # формат лога: Время - Имя - Уровень - Сообщение
    log_format = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'
    )

    # 1. Логирование в консоль
    #console_handler = logging.StreamHandler()
    #console_handler.setFormatter(log_format)
    #console_handler.setLevel(logging.INFO)

    # 2. Логирование в файл (с ротацией: макс 10МБ, храним 5 последних файлов)
    file_handler = RotatingFileHandler(
        os.path.join(log_dir, "server.log"),
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setFormatter(log_format)
    file_handler.setLevel(logging.DEBUG)

    # Настройка корневого логгера
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    #root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)

    # Уменьшение детальность логов от сторонних библиотек
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("transformers").setLevel(logging.ERROR)

    logging.info("Система логирования инициализирована.")