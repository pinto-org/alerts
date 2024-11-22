import logging
import logging.handlers
import os
import signal

from constants.config import ONE_HUNDRED_MEGABYTES

from bots import util
from monitors.preview.price import PricePreviewMonitor

if __name__ == "__main__":
    logging.basicConfig(
        format=f"Discord Price Bot : {util.LOGGING_FORMAT_STR_SUFFIX}",
        level=logging.INFO,
        handlers=[
            logging.handlers.RotatingFileHandler(
                "logs/discord_price_bot.log", maxBytes=ONE_HUNDRED_MEGABYTES, backupCount=1
            ),
            logging.StreamHandler(),
        ],
    )
    signal.signal(signal.SIGTERM, util.handle_sigterm)

    util.configure_main_thread_exception_logging()

    token = os.environ["DISCORD_PRICE_BOT_TOKEN"]
    prod = os.environ["IS_PROD"].lower() == "true"

    client = util.DiscordSidebarClient(PricePreviewMonitor)

    try:
        client.run(token)
    except (KeyboardInterrupt, SystemExit):
        pass
    # Note that discord bot cannot send shutting down messages in its channel, due to lib impl.
    client.stop()