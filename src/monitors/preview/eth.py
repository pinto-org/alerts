from constants.chain import Chain
from data_access.etherscan import get_gas_base_fee

from bots.util import *
from monitors.preview.preview import PreviewMonitor
from data_access.contracts.util import *
from data_access.contracts.beanstalk import BeanstalkClient
from data_access.util import *
from constants.addresses import *
from constants.config import *

class EthPreviewMonitor(PreviewMonitor):
    """Monitor data that offers a view into Eth mainnet."""

    def __init__(self, name_function, status_function):
        super().__init__("ETH", name_function, status_function, 2)
        self.beanstalk_client = BeanstalkClient()

    def _monitor_method(self):
        while self._thread_active:
            self.wait_for_next_cycle()
            self.iterate_display_index()

            gas_base_fee = get_gas_base_fee(Chain.BASE)
            self.name_function(f"{holiday_emoji()}{round_num(gas_base_fee, 3)} Gwei")

            if self.display_index == 0:
                eth_price = self.beanstalk_client.get_token_usd_price(WETH)
                self.status_function(f"ETH: ${round_num(eth_price)}")
            elif self.display_index == 1:
                btc_price = self.beanstalk_client.get_token_usd_price(CBBTC)
                self.status_function(f"BTC: ${round_num(btc_price)}")
            # elif self.display_index == 2:
            #     sol_price = self.beanstalk_client.get_token_usd_price(WSOL)
            #     self.status_function(f"SOL: ${round_num(sol_price)}")
