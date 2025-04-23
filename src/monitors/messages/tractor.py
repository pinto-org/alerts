import requests

from bots.util import links_footer, round_num
from constants.config import API_ENDPOINT
from data_access.addresses import shorten_hash
from data_access.contracts.util import bean_to_float, pods_to_float
from tools.util import retryable

def publish_requisition_str(event_log):
    blueprint_hash = f"0x{event_log.args.requisition[1].hex()}"
    order = find_tractor_order(blueprint_hash, event_log.blockNumber)
    if order['orderType'] == "SOW_V0":
        event_str = publish_sow_v0_str(order)
    else:
        event_str = f"🖋️🚜 Published unknown order {shorten_hash(order['blueprintHash'])}"
    event_str += links_footer(event_log.receipt, farmer=order['publisher'])
    return event_str

def cancel_blueprint_str(event_log):
    blueprint_hash = f"0x{event_log.args.blueprintHash.hex()}"
    order = find_tractor_order(blueprint_hash, event_log.blockNumber)
    if order['orderType'] == "SOW_V0":
        event_str = cancel_sow_v0_str(order)
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
    else:
        event_str = f"💥🚜 Executed unknown order {shorten_hash(order['blueprintHash'])}"
    event_str += links_footer(event_log.receipt, farmer=order['publisher'])
    return event_str

def publish_sow_v0_str(order):
    total_sow = bean_to_float(int(order['blueprintData']['totalAmountToSow']))
    amount_funded = bean_to_float(int(order['blueprintData']['cascadeAmountFunded']))
    min_temp = bean_to_float(int(order['blueprintData']['minTemp']))
    bean_tip = bean_to_float(int(order['beanTip']))
    event_str = (
        f"🖋️🚜 Published Sow Order {shorten_hash(order['blueprintHash'])}"
        f"\n> 🌱 Sow {round_num(total_sow, precision=0, avoid_zero=True)} Pinto at {round_num(min_temp, precision=2, avoid_zero=True)}% Temperature"
        f"\n> 🤖 Operator tip: {round_num(bean_tip, precision=2, avoid_zero=True)} Pinto"
        f"\n> {round_num(amount_funded, precision=0, avoid_zero=True)} Pinto are currently funding this order"
    )
    return event_str

def cancel_sow_v0_str(order):
    total_sow = bean_to_float(int(order['blueprintData']['totalAmountToSow']))
    min_temp = bean_to_float(int(order['blueprintData']['minTemp']))
    bean_tip = bean_to_float(int(order['beanTip']))
    event_str = (
        f"❌🚜 Cancelled Sow Order {shorten_hash(order['blueprintHash'])}"
        f"\n> 🌱 Sow {round_num(total_sow, precision=0, avoid_zero=True)} Pinto at {round_num(min_temp, precision=2, avoid_zero=True)}% Temperature"
        f"\n> 🤖 Operator tip: {round_num(bean_tip, precision=2, avoid_zero=True)} Pinto"
        f"\n> 🤖 Order was executed {order['executionStats']['executionCount']} time{'' if order['executionStats']['executionCount'] == 1 else 's'}"
    )
    return event_str

def execute_sow_v0_str(execution, order):
    beans = bean_to_float(int(execution['blueprintData']['beans']))
    pods = pods_to_float(int(execution['blueprintData']['pods']))
    temperature = (pods / beans - 1) * 100
    bean_tip = bean_to_float(int(order['beanTip']))
    profit = execution['tipUsd'] - execution['gasCostUsd']
    event_str = (
        f"💥🚜 Executed Sow Order {shorten_hash(order['blueprintHash'])}"
        f"\n> {round_num(beans, precision=0, avoid_zero=True)} Pinto Sown at {round_num(temperature, precision=2, avoid_zero=True)}% Temperature for {round_num(pods, precision=0, avoid_zero=True)} Pods"
        f"\n> 🤖 Operator received {round_num(bean_tip, precision=2, avoid_zero=True)} Pinto"
        f" and spent ~{round_num(execution['gasCostUsd'], precision=3, incl_dollar=True)} in gas"
        f" ({'+' if profit > 0 else ''}{round_num(profit, precision=2, incl_dollar=True)})"
    )
    if not order['blueprintData']['orderComplete']:
        remaining_sow = bean_to_float(int(order['blueprintData']['totalAmountToSow']) - int(order['blueprintData']['pintoSownCounter']))
        amount_funded = bean_to_float(int(order['blueprintData']['cascadeAmountFunded']))
        event_str += (
            f"\n> 🌱 Order can sow :PINTO: {round_num(remaining_sow, precision=0, avoid_zero=True)} more !Pinto"
            f"\n> {round_num(amount_funded, precision=0, avoid_zero=True)} Pinto are currently funding this order"
        )
    else:
        pinto_sown = bean_to_float(int(order['blueprintData']['pintoSownCounter']))
        event_str += f"\n> ✅ Order is fulfilled after sowing {round_num(pinto_sown, precision=0, avoid_zero=True)} Pinto"
    event_str += f"\n> 🤖 Order has been executed {int(execution['nonce']) + 1} time{'' if int(execution['nonce']) + 1 == 1 else 's'}"
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
