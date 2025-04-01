import logging
from bots.util import get_logs_by_names, round_num
from data_access.contracts.beanstalk import BeanstalkClient
from data_access.contracts.eth_events import EthEventsClient, EventClientType
from data_access.contracts.util import get_web3_instance, token_to_float
from data_access.util import execute_lambdas
from eth_abi import decode_abi
from tools.util import get_txn_receipt
from web3 import Web3

def seasonal_gauge_str(sunrise_receipt):
    beanstalk_client = BeanstalkClient()
    season_client = EthEventsClient(EventClientType.SEASON)

    seasons_info = get_seasons_and_blocks(season_client.logs_from_receipt(sunrise_receipt))

    b = seasons_info["current"]["block"]
    b_prev = seasons_info["prev"]["block"]

    # Parallelize all necessary rpc calls together
    parallelized = []
    parallelized.append(lambda: beanstalk_client.get_deposited_bdv_totals(b_prev))
    parallelized.append(lambda: beanstalk_client.get_deposited_bdv_totals(b))

    gauge_str_methods = [cultivation_factor_str, convert_down_penalty_str]
    for i in range(len(gauge_str_methods)):
        parallelized.append(lambda gauge_id=i, block=b_prev: beanstalk_client.get_gauge_value(gauge_id, block))
        parallelized.append(lambda gauge_id=i, block=b: beanstalk_client.get_gauge_value(gauge_id, block))

    async_values = execute_lambdas(*parallelized)

    gauge_strs = []
    gauge_strs.append(seed_gauge_str(*async_values[:2]))

    gen_gauge_values = async_values[2:]
    for i in range(len(gen_gauge_values) // 2):
        gauge_strs.append(
            gauge_str_methods[i]([
                gen_gauge_values[2 * i],
                gen_gauge_values[2 * i + 1]
            ])
        )

    return "\n".join(gauge_strs)

def get_seasons_and_blocks(current_logs):
    """Gets the season number and block associated with the current and previous season"""
    season_client = EthEventsClient(EventClientType.SEASON)

    evt_sunrise = get_logs_by_names(["Sunrise"], current_logs)[0]
    current_season_number = evt_sunrise.args.season

    prev_sunrise_txn = season_client.get_log_with_topics("Sunrise", [Web3.toHex(Web3.toBytes(current_season_number - 1).rjust(32, b'\x00'))])
    evt_prev_sunrise = prev_sunrise_txn[0].logs[0]
    return {
        "prev": { "season": current_season_number-1, "block": evt_prev_sunrise.blockNumber },
        "current": { "season": current_season_number, "block": evt_sunrise.blockNumber },
    }

def seed_gauge_str(before_bdvs, after_bdvs):
    return "todo"

def cultivation_factor_str(value_bytes):
    percent_factors = [token_to_float(decode_abi(['uint256'], v)[0], 6) for v in value_bytes]
    return (
        f"Cultivation Factor: {round_num(percent_factors[1], precision=2)}%"
        f"\n> {pct_change_str(percent_factors[0], percent_factors[1])}"
    )

def convert_down_penalty_str(value_bytes):
    percent_penalties = [token_to_float(decode_abi(['uint256', 'uint256'], v)[0], 18 - 2) for v in value_bytes]
    return (
        f"Convert Down Penalty: {round_num(percent_penalties[1], precision=2)}%"
        f"\n> {pct_change_str(percent_penalties[0], percent_penalties[1])}"
    )

def pct_change_str(before, after):
    diff = abs(after - before)
    if before < after:
        return f"📈 +{round_num(diff, precision=2)}% this Season"
    elif after < before:
        return f"📉 -{round_num(diff, precision=2)}% this Season"
    else:
        return f"📊 No change this Season"

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    receipt = get_txn_receipt(get_web3_instance(), "0x8e95accae8fdb9658f0af0c215c98e03b5c7f4a5fc97bb852d6177b5dacbcb6e")
    gauge_str = seasonal_gauge_str(receipt)
    logging.info(gauge_str)
