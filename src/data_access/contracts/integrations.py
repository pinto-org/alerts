from data_access.contracts.util import *
from data_access.contracts.eth_events import *

class WrappedDepositClient(ChainClient):

    def __init__(self, address, web3=None):
        super().__init__(web3)
        self.address = address
        self.contract = get_wrapped_silo_contract(address, self._web3)

    def get_underlying_asset(self):
        """Get the whitelisted deposit token underlying this wrapped deposit token"""
        return call_contract_function_with_retry(self.contract.functions.asset())
    
    def get_supply(self):
        """Get the current erc20 token supply"""
        return call_contract_function_with_retry(self.contract.functions.totalSupply())
    
    def get_redeem_rate(self):
        """Get the current redemption rate"""
        erc20_info = get_erc20_info(self.address, self._web3)
        return call_contract_function_with_retry(self.contract.functions.previewRedeem(10 ** erc20_info.decimals))
