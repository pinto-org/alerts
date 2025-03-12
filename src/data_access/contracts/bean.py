from abc import abstractmethod

from data_access.contracts.util import *

class BeanClient(ChainClient):
    """Common functionality related to the Bean token."""

    def __init__(self, block_number="latest", web3=get_web3_instance()):
        super().__init__(web3)
        self.block_number = block_number
        self.price_contract = get_bean_price_contract(web3=web3)

    def get_price_info(self, block_number=None):
        """Get all pricing info from oracle.

        Pricing data is returned as an array. See abi for structure.
        """
        block_number = block_number or self.block_number
        raw_price_info = call_contract_function_with_retry(self.price_contract.functions.price(), block_number=block_number)
        return BeanClient.map_price_info(raw_price_info)

    @abstractmethod
    def map_price_info(raw_price_info):
        price_dict = {}
        price_dict["price"] = raw_price_info[0]
        price_dict["liquidity"] = raw_price_info[1]
        price_dict["delta_b"] = raw_price_info[2]
        price_dict["pool_infos"] = {}
        # Map address:pool_info for each supported pool.
        for pool_info in raw_price_info[3]:
            pool_dict = {}
            pool_dict["pool"] = pool_info[0]  # Address
            pool_dict["tokens"] = pool_info[1]
            pool_dict["balances"] = pool_info[2]
            # Bean price of pool (6 decimals)
            pool_dict["price"] = pool_info[3]
            # USD value of the liquidity in the pool
            pool_dict["liquidity"] = pool_info[4]
            pool_dict["bean_liquidity"] = pool_info[5]
            pool_dict["non_bean_liquidity"] = pool_info[6]
            pool_dict["delta_b"] = pool_info[7]
            pool_dict["lp_usd"] = pool_info[8]  # LP Token price in USD
            pool_dict["lp_bdv"] = pool_info[9]  # LP Token price in BDV
            price_dict["pool_infos"][pool_info[0]] = pool_dict
        return price_dict
    
    def get_lp_token_value(self, token_address, decimals, liquidity_long=None, block_number=None):
        """Return the $/LP token value of an LP token at address as a float."""
        block_number = block_number or self.block_number
        if liquidity_long is None:
            try:
                liquidity_long = self.get_price_info(block_number=block_number)["pool_infos"][token_address]["liquidity"]
            # If the LP is not in the price aggregator, we do not know its value.
            except KeyError:
                return None
        liquidity_usd = token_to_float(liquidity_long, 6)
        token_supply = get_erc20_total_supply(token_address, decimals)
        return liquidity_usd / token_supply

    def avg_bean_price(self, price_info=None, block_number=None):
        """Current float bean price average across LPs from the Bean price oracle contract."""
        block_number = block_number or self.block_number
        if price_info:
            price = price_info["price"]
        else:
            price = self.get_price_info(block_number=block_number)["price"]
        return bean_to_float(price)

    def total_delta_b(self, price_info=None, block_number=None):
        """Current deltaB across all pools."""
        block_number = block_number or self.block_number
        if price_info:
            delta_b = price_info["delta_b"]
        else:
            delta_b = self.get_price_info(block_number=block_number)["delta_b"]
        return bean_to_float(delta_b)

    def get_pool_info(self, addr, block_number=None):
        """Return pool info as dict. If addr is Bean addr, return all info."""
        block_number = block_number or self.block_number
        price_info = self.get_price_info(block_number=block_number)
        if addr == BEAN_ADDR:
            return price_info
        else:
            return price_info["pool_infos"][addr]

    def well_bean_price(self, well_addr, block_number=None):
        """Current float Bean price in the given well."""
        block_number = block_number or self.block_number
        return bean_to_float(self.get_pool_info(well_addr, block_number=block_number)["price"])

    def block_price(self, block_number=None):
        block_number = block_number or self.block_number
        raw_price_info = call_contract_function_with_retry(self.price_contract.functions.price(), block_number=block_number)
        return bean_to_float(BeanClient.map_price_info(raw_price_info)["price"])
