import os
import requests
import json

def send_webhook_alert(text):
    url = os.environ.get("WEBHOOK_ERROR_ALERTS")
    if url is not None:
        data = {
            "username": "Python Bots",
            "content": text
        }
        response = requests.post(url, headers={"Content-Type": "application/json"}, data=json.dumps(data))
