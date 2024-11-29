from bots.util import *
from monitors.monitor import Monitor
from data_access.contracts.util import *
from data_access.contracts.eth_events import *
from data_access.contracts.bean import BeanClient
from data_access.contracts.beanstalk import BeanstalkClient
from data_access.util import *
from constants.addresses import *
from constants.config import *

from collections import defaultdict

class BeanstalkMonitor(Monitor):
    """Monitor the Beanstalk contract for events."""

    def __init__(self, msg_silo, msg_field, prod=False, dry_run=None):
        super().__init__(
            "Beanstalk", None, BEANSTALK_CHECK_RATE, prod=prod, dry_run=dry_run
        )
        self.msg_silo = msg_silo
        self.msg_field = msg_field
        self._eth_event_client = EthEventsClient(EventClientType.BEANSTALK)
        self.bean_client = BeanClient()
        self.beanstalk_client = BeanstalkClient()

    def _monitor_method(self):
        last_check_time = 0
        while self._thread_active:
            if time.time() < last_check_time + self.query_rate:
                time.sleep(0.5)
                continue
            last_check_time = time.time()
            for txn_pair in self._eth_event_client.get_new_logs(dry_run=self._dry_run):
                self._handle_txn_logs(txn_pair.txn_hash, txn_pair.logs)

    def _handle_txn_logs(self, txn_hash, event_logs):
        """Process the beanstalk event logs for a single txn.

        Note that Event Log Object is not the same as Event object.
        """

        if event_in_logs("L1DepositsMigrated", event_logs):
            # Ignore AddDeposit as a result of contract migrating silo
            remove_events_from_logs_by_name("AddDeposit", event_logs)

        # For each earn (plant/pick) event log remove a corresponding AddDeposit log.
        for earn_event_log in get_logs_by_names(["Plant", "Pick"], event_logs):
            for deposit_event_log in get_logs_by_names("AddDeposit", event_logs):
                if deposit_event_log.args.get("token") == (
                    earn_event_log.args.get("token") or BEAN_ADDR
                ) and deposit_event_log.args.get("amount") == (
                    earn_event_log.args.get("beans") or earn_event_log.args.get("amount")
                ):
                    # Remove event log from event logs
                    event_logs.remove(deposit_event_log)
                    # At most allow 1 match.
                    logging.info(
                        f"Ignoring a {earn_event_log.event} AddDeposit event {txn_hash.hex()}"
                    )
                    break

        if event_in_logs("ClaimFertilizer", event_logs):
            event_str = self.rinse_str(event_logs)
            if event_str:
                self.msg_silo(event_str)
            remove_events_from_logs_by_name("ClaimFertilizer", event_logs)

        # Process conversion logs as a batch.
        if event_in_logs("Convert", event_logs):
            msg, is_lambda = self.silo_conversion_str(event_logs)
            self.msg_silo(msg, to_main=not is_lambda)
            return
        # Else handle txn logs individually using default strings.

        # Determine net deposit/withdraw of each token
        net_deposits = defaultdict(int)
        silo_deposit_logs = get_logs_by_names(["AddDeposit", "RemoveDeposit", "RemoveDeposits"], event_logs)
        for event_log in silo_deposit_logs:
            sign = 1 if event_log.event == "AddDeposit" else -1
            token_address = event_log.args.get("token")
            token_amount_long = event_log.args.get("amount")
            net_deposits[token_address] += sign * token_amount_long
            event_logs.remove(event_log)
        
        # logging.info(f"net token amounts {net_deposits}")
        for token in net_deposits:
            event_str = self.silo_event_str(token, net_deposits[token], txn_hash)
            if event_str:
                self.msg_silo(event_str)

        for event_log in event_logs:
            event_str = self.field_event_str(event_log)
            if event_str:
                self.msg_field(event_str)
    
    def silo_event_str(self, token_addr, net_amount, txn_hash):
        """Logs a Silo Deposit/Withdraw"""

        event_str = ""

        if net_amount > 0:
            event_str += f"📥 Silo Deposit"
        elif net_amount < 0:
            event_str += f"📭 Silo Withdrawal"
        else:
            return ""

        bean_price = self.bean_client.avg_bean_price()
        token_info = get_erc20_info(token_addr)
        amount = token_to_float(abs(net_amount), token_info.decimals)

        # Use current bdv rather than the deposited bdv reported in the event
        bdv = amount * self.beanstalk_client.get_bdv(token_info)

        value = None
        if bdv > 0:
            value = bdv * bean_price

        event_str += f" - {round_num(amount, precision=2, avoid_zero=True)} {token_info.symbol}"
        # Some legacy events may not set BDV, skip valuation. Also do not value unripe assets.
        if value is not None and not token_addr.startswith(UNRIPE_TOKEN_PREFIX):
            event_str += f" ({round_num(value, 0, avoid_zero=True, incl_dollar=True)})"
            event_str += f"\n{value_to_emojis(value)}"

        event_str += f"\n<https://basescan.org/tx/{txn_hash.hex()}>"
        # Empty line that does not get stripped.
        event_str += "\n_ _"
        return event_str


    def field_event_str(self, event_log):
        """Create a string representing a single event log.

        Events that are from a convert call should not be passed into this function as they
        should be processed in batch.
        """

        event_str = ""
        bean_price = self.bean_client.avg_bean_price()

        # Ignore these events
        if event_log.event in ["RemoveWithdrawal", "RemoveWithdrawals" "Plant", "Pick", "L1DepositsMigrated"]:
            return ""
        # Sow event.
        elif event_log.event in ["Sow", "Harvest"]:
            # Pull args from the event log.
            beans_amount = bean_to_float(event_log.args.get("beans"))
            beans_value = beans_amount * bean_price
            pods_amount = bean_to_float(event_log.args.get("pods"))

            if event_log.event == "Sow":
                event_str += (
                    f"🚜 {round_num(beans_amount, 0, avoid_zero=True)} Pinto Sown for "
                    f"{round_num(pods_amount, 0, avoid_zero=True)} Pods ({round_num(beans_value, 0, avoid_zero=True, incl_dollar=True)})"
                )
                effective_temp = round((pods_amount / beans_amount - 1) * 100, 1)
                max_temp = self.beanstalk_client.get_max_temp()
                current_soil = self.beanstalk_client.get_current_soil()
                if int(effective_temp) == int(max_temp):
                    effective_temp = int(effective_temp)
                event_str += f"\n_Sow Temperature: {round_num(effective_temp, precision=0)}% (Max: {round_num(max_temp, precision=0)}%). Remaining Soil: {round_num(current_soil, precision=0)}_"
                event_str += f"\n{value_to_emojis(beans_value)}"
            elif event_log.event == "Harvest":
                harvest_amt_str = round_num(beans_amount, 0, avoid_zero=True)
                harvest_amt_str = f"{harvest_amt_str} Pods" if harvest_amt_str != "1" else f"{harvest_amt_str} Pod"
                event_str += f"👩‍🌾 {harvest_amt_str} Harvested for Pinto ({round_num(beans_value, 0, avoid_zero=True, incl_dollar=True)})"
                event_str += f"\n{value_to_emojis(beans_value)}"

        # Unknown event type.
        else:
            # logging.warning(
            #     f"Unexpected event log from Beanstalk contract ({event_log}). Ignoring."
            # )
            return ""

        event_str += f"\n<https://basescan.org/tx/{event_log.transactionHash.hex()}>"
        # Empty line that does not get stripped.
        event_str += "\n_ _"
        return event_str

    def silo_conversion_str(self, event_logs):
        """
        Returns string, boolean
        boolean indicates whether this is a lambda convert
        """
        bean_price = self.bean_client.avg_bean_price()
        # Find the relevant logs, should contain one RemoveDeposit and one AddDeposit.
        # print(event_logs)
        # in silo v3 AddDeposit event will always be present and these will always get set
        bdv_float = 0
        value = 0
        for event_log in event_logs:
            if event_log.event == "AddDeposit":
                bdv_float = bean_to_float(event_log.args.get("bdv"))
                value = bdv_float * bean_price
            elif event_log.event == "Convert":
                remove_token_addr = event_log.args.get("fromToken")
                _, _, remove_token_symbol, remove_decimals = get_erc20_info(
                    remove_token_addr, web3=self._web3
                ).parse()
                add_token_addr = event_log.args.get("toToken")
                _, _, add_token_symbol, add_decimals = get_erc20_info(
                    add_token_addr, web3=self._web3
                ).parse()
                remove_amount = event_log.args.get("fromAmount")
                add_amount = event_log.args.get("toAmount")

        # If both tokens are lp, use the to token (add_token)
        # Otherwise use whichever one is an lp token
        pool_token = BEAN_ADDR
        if add_token_addr in WHITELISTED_WELLS:
            pool_token = remove_token_addr
        elif remove_token_addr in WHITELISTED_WELLS:
            pool_token = add_token_addr

        event_str = (
            f"🔄 {round_token(remove_amount, remove_decimals, remove_token_addr)} {remove_token_symbol} "
            f"Converted to {round_token(add_amount, add_decimals, add_token_addr)} {add_token_symbol} "
        )

        event_str += f"({round_num(bdv_float, 0)} BDV)"
        event_str += f"\n_{latest_pool_price_str(self.bean_client, pool_token)}_ "
        if not remove_token_addr.startswith(UNRIPE_TOKEN_PREFIX):
            event_str += f"\n{value_to_emojis(value)}"
        event_str += f"\n<https://basescan.org/tx/{event_logs[0].transactionHash.hex()}>"
        # Empty line that does not get stripped.
        event_str += "\n_ _"
        # Indicate whether this is lambda convert
        return event_str, add_token_addr == remove_token_addr

    def rinse_str(self, event_logs):
        bean_amount = 0.0
        for event_log in event_logs:
            if event_log.event == "ClaimFertilizer":
                bean_amount += bean_to_float(event_log.args.beans)
        # Ignore rinses with essentially no beans bc they are clutter, especially on transfers.
        if bean_amount < 1:
            return ""
        bean_price = self.bean_client.avg_bean_price()
        event_str = f"💦 Sprouts Rinsed - {round_num(bean_amount,0)} Sprouts ({round_num(bean_amount * bean_price, 0, avoid_zero=True, incl_dollar=True)})"
        event_str += f"\n{value_to_emojis(bean_amount * bean_price)}"
        event_str += f"\n<https://basescan.org/tx/{event_logs[0].transactionHash.hex()}>"
        return event_str
