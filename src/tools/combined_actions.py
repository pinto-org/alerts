from bots.util import get_logs_by_names
from data_access.contracts.erc20 import get_erc20_info
from data_access.contracts.eth_events import EthEventsClient, EventClientType
from data_access.contracts.util import bean_to_float, pods_to_float, token_to_float

class WithdrawAndSow:
    def __init__(self, withdraw_token, withdraw_amount, beans_sown, pods_received):
        self.withdraw_token_info = get_erc20_info(withdraw_token)
        self.withdraw_amount = token_to_float(withdraw_amount, self.withdraw_token_info.decimals)
        self.beans_sown = bean_to_float(beans_sown)
        self.pods_received = pods_to_float(pods_received)
        self.temperature = 100 * (self.pods_received / self.beans_sown - 1)

def withdraw_sow_info(receipt):
    beanstalk_evt_client = EthEventsClient([EventClientType.BEANSTALK, EventClientType.WELL])

    txn_logs = beanstalk_evt_client.logs_from_receipt(receipt)
    sow_logs = get_logs_by_names("Sow", txn_logs)
    if len(sow_logs) != 1:
        return None



    pass

