import logging
from bots.util import get_logs_by_names
from data_access.contracts.eth_events import EthEventsClient, EventClientType
from data_access.contracts.util import get_web3_instance, token_to_float
from eth_abi import decode_abi
from tools.util import get_txn_receipt


def seasonal_gauge_str(sunrise_logs):
    gauge_str = ""

    gauge_str_methods = [cultivation_factor_str, convert_down_penalty_str]
    engages = sorted(get_logs_by_names(["Engaged"], sunrise_logs), key=lambda x: x.args.gaugeId)
    for engaged in engages:
        gauge_str += gauge_str_methods[engaged.args.gaugeId](engaged.args.value)

    return gauge_str

def cultivation_factor_str(value_bytes):
    decoded = decode_abi(['uint256'], value_bytes)
    percent_factor = token_to_float(decoded[0], 6)
    return "abc"

def convert_down_penalty_str(value_bytes):
    decoded = decode_abi(['uint256', 'uint256'], value_bytes)
    percent_penalty = token_to_float(decoded[0], 18 - 2)
    return "xyz"

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    season_evt_client = EthEventsClient(EventClientType.SEASON)
    receipt = get_txn_receipt(get_web3_instance(), "0x61948fa8a78cb78fec9cf577a9c28ae7c8c3a46b8c0e6588f3e3b971e55302d2")
    gauge_str = seasonal_gauge_str(season_evt_client.logs_from_receipt(receipt))
    logging.info(gauge_str)
