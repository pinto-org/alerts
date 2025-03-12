from collections import defaultdict
from bots.util import *
from data_access.contracts.beanstalk import BeanstalkClient
from monitors.monitor import Monitor
from data_access.contracts.util import *
from data_access.contracts.eth_events import *
from data_access.contracts.bean import BeanClient
from data_access.contracts.well import WellClient
from data_access.subgraphs.basin import BasinGraphClient
from data_access.util import *
from constants.addresses import *
from constants.config import *

from typing import List, Optional
class WellEventData:
    def __init__(
        self,
        receipt = None,
        event_type: Optional[str] = None,
        well_address: Optional[str] = None,
        well_tokens: Optional[List[str]] = None,
        token_in: Optional[str] = None,
        token_out: Optional[str] = None,
        token_amounts_in: Optional[List[int]] = None,
        token_amounts_out: Optional[List[int]] = None,
        amount_in: Optional[int] = None,
        amount_out: Optional[int] = None,
        bdv: Optional[float] = None,
        value: Optional[float] = None,
        well_price_str: Optional[str] = None,
        well_liquidity_str: Optional[str] = None
    ):
        self.receipt = receipt
        self.event_type = event_type
        self.well_address = well_address
        self.well_tokens = well_tokens
        self.token_in = token_in
        self.token_out = token_out
        self.token_amounts_in = token_amounts_in
        self.token_amounts_out = token_amounts_out
        self.amount_in = amount_in
        self.amount_out = amount_out
        self.bdv = bdv
        self.value = value
        self.well_price_str = well_price_str
        self.well_liquidity_str = well_liquidity_str

# Monitors all wells except those in the ignorelist
class OtherWellsMonitor(Monitor):
    def __init__(self, msg_exchange, msg_arbitrage, ignorelist, prod=False, dry_run=None):
        super().__init__("wells", None, WELL_CHECK_RATE, prod=prod, dry_run=dry_run)
        self.msg_exchange = msg_exchange
        self.msg_arbitrage = msg_arbitrage
        self._ignorelist = ignorelist
        self._eth_aquifer = EthEventsClient(EventClientType.AQUIFER, AQUIFER_ADDR)
        # All addresses
        self._eth_all_wells = EthEventsClient(EventClientType.WELL)
    
    def _monitor_method(self):
        last_check_time = 0
        while self._thread_active:
            if time.time() < last_check_time + self.query_rate:
                time.sleep(0.5)
                continue
            last_check_time = time.time()
            for txn_pair in self._eth_aquifer.get_new_logs(dry_run=self._dry_run):
                for event_log in txn_pair.logs:
                    event_str = self.aquifer_event_str(event_log)
                    if event_str:
                        self.msg_exchange(event_str)
            for txn_pair in self._eth_all_wells.get_new_logs(dry_run=self._dry_run):
                prev_log_index = {}
                for event_log in txn_pair.logs:
                    # Avoids double-reporting on whitelisted wells having a dedicated channel
                    address = event_log.get("address")
                    if address not in self._ignorelist:
                        if address not in prev_log_index:
                            prev_log_index[address] = 0
                        event_data = parse_event_data(event_log, prev_log_index[address], web3=self._web3)
                        event_str = single_event_str(event_data)
                        if event_str:
                            self.msg_exchange(event_str)
                        prev_log_index[address] = event_log.logIndex

    def aquifer_event_str(self, event_log):
        if event_log.event == "BoreWell":
            well = event_log.args.get("well")
            tokens = event_log.args.get("tokens")

            erc20_info_0 = get_erc20_info(tokens[0])
            erc20_info_1 = get_erc20_info(tokens[1])

            def erc20_linkstr(info):
                result = f"[{info.symbol}](<https://basescan.org/address/{info.addr.lower()}>)"
                return result

            event_str = (
                f"New Well created - {erc20_linkstr(erc20_info_0)} / {erc20_linkstr(erc20_info_1)}"
                f"\n<https://pinto.exchange/#/wells/{well.lower()}>"
            )
            event_str += "\n_ _"
            return event_str

# Monitors a set of Wells that are output to the same channel
class WellsMonitor(Monitor):
    """Monitor Wells for events.

    This provides events in Beanstalk exchange channel as well as Basin per-well channels.

    NOTE assumption that all wells contain Bean. Valuation is done in BDV using the bean side of the trade to
         directly determine value.
    ^^ make this assumption less strict, instead only skip valuation if no BDV
    """

    def __init__(self, msg_exchange, msg_arbitrage, addresses, arbitrage_senders=[], bean_reporting=False, prod=False, dry_run=None):
        super().__init__(f"specific well", None, WELL_CHECK_RATE, prod=prod, dry_run=dry_run)
        self.msg_exchange = msg_exchange
        self.msg_arbitrage = msg_arbitrage
        self.pool_addresses = addresses
        self.arbitrage_senders = arbitrage_senders
        self._eth_event_client = EthEventsClient(EventClientType.WELL, self.pool_addresses)
        self.bean_reporting = bean_reporting

    def _monitor_method(self):
        last_check_time = 0
        while self._thread_active:
            if time.time() < last_check_time + self.query_rate:
                time.sleep(0.5)
                continue
            last_check_time = time.time()
            for txn_pair in self._eth_event_client.get_new_logs(dry_run=self._dry_run):
                try:
                    self._handle_txn_logs(txn_pair.txn_hash, txn_pair.logs)
                except Exception as e:
                    logging.info(f"\n\n=> Exception during processing of txnHash {txn_pair.txn_hash.hex()}\n")
                    raise

    def _handle_txn_logs(self, txn_hash, event_logs):
        """Process the well event logs for a single txn."""

        # Convert alerts should appear in both exchange + silo event channels, but don't doublepost in telegram
        is_convert = event_sig_in_txn(BEANSTALK_EVENT_MAP["Convert"], txn_hash)
        to_tg = self.bean_reporting is False or not is_convert 

        individual_evts: List[WellEventData] = []
        prev_log_index = {}
        for event_log in event_logs:
            address = event_log.get("address")
            if address in self.pool_addresses:
                if address not in prev_log_index:
                    prev_log_index[address] = 0
                individual_evts.append(
                    parse_event_data(
                        event_log,
                        prev_log_index[address],
                        web3=self._web3
                    )
                )
                prev_log_index[address] = event_log.logIndex

        # Identify a fully arbitrage trade: all are swaps and sum of all bought/sold pinto are equal
        sum_pinto = 0
        abs_sum_pinto = 0
        trades = 0
        for i in range(len(individual_evts)):
            evt = individual_evts[i]
            if evt.event_type not in ["SWAP", "SHIFT"]:
                break
            if evt.token_out == BEAN_ADDR:
                sum_pinto += evt.amount_out
                abs_sum_pinto += evt.amount_out
            elif evt.token_in == BEAN_ADDR:
                sum_pinto -= evt.amount_in
                abs_sum_pinto += evt.amount_in
            trades += 1

        if trades > 0 and abs_sum_pinto == 0:
            return

        # Is considered full arbitrage even if the pinto amount mismatches by less than .1%. Some traders move
        # light pinto profits into their trading contract.
        if trades >= 2 and sum_pinto / abs_sum_pinto < 0.001:
            # This trade is pure arbitrage and can be consolidated into a single message
            event_str = pure_arbitrage_event_str(individual_evts)
            self.msg_arbitrage(event_str, to_tg=to_tg)
            return

        # Identify arbitrage trades or LP converts
        i = 0
        while i < len(individual_evts) - 1:
            evt1 = individual_evts[i]
            j = i + 1
            while j < len(individual_evts):
                evt2 = individual_evts[j]
                # 2 well arbitrage trade: Swap/Shift where subsequent trades are selling tokens bought in earlier ones
                # This is still identified in addition to the previous arbitrage case to account for more complex interactions
                if (
                    evt1.event_type in ["SWAP", "SHIFT"] and evt2.event_type in ["SWAP", "SHIFT"]
                    and evt1.token_out == evt2.token_in and evt1.amount_out == evt2.amount_in
                ):
                    del individual_evts[j]
                    del individual_evts[i]
                    event_str = arbitrage_event_str(evt1, evt2)
                    self.msg_arbitrage(event_str, to_tg=to_tg)
                    break
                # Moving LP (LP convert): LP removal that is followed by LP addition
                elif (
                    evt1.event_type == "LP" and evt1.token_amounts_in is None
                    and evt2.event_type == "LP" and evt2.token_amounts_in is not None
                ):
                    del individual_evts[j]
                    del individual_evts[i]
                    event_str = move_lp_event_str(evt1, evt2, is_convert=is_convert)
                    self.msg_exchange(event_str, to_tg=to_tg)
                    break
                else:
                    j += 1
            else:
                i += 1

        # Normal case
        for event_data in individual_evts:
            event_str = single_event_str(event_data, self.bean_reporting, is_convert=is_convert)
            if event_str:
                if event_log.receipt["from"] not in self.arbitrage_senders or event_data.bdv > 2000:
                    self.msg_exchange(event_str, to_tg=to_tg)
                else:
                    self.msg_arbitrage(event_str, to_tg=to_tg)

def parse_event_data(event_log, prev_log_index, web3=get_web3_instance()):
    bean_client = BeanClient(block_number=event_log.blockNumber)
    basin_graph_client = BasinGraphClient(block_number=event_log.blockNumber)

    retval = WellEventData()
    retval.receipt = event_log.receipt
    retval.well_address = event_log.get("address")

    # Parse possible values of interest from the event log. Not all will be populated.
    # Liquidity
    tokenAmountsIn = event_log.args.get("tokenAmountsIn")  # int[]
    lpAmountIn = event_log.args.get("lpAmountIn")
    tokenOut = event_log.args.get("tokenOut")
    tokenAmountOut = event_log.args.get("tokenAmountOut")
    tokenAmountsOut = event_log.args.get("tokenAmountsOut")
    lpAmountOut = event_log.args.get("lpAmountOut")
    # Swaps
    retval.token_in = event_log.args.get("fromToken")
    retval.token_out = event_log.args.get("toToken")
    retval.amount_in = event_log.args.get("amountIn")
    retval.amount_out = event_log.args.get("amountOut")

    well_client = WellClient(retval.well_address)
    retval.well_tokens = well_client.tokens()

    if event_log.event == "AddLiquidity":
        if tokenAmountsIn[0] == 0 and tokenAmountsIn[1] == 0:
            # When we initialize a new Well, 2 transactions have to occur for the multi flow pump
            # to begin working, so usually we do this via an add liquidity with an amount of 0.
            return retval

        retval.event_type = "LP"
        retval.token_amounts_in = tokenAmountsIn
        retval.bdv = token_to_float(lpAmountOut, WELL_LP_DECIMALS) * get_constant_product_well_lp_bdv(retval.well_address)
    elif event_log.event == "Sync":
        retval.event_type = "LP"
        deposit = basin_graph_client.get_add_liquidity_info(event_log.transactionHash, event_log.logIndex)
        if deposit:
            retval.token_amounts_in = list(map(int, deposit["liqReservesAmount"]))
            retval.value = float(deposit["transferVolumeUSD"])
        else:
            # Redundancy in case subgraph is not available
            retval.bdv = token_to_float(
                lpAmountOut, WELL_LP_DECIMALS
            ) * get_constant_product_well_lp_bdv(retval.well_address)
    elif event_log.event == "RemoveLiquidity" or event_log.event == "RemoveLiquidityOneToken":
        retval.event_type = "LP"
        if event_log.event == "RemoveLiquidityOneToken":
            retval.token_amounts_out = []
            for i in range(len(retval.well_tokens)):
                if tokenOut == retval.well_tokens[i]:
                    retval.token_amounts_out.append(tokenAmountOut)
                else:
                    retval.token_amounts_out.append(0)
        else:
            retval.token_amounts_out = tokenAmountsOut

        retval.bdv = token_to_float(lpAmountIn, WELL_LP_DECIMALS) * get_constant_product_well_lp_bdv(retval.well_address)
    elif event_log.event == "Swap":
        retval.event_type = "SWAP"
        if retval.token_in == BEAN_ADDR:
            retval.bdv = bean_to_float(retval.amount_in)
        elif retval.token_out == BEAN_ADDR:
            retval.bdv = bean_to_float(retval.amount_out)
    elif event_log.event == "Shift":
        shift_from_token = retval.well_tokens[0] if retval.well_tokens[1] == retval.token_out else retval.well_tokens[1]

        # Finds amount of tokens transferred to/from the well since any prior trades in this well
        if shift_from_token == WETH:
            retval.amount_in = get_eth_sent(event_log.transactionHash, retval.well_address, web3, (prev_log_index + 1, event_log.logIndex))
        else:
            retval.amount_in = get_tokens_sent(shift_from_token, event_log.transactionHash, retval.well_address, (prev_log_index + 1, event_log.logIndex))

        if retval.token_out == BEAN_ADDR:
            retval.bdv = bean_to_float(retval.amount_out)
        elif shift_from_token == BEAN_ADDR:
            retval.bdv = bean_to_float(retval.amount_in)

        if retval.amount_in is not None and retval.amount_in > 0:
            # not None and not 0, then it is a pseudo swap
            retval.token_in = shift_from_token
            retval.event_type = "SWAP"
        else:
            # one sided shift
            retval.event_type = "SHIFT"

    if retval.bdv is not None:
        try:
            retval.value = retval.bdv * bean_client.avg_bean_price()
        except Exception as e:
            logging.warning(f"Price contract failed to return a value. No value is assigned to this event")

    retval.bean_price_str = latest_pool_price_str(bean_client, BEAN_ADDR)
    retval.well_price_str = latest_pool_price_str(bean_client, retval.well_address)
    retval.well_liquidity_str = latest_well_lp_str(basin_graph_client, retval.well_address)
    return retval
    
def single_event_str(event_data: WellEventData, bean_reporting=False, is_convert=False):
    event_str = ""

    is_lpish = False
    is_swapish = False

    direction = ""

    if event_data.event_type == "LP":
        is_lpish = True
        remove_lp_icon = "🔄 ⬆️" if is_convert else "📤"
        add_lp_icon = "🔄 ⬇️" if is_convert else "📥"
        if event_data.token_amounts_in is not None:
            event_str += f"{add_lp_icon} LP added - "
            token_amounts = event_data.token_amounts_in
            if token_amounts[0] > 0 and token_amounts[1] == 0:
                direction = "📉"
            elif token_amounts[0] == 0 and token_amounts[1] > 0:
                direction = "📈"
        elif event_data.token_amounts_out is not None:
            event_str += f"{remove_lp_icon} LP removed - "
            token_amounts = event_data.token_amounts_out
            if token_amounts[0] > 0 and token_amounts[1] == 0:
                direction = "📈"
            elif token_amounts[0] == 0 and token_amounts[1] > 0:
                direction = "📉"
        else:
            raise ValueError("LP event was missing token amounts")

        for i in range(len(event_data.well_tokens)):
            erc20_info = get_erc20_info(event_data.well_tokens[i])
            # token_amounts can be unavailable if subgraphs are unresponsive
            if token_amounts:
                event_str += f"{round_token(token_amounts[i], erc20_info.decimals, erc20_info.addr)} "
            event_str += f"{erc20_info.symbol}"
            if i < len(event_data.well_tokens) - 1:
                event_str += f" and"
            event_str += f" "
    else:
        if event_data.event_type == "SWAP":
            is_swapish = True
            erc20_info_in = get_erc20_info(event_data.token_in)
            erc20_info_out = get_erc20_info(event_data.token_out)
            amount_in_str = round_token(event_data.amount_in, erc20_info_in.decimals, erc20_info_in.addr)
            amount_out_str = round_token(event_data.amount_out, erc20_info_out.decimals, erc20_info_out.addr)
        elif event_data.event_type == "SHIFT":
            erc20_info_out = get_erc20_info(event_data.token_out)
            amount_out_str = round_token(event_data.amount_out, erc20_info_out.decimals, erc20_info_out.addr)
            event_str += f"🔀 {amount_out_str} {erc20_info_out.symbol} shifted out "
        else:
            # Irrelevant event/invalid event data encountered
            return ""
        
    if is_swapish:
        if bean_reporting and erc20_info_out.symbol == "PINTO":
            event_str += f"📗 {amount_out_str} {erc20_info_out.symbol} bought for {amount_in_str} {erc20_info_in.symbol} "
            if event_data.amount_out != 0:
                event_str += f"@ ${round_num(event_data.value/bean_to_float(event_data.amount_out), 4)} "
            direction = "📈"
        elif bean_reporting and erc20_info_in.symbol == "PINTO":
            event_str += f"📕 {amount_in_str} {erc20_info_in.symbol} sold for {amount_out_str} {erc20_info_out.symbol} "
            if event_data.amount_in != 0:
                event_str += f"@ ${round_num(event_data.value/bean_to_float(event_data.amount_in), 4)} "
            direction = "📉"
        else:
            event_str += (
                f"🔁 {amount_in_str} {erc20_info_in.symbol} swapped "
                f"for {amount_out_str} {erc20_info_out.symbol} "
            )

    if event_data.value is not None and event_data.value != 0:
        event_str += f"({round_num(event_data.value, 0, avoid_zero=True, incl_dollar=True)})"
        if (is_swapish or is_lpish) and bean_reporting:
            event_str += (
                f"\n> :PINTO:{direction} _{event_data.bean_price_str}_"
                f"\n> :{SILO_TOKENS_MAP.get(event_data.well_address.lower()).upper()}:{direction} _{event_data.well_price_str}_"
            )
        if is_lpish and not bean_reporting:
            event_str += f"\n_{event_data.well_liquidity_str}_ "
        event_str += f"\n{value_to_emojis(event_data.value)}"

    event_str += links_footer(event_data.receipt)
    return event_str

def pure_arbitrage_event_str(all_events: List[WellEventData]):
    event_str = ""
    from_strs = []
    to_strs = []
    sum_bean = 0
    dollars_in = 0
    dollars_out = 0

    beanstalk_client = BeanstalkClient(block_number=all_events[0].receipt.blockNumber)

    # Sum totals of non-bean tokens in each well (the same well could be swapped in multiple times)
    from_tokens = defaultdict(int)
    to_tokens = defaultdict(int)
    encountered_wells = set()
    well_price_strs = []
    for i in range(len(all_events)):
        evt = all_events[i]
        # Identify from/to tokens (non-bean) and profits
        if evt.token_out == BEAN_ADDR:
            from_tokens[evt.token_in] += evt.amount_in
        elif evt.token_in == BEAN_ADDR:
            sum_bean += evt.amount_in
            to_tokens[evt.token_out] += evt.amount_out

        if i == 0:
            well_price_strs.append(f"> :PINTO:📊 _{evt.bean_price_str}_")
        direction = "📈" if evt.token_out == BEAN_ADDR else "📉"
        well = SILO_TOKENS_MAP.get(evt.well_address.lower())
        if well not in encountered_wells:
            encountered_wells.add(well)
            well_price_strs.append(f"> :{well.upper()}:{direction} _{evt.well_price_str}_")

    # Generate strings from totals
    for nbt in from_tokens:
        erc20_info = get_erc20_info(nbt)
        from_strs.append(f"{round_token(from_tokens[nbt], erc20_info.decimals, erc20_info.addr)} {erc20_info.symbol}")
        dollars_in += from_tokens[nbt] * beanstalk_client.get_token_usd_price(nbt) / 10 ** erc20_info.decimals

    for nbt in to_tokens:
        erc20_info = get_erc20_info(nbt)
        to_strs.append(f"{round_token(to_tokens[nbt], erc20_info.decimals, erc20_info.addr)} {erc20_info.symbol}")
        dollars_out += to_tokens[nbt] * beanstalk_client.get_token_usd_price(nbt) / 10 ** erc20_info.decimals

    bean_amount = round_token(sum_bean, 6, BEAN_ADDR)
    deltas_str = '\n'.join(well_price_strs)
    profit = dollars_out - dollars_in
    profit_str = f"{'+' if profit >= 0 else '-'}{round_num(abs(profit), 2, avoid_zero=False, incl_dollar=True)}"
    event_str += (
        f"{', '.join(from_strs)} exchanged for {', '.join(to_strs)}, using {bean_amount} PINTO ({profit_str})"
        f"\n{deltas_str}"
        f"\n{value_to_emojis(dollars_in + dollars_out)}"
    )
    event_str += links_footer(all_events[0].receipt)
    return event_str

def arbitrage_event_str(evt1: WellEventData, evt2: WellEventData):
    event_str = ""

    beanstalk_client = BeanstalkClient(block_number=evt1.receipt.blockNumber)

    erc20_info_in = get_erc20_info(evt1.token_in)
    erc20_info_out = get_erc20_info(evt2.token_out)
    erc20_info_arb = get_erc20_info(evt1.token_out)
    amount_in_str = round_token(evt1.amount_in, erc20_info_in.decimals, erc20_info_in.addr)
    amount_out_str = round_token(evt2.amount_out, erc20_info_out.decimals, erc20_info_out.addr)
    amount_arb_str = round_token(evt1.amount_out, erc20_info_arb.decimals, erc20_info_arb.addr)

    spend_amount = evt1.amount_in * beanstalk_client.get_token_usd_price(evt1.token_in) / 10 ** erc20_info_in.decimals
    receive_amount = evt2.amount_out * beanstalk_client.get_token_usd_price(evt2.token_out) / 10 ** erc20_info_out.decimals
    profit = receive_amount - spend_amount
    profit_str = f"{'+' if profit >= 0 else '-'}{round_num(abs(profit), 2, avoid_zero=False, incl_dollar=True)}"

    event_str += (
        f"{amount_in_str} {erc20_info_in.symbol} exchanged for {amount_out_str} {erc20_info_out.symbol}, "
        f"using {amount_arb_str} {erc20_info_arb.symbol} ({profit_str})"
        f"\n> :PINTO:📊 _{evt1.bean_price_str}_"
    )
    well1 = SILO_TOKENS_MAP.get(evt1.well_address.lower())
    well2 = SILO_TOKENS_MAP.get(evt2.well_address.lower())
    if well1 is not None:
        event_str += f"\n> :{well1.upper()}:📈 _{evt1.well_price_str}_"
    if well2 is not None:
        event_str += f"\n> :{well2.upper()}:📉 _{evt2.well_price_str}_"

    event_str += f"\n{value_to_emojis(evt1.value)}"

    event_str += links_footer(evt1.receipt)
    return event_str

def move_lp_event_str(evt1: WellEventData, evt2: WellEventData, is_convert=True):
    event_str = ""

    lead_icon = "🔄" if is_convert else "⚖️"

    well1 = SILO_TOKENS_MAP.get(evt1.well_address.lower())
    well2 = SILO_TOKENS_MAP.get(evt2.well_address.lower())
    if well1 is None:
        well1 = get_erc20_info(evt1.well_address).symbol
    if well2 is None:
        well2 = get_erc20_info(evt2.well_address).symbol

    erc20_tokens_removed = [get_erc20_info(evt1.well_tokens[0]), get_erc20_info(evt1.well_tokens[1])]
    erc20_tokens_added = [get_erc20_info(evt2.well_tokens[0]), get_erc20_info(evt2.well_tokens[1])]
    amounts_out_str = [
        round_token(evt1.token_amounts_out[0], erc20_tokens_removed[0].decimals, erc20_tokens_removed[0].addr),
        round_token(evt1.token_amounts_out[1], erc20_tokens_removed[1].decimals, erc20_tokens_removed[1].addr)
    ]
    amounts_in_str = [
        round_token(evt2.token_amounts_in[0], erc20_tokens_added[0].decimals, erc20_tokens_added[0].addr),
        round_token(evt2.token_amounts_in[1], erc20_tokens_added[1].decimals, erc20_tokens_added[1].addr) 
    ]

    event_str += (
        f"{lead_icon} LP moved from {well1} to {well2} ({round_num(evt2.value, 0, avoid_zero=True, incl_dollar=True)})"
        f"\n📤 {amounts_out_str[0]} {erc20_tokens_removed[0].symbol} and {amounts_out_str[1]} {erc20_tokens_removed[1].symbol}"
        f"\n📥 {amounts_in_str[0]} {erc20_tokens_added[0].symbol} and {amounts_in_str[1]} {erc20_tokens_added[1].symbol}"
        f"\n> :PINTO: _{evt1.bean_price_str}_"
        f"\n> :{well1.upper()}: _{evt1.well_price_str}_"
        f"\n> :{well2.upper()}: _{evt2.well_price_str}_"
        f"\n{value_to_emojis(evt2.value)}"
    )

    event_str += links_footer(evt1.receipt)
    return event_str
