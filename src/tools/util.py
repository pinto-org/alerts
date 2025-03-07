import re
from constants.config import DISCORD_TOKEN_EMOJIS, TG_TOKEN_EMOJIS
from hexbytes.main import HexBytes
import logging
import json
import os
import time
from web3 import Web3, WebsocketProvider
from web3.datastructures import AttributeDict
from web3.logs import DISCARD


URL = "wss://" + os.environ["RPC_URL"]
web3 = Web3(WebsocketProvider(URL, websocket_timeout=60))


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


def web3_call_with_retries(web3_function, max_retries=5):
    """Decorator to wrap web3 calls that could fail and gracefully handle retries."""

    def retry_wrapper(web3, txn_hash):
        try_count = 0
        while True:
            try_count += 1
            try:
                return web3_function(web3, txn_hash)
            except Exception as e:
                if try_count < max_retries:
                    logging.warning(f"Failed to get txn. Retrying...\n{e}")
                    time.sleep(15)
                    continue
                logging.error(
                    f"Failed to get txn after {try_count} retries. Was the block orphaned?"
                )
                raise (e)

    return retry_wrapper

@web3_call_with_retries
def get_txn_receipt_or_wait(web3, txn_hash):
    """Get the transaction receipt and handle errors and block delays cleanly.

    Occasionally web3 will fail to pull the txn with "not found" error. This is likely
    because the txn has not been confirmed at the time of call, even though the logs may
    have already been seen. In this case, wait and hope it will confirm soon.

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

    # For each word in the mapping, replace in a case-insensitive way
    for word in mapping:
        # Use re.IGNORECASE to match the word regardless of case
        pattern = rf'(\b|\s)([<])?(\d[\d,\.]*\s)?(?<!!)({re.escape(word)})\b(?!\.\w|:\d)'
        text = re.sub(pattern, replacer, text, flags=re.IGNORECASE)

    # Ignore/strip occurrences where an emoji was explicitly rejected
    def retain_casing(match):
        matched_text = match.group(0)
        return matched_text[1:]
    for key in mapping:
        text = re.sub(f"!({re.escape(key)})", retain_casing, text, flags=re.IGNORECASE)

    return text

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    logging.info(f"With discord emoji {embellish_token_emojis('100 PINTO sold for <0.1 cbETH (extra :PINTO:)', DISCORD_TOKEN_EMOJIS)}")
    logging.info(f"With telegram emoji {embellish_token_emojis('100 PINTO sold for <0.1 cbETH', TG_TOKEN_EMOJIS)}")
    logging.info(f"Discord lp {embellish_token_emojis('🌊 PINTOcbBTC: $2,254,626', DISCORD_TOKEN_EMOJIS)}")
    logging.info(f"With rejection {embellish_token_emojis(':PINTO: 500 Deposited !PINTO', DISCORD_TOKEN_EMOJIS)}")
    receipt = get_txn_receipt_or_wait(web3, '0x8b0f3901f9a8ea224c691662877df79d6a9e2e160c2b3e2551e40793aed545d7')
    logging.info(f"got receipt {receipt}")
