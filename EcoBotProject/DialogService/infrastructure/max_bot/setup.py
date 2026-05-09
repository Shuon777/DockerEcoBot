import os
from maxapi import Bot, Dispatcher

if not os.getenv("MAX_BOT_TOKEN"):
    raise RuntimeError(
        "MAX_BOT_TOKEN environment variable is required to run the MAX bot"
    )

bot = Bot()  # maxapi читает MAX_BOT_TOKEN из окружения
dp = Dispatcher()
