from bots.util import get_logs_by_names, round_num, round_token
from constants.addresses import BEAN_ADDR
from data_access.contracts.erc20 import get_erc20_info
from data_access.contracts.eth_events import EthEventsClient, EventClientType
from data_access.contracts.util import bean_to_float, pods_to_float, token_to_float
from tools.silo import net_deposit_withdrawal_stalk

class WithdrawAndSow:
    def __init__(self, withdraw_token, withdraw_amount, beans_sown, pods_received):
        self.withdraw_token_info = get_erc20_info(withdraw_token)
        self.withdraw_amount = token_to_float(withdraw_amount, self.withdraw_token_info.decimals)
        self.beans_sown = bean_to_float(beans_sown)
        self.pods_received = pods_to_float(pods_received)
        self.temperature = 100 * (self.pods_received / self.beans_sown - 1)

        self.withdraw_amount_str = round_token(withdraw_amount, self.withdraw_token_info.decimals, self.withdraw_token_info.addr)
        self.pods_received_str = round_num(self.pods_received, 0, avoid_zero=True)
        self.temperature_str = f"{round_num(self.temperature, 2)}%"

def withdraw_sow_info(receipt):
    """
    Identifies whether this transaction contains a simple withdrawal/sow. Does not match
    multiple withdrawaled tokens, multiple sows, or sowing from both a withdraw and external capital
    """
    beanstalk_evt_client = EthEventsClient([EventClientType.BEANSTALK, EventClientType.WELL])

    txn_logs = beanstalk_evt_client.logs_from_receipt(receipt)
    sow_logs = get_logs_by_names("Sow", txn_logs)
    if len(sow_logs) != 1:
        return None
    sow_amount = sow_logs[0].args.beans

    # Amount doesnt need to match if its tractor; guaranteed to be withdraw/sow
    is_tractor = len(get_logs_by_names("Tractor", txn_logs)) > 0

    net_withdrawal = net_deposit_withdrawal_stalk(txn_logs)
    # TODO: handle multiple accounts. Determine which account according to Tractor evt
    if len(net_withdrawal) == 0:
        return None
    net_withdrawal = next(iter(net_withdrawal.values()))
    if len(net_withdrawal) != 1:
        return None

    withdrawal_token = next(iter(net_withdrawal))
    withdrawal_amount = abs(net_withdrawal[withdrawal_token]["amount"])

    # Verify amount of sow
    if withdrawal_token == BEAN_ADDR:
        if not is_tractor and sow_amount != withdrawal_amount:
            return None
    else:
        # Check amount of beans removed on LP removal
        remove_liq_logs = get_logs_by_names("RemoveLiquidityOneToken", txn_logs)
        if (
            len(remove_liq_logs) != 1 or
            remove_liq_logs[0].args.lpAmountIn != withdrawal_amount or
            remove_liq_logs[0].args.tokenOut != BEAN_ADDR or
            (not is_tractor and remove_liq_logs[0].args.tokenAmountOut != sow_amount)
        ):
            return None

    return WithdrawAndSow(withdrawal_token, withdrawal_amount, sow_amount, sow_logs[0].args.pods)
