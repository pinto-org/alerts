from math import log
from bots.util import *
from data_access.contracts.erc20 import get_erc20_info
from data_access.subgraphs.beanstalk import BeanstalkGraphClient
from monitors.messages.tractor import cancel_blueprint_str, publish_requisition_str, tractor_str
from monitors.monitor import Monitor
from data_access.contracts.util import *
from data_access.contracts.eth_events import *
from data_access.contracts.bean import BeanClient
from data_access.contracts.beanstalk import BeanstalkClient
from data_access.util import *
from constants.addresses import *
from constants.config import *

from tools.combined_actions import withdraw_sow_info
from tools.silo import net_deposit_withdrawal_stalk
from tools.spinto import has_spinto_action_size
from concurrent.futures import ThreadPoolExecutor

from tools.util import detached_future_done

class BeanstalkMonitor(Monitor):
    """Monitor the Beanstalk contract for events."""

    def __init__(self, msg_silo, msg_field, msg_tractor, prod=False, dry_run=None):
        super().__init__(
            "Beanstalk", None, BEANSTALK_CHECK_RATE, prod=prod, dry_run=dry_run
        )
        self.msg_silo = msg_silo
        self.msg_field = msg_field
        self.msg_tractor = msg_tractor
        self._eth_event_client = EthEventsClient([EventClientType.BEANSTALK])
        self.beanstalk_contract = get_beanstalk_contract()
        self.tractor_executor = ThreadPoolExecutor(max_workers=30)

    def _monitor_method(self):
        self.last_check_time = 0
        while self._thread_active:
            if time.time() < self.last_check_time + self.query_rate:
                time.sleep(0.5)
                continue
            self.last_check_time = time.time()
            for txn_pair in self._eth_event_client.get_new_logs(dry_run=self._dry_run):
                if len(txn_pair.logs):
                    try:
                        self._handle_txn_logs(txn_pair.logs)
                    except Exception as e:
                        logging.info(f"\n\n=> Exception during processing of txnHash {txn_pair.txn_hash.hex()}\n")
                        raise

    def _handle_txn_logs(self, event_logs):
        """Process the beanstalk event logs for a single txn.

        Note that Event Log Object is not the same as Event object.
        """

        receipt = event_logs[0].receipt
        logIndex = event_logs[0].logIndex

        # Handle tractor logs in a separate thread. API access can have a significant delay.
        tractor_logs = get_logs_by_names(["PublishRequisition", "CancelBlueprint", "Tractor"], event_logs)
        if tractor_logs:
            future = self.tractor_executor.submit(self.handle_tractor_logs, tractor_logs)
            future.add_done_callback(detached_future_done(receipt.transactionHash.hex()))

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
                        f"Ignoring a {earn_event_log.event} AddDeposit event {receipt.transactionHash.hex()}"
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
            if not is_lambda:
                self.msg_silo(msg)
            return
        # Else handle txn logs individually using default strings.

        # Determine net deposit/withdraw of each account/token, removing relevant events from the log list
        net_deposits = net_deposit_withdrawal_stalk(event_logs=event_logs, remove_from_logs=True)

        for account in net_deposits:
            for token in net_deposits[account]:
                event_str = self.silo_event_str(account, token, net_deposits[account][token], receipt, logIndex)
                if event_str:
                    self.msg_silo(event_str)

        for event_log in event_logs:
            event_str = self.field_event_str(event_log)
            if event_str:
                self.msg_field(event_str)

    def handle_tractor_logs(self, tractor_logs):
        for evt in tractor_logs:
            if evt.event == "PublishRequisition":
                self.msg_tractor(publish_requisition_str(evt))
            elif evt.event == "CancelBlueprint":
                self.msg_tractor(cancel_blueprint_str(evt))
            elif evt.event == "Tractor":
                self.msg_tractor(tractor_str(evt))
    
    def silo_event_str(self, account, token_addr, values, receipt, logIndex):
        """Logs a Silo Deposit/Withdraw"""
        beanstalk_client = BeanstalkClient(block_number=receipt.blockNumber)
        bean_client = BeanClient(block_number=receipt.blockNumber)

        # If there is an sPinto deposit or withdrawal event using the same amount, ignore this event
        if has_spinto_action_size(receipt, values["amount"]):
            return ""

        token_info = get_erc20_info(token_addr)
        amount = token_to_float(abs(values["amount"]), token_info.decimals)

        event_str = ""
        if values["amount"] > 0:
            event_str += f"📥 Silo Deposit"
        elif values["amount"] < 0:
            event_str += f"📭 Silo Withdrawal"
        else:
            return ""

        # Use current bdv rather than the deposited bdv reported in the event
        bean_price = bean_client.avg_bean_price()
        value = abs(bean_to_float(values["bdv"])) * bean_price

        event_str += f" - {round_num(amount, precision=2, avoid_zero=True)} {token_info.symbol}"
        event_str += f" ({round_num(value, 0, avoid_zero=True, incl_dollar=True)})"

        subinfo = []
        if values["stalk"] > 0:
            subinfo.append(f"Stalk Minted: {round_num(stalk_to_float(values['stalk']), 0, avoid_zero=True)}")
        else:
            subinfo.append(f"Stalk Burned: {round_num(stalk_to_float(-values['stalk']), 0, avoid_zero=True)}")

        total_stalk = beanstalk_client.get_total_stalk()
        subinfo.append(f"Total Stalk: {round_num(total_stalk, 0)}")

        event_str += f"\n_{'. '.join(subinfo)}_"

        # Extra info if this is withdraw/sow
        sow = withdraw_sow_info(receipt, logIndex)
        if sow:
            event_str += f"\n> 🌾 Sowed in the Field for {sow.pods_received_str} Pods at {sow.temperature_str} Temperature"

        event_str += f"\n{value_to_emojis(value)}"
        event_str += links_footer(receipt, farmer=account)
        return event_str


    def field_event_str(self, event_log):
        if event_log.event not in ["Sow", "Harvest"]:
            return ""

        beanstalk_client = BeanstalkClient(block_number=event_log.blockNumber)
        beanstalk_graph_client = BeanstalkGraphClient(block_number=event_log.blockNumber)
        bean_client = BeanClient(block_number=event_log.blockNumber)
        event_str = ""

        beans_amount = bean_to_float(event_log.args.get("beans"))
        pods_amount = bean_to_float(event_log.args.get("pods"))

        bean_price = bean_client.avg_bean_price()
        beans_value = beans_amount * bean_price

        if event_log.event == "Sow":
            effective_temp = (pods_amount / beans_amount - 1) * 100
            max_temp = beanstalk_client.get_max_temp()
            current_soil = beanstalk_client.get_current_soil()
            is_morning = True
            if abs(effective_temp - max_temp) < 0.01:
                effective_temp = max_temp
                is_morning = False
            is_tractor = bool(self.beanstalk_contract.events["Tractor"]().processReceipt(event_log.receipt, errors=DISCARD))

            emoji = "🚜" if is_tractor else "⛏️"
            event_str += (
                f"{emoji} {round_num(beans_amount, 0, avoid_zero=True)} Pinto Sown for "
                f"{round_num(pods_amount, 0, avoid_zero=True)} Pods "
                f"at {round_num_abbreviated(beanstalk_client.get_podline_length(), precision=3)} in Line "
                f"({round_num(beans_value, 0, avoid_zero=True, incl_dollar=True)})"
                f"\n🧑‍🌾 Farmer has {round_num_abbreviated(beanstalk_graph_client.get_farmer_pod_count(event_log.args.account), precision=1)} Pods"
            )
            event_str += (
                f"\n_Sow Temperature: {round_num(effective_temp, precision=2)}% "
                f"(Max: {round_num(max_temp, precision=2)}%). "
                f"Remaining Soil: {round_num(current_soil, precision=(0 if current_soil > 2 else 2))}_"
            )
            if is_morning:
                pods_saved = beans_amount * (max_temp - effective_temp) / 100
                event_str += f"\n> 🌅 {round_num(pods_saved, 0, avoid_zero=True)} fewer Pods minted due to Morning sow"

            # Extra info if this is withdraw/sow
            sow = withdraw_sow_info(event_log.receipt, event_log.logIndex)
            if sow:
                withdraw_token = Web3.to_checksum_address(sow.withdraw_token_info.addr)
                direction = "📈" if withdraw_token != BEAN_ADDR else "📊"

                event_str += f"\n> 📭 Sowed using :{sow.withdraw_token_info.symbol.upper()}: {sow.withdraw_amount_str} Deposited !{sow.withdraw_token_info.symbol}"
                event_str += f"\n> :PINTO:{direction} _{latest_pool_price_str(bean_client, BEAN_ADDR)}_"
                if withdraw_token != BEAN_ADDR:
                    event_str += f"\n> :{sow.withdraw_token_info.symbol.upper()}:{direction} _{latest_pool_price_str(bean_client, withdraw_token)}_"

            event_str += f"\n{value_to_emojis(beans_value)}"
        elif event_log.event == "Harvest":
            harvest_amt_str = round_num(beans_amount, 0, avoid_zero=True)
            harvest_amt_str = f"{harvest_amt_str} Pods" if harvest_amt_str != "1" else f"{harvest_amt_str} Pod"
            event_str += f"👩‍🌾 {harvest_amt_str} Harvested for Pinto ({round_num(beans_value, 0, avoid_zero=True, incl_dollar=True)})"
            event_str += f"\n{value_to_emojis(beans_value)}"

        event_str += links_footer(event_log.receipt, farmer=event_log.args.account)
        return event_str

    def silo_conversion_str(self, event_logs):
        """
        Returns string, boolean
        boolean indicates whether this is a lambda convert
        """
        bean_client = BeanClient(block_number=event_logs[0].blockNumber)

        bean_price = bean_client.avg_bean_price()
        # Find the relevant logs, should contain one RemoveDeposit and one AddDeposit.
        # print(event_logs)
        # in silo v3 AddDeposit event will always be present and these will always get set
        bdv_float = 0
        value = 0
        penalty_bonus_str = None
        account = None
        for event_log in event_logs:
            if event_log.event == "AddDeposit":
                bdv_float = bean_to_float(event_log.args.get("bdv"))
                value = bdv_float * bean_price
            elif event_log.event == "Convert":
                remove_token_addr = event_log.args.get("fromToken")
                _, _, remove_token_symbol, remove_decimals = get_erc20_info(remove_token_addr).parse()
                add_token_addr = event_log.args.get("toToken")
                _, _, add_token_symbol, add_decimals = get_erc20_info(add_token_addr).parse()
                remove_amount = event_log.args.get("fromAmount")
                add_amount = event_log.args.get("toAmount")
                account = event_log.args.get("account")
            elif event_log.event == "ConvertDownPenalty":
                stalk_penalized = stalk_to_float(event_log.args.grownStalkLost)
                if stalk_penalized > 0:
                    stalk_not_penalized = stalk_to_float(event_log.args.grownStalkKept)
                    penalty_percent = 100 * stalk_penalized / (stalk_penalized + stalk_not_penalized)

                    penalty_bonus_str = (
                        f"🌱🔥 {round_num(stalk_penalized, 0, avoid_zero=True)} Mown Stalk burned from penalty "
                        f"({round_num(penalty_percent, 2, avoid_zero=True)}%)"
                    )

        if remove_token_addr == BEAN_ADDR:
            direction_emojis = ["⬇️", "📉"]
        elif add_token_addr == BEAN_ADDR:
            direction_emojis = ["⬆️", "📈"]
        else:
            # LP convert is harder to identify direction, requires future subgraph work.
            direction_emojis = ["", ""]

        event_str = (
            f"🔄 {direction_emojis[0]} {round_token(remove_amount, remove_decimals, remove_token_addr)} {remove_token_symbol} "
            f"Converted to {round_token(add_amount, add_decimals, add_token_addr)} {add_token_symbol} "
            f"({round_num(bdv_float, 0)} PDV)"
        )

        if penalty_bonus_str:
            event_str += f"\n_{penalty_bonus_str}_"

        event_str += f"\n> :PINTO:{direction_emojis[1]} _{latest_pool_price_str(bean_client, BEAN_ADDR)}_"
        # If regular convert, identifies the non-bean address
        # If LP convert, both are added with the removed token coming first
        if remove_token_addr in [*WHITELISTED_WELLS, *DEWHITELISTED_WELLS]:
            event_str += f"\n> :{remove_token_symbol.upper()}:{direction_emojis[1]} _{latest_pool_price_str(bean_client, remove_token_addr)}_"
        if add_token_addr in [*WHITELISTED_WELLS, *DEWHITELISTED_WELLS]:
            event_str += f"\n> :{add_token_symbol.upper()}:{direction_emojis[1]} _{latest_pool_price_str(bean_client, add_token_addr)}_"

        if not remove_token_addr.startswith(UNRIPE_TOKEN_PREFIX):
            event_str += f"\n{value_to_emojis(value)}"

        event_str += links_footer(event_logs[0].receipt, farmer=account)
        # Indicate whether this is lambda convert
        return event_str, add_token_addr == remove_token_addr

    def rinse_str(self, event_logs):
        bean_client = BeanClient(block_number=event_logs[0].blockNumber)

        bean_amount = 0.0
        for event_log in event_logs:
            if event_log.event == "ClaimFertilizer":
                bean_amount += bean_to_float(event_log.args.beans)
        # Ignore rinses with essentially no beans bc they are clutter, especially on transfers.
        if bean_amount < 1:
            return ""
        bean_price = bean_client.avg_bean_price()
        event_str = f"💦 Sprouts Rinsed - {round_num(bean_amount,0)} Sprouts ({round_num(bean_amount * bean_price, 0, avoid_zero=True, incl_dollar=True)})"
        event_str += f"\n{value_to_emojis(bean_amount * bean_price)}"

        event_str += links_footer(event_logs[0].receipt)
        return event_str
