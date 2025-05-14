from bots.util import round_num, round_token, value_to_emojis
from data_access.contracts.beanstalk import BeanstalkClient
from data_access.contracts.erc20 import get_erc20_info
from data_access.contracts.integrations import MorphoClient

def morpho_market_str(event_logs, market):
    morpho_client = MorphoClient(market, block_number=event_logs[0].blockNumber)
    beanstalk_client = BeanstalkClient(block_number=event_logs[0].blockNumber)

    market_data = morpho_client.get_market_data()
    utilization = market_data.get_utilization_rate()
    liquidity = market_data.get_available_liquidity()
    borrow_apy, supply_apy = morpho_client.get_inst_rates(market_data)
    erc20_supply = get_erc20_info(market.loanToken)
    erc20_collateral = get_erc20_info(market.collateralToken)

    event_str = ""
    value = 0
    emojis = None

    for event_log in event_logs:
        if event_log.event in ["Supply", "Withdraw"]:
            value = max(value, get_tokens_value(event_log.args.assets, erc20_supply, beanstalk_client))
            dyn = ["📥 🏦 Added", "📉", "📈"] if event_log.event == "Supply" else ["📤 🏦 Removed", "📈", "📉"]
            event_str += f"{dyn[0]} market liquidity: {round_token(event_log.args.assets, erc20_supply.decimals, erc20_supply.addr)} {erc20_supply.symbol}\n"
        elif event_log.event in ["SupplyCollateral", "WithdrawCollateral"]:
            value = max(value, get_tokens_value(event_log.args.assets, erc20_collateral, beanstalk_client))
            dyn = ["📥 🛡️ Increased", "📊", "📊"] if event_log.event == "SupplyCollateral" else ["📤 ⚡️ Decreased", "📊", "📊"]
            event_str += (
                f"{dyn[0]} collateral by {round_token(event_log.args.assets, erc20_collateral.decimals, erc20_collateral.addr)} {erc20_collateral.symbol} "
                f"({round_num(value, 0, avoid_zero=True, incl_dollar=True)})\n"
            )
        elif event_log.event in ["Borrow", "Repay"]:
            value = max(value, get_tokens_value(event_log.args.assets, erc20_supply, beanstalk_client))
            dyn = ["📤 ⚡️ Borrowed", "📈", "📉"] if event_log.event == "Borrow" else ["📥 🛡️ Repaid", "📉", "📈"]
            event_str += f"{dyn[0]} {round_token(event_log.args.assets, erc20_supply.decimals, erc20_supply.addr)} {erc20_supply.symbol}\n"
        elif event_log.event == "Liquidate":
            value = max(value, get_tokens_value(event_log.args.seizedAssets, erc20_collateral, beanstalk_client))
            dyn = [None, "📉", "📈"]
            event_str += (
                f"🚨 🫣 Liquidated {round_token(event_log.args.seizedAssets, erc20_collateral.decimals, erc20_collateral.addr)} {erc20_collateral.symbol} "
                f"({round_num(value, 0, avoid_zero=True, incl_dollar=True)}) "
                f"to repay {round_token(event_log.args.repaidAssets, erc20_supply.decimals, erc20_supply.addr)} {erc20_supply.symbol}\n"
            )

        # Rate-affecting event takes precedence over collateral event
        if emojis is None or emojis[0] == "📊":
            emojis = dyn[1:]

    if event_log.event != "Liquidate":
        account = event_log.args.get("onBehalf")
    else:
        account = event_log.args.get("borrower")

    account_position = get_position_info(morpho_client, market_data, account)

    if event_log.event in ["SupplyCollateral", "WithdrawCollateral", "Borrow", "Repay", "Liquidate"]:
        position_str = (
            f"_New Position LTV: {round_num(account_position['ltv'] * 100, 2)}% / {round_num(market.lltv * 100, 2)}%. "
            f"Collateral: {round_token(account_position['collateral'], erc20_collateral.decimals, erc20_collateral.addr)} {erc20_collateral.symbol}. "
            f"Borrowing: {round_token(account_position['borrowed'], erc20_supply.decimals, erc20_supply.addr)} {erc20_supply.symbol} _"
        )
    else:
        position_str = (
            f"_Account is supplying {round_token(account_position['supplied'], erc20_supply.decimals, erc20_supply.addr)} {erc20_supply.symbol} _"
        )

    market_state_str = (
        f"\n> {emojis[0]} Utilization: {round_num(utilization * 100, 2)}%, "
        f"Borrow APY: {round_num(borrow_apy * 100, 2)}%, "
        f"Supply APY: {round_num(supply_apy * 100, 2)}%"
        f"\n> {emojis[1]} Available !{erc20_supply.symbol} to borrow: :{erc20_supply.symbol}: {round_token(liquidity, erc20_supply.decimals, erc20_supply.addr)}"
    )

    event_str += position_str + market_state_str
    event_str += f"\n{value_to_emojis(value)}"

    return event_str, account

# Gets detailed info about this account's position
def get_position_info(morpho_client, market_data, account):
    position = morpho_client.get_account_position(account)
    oracle_price = morpho_client.get_oracle_price()

    supply_amount = int(position.supply_shares * market_data.total_supply_assets / market_data.total_supply_shares)
    borrowed_amount = int(position.borrow_shares * market_data.total_borrow_assets / market_data.total_borrow_shares)
    collateral_value_in_loan_token = position.collateral * oracle_price / 10**36
    ltv = borrowed_amount / collateral_value_in_loan_token

    return {
        "supplied": supply_amount,
        "borrowed": borrowed_amount,
        "collateral": position.collateral,
        "ltv": ltv,
    }

def get_tokens_value(amount, erc20_info, beanstalk_client):
    return amount * beanstalk_client.get_token_usd_price(erc20_info.addr) / 10 ** erc20_info.decimals
