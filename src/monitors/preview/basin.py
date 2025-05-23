from bots.util import *
from monitors.preview.preview import PreviewMonitor
from data_access.contracts.util import *
from data_access.subgraphs.basin import BasinGraphClient
from data_access.util import *
from constants.addresses import *
from constants.config import *

class BasinStatusPreviewMonitor(PreviewMonitor):
    """Monitor data that offers view into current Basin token status via discord nickname/status.

    Note that this was implemented in a generalized fashion, then switched to specifically ETH:BEAN. I expect
    it to return to an all-well implementation in the future.
    """

    def __init__(self, name_function, status_function):
        super().__init__("BasinStatus", name_function, status_function, 1)
        self.last_name = ""
        self.basin_graph_latest = BasinGraphClient(block_number="latest")

    def _monitor_method(self):
        while self._thread_active:
            self.wait_for_next_cycle()
            self.iterate_display_index()

            liquidity = 0
            volume = 0
            well_count = 0
            wells = self.basin_graph_latest.get_wells_stats()

            for well in wells:
                if well["id"] in {token.lower() for token in WHITELISTED_WELLS}:
                    liquidity += float(well["totalLiquidityUSD"])
                    volume += float(well["cumulativeTradeVolumeUSD"])
                    well_count += 1

            name_str = f"Liq: ${round_num(liquidity, 0)}"
            if name_str != self.last_name:
                self.name_function(name_str)
                self.last_name = name_str

            # Rotate data and update status.
            if self.display_index == 0:
                self.status_function(f"Cumul Vol: ${round_num_abbreviated(volume, capitalize=False)}")
            else:
                self.status_function(f"{well_count} Wells")
