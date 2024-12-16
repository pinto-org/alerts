from bots.util import *
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
        well_liquidity_str: Optional[str] = None,
    ):
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
    def __init__(self, message_function, ignorelist, discord=False, prod=False, dry_run=None):
        super().__init__("wells", message_function, WELL_CHECK_RATE, prod=prod, dry_run=dry_run)
        self._ignorelist = ignorelist
        self._discord = discord
        self._eth_aquifer = EthEventsClient(EventClientType.AQUIFER, AQUIFER_ADDR)
        # All addresses
        self._eth_all_wells = EthEventsClient(EventClientType.WELL)
        self.basin_graph_client = BasinGraphClient()
        self.bean_client = BeanClient()
    
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
                        self.message_function(event_str)
            for txn_pair in self._eth_all_wells.get_new_logs(dry_run=self._dry_run):
                for event_log in txn_pair.logs:
                    # Avoids double-reporting on whitelisted wells having a dedicated channel
                    if event_log.get("address") not in self._ignorelist:
                        event_data = parse_event_data(event_log, self.basin_graph_client, self.bean_client, web3=self._web3)
                        event_str = well_event_str(event_data, txn_pair.txn_hash.hex())
                        if event_str:
                            self.message_function(event_str)

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

    def __init__(self, message_function, addresses, bean_reporting=False, prod=False, dry_run=None):
        super().__init__(f"specific well", message_function, WELL_CHECK_RATE, prod=prod, dry_run=dry_run)
        self.pool_addresses = addresses
        self._eth_event_client = EthEventsClient(EventClientType.WELL, self.pool_addresses)
        self.basin_graph_client = BasinGraphClient()
        self.bean_client = BeanClient()
        self.bean_reporting = bean_reporting

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
        """Process the well event logs for a single txn."""

        logging.info(f"Handling txn logs for hash {event_logs}")

        # Convert alerts should appear in both exchange + silo event channels, but don't doublepost in telegram
        is_convert = event_sig_in_txn(BEANSTALK_EVENT_MAP["Convert"], txn_hash)
        to_tg = self.bean_reporting is False or not is_convert 

        for event_log in event_logs:
            if event_log.get("address") in self.pool_addresses:
                event_data = parse_event_data(event_log, self.basin_graph_client, self.bean_client, web3=self._web3)
                event_str = well_event_str(event_data, txn_hash.hex(), self.bean_reporting, is_convert=is_convert)
                if event_str:
                    self.message_function(event_str, to_tg=to_tg)

def parse_event_data(event_log, basin_graph_client, bean_client, web3=None):
    retval = WellEventData()
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
        retval.bdv = token_to_float(lpAmountOut, WELL_LP_DECIMALS) * get_constant_product_well_lp_bdv(
            retval.well_address, web3=web3
        )
    elif event_log.event == "Sync":
        retval.event_type = "LP"
        deposit = basin_graph_client.try_get_well_deposit_info(
            event_log.transactionHash, event_log.logIndex
        )
        if deposit:
            retval.value = float(deposit["amountUSD"])
            retval.token_amounts_in = deposit["reserves"]
        else:
            # Redundancy in case subgraph is not available
            retval.bdv = token_to_float(
                lpAmountOut, WELL_LP_DECIMALS
            ) * get_constant_product_well_lp_bdv(retval.well_address, web3=web3)
    elif event_log.event == "RemoveLiquidity" or event_log.event == "RemoveLiquidityOneToken":
        retval.event_type = "LP"
        if event_log.event == "RemoveLiquidityOneToken":
            for i in range(len(retval.well_tokens)):
                if tokenOut == retval.well_tokens[i]:
                    retval.token_amounts_out.append(tokenAmountOut)
                else:
                    retval.token_amounts_out.append(0)
        else:
            retval.token_amounts_out = tokenAmountsOut[i]

        retval.bdv = token_to_float(lpAmountIn, WELL_LP_DECIMALS) * get_constant_product_well_lp_bdv(
            retval.well_address, web3=web3
        )
    elif event_log.event == "Swap":
        retval.event_type = "SWAP"
        if retval.token_in == BEAN_ADDR:
            retval.bdv = bean_to_float(retval.amount_in)
        elif retval.token_out == BEAN_ADDR:
            retval.bdv = bean_to_float(retval.amount_out)
    elif event_log.event == "Shift":
        shift_from_token = retval.well_tokens[0] if retval.well_tokens[1] == retval.token_out else retval.well_tokens[1]

        if shift_from_token == WETH:
            retval.amount_in = get_eth_sent(event_log.transactionHash, retval.well_address, web3, event_log.logIndex)
        else:
            retval.amount_in = get_tokens_sent(shift_from_token, event_log.transactionHash, retval.well_address, event_log.logIndex)

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

    retval.well_price_str = latest_pool_price_str(bean_client, retval.well_address)
    retval.well_liquidity_str = latest_well_lp_str(basin_graph_client, retval.well_address)
    return retval

    
def well_event_str(event_data: WellEventData, txn_hash, bean_reporting=False, is_convert=False):

    event_str = ""

    is_lpish = False
    is_swapish = False

    remove_lp_icon = "🔄" if is_convert else "📤"
    add_lp_icon = "🔄" if is_convert else "📥"

    if event_data.event_type == "LP":
        is_lpish = True
        if event_data.token_amounts_in is not None:
            event_str += f"{add_lp_icon} LP added - "
            token_amounts = event_data.token_amounts_in
        else:
            event_str += f"{remove_lp_icon} LP removed - "
            token_amounts = event_data.token_amounts_out

        for i in range(len(event_data.well_tokens)):
            erc20_info = get_erc20_info(event_data.well_tokens[i])
            event_str += f"{round_token(token_amounts[i], erc20_info.decimals, erc20_info.addr)} {erc20_info.symbol}"
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
            event_str += f"📗 {amount_out_str} {erc20_info_out.symbol} bought for {amount_in_str} {erc20_info_in.symbol} @ ${round_num(event_data.value/bean_to_float(event_data.amount_out), 4)} "
        elif bean_reporting and erc20_info_in.symbol == "PINTO":
            event_str += f"📕 {amount_in_str} {erc20_info_in.symbol} sold for {amount_out_str} {erc20_info_out.symbol} @ ${round_num(event_data.value/bean_to_float(event_data.amount_in), 4)} "
        else:
            event_str += (
                f"🔁 {amount_in_str} {erc20_info_in.symbol} swapped "
                f"for {amount_out_str} {erc20_info_out.symbol} "
            )

    if event_data.value is not None and event_data.value != 0:
        event_str += f"({round_num(event_data.value, 0, avoid_zero=True, incl_dollar=True)})"
        if (is_swapish or is_lpish) and bean_reporting:
            event_str += f"\n_{event_data.well_price_str}_ "
        if is_lpish and not bean_reporting:
            event_str += f"\n_{event_data.well_liquidity_str}_ "
        event_str += f"\n{value_to_emojis(event_data.value)}"

    event_str += f"\n<https://basescan.org/tx/{txn_hash}>"
    # Empty line that does not get stripped.
    event_str += "\n_ _"
    return event_str
