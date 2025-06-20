import re
from constants.config import DISCORD_TOKEN_EMOJIS
from hexbytes.main import HexBytes
import logging
import os
import time
from web3 import Web3, WebsocketProvider
from web3.datastructures import AttributeDict
from web3.logs import DISCARD

from datetime import datetime


URL = "wss://" + os.environ["RPC_URL"]
web3 = Web3(WebsocketProvider(URL, websocket_timeout=60))


def noop(*args, **kwargs):
    pass

# Compares a topic (which has leading zeros) with an ethereum address
def topic_is_address(topic, address):
    return "0x" + topic.hex().lstrip("0x").zfill(40) == address.lower()

def topic_to_address(topic):
    return Web3.to_checksum_address(f"0x{topic.hex()[-40:]}")

def format_log_str(log, indent=0):
    """Format decoded log AttributeDict as a nice str."""
    ret_str_list = []
    for key, value in log.items():
        if isinstance(value, AttributeDict):
            str_value = f"\n{format_log_str(value, 2)}"
        elif isinstance(value, HexBytes):
            str_value = value.hex()
        else:
            str_value = str(value)
        item_str = f'{" " * indent}{key}: {str_value}'
        if key == "event":
            ret_str_list.insert(0, item_str)
        else:
            ret_str_list.append(item_str)
    return "\n".join(ret_str_list)

def retryable(max_retries=5, retry_delay=10, show_retry_error=True):
    """Decorator to wrap calls that could fail and gracefully handle retries."""
    def decorator(fn):
        def retry_wrapper(*args, **kwargs):
            try_count = 0
            while True:
                try_count += 1
                try:
                    return fn(*args, **kwargs)
                except Exception as e:
                    if try_count < max_retries:
                        if show_retry_error:
                            logging.warning(f"Failed to get result. Retrying...\n{e}")
                        time.sleep(retry_delay)
                        continue
                    logging.error(
                        f"Failed to get result after {try_count} retries."
                    )
                    raise (e)
        return retry_wrapper
    return decorator

@retryable()
def get_txn_receipt(web3, txn_hash):
    """
    Get the transaction receipt and handle errors and block delays cleanly.

    Returns:
        AttributeDict containing a single txn receipt.
    """
    return web3.eth.get_transaction_receipt(txn_hash)

def format_farm_call_str(decoded_txn, beanstalk_contract):
    """Break down a farm() call and return a list of the sub-method it calls.

    Args:
        txn: a decoded web3.transaction object.

    Return:
        str representing the farm call in human readable format.
    """
    ret_str = ""
    # Possible to have multiple items in this list, what do they represent?
    # [1] is args, ['data'] is data arg
    farm_data_arg_list = decoded_txn[1]["data"]
    # logging.info(f'farm_data_arg_list: {farm_data_arg_list}')

    for sub_method_call_bytes in farm_data_arg_list:
        sub_method_selector = sub_method_call_bytes[:4]
        logging.info(f"\nsub_method_selector: {sub_method_selector.hex()}")
        # sub_method_input = sub_method_call_bytes[4:]
        # logging.info(f'sub_method_input: {sub_method_input.hex()}')
        decoded_sub_method_call = beanstalk_contract.decode_function_input(sub_method_call_bytes)
        logging.info(f"decoded_sub_method_call: {decoded_sub_method_call}")
        ret_str += f"  sub-call: {decoded_sub_method_call[0].function_identifier}"
        ret_str += "\n  args:"
        for arg_name, value in decoded_sub_method_call[1].items():
            # Clean up bytes as strings for printing.
            if type(value) is bytes:
                value = value.hex()
            ret_str += f"\n    {arg_name}: {value}"
        ret_str += "\n\n"
    return ret_str

def embellish_token_emojis(text, mapping):
    # Replace occurrences of placeholders where an emoji is explicitly requested
    for key in mapping:
        text = text.replace(f":{key}:", mapping[key])

    # Function to handle case-sensitive replacement while preserving original case
    def replacer(match):
        pre_whitespace = match.group(1)
        sign = match.group(2) or ""
        number = match.group(3) or ""
        word = match.group(4)
        emoji = mapping[word.upper()]  # Retrieve emoji based on uppercase word
        return f"{pre_whitespace}{emoji} {sign}{number}{word}"

    # Normalize text to guarantee some whitespace before any leading < prior to regex operations
    text = f" {text}"

    # For each word in the mapping, replace in a case-insensitive way
    for word in mapping:
        # Use re.IGNORECASE to match the word regardless of case
        pattern = rf'(?<!-)(\b|\s)([<])?(\d[\d,\.]*\s)?(?<!!)({re.escape(word)})\b(?!\.\w|:\d)'
        text = re.sub(pattern, replacer, text, flags=re.IGNORECASE)

    text = text.strip()

    # Ignore/strip occurrences where an emoji was explicitly rejected
    def retain_casing(match):
        matched_text = match.group(0)
        return matched_text[1:]
    for key in mapping:
        text = re.sub(f"!({re.escape(key)})", retain_casing, text, flags=re.IGNORECASE)

    # Other
    today = datetime.today()
    if today.month == 4 and today.day == 1:
        text = text.replace("🧑‍🌾", mapping["MC"])

    return text

def detached_future_done(txn_hash):
    def inner(future):
        try:
            future.result()
        except Exception as e:
            logging.error(f"Background task failed for {txn_hash}", exc_info=e)
    return inner

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    # logging.info(f"With discord emoji {embellish_token_emojis('100 PINTO sold for <0.1 cbETH (extra :PINTO:)', DISCORD_TOKEN_EMOJIS)}")
    # logging.info(f"With telegram emoji {embellish_token_emojis('100 PINTO sold for <0.1 cbETH', TG_TOKEN_EMOJIS)}")
    # logging.info(f"Discord lp {embellish_token_emojis('🌊 PINTOcbBTC: $2,254,626', DISCORD_TOKEN_EMOJIS)}")
    # logging.info(f"With rejection {embellish_token_emojis(':PINTO: 500 Deposited !PINTO', DISCORD_TOKEN_EMOJIS)}")
    logging.info(f"Normal {embellish_token_emojis('2500 sPinto', DISCORD_TOKEN_EMOJIS)}")
    logging.info(f"With nested word {embellish_token_emojis('500 PT-sPinto and :SPECTRA_LP: 1700 LP', DISCORD_TOKEN_EMOJIS)}")
    logging.info(f"With leading < {embellish_token_emojis('<1 PINTO exchanged for <0.01 WETH, 1 PINTO', DISCORD_TOKEN_EMOJIS)}")
    # receipt = get_txn_receipt(web3, '0x9e810260341f174b8596c8acd7c6230ed06e90174de2d8c660faf8f71c437c63')
    # logging.info(f"got receipt {receipt}")
