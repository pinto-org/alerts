import datetime
import re
from bots.util import round_num, round_token, value_to_emojis
from data_access.contracts.bean import BeanClient
from data_access.contracts.erc20 import get_amount_burned, get_amount_minted, get_burn_logs, get_erc20_info, get_mint_logs
from data_access.contracts.integrations import CurveSpectraClient, WrappedDepositClient
from data_access.contracts.util import get_block, get_erc20_transfer_logs, token_to_float
from tools.util import topic_to_address

def spectra_pool_str(event_log, spectra_pool):
    pool_client = CurveSpectraClient(spectra_pool, block_number=event_log.blockNumber)
    spinto_client = WrappedDepositClient(spectra_pool.ibt, spectra_pool.underlying, block_number=event_log.blockNumber)
    bean_client = BeanClient(block_number=event_log.blockNumber)

    token_infos = [get_erc20_info(spectra_pool.ibt), get_erc20_info(spectra_pool.pt)]
    underlying_erc20_info = get_erc20_info(spectra_pool.underlying)
    ibt_erc20_info = get_erc20_info(spectra_pool.ibt)

    ibt_to_pt_rate = pool_client.get_ibt_to_pt_rate()
    ibt_to_underlying_rate = spinto_client.get_redeem_rate()
    underlying_to_pt_rate = ibt_to_pt_rate / ibt_to_underlying_rate

    underlying_price = bean_client.avg_bean_price()
    ibt_price = ibt_to_underlying_rate * underlying_price
    pt_price = ibt_price / ibt_to_pt_rate
    yt_price = ibt_price - pt_price

    msg_case = 0
    if event_log.event == "TokenExchange":
        # (0) Fixed yield 10%: 100 -> 110 pinto (bought 110 PT-spinto with 90 spinto)
        # (1) Exited fixed yield: sold 1000 PT-spinto for 900 spinto (910 pinto)
        # (2) Exited leveraged yield: sold 1050 YT-spinto for 100 spinto
        # (3) Leveraged yield 10.5x: bought 1050 YT-spinto for 100 spinto
        sold_id = event_log.args.get("sold_id")
        tokens_sold = event_log.args.get("tokens_sold")
        bought_id = event_log.args.get("bought_id")
        tokens_bought = event_log.args.get("tokens_bought")

        tokens_sold_str = f"{round_token(tokens_sold, token_infos[sold_id].decimals, token_infos[sold_id].addr)} {token_infos[sold_id].symbol}"
        tokens_bought_str = f"{round_token(tokens_bought, token_infos[bought_id].decimals, token_infos[bought_id].addr)} {token_infos[bought_id].symbol}"

        apy_direction = "📉" if sold_id == 0 else "📈"
        if sold_id == 0:
            value = ibt_price * token_to_float(tokens_sold, token_infos[0].decimals)
        if sold_id == 1:
            msg_case += 1
            value = ibt_price * token_to_float(tokens_bought, token_infos[0].decimals)

        # Check if YT was minted/burned. The pool swap is enough to determine the direction
        yt_amount = get_amount_minted(spectra_pool.yt, event_log.receipt) + get_amount_burned(spectra_pool.yt, event_log.receipt)
        if yt_amount > 0:
            msg_case += 2
            yt_erc20_info = get_erc20_info(spectra_pool.yt)
            yt_amount_str = f"{round_token(yt_amount, yt_erc20_info.decimals, yt_erc20_info.addr)} {yt_erc20_info.symbol}"

        if msg_case <= 1:
            ibt_underlying = (tokens_sold if msg_case == 0 else tokens_bought) * ibt_to_underlying_rate
            # Intentionally uses sold token decimals and underlying address. This is because tokens_sold is in terms of
            # the ibt, and ibt_to_underlying_rate does not have decimals applied.
            ibt_underlying_str = round_token(ibt_underlying, token_infos[sold_id].decimals, underlying_erc20_info.addr)

        if msg_case == 0:
            pt_underlying = tokens_bought
            pt_underlying_str = round_token(pt_underlying, token_infos[bought_id].decimals, token_infos[bought_id].addr)
            event_str = (
                f"🔒📥 Fixed yield {round_num((pt_underlying / ibt_underlying - 1) * 100, 2)}%: :{underlying_erc20_info.symbol}: {ibt_underlying_str} -> {pt_underlying_str} {underlying_erc20_info.symbol} "
                f"(bought {tokens_bought_str} with {tokens_sold_str})"
            )
        elif msg_case == 1:
            event_str = f"🔒📤 Exited fixed yield: sold {tokens_sold_str} for {tokens_bought_str} ({ibt_underlying_str} {underlying_erc20_info.symbol})"
        elif msg_case == 2:
            # the controlling contract is the one which minted PT/YT in this txn
            controller = topic_to_address(get_burn_logs(spectra_pool.yt, event_log.receipt)[0].topics[1])
            # Identify how much ibt is sent where the receiver is neither PT nor the pool (goes to user or is burned)
            ibt_from_controller = get_erc20_transfer_logs(spectra_pool.ibt, event_log.receipt, sender=controller)
            base_ibt_amount = int([log for log in ibt_from_controller if topic_to_address(log.topics[2]) not in [spectra_pool.pt, spectra_pool.pool]][0].data, 16)
            base_ibt_amount_str = f"{round_token(base_ibt_amount, ibt_erc20_info.decimals, ibt_erc20_info.addr)} {ibt_erc20_info.symbol}"
            event_str = f"⚡📤 Exited leveraged yield: sold {yt_amount_str} for {base_ibt_amount_str}"
        elif msg_case == 3:
            # the controlling contract is the one which minted PT/YT in this txn
            controller = topic_to_address(get_mint_logs(spectra_pool.yt, event_log.receipt)[0].topics[2])
            # Identify how much ibt is received where the sender is neither PT nor the pool (comes from user or a new mint)
            ibt_from_controller = get_erc20_transfer_logs(spectra_pool.ibt, event_log.receipt, recipient=controller)
            base_ibt_amount = int([log for log in ibt_from_controller if topic_to_address(log.topics[1]) not in [spectra_pool.pt, spectra_pool.pool]][0].data, 16)
            base_ibt_amount_str = f"{round_token(base_ibt_amount, ibt_erc20_info.decimals, ibt_erc20_info.addr)} {ibt_erc20_info.symbol}"

            yt_to_ibt_ratio = token_to_float(yt_amount, yt_erc20_info.decimals) / token_to_float(base_ibt_amount, ibt_erc20_info.decimals)
            event_str = f"⚡📥 Leveraged yield {round_num(yt_to_ibt_ratio, 1)}x: bought {yt_amount_str} for {base_ibt_amount_str}"

        event_str += f" ({round_num(value, 0, avoid_zero=True, incl_dollar=True)})"
        maturity_str = "Matures" if msg_case < 2 else "Expires"
    else:
        if event_log.event == "RemoveLiquidityOne":
            token_idx = event_log.args.get("coin_index")
            token_amount = event_log.args.get("coin_amount")

            if token_idx == 0:
                value = ibt_price * token_to_float(token_amount, token_infos[0].decimals)
            else:
                value = pt_price * token_to_float(token_amount, token_infos[1].decimals)

            tokens_removed_str = f"{round_token(token_amount, token_infos[token_idx].decimals, token_infos[token_idx].addr)} {token_infos[token_idx].symbol}"
            event_str = f"📤 LP removed - {tokens_removed_str} ({round_num(value, 0, avoid_zero=True, incl_dollar=True)})"
            apy_direction = "📈" if token_idx == 0 else "📉"
        else:
            token_amounts = event_log.args.get("token_amounts")

            token_strs = [f"{round_token(token_amounts[i], token_infos[i].decimals, token_infos[i].addr)} {token_infos[i].symbol}" for i in range(2)]
            dynamic = ["📥", "added"] if event_log.event == "AddLiquidity" else ["📤", "removed"]

            value = ibt_price * token_to_float(token_amounts[0], token_infos[0].decimals) + pt_price * token_to_float(token_amounts[1], token_infos[1].decimals)
            event_str = (
                f"{dynamic[0]} LP {dynamic[1]} - {' and '.join(token_strs)}"
                f" ({round_num(value, 0, avoid_zero=True, incl_dollar=True)})"
            )
            # TODO: can infer the direction according to whether the added proportion was higher or lower than
            # the computed apr in subinfo.
            apy_direction = "📊"
            if event_log.event == "AddLiquidity":
                pt_minted = get_amount_minted(spectra_pool.pt, event_log.receipt)
                if pt_minted > 0:
                    pt_minted = get_amount_minted(spectra_pool.pt, event_log.receipt)
                    pt_erc20_info = get_erc20_info(spectra_pool.pt)
                    pt_amount_str = f"{round_token(pt_minted, pt_erc20_info.decimals, pt_erc20_info.addr)} {pt_erc20_info.symbol}"
                    pt_value = pt_price * token_to_float(pt_minted, pt_erc20_info.decimals)

                    yt_minted = get_amount_minted(spectra_pool.yt, event_log.receipt)
                    yt_erc20_info = get_erc20_info(spectra_pool.yt)
                    yt_amount_str = f"{round_token(yt_minted, yt_erc20_info.decimals, yt_erc20_info.addr)} {yt_erc20_info.symbol}"
                    yt_value = yt_price * token_to_float(yt_minted, yt_erc20_info.decimals)

                    event_str += (
                        f"\n> _🪙 Minted {pt_amount_str} to pool ({round_num(pt_value, 0, avoid_zero=True, incl_dollar=True)})_"
                        f"\n> _🪙 Minted {yt_amount_str} to wallet ({round_num(yt_value, 0, avoid_zero=True, incl_dollar=True)})_"
                    )

        maturity_str = "Matures"

    # Subinfo
    timestamp = get_block(block_number=event_log.blockNumber).timestamp
    event_dt = datetime.datetime.fromtimestamp(timestamp, datetime.timezone.utc)
    hours_to_maturity = (spectra_pool.maturity - event_dt).total_seconds() / (60 * 60)
    apr = ((underlying_to_pt_rate - 1) / hours_to_maturity) * 24 * 365
    event_str += f"\n> _{apy_direction} Implied apr: {round_num(apr * 100, 2)}%. {maturity_str} in {round_num(hours_to_maturity / 24, 0)} days_"

    event_str += f"\n{value_to_emojis(value)}"

    return _remove_expiry_symbol(event_str)

def _remove_expiry_symbol(event_str):
    """Removes the expiry timestamp portion from the token symbol, i.e. PT-sPINTO-1758153782"""
    return re.sub(r'(\b(?:Y|P)T-.+)-\d{8,}\b', r'\1', event_str)
