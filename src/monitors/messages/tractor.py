import requests

from bots.util import links_footer
from constants.config import API_ENDPOINT
from data_access.addresses import shorten_hash
from monitors.messages.tractor_blueprints.convert_up_v0 import cancel_convert_up_v0_str, execute_convert_up_v0_str, publish_convert_up_v0_str
from monitors.messages.tractor_blueprints.sow_v0 import cancel_sow_v0_str, execute_sow_v0_str, publish_sow_v0_str
from tools.util import retryable

def publish_requisition_str(event_log):
    blueprint_hash = f"0x{event_log.args.requisition[1].hex()}"
    order = find_tractor_order(blueprint_hash, event_log.blockNumber)
    if order['orderType'] == "SOW_V0":
        event_str = publish_sow_v0_str(order)
    elif order['orderType'] == "CONVERT_UP_V0":
        event_str = publish_convert_up_v0_str(order)
    else:
        event_str = f"🖋️🚜 Published unknown order {shorten_hash(order['blueprintHash'])}"
    event_str += links_footer(event_log.receipt, farmer=order['publisher'])
    return event_str

def cancel_blueprint_str(event_log):
    blueprint_hash = f"0x{event_log.args.blueprintHash.hex()}"
    order = find_tractor_order(blueprint_hash, event_log.blockNumber)
    if order['orderType'] == "SOW_V0":
        event_str = cancel_sow_v0_str(order)
    elif order['orderType'] == "CONVERT_UP_V0":
        event_str = cancel_convert_up_v0_str(order)
    else:
        event_str = f"❌🚜 Cancelled unknown order {shorten_hash(order['blueprintHash'])}"
    event_str += links_footer(event_log.receipt, farmer=order['publisher'])
    return event_str

def tractor_str(event_log):
    blueprint_hash = f"0x{event_log.args.blueprintHash.hex()}"
    execution = find_tractor_execution(blueprint_hash, event_log.args.nonce, event_log.blockNumber)
    order = find_tractor_order(blueprint_hash, event_log.blockNumber)
    if order['orderType'] == "SOW_V0":
        event_str = execute_sow_v0_str(execution, order)
    elif order['orderType'] == "CONVERT_UP_V0":
        event_str = execute_convert_up_v0_str(execution, order)
    else:
        event_str = f"💥🚜 Executed unknown order {shorten_hash(order['blueprintHash'])}"
    event_str += links_footer(event_log.receipt, farmer=order['publisher'])
    return event_str

@retryable(max_retries=12, retry_delay=10, show_retry_error=False)
def find_tractor_order(blueprint_hash: str, min_block: int) -> dict:
    url = f"{API_ENDPOINT}/tractor/orders"
    payload = {
        "blueprintHash": blueprint_hash
    }
    
    response = requests.post(url, json=payload)
    response.raise_for_status()

    body = response.json()
    if body['lastUpdated'] < min_block:
        raise Exception(f"API is not up to date yet, might retry...")
    
    # Only one order can exist for a blueprint hash
    return body['orders'][0]

@retryable(max_retries=12, retry_delay=10, show_retry_error=False)
def find_tractor_execution(blueprint_hash: str, nonce: int, min_block: int) -> dict:
    url = f"{API_ENDPOINT}/tractor/executions"
    payload = {
        "blueprintHash": blueprint_hash,
        "limit": 10000
    }
    
    response = requests.post(url, json=payload)
    response.raise_for_status()

    body = response.json()
    if body['lastUpdated'] < min_block:
        raise Exception(f"API is not up to date yet, might retry...")
    
    # Find the execution with matching nonce
    return [execution for execution in body['executions'] if int(execution['nonce']) == nonce][0]
