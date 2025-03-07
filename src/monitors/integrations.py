from bots.util import *
from data_access.contracts.bean import BeanClient
from data_access.contracts.beanstalk import BeanstalkClient
from data_access.contracts.integrations import WrappedDepositClient
from data_access.subgraphs.beanstalk import BeanstalkGraphClient
from monitors.monitor import Monitor
from data_access.contracts.util import *
from data_access.contracts.eth_events import *
from data_access.util import *
from constants.addresses import *
from constants.config import *
from tools.silo import StemTipCache, net_erc1155_transfers, unpack_address_and_stem
from web3.logs import DISCARD

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
        self.beanstalk_contract = get_beanstalk_contract(self._web3)

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
            owner = event_log.args.get("owner")
            pinto_amount = token_to_float(event_log.args.get("assets"), underlying_info.decimals)
            pinto_amount_str = round_token(event_log.args.get("assets"), underlying_info.decimals, underlying_info.addr)
            sPinto_amount_str = round_token(event_log.args.get("shares"), wrapped_info.decimals, wrapped_info.addr)

            # Determine whether the source/destination pinto is deposited, and how much stalk is involved
            is_deposited, stalk_amount = self._spinto_deposit_info(wrapped_info, owner, event_log)
            if_deposited_str = "Deposited " if is_deposited else ""

            token_strings = [
                f":{underlying_info.symbol}: {pinto_amount_str} {if_deposited_str}!{underlying_info.symbol}",
                f"{sPinto_amount_str} {wrapped_info.symbol}"
            ]
            if event_log.event == "Deposit":
                event_str += f"📥 {token_strings[0]} wrapped to {token_strings[1]}"
                direction = ["Added", "📈", "📉"]
            else:
                event_str += f"📭 {token_strings[1]} unwrapped to {token_strings[0]}"
                direction = ["Removed", "📉", "📈"]

            wrapped_supply = token_to_float(self.spinto_client.get_supply(), wrapped_info.decimals)
            redeem_rate = token_to_float(self.spinto_client.get_redeem_rate(), underlying_info.decimals)

            deposit_gspbdv = -1 + stalk_to_float(stalk_amount) / pinto_amount
            total_gspbdv = self.beanstalk_graph_client.get_account_gspbdv(wrapped_info.addr)
            gspbdv_avg_direction = direction[1] if deposit_gspbdv > total_gspbdv else direction[2]
            event_str += (
                f"\n> _🌱 {gspbdv_avg_direction} {direction[0]} {round_num(deposit_gspbdv, precision=4)} Grown Stalk per PDV. "
                f"New average: {round_num(total_gspbdv, precision=4)}_"
                f"\n> _:SPINTO: {direction[1]} !{wrapped_info.symbol} Supply: {round_num(wrapped_supply, precision=0)}. "
                f"Redeems For {round_num(redeem_rate, precision=4)} !{underlying_info.symbol}_ "
            )

            bean_price = self.bean_client.avg_bean_price()
            event_str += f"\n{value_to_emojis(pinto_amount * bean_price)}"

        return event_str

    def _spinto_deposit_info(self, wrapped_info, owner, event_log):
        """
        Returns whether the Pinto was already deposited, and the amount of stalk
        on the deposit which was added/removed to spinto
        """

        stalk = 0
        stem_tips = StemTipCache()
        farmer_transfers = net_erc1155_transfers(wrapped_info.addr, owner, event_log.receipt)
        if len(farmer_transfers) > 0:
            is_deposited = True
            evt_add_deposit = self.beanstalk_contract.events["AddDeposit"]().processReceipt(event_log.receipt, errors=DISCARD)
            # Silo wrap/unwrap: in both directions, use the IDs from 1155 transfer events
            for id in farmer_transfers:
                token, stem = unpack_address_and_stem(id)
                stem_tip = stem_tips.get_stem_tip(token)
                amount = abs(farmer_transfers[id])

                # Identify the corresponding AddDeposit event to get the associated bdv
                add_deposit = [evt for evt in evt_add_deposit if evt.args.get("token") == token and evt.args.get("stem") == stem and evt.args.get("amount") == amount]
                bdv = add_deposit[0].args.get("bdv")

                # Return stalk amount
                grown_stalk = bdv * (stem_tip - stem)
                stalk += bdv * 10 ** 10 + grown_stalk
        else:
            is_deposited = False
            # Direct wrap/unwrap are identifiable by no Transfer event between farmer and spinto
            if event_log.event == "Deposit":
                # Direct wrap: always brings zero grown stalk
                stalk = 10 ** 10 * event_log.args.get("assets")
            else:
                # Direct unwrap: analyze all of the Remove events after the final AddDeposit event
                evt_add_deposit = self.beanstalk_contract.events["AddDeposit"]().processReceipt(event_log.receipt, errors=DISCARD)
                evt_remove_deposits = self.beanstalk_contract.events["RemoveDeposits"]().processReceipt(event_log.receipt, errors=DISCARD)

                max_deposit_idx = max(evt_add_deposit, key=lambda evt: evt.logIndex).logIndex
                evt_remove_deposits = [evt for evt in evt_remove_deposits if evt.logIndex > max_deposit_idx]

                for evt_remove in evt_remove_deposits:
                    token = evt_remove.args.get("token")
                    stem_tip = stem_tips.get_stem_tip(token)
                    for i in range(len(evt_remove.args.get("bdvs"))):
                        bdv = evt_remove.args.get("bdvs")[i]
                        grown_stalk = bdv * (stem_tip - evt_remove.args.get("stems")[i])
                        stalk += bdv * 10 ** 10 + grown_stalk

        return is_deposited, stalk
