from bots.util import *
from data_access.contracts.bean import BeanClient
from monitors.monitor import Monitor
from data_access.contracts.util import *
from data_access.contracts.eth_events import *
from data_access.util import *
from constants.addresses import *
from constants.config import *

class IntegrationsMonitor(Monitor):
    """Monitors various external contracts interacting with beanstalk."""

    def __init__(self, msg_spinto, prod=False, dry_run=None):
        super().__init__(
            "Integrations", None, BEANSTALK_CHECK_RATE, prod=prod, dry_run=dry_run
        )
        self.msg_spinto = msg_spinto
        self._eth_event_client = EthEventsClient(EventClientType.INTEGRATIONS)
        self.bean_client = BeanClient()

    def _monitor_method(self):
        last_check_time = 0
        while self._thread_active:
            if time.time() < last_check_time + self.query_rate:
                time.sleep(0.5)
                continue
            last_check_time = time.time()
            for txn_pair in self._eth_event_client.get_new_logs(dry_run=self._dry_run):
                try:
                    self._handle_txn_logs(txn_pair.logs)
                except Exception as e:
                    logging.info(f"\n\n=> Exception during processing of txnHash {txn_pair.txn_hash.hex()}\n")
                    raise

    def _handle_txn_logs(self, event_logs):
        for event_log in event_logs:
            if event_log.address == SPINTO_ADDR:
                event_str = self.spinto_str(event_log)
                if not event_str:
                    continue
                event_str += links_footer(event_logs[0].receipt)
                self.msg_spinto(event_str)

    def spinto_str(self, event_log):
        event_str = ""

        token_info = get_erc20_info(event_log.address)

        # assets/shares
        if event_log.event == "Deposit" or event_log.event == "Withdraw":
            assets = round_token(event_log.args.get("assets"), BEAN_DECIMALS, BEAN_ADDR)
            shares = round_token(event_log.args.get("shares"), token_info.decimals, SPINTO_ADDR)

            if event_log.event == "Deposit":
                emoji = "📥"
                direction = "wrapped to"
            else:
                emoji = "📭"
                direction = "unwrapped from"

            event_str += f"{emoji} :PINTO: {assets} Deposited !PINTO {direction} {shares} {token_info.symbol}"

            bean_price = self.bean_client.avg_bean_price()
            event_str += f"\n{value_to_emojis(assets * bean_price)}"

        return event_str
