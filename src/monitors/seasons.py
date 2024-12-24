from abc import abstractmethod

from bots.util import *
from data_access.subgraphs.basin import BasinGraphClient
from data_access.subgraphs.bean import BeanGraphClient
from monitors.monitor import Monitor
from data_access.contracts.util import *
from data_access.contracts.eth_events import *
from data_access.contracts.bean import BeanClient
from data_access.contracts.beanstalk import BeanstalkClient
from data_access.subgraphs.beanstalk import BeanstalkGraphClient
from data_access.util import *
from constants.addresses import *
from constants.config import *

class SeasonsMonitor(Monitor):
    def __init__(
        self, message_function, short_msgs=False, prod=False, dry_run=None
    ):
        super().__init__(
            "Seasons", message_function, SUNRISE_CHECK_PERIOD, prod=prod, dry_run=dry_run
        )
        # Toggle shorter messages (must fit into <280 character safely).
        self.short_msgs = short_msgs
        self._eth_event_client = EthEventsClient(EventClientType.SEASON)
        self._eth_all_wells = EthEventsClient(EventClientType.WELL, WHITELISTED_WELLS)
        self.beanstalk_graph_client = BeanstalkGraphClient()
        self.bean_graph_client = BeanGraphClient()
        self.basin_graph_client = BasinGraphClient()
        self.bean_client = BeanClient()
        self.beanstalk_client = BeanstalkClient()
        # Most recent season processed. Do not initialize.
        self.current_season_id = None

    def _monitor_method(self):
        while self._thread_active:
            # Wait until the eligible for a sunrise.
            self._wait_until_expected_sunrise()
            # Once the sunrise is complete, get the season stats.
            seasonal_sg = self._block_and_get_season_stats()
            # A new season has begun.
            if seasonal_sg:
                block = seasonal_sg.current_beanstalk.sunrise_block
                # Get the txn hash + any flood events for this sunrise call
                sunrise_logs = self._eth_event_client.get_log_range(block, block)
                if len(sunrise_logs) > 0:
                    seasonal_sg.current_beanstalk.sunrise_hash = sunrise_logs[0].txn_hash.hex()
                    seasonal_sg.current_beanstalk.well_plenty_logs = get_logs_by_names(["SeasonOfPlentyWell"], sunrise_logs[0].logs)
                    seasonal_sg.current_beanstalk.field_plenty_logs = get_logs_by_names(["SeasonOfPlentyField"], sunrise_logs[0].logs)
                    if len(seasonal_sg.current_beanstalk.well_plenty_logs) > 0:
                        # Get swap logs if there was flood plenty
                        sunrise_swap_logs = self._eth_all_wells.get_log_range(block, block)
                        if len(sunrise_swap_logs) > 0:
                            # Ensure these logs match the sunrise txn hash
                            sunrise_tx_logs = next(txn.logs for txn in sunrise_swap_logs if txn.txn_hash.hex() == seasonal_sg.current_beanstalk.sunrise_hash)
                            seasonal_sg.current_beanstalk.flood_swap_logs = get_logs_by_names(["Swap"], sunrise_tx_logs)

                # Report season summary to users.
                self.message_function(
                    self.season_summary_string(
                        seasonal_sg, short_str=self.short_msgs
                    )
                )

    def _wait_until_expected_sunrise(self):
        """Wait until beanstalk is eligible for a sunrise call.

        Assumes sunrise timing cycle beings with Unix Epoch (1/1/1970 00:00:00 UTC).
        This is not exact since we do not bother with syncing local and graph time.
        """
        if self._dry_run == ["seasons"]:
            time.sleep(1)
            return

        seconds_until_next_sunrise = SEASON_DURATION - time.time() % SEASON_DURATION
        sunrise_ready_timestamp = time.time() + seconds_until_next_sunrise
        loop_count = 0
        while self._thread_active and time.time() < sunrise_ready_timestamp:
            if loop_count % 60 == 0:
                logging.info(
                    f"Blindly waiting {int((sunrise_ready_timestamp - time.time())/60)} "
                    "more minutes until expected sunrise."
                )
            loop_count += 1
            time.sleep(1)

    def _block_and_get_season_stats(self):
        """Blocks until sunrise is complete, then returns stats of current and previous season.

        Repeatedly makes graph calls to check sunrise status.
        """
        while self._thread_active:
            current_beanstalk_stats, prev_beanstalk_stats = self.beanstalk_graph_client.season_stats()
            current_bean_stats, prev_bean_stats = self.bean_graph_client.season_stats()
            well_hourly_stats = self.basin_graph_client.get_well_hourlies(time.time() - SEASON_DURATION)
            # If a new season is detected and sunrise was sufficiently recent.
            if (
                self.current_season_id != current_beanstalk_stats.season
                and int(current_beanstalk_stats.created_at) > time.time() - SEASON_DURATION / 2
                and current_beanstalk_stats.season == current_bean_stats.season
                and len(well_hourly_stats) == len(WHITELISTED_WELLS)
            ) or self._dry_run:
                self.current_season_id = current_beanstalk_stats.season
                logging.info(f"New season detected with id {self.current_season_id}")
                return SeasonalData(prev_beanstalk_stats, current_beanstalk_stats, prev_bean_stats, current_bean_stats, well_hourly_stats)
            time.sleep(self.query_rate)
        return None

    def season_summary_string(self, sg, short_str=False):
        # eth_price = self.beanstalk_client.get_token_usd_twap(WETH, 3600)
        # wsteth_price = self.beanstalk_client.get_token_usd_twap(WSTETH, 3600)
        # wsteth_eth_price = wsteth_price / eth_price

        # new_farmable_beans = float(s.current_beanstalk.silo_hourly_bean_mints)
        reward_beans = sg.current_beanstalk.reward_beans
        incentive_beans = sg.current_beanstalk.incentive_beans
        pod_rate = sg.current_beanstalk.pod_rate * 100
        price = sg.current_beanstalk.price
        delta_b = sg.current_beanstalk.delta_b
        issued_soil = sg.current_beanstalk.issued_soil
        new_pods = sg.prev_beanstalk.new_pods
        sown_beans = sg.prev_beanstalk.sown_beans
        delta_temp = sg.current_beanstalk.temperature - sg.prev_beanstalk.temperature

        # Silo asset balances.
        current_silo_bdv = sg.current_beanstalk.deposited_bdv
        prev_silo_bdv = sg.prev_beanstalk.deposited_bdv
        silo_assets_changes = self.beanstalk_graph_client.silo_assets_seasonal_changes(
            sg.current_beanstalk.pre_assets, sg.prev_beanstalk.pre_assets
        )
        silo_assets_changes.sort(
            key=lambda a: int(a.final_season_asset["depositedBDV"]), reverse=True
        )

        # Current state.
        new_season = sg.prev_beanstalk.season + 1
        ret_string = f"⏱ Season {new_season} has started!"
        if not short_str:
            ret_string += f"\n💵 Pinto price is ${round_num(price, 4)}"
        else:
            ret_string += f" — Pinto price is ${round_num(price, 4)}"

        ret_string += f'\n⚖️ {"+" if delta_b >= 0 else ""}{round_num(delta_b, 0)} TWAΔP'

        supply = get_erc20_total_supply(BEAN_ADDR, 6)
        ret_string += f"\n🪙 {round_num(supply, precision=0)} Pinto Supply (${round_num(supply * price, precision=0)})"

        season_block = self.beanstalk_client.get_season_block()
        # Flood stats
        is_raining = self.beanstalk_client.is_raining()
        rain_flood_string = ""
        flood_beans = 0
        if hasattr(sg.current_beanstalk, 'well_plenty_logs') and len(sg.current_beanstalk.well_plenty_logs) > 0:
            pre_flood_price = self.bean_client.block_price(season_block - 1)
            rain_flood_string += f"\n\n**It is Flooding!**"
            rain_flood_string += f"\nPinto price was {round_num(pre_flood_price, precision=4, incl_dollar=True)}"
            flood_field_beans = 0
            flood_well_beans = 0
            if len(sg.current_beanstalk.field_plenty_logs) > 0:
                log = sg.current_beanstalk.field_plenty_logs[0]
                flood_field_beans = log.args.get('toField') / 10 ** BEAN_DECIMALS
                rain_flood_string += f"\n{round_num(flood_field_beans, 0)} Pinto minted to the Field"

            flood_breakdown = ""
            for i in range(len(sg.current_beanstalk.well_plenty_logs)):
                log = sg.current_beanstalk.well_plenty_logs[i]
                token = log.args.get('token')
                plenty_amount = log.args.get('amount')
                erc20_info = get_erc20_info(token)
                amount = round_token(plenty_amount, erc20_info.decimals, token)
                value = plenty_amount * self.beanstalk_client.get_token_usd_price(token) / 10 ** erc20_info.decimals
                flood_breakdown += f"\n> {amount} {erc20_info.symbol} ({round_num(value, precision=0, incl_dollar=True)})"

                flood_well_beans += sg.current_beanstalk.flood_swap_logs[i].args.get('amountIn') / 10 ** BEAN_DECIMALS

            rain_flood_string += f"\n{round_num(flood_well_beans, 0)} Pinto minted and sold for:"
            rain_flood_string += flood_breakdown
            flood_beans += flood_field_beans + flood_well_beans
        elif is_raining:
            rain_flood_string += f"\n\n☔ **It is Raining!** ☔"

        # Well info.
        wells_info = []
        for well_addr in WHITELISTED_WELLS:
            wells_info.append(self.bean_client.get_pool_info(well_addr))

        # Sort highest liquidity wells first
        wells_info = sorted(wells_info, key=lambda x: x['liquidity'], reverse=True)

        total_liquidity = 0
        for well_info in wells_info:
            total_liquidity += token_to_float(well_info['liquidity'], 6)
        total_liquidity = round_num(total_liquidity, 0, incl_dollar=True)

        wells_volume = 0
        for stats in sg.well:
            wells_volume += float(stats.get("deltaTradeVolumeUSD"))

        # Full string message.
        if not short_str:

            ret_string += f"\n🧮 {sg.prev_bean.crosses} (+{sg.prev_bean.deltaCrosses}) Peg crosses"

            # Flood
            ret_string += rain_flood_string

            # ret_string += f"\n🪙 TWA ETH price is ${round_num(eth_price, 2)}"
            # ret_string += f"\n🪙 TWA wstETH price is ${round_num(wsteth_price, 2)} (1 wstETH = {round_num(wsteth_eth_price, 4)} ETH)"
            # Bean Supply stats.
            ret_string += f"\n\n**Supply**"
            ret_string += f"\n🌱 :PINTO: {round_num(reward_beans + flood_beans + incentive_beans, 0, avoid_zero=True)} total Pinto minted"
            ret_string += f"\n> ⚖️ :PINTO: {round_num(reward_beans, 0, avoid_zero=True)} TWAΔP"
            if flood_beans > 0:
                ret_string += f"\n> 🌊 :PINTO: {round_num(flood_field_beans, 0, avoid_zero=True)} minted to Field from Flood"
                ret_string += f"\n> 🌊 :PINTO: {round_num(flood_well_beans, 0, avoid_zero=True)} minted and sold from Flood"
            ret_string += f"\n> ☀️ :PINTO: {round_num(incentive_beans, 0)} gm reward"
            ret_string += f"\n🚜 {round_num(sown_beans, 0, avoid_zero=True)} Pinto Sown"

            # Liquidity stats.
            ret_string += f"\n\n**Liquidity**"
            ret_string += f"\n🌊 :PINTO: Total Liquidity: {total_liquidity}"

            for well_info in wells_info:
                ret_string += f"\n> {SILO_TOKENS_MAP[well_info['pool'].lower()]}: ${round_num(token_to_float(well_info['liquidity'], 6), 0)} - "
                ret_string += (
                    f"_ΔP [{round_num(token_to_float(well_info['delta_b'], 6), 0)}], "
                )
                ret_string += f"price [${round_num(token_to_float(well_info['price'], 6), 4)}]_"
            ret_string += f"\n⚖️ :PINTO: Hourly volume: {round_num(wells_volume, 0, incl_dollar=True)}"

            # Silo stats.
            was_raining = self.beanstalk_client.is_raining(sg.prev_beanstalk.sunrise_block)
            crop_ratio = BeanstalkClient.calc_crop_ratio(sg.current_beanstalk.beanToMaxLpGpPerBdvRatio, is_raining)
            prev_crop_ratio = BeanstalkClient.calc_crop_ratio(sg.prev_beanstalk.beanToMaxLpGpPerBdvRatio, was_raining)
            crop_ratio_delta = crop_ratio - prev_crop_ratio

            ret_string += f"\n\n**Silo**"
            ret_string += f"\n🏦 {round_num(current_silo_bdv, 0)} PDV in Silo"
            delta_bdv = current_silo_bdv - prev_silo_bdv
            if delta_bdv < 0:
                ret_string += f"\n> 📉 {round_num(abs(delta_bdv), 0)} decrease this Season"
            elif prev_silo_bdv == current_silo_bdv:
                ret_string += f"\n> 📊 No change this Season"
            else:
                ret_string += f"\n> 📈 {round_num(delta_bdv, 0)} increase this Season"
            ret_string += f"\n🧽 {round_num(sg.current_bean.supplyInPegLP * 100, 2)}% Liquidity to Supply Ratio"
            ret_string += f"\n🌾 {round_num(crop_ratio * 100, 2)}% ({'+' if crop_ratio_delta >= 0 else ''}{round_num(crop_ratio_delta * 100, 2)}%) Crop Ratio"

            # Gets current and previous season seeds for each asset
            parallelized = []
            for asset_changes in silo_assets_changes:
                parallelized.append(lambda token=asset_changes.token: self.beanstalk_client.get_seeds(token))
                parallelized.append(lambda token=asset_changes.token, block=season_block - 1: self.beanstalk_client.get_seeds(token, block))

            # seed_results = execute_lambdas(*parallelized)

            # for i in range(len(silo_assets_changes)):

            #     asset_changes = silo_assets_changes[i]
            #     seeds_now = seed_results[2*i]
            #     seeds_prev = seed_results[2*i + 1]

            #     ret_string += f"\n"
            #     _, _, token_symbol, decimals = get_erc20_info(
            #         asset_changes.token, web3=self._web3
            #     ).parse()
            #     delta_asset = token_to_float(asset_changes.delta_asset, decimals)
            #     delta_seeds = seeds_now - seeds_prev
            #     # Asset BDV at final season end, deduced from subgraph data.
            #     asset_bdv = bean_to_float(
            #         asset_changes.final_season_asset["depositedBDV"]
            #     ) / token_to_float(asset_changes.final_season_asset["depositedAmount"], decimals)
            #     # asset_bdv = bean_to_float(asset_changes.final_season_bdv)
            #     current_bdv = asset_changes.final_season_asset["depositedBDV"]

            #     ret_string += f"{token_symbol}:"

            #     # BDV
            #     if delta_asset < 0:
            #         ret_string += f"\n\t📉 PDV: {round_num(abs(delta_asset * asset_bdv), 0)}"
            #     elif delta_asset == 0:
            #         ret_string += f"\n\t📊 PDV: No change"
            #     else:
            #         ret_string += f"\n\t📈 PDV: {round_num(abs(delta_asset * asset_bdv), 0)}"

            #     # Seeds
            #     if delta_seeds < 0:
            #         ret_string += f"\n\t📉 Seeds: {round_num(abs(delta_seeds), 3, avoid_zero=True)}"
            #     elif delta_seeds == 0:
            #         ret_string += f"\n\t📊 Seeds: No change"
            #     else:
            #         ret_string += f"\n\t📈 Seeds: {round_num(abs(delta_seeds), 3, avoid_zero=True)}"

            #     # ret_string += f' — {token_symbol}  ({round_num(bean_to_float(current_bdv)/current_silo_bdv*100, 1)}% of Silo)'
            #     ret_string += f"\n\t📊 Totals: {round_num_abbreviated(bean_to_float(current_bdv))} PDV, {round_num(seeds_now, 3)} Seeds, {round_num(bean_to_float(current_bdv)/current_silo_bdv*100, 1)}% of Silo"

            # Field.
            ret_string += f"\n\n**Field**"
            ret_string += f"\n🌾 {round_num(new_pods, 0, avoid_zero=True)} Pods minted"
            ret_string += f"\n🏞 "
            if issued_soil == 0:
                ret_string += f"No"
            else:
                ret_string += f"{round_num(issued_soil, 0, avoid_zero=True)}"
            ret_string += f" Soil in Field"

            line_length = self.beanstalk_client.get_podline_length()
            ret_string += f"\n {round_num_abbreviated(line_length, precision=3)} Pods in Line"
            ret_string += f"\n🌡 {round_num(sg.current_beanstalk.temperature, 0)}% ({'+' if delta_temp >= 0 else ''}{round_num(delta_temp, 0)}%) Max Temperature"
            ret_string += f"\n🧮 {round_num(pod_rate, 2)}% Pod Rate"

            # Barn.
            # ret_string += f"\n\n**Barn**"
            # ret_string += f"\n{percent_to_moon_emoji(percent_recap)} {round_num(fertilizer_bought, 0)} Fertilizer sold ({round_num(percent_recap*100, 2)}% recapitalized)"

            # Txn hash of sunrise/gm call.
            if hasattr(sg.current_beanstalk, 'sunrise_hash'):
                ret_string += f"\n\n<https://basescan.org/tx/{sg.current_beanstalk.sunrise_hash}>"
                ret_string += "\n_ _"  # Empty line that does not get stripped.

        # Short string version (for Twitter).
        else:
            # Display total liquidity only
            ret_string += f"\n\n🌊 Total Liquidity: {total_liquidity}"

            if wells_volume > 0:
                ret_string += f"\n📊 Hourly volume: {round_num(wells_volume, 0, incl_dollar=True)}"

            ret_string += f"\n"
            if reward_beans > 0:
                ret_string += f"\n🌱 {round_num(reward_beans + flood_beans, 0, avoid_zero=True)} Pinto Minted"
                if flood_beans > 0:
                    ret_string += f" (💧 {round_num(flood_beans, 0)} from Flood)"
            if sown_beans > 0:
                ret_string += f"\n🚜 {round_num(sown_beans, 0, avoid_zero=True)} Pinto Sown for {round_num(new_pods, 0, avoid_zero=True)} Pods"

            ret_string += f"\n🌡 {round_num(sg.current_beanstalk.temperature, 0)}% ({'+' if delta_temp >= 0 else ''}{round_num(delta_temp, 0)}%) Max Temperature"
            # ret_string += f"\n🧮 {round_num(pod_rate, 0)}% Pod Rate"
        return ret_string

    @abstractmethod
    def silo_balance_str(name, deposits=None, bdv=None):
        """Return string representing the total deposited amount of a token."""
        ret_string = f"\n"
        if deposits is not None:
            ret_string += f"🏦 {round_num(deposits, 0)} {name} in Silo"
        elif bdv is not None:
            ret_string += f"🏦 {round_num(bdv, 0)} PDV worth of {name} in Silo"
        else:
            raise ValueError("Must specify either delta_deposits or pdv (Pinto denominated value)")
        return ret_string

class SeasonalData:
    def __init__(self, prev_beanstalk, current_beanstalk, prev_bean, current_bean, well):
        self.prev_beanstalk = prev_beanstalk
        self.current_beanstalk = current_beanstalk
        self.prev_bean = prev_bean
        self.current_bean = current_bean
        self.well = well
