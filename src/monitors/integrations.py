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
from tools.spinto import spinto_deposit_info

class IntegrationsMonitor(Monitor):
    """Monitors various external contracts interacting with beanstalk."""

    def __init__(self, msg_spinto, prod=False, dry_run=None):
        super().__init__(
            "Integrations", None, BEANSTALK_CHECK_RATE, prod=prod, dry_run=dry_run
        )
        self.msg_spinto = msg_spinto
        self._eth_event_client = EthEventsClient(EventClientType.INTEGRATIONS)
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
        bean_client = BeanClient(block_number=event_log.blockNumber)

        event_str = ""

        underlying_asset = self.spinto_client.get_underlying_asset()
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

            wrapped_supply = token_to_float(self.spinto_client.get_supply(), wrapped_info.decimals)
            redeem_rate = token_to_float(self.spinto_client.get_redeem_rate(), underlying_info.decimals)

            deposit_gspbdv = -1 + stalk_to_float(stalk_amount) / pinto_amount
            total_gspbdv = self.beanstalk_graph_client.get_account_gspbdv(wrapped_info.addr)
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
