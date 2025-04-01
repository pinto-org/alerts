import logging
from bots.util import round_num
from data_access.contracts.beanstalk import BeanstalkClient
from data_access.contracts.util import get_web3_instance, token_to_float
from data_access.util import execute_lambdas
from eth_abi import decode_abi
from tools.util import get_txn_receipt

def seasonal_gauge_str(sunrise_receipt):
    beanstalk_client = BeanstalkClient()
    b = sunrise_receipt.blockNumber

    gauge_strs = []

    # Parallelize rpc calls
    parallelized = []
    gauge_str_methods = [cultivation_factor_str, convert_down_penalty_str]
    for i in range(len(gauge_str_methods)):
        parallelized.append(lambda gauge_id=i, block=b-1: beanstalk_client.get_gauge_value(gauge_id, block))
        parallelized.append(lambda gauge_id=i, block=b: beanstalk_client.get_gauge_value(gauge_id, block))

    gauge_values = execute_lambdas(*parallelized)

    for i in range(len(gauge_values) // 2):
        gauge_strs.append(
            gauge_str_methods[i]([
                gauge_values[2 * i],
                gauge_values[2 * i + 1]
            ])
        )

    return "\n".join(gauge_strs)

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
    receipt = get_txn_receipt(get_web3_instance(), "0x61948fa8a78cb78fec9cf577a9c28ae7c8c3a46b8c0e6588f3e3b971e55302d2")
    gauge_str = seasonal_gauge_str(receipt)
    logging.info(gauge_str)
