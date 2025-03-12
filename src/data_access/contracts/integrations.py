from data_access.contracts.util import *
from data_access.contracts.eth_events import *

class WrappedDepositClient(ChainClient):

    def __init__(self, address, web3=None):
        super().__init__(web3)
        self.address = address
        self.contract = get_wrapped_silo_contract(address)

    def get_underlying_asset(self):
        """Get the whitelisted deposit token underlying this wrapped deposit token"""
        return call_contract_function_with_retry(self.contract.functions.asset())
    
    def get_supply(self):
        """Get the current erc20 token supply"""
        return call_contract_function_with_retry(self.contract.functions.totalSupply())
    
    def get_redeem_rate(self):
        """Get the current redemption rate"""
        erc20_info = get_erc20_info(self.address)
        return call_contract_function_with_retry(self.contract.functions.previewRedeem(10 ** erc20_info.decimals))

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    client = WrappedDepositClient('0x00b174d66adA7d63789087F50A9b9e0e48446dc1')
    rate = client.get_redeem_rate()
    logging.info(rate)
