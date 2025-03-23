from bots.util import round_num, round_token, value_to_emojis
from constants.addresses import BEAN_ADDR
from data_access.contracts.bean import BeanClient
from data_access.contracts.erc20 import get_erc20_info
from data_access.contracts.integrations import WrappedDepositClient
from data_access.contracts.util import stalk_to_float, token_to_float
from data_access.subgraphs.beanstalk import BeanstalkGraphClient
from tools.spinto import spinto_deposit_info

def spinto_str(event_log):
    bean_client = BeanClient(block_number=event_log.blockNumber)
    spinto_client = WrappedDepositClient(event_log.address, BEAN_ADDR, block_number=event_log.blockNumber)
    beanstalk_graph_client = BeanstalkGraphClient(block_number=event_log.blockNumber)

    event_str = ""

    underlying_asset = spinto_client.get_underlying_asset()
    underlying_info = get_erc20_info(underlying_asset)
    wrapped_info = get_erc20_info(event_log.address)

    if event_log.event == "Deposit" or event_log.event == "Withdraw":
        owner = event_log.args.get("owner")
        pinto_amount = token_to_float(event_log.args.get("assets"), underlying_info.decimals)
        pinto_amount_str = round_token(event_log.args.get("assets"), underlying_info.decimals, underlying_info.addr)
        sPinto_amount_str = round_token(event_log.args.get("shares"), wrapped_info.decimals, wrapped_info.addr)

        # Determine whether the source/destination pinto is deposited, and how much stalk is involved
        is_deposited, stalk_amount = spinto_deposit_info(wrapped_info, owner, event_log)
        if_deposited_str = "Deposited " if is_deposited else ""

        token_strings = [
            f":{underlying_info.symbol}: {pinto_amount_str} {if_deposited_str}!{underlying_info.symbol}",
            f"{sPinto_amount_str} {wrapped_info.symbol}"
        ]
        if event_log.event == "Deposit":
            event_str += f"📥 {token_strings[0]} wrapped to {token_strings[1]}"
            direction = ["Added", "📈", "📉", "deposited"]
        else:
            event_str += f"📭 {token_strings[1]} unwrapped to {token_strings[0]}"
            direction = ["Removed", "📉", "📈", "withdrawn"]

        wrapped_supply = token_to_float(spinto_client.get_supply(), wrapped_info.decimals)
        redeem_rate = spinto_client.get_redeem_rate()

        deposit_gspbdv = -1 + stalk_to_float(stalk_amount) / pinto_amount
        total_gspbdv = beanstalk_graph_client.get_account_gspbdv(wrapped_info.addr)
        gspbdv_avg_direction = direction[1] if deposit_gspbdv > total_gspbdv else direction[2]
        event_str += (
            f"\n> _🌱 {gspbdv_avg_direction} New average Grown Stalk per PDV: {round_num(total_gspbdv, precision=4)} "
            f"({direction[0]} {round_num(deposit_gspbdv, precision=4 if deposit_gspbdv != 0 else 0)} per {direction[3]} PDV)_"
            f"\n> _:SPINTO: {direction[1]} !{wrapped_info.symbol} Supply: {round_num(wrapped_supply, precision=0)}. "
            f"Redeems For {round_num(redeem_rate, precision=4)} !{underlying_info.symbol}_ "
        )

        bean_price = bean_client.avg_bean_price()
        event_str += f"\n{value_to_emojis(pinto_amount * bean_price)}"

    return event_str
