import datetime
import logging
import logging.handlers
import os
import signal
import threading
import time

from monitors.integrations import IntegrationsMonitor
import telebot
from telebot import apihelper

from bots import util
from constants.config import *
from constants.channels import *
from constants.addresses import *

from monitors.peg_cross import PegCrossMonitor
from monitors.seasons import SeasonsMonitor
from monitors.well import WellsMonitor
from monitors.beanstalk import BeanstalkMonitor
from monitors.market import MarketMonitor
from tools.msg_aggregator import MsgAggregator
from tools.util import embellish_token_emojis, noop
from tools.webhook_alerts import activate_webhook_on_error_logs

# Telegram rate limit is 1 msg/s per channel.
RATE_LIMIT = 1.5

class TelegramBot(object):
    def __init__(self, token, prod=False, dry_run=None):
        if prod:
            self._main_chat_id = BS_TELE_CHAT_ID_PRODUCTION
            self._seasons_chat_id = BS_TELE_CHAT_ID_SEASONS
            logging.info("Configured as a production instance.")
        else:
            self._main_chat_id = BS_TELE_CHAT_ID_STAGING
            self._seasons_chat_id = BS_TELE_CHAT_ID_STAGING
            logging.info("Configured as a staging instance.")

        activate_webhook_on_error_logs()

        apihelper.SESSION_TIME_TO_LIVE = 5 * 60
        self.tele_bot = telebot.TeleBot(token, parse_mode="Markdown")

        def send_msg_main(msg):
            logging.info(f"Sending message:\n{msg}\n")
            self.tele_bot.send_message(chat_id=self._main_chat_id, text=msg, disable_web_page_preview=True)

        def send_msg_seasons(msg):
            logging.info(f"Sending message:\n{msg}\n")
            self.tele_bot.send_message(chat_id=self._seasons_chat_id, text=msg, disable_web_page_preview=True)

        # Wrap send functions in the aggregator to combine burst messages together
        self.msg_main_agg = MsgAggregator(send_msg_main, RATE_LIMIT)
        self.msg_seasons_agg = MsgAggregator(send_msg_seasons, RATE_LIMIT)

        # send_main_chat = self.send_msg_factory([self.msg_main_agg])
        # send_both_chats = self.send_msg_factory([self.msg_main_agg, self.msg_seasons_agg])
        send_seasons_chat = self.send_msg_factory([self.msg_seasons_agg])

        # self.peg_cross_monitor = PegCrossMonitor(send_main_chat, prod=prod)
        # self.peg_cross_monitor.start()

        self.sunrise_monitor = SeasonsMonitor(send_seasons_chat, send_seasons_chat, prod=prod, dry_run=dry_run)
        self.sunrise_monitor.start()

        # self.wells_monitor = WellsMonitor(
        #     send_main_chat, noop, [*WHITELISTED_WELLS, *DEWHITELISTED_WELLS],
        #     arbitrage_senders=[],
        #     bean_reporting=True, prod=prod, dry_run=dry_run
        # )
        # self.wells_monitor.start()

        # self.beanstalk_monitor = BeanstalkMonitor(send_main_chat, send_main_chat, send_main_chat, prod=prod, dry_run=dry_run)
        # self.beanstalk_monitor.start()

        # self.market_monitor = MarketMonitor(send_main_chat, prod=prod, dry_run=dry_run)
        # self.market_monitor.start()

        # self.integrations_monitor = IntegrationsMonitor(
        #     send_main_chat, send_main_chat, prod=prod, dry_run=dry_run
        # )
        # self.integrations_monitor.start()

        # Start monitor status logging
        threading.Thread(target=self.log_monitor_status).start()

    def send_msg_factory(self, aggregators):
        def send_msg(msg, to_main=True, to_tg=True):

            # Ignore empty/nonprimary messages.
            if not msg or not to_main or not to_tg:
                return
            # Remove URL pointy brackets used by md formatting to suppress link previews.
            msg_split = msg.rsplit("<http", 1)
            if len(msg_split) == 2:
                msg = msg_split[0] + "http" + msg_split[1].replace(">", "")

            msg = embellish_token_emojis(msg, TG_TOKEN_EMOJIS)

            for agg in aggregators:
                agg.append_message(msg)
                logging.info(f"A message was queued to be sent.")

        return send_msg

    def log_monitor_status(self):
        """Log the status of all monitors every 60 seconds."""
        while True:
            try:
                logging.info(f"Sunrise Monitor last update: Season {self.sunrise_monitor.current_season_id}")
                # logging.info(f"Well Monitor last update:           {datetime.datetime.fromtimestamp(self.wells_monitor.last_check_time)}")
                # logging.info(f"Beanstalk Monitor last update:      {datetime.datetime.fromtimestamp(self.beanstalk_monitor.last_check_time)}")
                # logging.info(f"Market Monitor last update:         {datetime.datetime.fromtimestamp(self.market_monitor.last_check_time)}")
                # logging.info(f"Integrations Monitor last update:   {datetime.datetime.fromtimestamp(self.integrations_monitor.last_check_time)}")
                # logging.info(f"Peg Monitor last update:            {datetime.datetime.fromtimestamp(self.peg_cross_monitor.last_check_time)}")
            except Exception as e:
                logging.error("Error in monitor status logging", exc_info=True)
            time.sleep(60)

    def stop(self):
        # self.peg_cross_monitor.stop()
        self.sunrise_monitor.stop()
        # self.wells_monitor.stop()
        # self.beanstalk_monitor.stop()
        # self.market_monitor.stop()
        # self.integrations_monitor.stop()
        # self.msg_main_agg.stop()
        self.msg_seasons_agg.stop()

if __name__ == "__main__":
    """Quick test and demonstrate functionality."""
    logging.basicConfig(
        format=f"Telegram Bot : {LOGGING_FORMAT_STR_SUFFIX}",
        level=logging.INFO,
        handlers=[
            logging.handlers.RotatingFileHandler(
                "logs/telegram_bot.log", maxBytes=ONE_HUNDRED_MEGABYTES, backupCount=1
            ),
            logging.StreamHandler(),
        ],
    )
    signal.signal(signal.SIGTERM, util.handle_sigterm)

    util.configure_main_thread_exception_logging()

    token = os.environ["TELEGRAM_BS_BOT_TOKEN"]
    prod = os.environ["IS_PROD"].lower() == "true"
    dry_run = os.environ.get("DRY_RUN")
    if dry_run:
        dry_run = dry_run.split(',')

    bot = TelegramBot(token=token, prod=prod, dry_run=dry_run)
    try:
        bot.tele_bot.infinity_polling()
    except (KeyboardInterrupt, SystemExit):
        pass
    bot.stop()
