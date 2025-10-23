import logging
from bots.util import get_logs_by_names, round_num
from constants.addresses import BEAN_ADDR, BEANSTALK_ADDR
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
    season_client = EthEventsClient([EventClientType.SEASON])

    seasons_info = get_seasons_and_blocks(season_client.logs_from_receipt(sunrise_receipt))
    b = seasons_info["current"]["block"]
    b_prev = seasons_info["prev"]["block"]

    # Parallelize all necessary rpc calls together
    parallelized = []
    parallelized.append(lambda: beanstalk_client.get_deposited_bdv_totals(b_prev))
    parallelized.append(lambda: beanstalk_client.get_deposited_bdv_totals(b))

    gauge_str_methods = [cultivation_factor_str, cultivation_gauge_str, convert_down_penalty_str, convert_up_bonus_str]
    for i in range(len(gauge_str_methods)):
        parallelized.append(lambda gauge_id=gauge_str_methods[i].gauge_id, fn=gauge_str_methods[i].data_getter, block=b_prev: getattr(beanstalk_client, fn)(gauge_id, block))
        parallelized.append(lambda gauge_id=gauge_str_methods[i].gauge_id, fn=gauge_str_methods[i].data_getter, block=b: getattr(beanstalk_client, fn)(gauge_id, block))

    async_values = execute_lambdas(*parallelized)

    gauge_strs = []
    gauge_strs.append(f"🌅 Season {seasons_info['current']['season']}\n")
    gauge_strs.append("**Seed Gauge**")
    gauge_strs.append(seed_gauge_str(seasons_info, async_values[:2]))

    gauge_strs.append("\n**Other Gauges**")
    gen_gauge_results = async_values[2:]
    for i in range(len(gen_gauge_results) // 2):
        gauge_strs.append(
            gauge_str_methods[i]([
                gen_gauge_results[2 * i],
                gen_gauge_results[2 * i + 1]
            ])
        )
    return "\n".join(gauge_strs)

def get_seasons_and_blocks(current_logs):
    """Gets the season number and block associated with the current and previous season"""
    evt_sunrise = get_logs_by_names(["Sunrise"], current_logs)[0]
    current_season_number = evt_sunrise.args.season

    # Direct eth_getLogs call to find previous Sunrise event
    web3 = get_web3_instance()
    sunrise_signature = Web3.keccak(text="Sunrise(uint256)").hex()

    prev_sunrise_logs = web3.eth.get_logs({
        'address': BEANSTALK_ADDR,
        'topics': [
            sunrise_signature,
            Web3.toHex(Web3.toBytes(current_season_number - 1).rjust(32, b'\x00'))
        ],
        'fromBlock': evt_sunrise.blockNumber - 10000,
        'toBlock': evt_sunrise.blockNumber - 1
    })

    # Extract blockNumber directly from the raw log
    prev_sunrise_block = prev_sunrise_logs[0]['blockNumber']

    return {
        "prev": { "season": current_season_number-1, "block": prev_sunrise_block },
        "current": { "season": current_season_number, "block": evt_sunrise.blockNumber },
    }

def seed_gauge_str(seasons_info, asset_bdvs):
    beanstalk_client = BeanstalkClient()
    b = seasons_info["current"]["block"]
    b_prev = seasons_info["prev"]["block"]

    assets = [BEAN_ADDR, *WHITELISTED_WELLS]
    parallelized = []
    parallelized.append(lambda: beanstalk_client.get_crop_ratio(b_prev))
    parallelized.append(lambda: beanstalk_client.get_crop_ratio(b))
    # Get seeds/gauge point info for every asset
    for asset in assets:
        parallelized.append(lambda token=asset, block=b_prev: beanstalk_client.get_seeds(token, block))
        parallelized.append(lambda token=asset, block=b: beanstalk_client.get_seeds(token, block))
        parallelized.append(lambda token=asset, block=b_prev: beanstalk_client.get_gauge_points(token, block))
        parallelized.append(lambda token=asset, block=b: beanstalk_client.get_gauge_points(token, block))

    async_values = execute_lambdas(*parallelized)
    crop_ratios = async_values[:2]
    gauge_values = async_values[2:]

    total_lp_bdvs = [sum(season[token] for token in season if token != BEAN_ADDR) for season in asset_bdvs]

    strs = []
    lp_strs = []
    strs.append((
        f"🌾 Crop Ratio: {round_num(crop_ratios[1], precision=1)}%"
        f"\n> {amt_change_str(crop_ratios[0], crop_ratios[1], precision=1, is_percent=True, use_emoji=True)}"
    ))

    for i in range(len(assets)):
        asset_str = (
            f"{SILO_TOKENS_MAP.get(assets[i].lower())}"
            f"\n> {round_num(gauge_values[4 * i + 1], 3)} Seeds ({amt_change_str(gauge_values[4 * i], gauge_values[4 * i + 1], precision=3, is_percent=False, use_emoji=False)})"
        )
        # For LP: add gauge info
        if assets[i] != BEAN_ADDR:
            bdv_pcts = [100 * (asset_bdvs[j][assets[i]] / total) for j, total in enumerate(total_lp_bdvs)]
            asset_str += (
                f"\n> {round_num(gauge_values[4 * i + 3], 0)} Gauge Points ({amt_change_str(gauge_values[4 * i + 2], gauge_values[4 * i + 3], precision=0, is_percent=False, use_emoji=False)})"
                f"\n> {round_num(bdv_pcts[1], 2)}% of Deposited LP PDV ({amt_change_str(bdv_pcts[0], bdv_pcts[1], precision=2, is_percent=True, use_emoji=False)})"
            )
            lp_strs.append(asset_str)
        else:
            strs.append(asset_str)

    # Sort lp tokens by highest seeds
    paired = [(lp_strs[i], gauge_values[4 * (i + 1) + 1]) for i in range(len(lp_strs))]
    paired.sort(key=lambda x: x[1], reverse=True)
    strs.extend([item[0] for item in paired])

    return "\n".join(strs)

def cultivation_factor_str(value_bytes):
    percent_factors = [token_to_float(decode_abi(['uint256'], v)[0], 6) for v in value_bytes]
    return (
        f"🪱 Cultivation Factor: {round_num(percent_factors[1], precision=2)}%"
        f"\n> {amt_change_str(percent_factors[0], percent_factors[1], precision=2, is_percent=True, use_emoji=True)}"
    )
cultivation_factor_str.gauge_id = 0
cultivation_factor_str.data_getter = 'get_gauge_value'

def cultivation_gauge_str(data_bytes):
    cultivation_temperatures = [token_to_float(
        decode_abi(['uint256', 'uint256', 'uint256', 'uint256', 'uint256', 'uint256'], bytes)[4], 6
    ) for bytes in data_bytes]
    return (
        f"☀️ Cultivation Temperature: {round_num(cultivation_temperatures[1], precision=2)}%"
        f"\n> {amt_change_str(cultivation_temperatures[0], cultivation_temperatures[1], precision=2, is_percent=True, use_emoji=True)}"
    )
cultivation_gauge_str.gauge_id = 0
cultivation_gauge_str.data_getter = 'get_gauge_data'

def convert_down_penalty_str(value_bytes):
    decoded = [decode_abi(['uint256', 'uint256'], bytes) for bytes in value_bytes]
    percent_penalties = [token_to_float(v[0], 18 - 2) for v in decoded]
    blight_factors = [v[1] for v in decoded]
    return (
        f"🔄 Convert Down Penalty: {round_num(percent_penalties[1], precision=2)}%"
        f"\n> {amt_change_str(percent_penalties[0], percent_penalties[1], precision=2, is_percent=True, use_emoji=True)}"
        f"\n> 🥀 Blight Factor: {blight_factors[1]} ({amt_change_str(blight_factors[0], blight_factors[1], precision=0)})"
    )
convert_down_penalty_str.gauge_id = 1
convert_down_penalty_str.data_getter = 'get_gauge_value'

def convert_up_bonus_str(value_bytes):
    decoded = [decode_abi(['uint256', 'uint256', 'uint256'], bytes) for bytes in value_bytes]
    bonus_stalk_per_bdv = [token_to_float(v[0], 10) for v in decoded]
    max_convert_capacity = [token_to_float(v[1], 6) for v in decoded]
    return (
        f"⬆️ Convert Up Bonus: {round_num(bonus_stalk_per_bdv[1], precision=2)} Stalk per PDV"
        f"\n> {amt_change_str(bonus_stalk_per_bdv[0], bonus_stalk_per_bdv[1], scientific=True, use_emoji=True)}"
        f"\n> 🛢️ Seasonal Capacity: {round_num(max_convert_capacity[1], precision=0)} PDV ({amt_change_str(max_convert_capacity[0], max_convert_capacity[1], precision=0)})"
    )
convert_up_bonus_str.gauge_id = 2
convert_up_bonus_str.data_getter = 'get_gauge_value'

def amt_change_str(before, after, precision=2, is_percent=False, use_emoji=False, scientific=False):
    diff = abs(after - before)
    if before < after:
        if not scientific:
            diff_str = round_num(diff, precision=precision, avoid_zero=True)
            return f"{'📈 ' if use_emoji else ''}+{' ' if diff_str.startswith('<') else ''}{diff_str}{'%' if is_percent else ''} this Season"
        else:
            return f"{'📈 ' if use_emoji else ''}+{diff:.2e} this Season"
    elif after < before:
        if not scientific:
            diff_str = round_num(diff, precision=precision, avoid_zero=True)
            return f"{'📉 ' if use_emoji else ''}-{' ' if diff_str.startswith('<') else ''}{diff_str}{'%' if is_percent else ''} this Season"
        else:
            return f"{'📉 ' if use_emoji else ''}-{diff:.2e} this Season"
    else:
        return f"{'📊 ' if use_emoji else ''}No change this Season"

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # receipt = get_txn_receipt(get_web3_instance(), "0x0bbf37cf9f8e5e21867679bf2d8734695d018b89bd2c34b44d1d899d75edfb9b")
    receipt = get_txn_receipt(get_web3_instance(), "0x095bed5217a03ef8beff957534381a2babf64171c02f824152e3fa51133055c4")
    gauge_str = seasonal_gauge_str(receipt)
    logging.info(gauge_str)
