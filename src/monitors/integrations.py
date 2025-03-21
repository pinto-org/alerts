import datetime
from bots.util import *
from constants.spectra import SPECTRA_SPINTO_POOLS
from data_access.contracts.bean import BeanClient
from data_access.contracts.erc20 import get_amount_burned, get_amount_minted, get_erc20_info, get_mint_logs
from data_access.contracts.integrations import CurveSpectraClient, WrappedDepositClient
from data_access.subgraphs.beanstalk import BeanstalkGraphClient
from monitors.monitor import Monitor
from data_access.contracts.util import *
from data_access.contracts.eth_events import *
from data_access.util import *
from constants.addresses import *
from constants.config import *
from tools.spinto import spinto_deposit_info
from tools.util import topic_to_address

class IntegrationsMonitor(Monitor):
    """Monitors various external contracts interacting with beanstalk."""

    def __init__(self, msg_spinto, msg_spectra, prod=False, dry_run=None):
        super().__init__(
            "Integrations", None, BEANSTALK_CHECK_RATE, prod=prod, dry_run=dry_run
        )
        self.msg_spinto = msg_spinto
        self.msg_spectra = msg_spectra
        self._eth_event_client = EthEventsClient(EventClientType.INTEGRATIONS)

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
                msg_fn = self.msg_spinto

            # spectra
            spectra_pool = next((s for s in SPECTRA_SPINTO_POOLS if event_log.address == s.pool), None)
            if spectra_pool:
                event_str = self.spectra_pool_str(event_log, spectra_pool)
                msg_fn = self.msg_spectra

            if not event_str:
                continue
            event_str += links_footer(event_logs[0].receipt)
            msg_fn(event_str)

    def spinto_str(self, event_log):
        bean_client = BeanClient(block_number=event_log.blockNumber)
        spinto_client = WrappedDepositClient(event_log.address, BEAN_ADDR, block_number=event_log.blockNumber)
        beanstalk_graph_client = BeanstalkGraphClient(block_number=event_log.blockNumber)

        event_str = ""

        underlying_asset = spinto_client.get_underlying_asset()
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

            wrapped_supply = token_to_float(spinto_client.get_supply(), wrapped_info.decimals)
            redeem_rate = spinto_client.get_redeem_rate()

            deposit_gspbdv = -1 + stalk_to_float(stalk_amount) / pinto_amount
            total_gspbdv = beanstalk_graph_client.get_account_gspbdv(wrapped_info.addr)
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

    def spectra_pool_str(self, event_log, spectra_pool):
        # pool_client = CurveSpectraClient(spectra_pool, block_number=event_log.blockNumber)
        pool_client = CurveSpectraClient(spectra_pool, block_number='latest')#TODO
        spinto_client = WrappedDepositClient(spectra_pool.ibt, spectra_pool.underlying, block_number=event_log.blockNumber)

        token_infos = [get_erc20_info(spectra_pool.ibt), get_erc20_info(spectra_pool.pt)]
        underlying_erc20_info = get_erc20_info(spectra_pool.underlying)
        ibt_erc20_info = get_erc20_info(spectra_pool.ibt)

        ibt_to_pt_rate = pool_client.get_ibt_to_pt_rate()
        ibt_to_underlying_rate = spinto_client.get_redeem_rate()
        underlying_to_pt_rate = ibt_to_pt_rate / ibt_to_underlying_rate

        msg_case = 0
        if event_log.event == "TokenExchange":
            sold_id = event_log.args.get("sold_id")
            tokens_sold = event_log.args.get("tokens_sold")
            bought_id = event_log.args.get("bought_id")
            tokens_bought = event_log.args.get("tokens_bought")

            tokens_sold_str = f"{round_token(tokens_sold, token_infos[sold_id].decimals, token_infos[sold_id].addr)} {token_infos[sold_id].symbol}"
            tokens_bought_str = f"{round_token(tokens_bought, token_infos[bought_id].decimals, token_infos[bought_id].addr)} {token_infos[bought_id].symbol}"

            apy_direction = "📉" if sold_id == 0 else "📈"
            if sold_id == 1:
                msg_case += 1

            # Check if YT was minted/burned. The pool swap is enough to determine the direction
            yt_amount = get_amount_minted(spectra_pool.yt, event_log.receipt) + get_amount_burned(spectra_pool.yt, event_log.receipt)
            if yt_amount > 0:
                msg_case += 2
                yt_erc20_info = get_erc20_info(spectra_pool.yt)
                yt_amount_str = f"{round_token(yt_amount, yt_erc20_info.decimals, yt_erc20_info.addr)} {yt_erc20_info.symbol}"

            if msg_case <= 1:
                ibt_underlying = (tokens_sold if msg_case == 0 else tokens_bought) * ibt_to_underlying_rate
                # Intentionally uses sold token decimals and underlying address. This is because tokens_sold is in terms of
                # the ibt, and ibt_to_underlying_rate does not have decimals applied.
                ibt_underlying_str = round_token(ibt_underlying, token_infos[sold_id].decimals, underlying_erc20_info.addr)

            if msg_case == 0:
                pt_underlying = tokens_bought
                pt_underlying_str = round_token(pt_underlying, token_infos[bought_id].decimals, token_infos[bought_id].addr)
                event_str = (
                    f"Fixed yield {round_num((pt_underlying / ibt_underlying - 1) * 100, 2)}%: {ibt_underlying_str} -> {pt_underlying_str} {underlying_erc20_info.symbol} "
                    f"(bought {tokens_bought_str} with {tokens_sold_str})"
                )
            elif msg_case == 1:
                event_str = f"Exited fixed yield: sold {tokens_sold_str} for {tokens_bought_str} ({ibt_underlying_str} {underlying_erc20_info.symbol})"
            elif msg_case == 2:
                event_str = f"Exited leveraged yield: sold {tokens_sold_str} for {tokens_bought_str}"
            elif msg_case == 3:
                # the controlling contract is the one which minted PT/YT in this txn
                controller = topic_to_address(get_mint_logs(spectra_pool.yt, event_log.receipt)[0].topics[2])
                # Identify how much ibt is received where the sender is neither PT nor the pool (comes from user or a new mint)
                ibt_to_controller = get_erc20_transfer_logs(spectra_pool.ibt, controller, event_log.receipt)
                base_ibt_amount = int([log for log in ibt_to_controller if topic_to_address(log.topics[1]) not in [spectra_pool.pt, spectra_pool.pool]][0].data, 16)
                yt_to_ibt_ratio = token_to_float(yt_amount, yt_erc20_info.decimals) / token_to_float(base_ibt_amount, ibt_erc20_info.decimals)
                event_str = f"Leveraged yield {round_num(yt_to_ibt_ratio, 1)}x: bought {yt_amount_str} for {tokens_bought_str}"

            maturity_str = "Matures" if msg_case < 2 else "Expires"

            hours_to_maturity = (spectra_pool.maturity - datetime.datetime.now(datetime.timezone.utc)).total_seconds() / (60 * 60)
            apr = ((underlying_to_pt_rate - 1) / hours_to_maturity) * 24 * 365
            event_str += f"\n> {apy_direction} Implied apy: {round_num(apr * 100, 2)}%. {maturity_str} in {round_num(hours_to_maturity / 24, 0)} days"

        # (0) Fixed yield 10%: 100 -> 110 pinto (bought 110 PT-spinto with 90 spinto)
        # (1) Exited fixed yield: sold 1000 PT-spinto for 900 spinto (910 pinto)
        # (2) Exited leveraged yield: sold 1050 YT-spinto for 100 spinto
        # (3) Leveraged yield 10.5x: bought 1050 YT-spinto for 100 spinto
        # > (direction chart) Implied apy: x%. (Matures|Expires) in y days

        # (0) PT: fix yield - swaps sPinto to PT
        # (1) PT: exit position - swaps PT to sPinto
        # (2) YT: exit position - swaps sPinto to PT and burns YT
        # (3) YT: yield leverage - mints YT/PT and swaps PT to sPinto  
        return event_str
