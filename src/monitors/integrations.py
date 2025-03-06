from bots.util import *
from data_access.contracts.bean import BeanClient
from data_access.contracts.integrations import WrappedDepositClient
from data_access.subgraphs.beanstalk import BeanstalkGraphClient
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
        self.spinto_client = WrappedDepositClient(SPINTO_ADDR)
        self.beanstalk_graph_client = BeanstalkGraphClient()

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
            # sPinto integration
            if event_log.address == SPINTO_ADDR:
                event_str = self.spinto_str(event_log)
                if not event_str:
                    continue
                event_str += links_footer(event_logs[0].receipt)
                self.msg_spinto(event_str)

    def spinto_str(self, event_log):
        event_str = ""

        underlying_asset = self.spinto_client.get_underlying_asset()
        underlying_info = get_erc20_info(underlying_asset)
        wrapped_info = get_erc20_info(event_log.address)

        if event_log.event == "Deposit" or event_log.event == "Withdraw":
            # owner = event_log.args.get("owner")
            pinto_amount = token_to_float(event_log.args.get("assets"), underlying_info.decimals)
            pinto_amount_str = round_token(event_log.args.get("assets"), underlying_info.decimals, underlying_info.addr)
            sPinto_amount_str = round_token(event_log.args.get("shares"), wrapped_info.decimals, wrapped_info.addr)

            token_strings = [
                f":{underlying_info.symbol}: {pinto_amount_str} Deposited !{underlying_info.symbol}",
                f"{sPinto_amount_str} {wrapped_info.symbol}"
            ]
            if event_log.event == "Deposit":
                event_str += f"📥 {token_strings[0]} wrapped to {token_strings[1]}"
            else:
                event_str += f"📭 {token_strings[1]} unwrapped to {token_strings[0]}"

            wrapped_supply = token_to_float(self.spinto_client.get_supply(), wrapped_info.decimals)
            redeem_rate = token_to_float(self.spinto_client.get_redeem_rate(), underlying_info.decimals)
            gspbdv = self.beanstalk_graph_client.get_account_gspbdv(wrapped_info.addr)
            event_str += (
                f"\n_{wrapped_info.symbol} Supply: {round_num(wrapped_supply, precision=0)}. "
                f"Redeems For {round_num(redeem_rate, precision=4)} !{underlying_info.symbol}. "
                f"{round_num(gspbdv, precision=4)} Grown Stalk per PDV_"
            )

            bean_price = self.bean_client.avg_bean_price()
            event_str += f"\n{value_to_emojis(pinto_amount * bean_price)}"

        return event_str

    def _spinto_moved_deposit_stalk():
        """Returns the amount of stalk on the deposit which was added/removed to spinto"""
        # Silo wrap/unwrap: in both directions of that case you want to look for the
        # TransferBatch event. then extract the IDs. Then from the IDs you can extract the Stem

        # Direct wrap/unwrap are identifiable by no Transfer event from farmer to spinto
        # Direct wrap: always brings zero stalk
        # Direct unwrap: analyze all of the Remove events after the last AddDeposit event
