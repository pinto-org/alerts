import abc
from enum import Enum
import logging
import logging.handlers
import os
import signal
import subprocess

import discord
from discord.ext import tasks, commands

from bots import util
from constants.addresses import *
from constants.channels import *
from constants.config import *

from monitors.basin_periodic import BasinPeriodicMonitor
from monitors.well import WellsMonitor
from tools.webhook_alerts import activate_webhook_on_error_logs

class Channel(Enum):
    REPORT = 0
    DAILY = 1
    WHITELISTED = 2
    WELLS_OTHER = 3


class DiscordClient(discord.ext.commands.Bot):
    def __init__(self, prod=False, dry_run=None):
        super().__init__(command_prefix=commands.when_mentioned_or("!"))
        self.nickname = ""

        if prod:
            self._chat_id_report = DEX_DISCORD_CHANNEL_ID_TEST
            self._chat_id_daily = DEX_DISCORD_CHANNEL_ID_DAILY
            self._chat_id_whitelisted_wells = DEX_DISCORD_CHANNEL_ID_WHITELISTED
            self._chat_id_other_wells = DEX_DISCORD_CHANNEL_ID_WELLS_OTHER
            logging.info("Configured as a production instance.")
        else:
            self._chat_id_report = DEX_DISCORD_CHANNEL_ID_TEST
            self._chat_id_daily = DEX_DISCORD_CHANNEL_ID_TEST
            self._chat_id_whitelisted_wells = DEX_DISCORD_CHANNEL_ID_TEST
            self._chat_id_other_wells = DEX_DISCORD_CHANNEL_ID_TEST
            logging.info("Configured as a staging instance.")

        self.msg_queue = []

        activate_webhook_on_error_logs()

        # Update root logger to send logging Errors in a Discord channel.
        discord_report_handler = util.MsgHandler(self.send_msg_report)
        discord_report_handler.setLevel(logging.ERROR)
        discord_report_handler.setFormatter(LOGGING_FORMATTER)
        logging.getLogger().addHandler(discord_report_handler)

        self.period_monitor = BasinPeriodicMonitor(
            self.send_msg_daily, prod=prod, dry_run=dry_run
        )
        self.period_monitor.start()

        self.well_monitor_whitelisted = WellsMonitor(
            self.send_msg_whitelisted, [*WHITELISTED_WELLS, *DEWHITELISTED_WELLS], prod=prod, dry_run=dry_run
        )
        self.well_monitor_whitelisted.start()

        # Ignore exceptions of this type and retry. Note that no logs will be generated.
        # Ignore base class, because we always want to reconnect.
        # https://discordpy.readthedocs.io/en/latest/api.html#discord.ClientUser.edit
        # https://discordpy.readthedocs.io/en/latest/api.html#exceptions
        # self._update_naming.add_exception_type(discord.DiscordException)

        # Ignore exceptions of this type and retry. Note that no logs will be generated.
        self.send_queued_messages.add_exception_type(discord.errors.DiscordServerError)
        # Start the message queue sending task in the background.
        self.send_queued_messages.start()

    def stop(self):
        self.period_monitor.stop()
        self.well_monitor_whitelisted.stop()
        self.well_monitor_other.stop()

    def send_msg_report(self, text):
        """Send a message through the Discord bot in the report/test channel."""
        self.msg_queue.append((Channel.REPORT, text))

    def send_msg_daily(self, text):
        """Send a message through the Discord bot in the daily update channel."""
        self.msg_queue.append((Channel.DAILY, text))

    def send_msg_whitelisted(self, text):
        """Send a message through the Discord bot in the beanstalk whitelisted wells channel."""
        self.msg_queue.append((Channel.WHITELISTED, text))

    def send_msg_wells_other(self, text):
        """Send a message through the Discord bot in the other wells channel."""
        self.msg_queue.append((Channel.WELLS_OTHER, text))

    async def on_ready(self):
        self._channel_report = self.get_channel(self._chat_id_report)
        self._channel_daily = self.get_channel(self._chat_id_daily)
        self._channel_whitelisted = self.get_channel(self._chat_id_whitelisted_wells)
        self._channel_wells_other = self.get_channel(self._chat_id_other_wells)

        logging.info(
            f"Discord channels are {self._channel_report}, {self._channel_daily}, {self._channel_whitelisted}, {self._chat_id_other_wells}"
        )

        # Guild IDs for all servers this bot is in.
        self.current_guilds = []
        for guild in self.guilds:
            self.current_guilds.append(guild)
            logging.info(f"Guild found: {guild.id}")

    @tasks.loop(seconds=0.4, reconnect=True)
    async def send_queued_messages(self):
        """Send messages in queue.

        Reconnect logic applies to Loop._valid_exception (OSError, discord.GatewayNotFound,
        discord.ConnectionClosed, aiohttp.ClientError, asyncio.TimeoutError).

        We handle unexpected exceptions in this method so that:
        1. We can log them usefully.
        2. This thread does not crash forever.
        The Discord.py lib allows us to ignore an exception and restart, or die on the exception.
        We want to log it _and_ not die.
        """
        try:
            for channel, msg in self.msg_queue:
                # Discord has limit of 2k but sometimes it still fails with 2k. It is preferable to allow moderate truncation.
                if len(msg) > 1950:
                    msg = msg[-1950:]
                    logging.error(f"Clipping message length down to 1950.")
                logging.info(f"Sending message through {channel} channel:\n{msg}\n")
                # Ignore empty messages.
                if not msg:
                    pass
                elif channel is Channel.REPORT:
                    await self._channel_report.send(msg)
                elif channel is Channel.DAILY:
                    await self._channel_daily.send(msg)
                elif channel is Channel.WHITELISTED:
                    await self._channel_whitelisted.send(msg)
                elif channel is Channel.WELLS_OTHER:
                    await self._channel_wells_other.send(msg)
                else:
                    logging.error(f"Unknown channel seen in msg queue: {channel}")
                self.msg_queue = self.msg_queue[1:]
        except Exception as e:
            logging.error(e, exc_info=True)
            logging.warning("Failed to send message to Discord server. Will retry.")
            # Move the failing message to the back of the queue, in case there was something wrong with the message
            self.msg_queue.append(self.msg_queue.pop(0))

    @send_queued_messages.before_loop
    async def before_send_queued_messages_loop(self):
        """Wait until the bot logs in."""
        await self.wait_until_ready()

    async def on_message(self, message):
        """Respond to messages."""
        # Do not reply to itself.
        if message.author.id == self.user.id:
            return

        # Process commands.
        await self.process_commands(message)

    @abc.abstractmethod
    def isDM(self, channel):
        """Return True is this context is from a dm, else False."""
        return isinstance(channel, discord.channel.DMChannel)


def channel_id(ctx):
    """Returns a string representation of the channel id from a context object."""
    return str(ctx.channel.id)


if __name__ == "__main__":
    logging.basicConfig(
        format=f"Discord Basin Bot : {LOGGING_FORMAT_STR_SUFFIX}",
        level=logging.INFO,
        handlers=[
            logging.handlers.RotatingFileHandler(
                "logs/discord_basin_bot.log", maxBytes=ONE_HUNDRED_MEGABYTES, backupCount=1
            ),
            logging.StreamHandler(),
        ],
    )
    signal.signal(signal.SIGTERM, util.handle_sigterm)

    util.configure_main_thread_exception_logging()

    token = os.environ["DISCORD_DEX_BOT_TOKEN"]
    prod = os.environ["IS_PROD"].lower() == "true"
    dry_run = os.environ.get("DRY_RUN")
    if dry_run:
        dry_run = dry_run.split(',')

    discord_client = DiscordClient(prod=prod, dry_run=dry_run)

    try:
        discord_client.run(token)
    except (KeyboardInterrupt, SystemExit):
        pass
    # Note that discord bot cannot send shutting down messages in its channel, due to lib impl.
    discord_client.stop()
