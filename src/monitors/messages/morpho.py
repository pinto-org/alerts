import logging
from bots.util import round_num, round_token
from data_access.contracts.erc20 import get_erc20_info
from data_access.contracts.integrations import MorphoClient

def morpho_market_str(event_log, market):
    # TODO: Consider how to format messages when multiple occur together (i.e. add collateral and borrow)
    morpho_client = MorphoClient(market, block_number=event_log.blockNumber)

    market_data = morpho_client.get_market_data()
    utilization = market_data.get_utilization_rate()
    liquidity = market_data.get_available_liquidity()
    borrow_apy, supply_apy = morpho_client.get_inst_rates(market_data)
    erc20_supply = get_erc20_info(market.loanToken)
    erc20_collateral = get_erc20_info(market.collateralToken)

    logging.info(f"Utilization: {utilization}, Liquidity: {liquidity}, Borrow APY: {borrow_apy}, Supply APY: {supply_apy}")

    if event_log.event != "Liquidate":
        account = event_log.args.get("onBehalf")
    else:
        account = event_log.args.get("borrower")

    account_position = get_position_info(morpho_client, market_data, account)

    if event_log.event in ["SupplyCollateral", "WithdrawCollateral", "Borrow", "Repay", "Liquidate"]:
        position_str = (
            f"_New Position LTV: {round_num(account_position['ltv'] * 100, 2)}% / {round_num(market.lltv * 100, 2)}%. "
            f"Total borrow: {round_token(account_position['borrowed'], erc20_supply.decimals, erc20_supply.addr)} {erc20_supply.symbol}_"
        )
    else:
        position_str = (
            f"_Account is supplying {round_token(account_position['supplied'], erc20_supply.decimals, erc20_supply.addr)} {erc20_supply.symbol}_"
        )

    market_state_str = (
        f"\n> _Utilization: {round_num(utilization * 100, 2)}%, "
        f"Borrow APY: {round_num(borrow_apy * 100, 2)}%, "
        f"Supply APY: {round_num(supply_apy * 100, 2)}%_"
        f"\n> Available !{erc20_supply.symbol} to borrow: :{erc20_supply.symbol}: {round_token(liquidity, erc20_supply.decimals, erc20_supply.addr)}"
    )

    return position_str + market_state_str
    # logging.info(position_str + market_state_str)
    # logging.info(f"Account: {account}, Supplied: {account_position['supplied']}, Borrowed: {account_position['borrowed']}, Collateral: {account_position['collateral']}, LTV: {account_position['ltv']}")

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
