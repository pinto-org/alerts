from data_access.contracts.util import *
from data_access.contracts.eth_events import *

class BeanstalkClient(ChainClient):
    """Common functionality related to the Beanstalk contract."""

    def __init__(self, block_number="latest", web3=get_web3_instance()):
        super().__init__(web3)
        self.block_number = block_number
        self.contract = get_beanstalk_contract(web3=web3)

    def get_season(self, block_number=None):
        """Get current season."""
        block_number = block_number or self.block_number
        return call_contract_function_with_retry(self.contract.functions.season(), block_number=block_number)
    
    def is_raining(self, block_number=None):
        """Returns true if the system is currently Raining."""
        block_number = block_number or self.block_number
        season_struct = call_contract_function_with_retry(self.contract.functions.getSeasonStruct(), block_number=block_number)
        return season_struct[4]

    def get_max_temp(self, block_number=None):
        """Gets the current max temperature"""
        block_number = block_number or self.block_number
        return call_contract_function_with_retry(self.contract.functions.maxTemperature(), block_number=block_number) / 10 ** 6

    def get_current_soil(self, block_number=None):
        """Gets the current soil in the field"""
        block_number = block_number or self.block_number
        return call_contract_function_with_retry(self.contract.functions.totalSoil(), block_number=block_number) / 10 ** 6

    def get_total_stalk(self, block_number=None):
        """Gets the total stalk in the silo"""
        block_number = block_number or self.block_number
        return stalk_to_float(call_contract_function_with_retry(self.contract.functions.totalStalk(), block_number=block_number))

    def get_season_block(self, block_number=None):
        """Get the block in which the latest season started"""
        block_number = block_number or self.block_number
        return call_contract_function_with_retry(self.contract.functions.sunriseBlock(), block_number=block_number)

    def get_total_deposited_beans(self, block_number=None):
        """Get current total deposited Beans in the Silo."""
        block_number = block_number or self.block_number
        return bean_to_float(
            call_contract_function_with_retry(self.contract.functions.totalDepositedBeans(), block_number=block_number)
        )

    def get_total_deposited(self, address, decimals, block_number=None):
        """Return the total deposited of the token at address as a float."""
        block_number = block_number or self.block_number
        return token_to_float(
            call_contract_function_with_retry(self.contract.functions.getTotalDeposited(address), block_number=block_number),
            decimals
        )

    def get_recap_funded_percent(self, block_number=None):
        """Return the % of target funds that have already been funded via fertilizer sales."""
        # Note that % recap is same for all unripe tokens.
        block_number = block_number or self.block_number
        return token_to_float(
            call_contract_function_with_retry(
                self.contract.functions.getRecapFundedPercent(UNRIPE_LP_ADDR),
                block_number=block_number
            ),
            6
        )

    def get_seeds(self, token, block_number=None):
        """Returns the current amount of Seeds awarded for depositing `token` in the silo."""
        block_number = block_number or self.block_number
        token = Web3.to_checksum_address(token)
        token_settings = call_contract_function_with_retry(self.contract.functions.tokenSettings(token), block_number=block_number)
        return token_settings[1] / 10 ** 6

    def get_bdv(self, erc20_info, block_number=None):
        """Returns the current bdv `token`."""
        block_number = block_number or self.block_number
        token = Web3.to_checksum_address(erc20_info.addr)
        bdv = call_contract_function_with_retry(self.contract.functions.bdv(token, 10 ** erc20_info.decimals), block_number=block_number)
        return bean_to_float(bdv)
    
    def get_stem_tip(self, token, block_number=None):
        block_number = block_number or self.block_number
        return call_contract_function_with_retry(self.contract.functions.stemTipForToken(token), block_number=block_number)

    def get_token_usd_price(self, token_addr, block_number=None):
        block_number = block_number or self.block_number
        response = call_contract_function_with_retry(self.contract.functions.getTokenUsdPrice(token_addr), block_number=block_number)
        return float(response / 10**6)
    
    def get_token_usd_twap(self, token_addr, lookback, block_number=None):
        block_number = block_number or self.block_number
        response = call_contract_function_with_retry(self.contract.functions.getTokenUsdTwap(token_addr, lookback), block_number=block_number)
        return float(response / 10**6)
    
    def get_harvested_pods(self, field_id=0, block_number=None):
        block_number = block_number or self.block_number
        return bean_to_float(
            call_contract_function_with_retry(self.contract.functions.harvestableIndex(field_id), block_number=block_number)
        )

    def get_podline_length(self, field_id=0, block_number=None):
        block_number = block_number or self.block_number
        pod_index = call_contract_function_with_retry(self.contract.functions.podIndex(field_id), block_number=block_number)
        harvestable_index = call_contract_function_with_retry(self.contract.functions.harvestableIndex(field_id), block_number=block_number)
        return bean_to_float(pod_index - harvestable_index)

    @classmethod
    def calc_crop_ratio(cls, beanToMaxLpGpPerBdvRatio, is_raining):
        """
        Calcualtes the current crop ratio. Result value ranges from 33.33% to 100%.
        beanToMaxLpGpPerBdvRatio ranges from 0 to 100e18
        """
        if is_raining:
            lower_bound = 0.3333
        else:
            lower_bound = 0.50

        return lower_bound + (1 - lower_bound) * (beanToMaxLpGpPerBdvRatio / 100e18)

if __name__ == "__main__":
    """Quick test and demonstrate functionality."""
    logging.basicConfig(level=logging.INFO)
    bs = BeanstalkClient()
    # logging.info(f"season {bs.get_season()}")
    # logging.info(f"bean seeds {bs.get_seeds(BEAN_ADDR)}")
    # logging.info(f"season block {bs.get_season_block()}")
    client = EthEventsClient(EventClientType.SEASON)
    events = client.get_log_range(22722127, 22722127)
    for i in range(len(events)):
        logging.info(f"found txn: {events[i].txn_hash.hex()}")
    # logging.info(f"lp bdv {bs.get_bdv(get_erc20_info(PINTO_CBETH_ADDR), 20566115)}")
    logging.info(f"Crop ratio: {BeanstalkClient.calc_crop_ratio(int(50e18), False)}")
    logging.info(f"Crop ratio: {BeanstalkClient.calc_crop_ratio(int(50e18), True)}")
