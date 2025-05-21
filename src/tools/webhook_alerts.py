import requests
import os
import logging
import json

from bots import util
from constants.config import LOGGING_FORMATTER
from tools.util import retryable

def activate_webhook_on_error_logs():
    # Update root logger to send logging errors via discord webhook.
    webhook_report_handler = util.MsgHandler(send_webhook_alert)
    webhook_report_handler.setLevel(logging.ERROR)
    webhook_report_handler.setFormatter(LOGGING_FORMATTER)
    logging.getLogger().addHandler(webhook_report_handler)

def send_webhook_alert(text):
    logging.info(f"Sending webhook error alert")
    try:
        _send_webhook_alert(text)
    except Exception as e:
        logging.error(f"Error sending webhook alert: {e}")

@retryable(max_retries=10, retry_delay=60, show_retry_error=True)
def _send_webhook_alert(text):
    url = os.environ.get("WEBHOOK_ERROR_ALERTS")
    if url is not None:
        data = {
            "username": "Python Bots",
            "content": text
        }
        requests.post(url, headers={"Content-Type": "application/json"}, data=json.dumps(data))
    else:
        raise ValueError("WEBHOOK_ERROR_ALERTS environment variable not set")
