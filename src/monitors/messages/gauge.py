import logging
from bots.util import get_logs_by_names, round_num
from constants.addresses import BEAN_ADDR
from constants.config import SILO_TOKENS_MAP, WHITELISTED_WELLS
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
    gauge_strs.append("**Seed Gauge**")
    gauge_strs.append(seed_gauge_str(seasons_info, async_values[:2]))

    gauge_strs.append("\n**Other Gauges**")
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

def seed_gauge_str(seasons_info, asset_bdvs):
    beanstalk_client = BeanstalkClient()
    b = seasons_info["current"]["block"]
    b_prev = seasons_info["prev"]["block"]

    # Get seeds/gauge point info for every asset
    assets = [BEAN_ADDR, *WHITELISTED_WELLS]
    parallelized = []
    for asset in assets:
        parallelized.append(lambda token=asset, block=b_prev: beanstalk_client.get_seeds(token, block))
        parallelized.append(lambda token=asset, block=b: beanstalk_client.get_seeds(token, block))
        parallelized.append(lambda token=asset, block=b_prev: beanstalk_client.get_gauge_points(token, block))
        parallelized.append(lambda token=asset, block=b: beanstalk_client.get_gauge_points(token, block))

    async_values = execute_lambdas(*parallelized)

    total_lp_bdvs = [sum(season[token] for token in season if token != BEAN_ADDR) for season in asset_bdvs]

    asset_strs = []
    for i in range(len(assets)):
        asset_str = (
            f"{SILO_TOKENS_MAP.get(assets[i].lower())}"
            f"\n> {round_num(async_values[4 * i + 1], 3)} Seeds ({pct_change_str(async_values[4 * i], async_values[4 * i + 1], precision=3, is_percent=False, use_emoji=False)})"
        )
        # For LP: add gauge info
        if assets[i] != BEAN_ADDR:
            bdv_pcts = [100 * (asset_bdvs[0][assets[i]] / total) for total in total_lp_bdvs]
            asset_str += (
                f"\n> {round_num(async_values[4 * i + 3], 0)} Gauge Points ({pct_change_str(async_values[4 * i + 2], async_values[4 * i + 3], precision=0, is_percent=False, use_emoji=False)})"
                f"\n> {round_num(bdv_pcts[1], 2)}% of Deposited LP PDV ({pct_change_str(bdv_pcts[0], bdv_pcts[1], precision=2, is_percent=True, use_emoji=False)})"
            )
        asset_strs.append(asset_str)
    return "\n".join(asset_strs)

def cultivation_factor_str(value_bytes):
    percent_factors = [token_to_float(decode_abi(['uint256'], v)[0], 6) for v in value_bytes]
    return (
        f"🪱 Cultivation Factor: {round_num(percent_factors[1], precision=2)}%"
        f"\n> {pct_change_str(percent_factors[0], percent_factors[1], precision=2, is_percent=True, use_emoji=True)}"
    )

def convert_down_penalty_str(value_bytes):
    percent_penalties = [token_to_float(decode_abi(['uint256', 'uint256'], v)[0], 18 - 2) for v in value_bytes]
    return (
        f"🔄 Convert Down Penalty: {round_num(percent_penalties[1], precision=2)}%"
        f"\n> {pct_change_str(percent_penalties[0], percent_penalties[1], precision=2, is_percent=True, use_emoji=True)}"
    )

def pct_change_str(before, after, precision=2, is_percent=False, use_emoji=False):
    diff = abs(after - before)
    if before < after:
        return f"{'📈 ' if use_emoji else ''}+{round_num(diff, precision=precision, avoid_zero=True)}{'%' if is_percent else ''} this Season"
    elif after < before:
        return f"{'📉 ' if use_emoji else ''}-{round_num(diff, precision=precision, avoid_zero=True)}{'%' if is_percent else ''} this Season"
    else:
        return f"{'📊 ' if use_emoji else ''}No change this Season"

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    receipt = get_txn_receipt(get_web3_instance(), "0x8e95accae8fdb9658f0af0c215c98e03b5c7f4a5fc97bb852d6177b5dacbcb6e")
    gauge_str = seasonal_gauge_str(receipt)
    logging.info(gauge_str)
