from data_access.contracts.util import *
from data_access.contracts.eth_events import *

class WrappedDepositClient(ChainClient):

    def __init__(self, address, block_number='latest', web3=get_web3_instance()):
        super().__init__(web3)
        self.address = address
        self.block_number = block_number
        self.contract = get_wrapped_silo_contract(address, web3=web3)

    def get_underlying_asset(self, block_number=None):
        """Get the whitelisted deposit token underlying this wrapped deposit token"""
        block_number = block_number or self.block_number
        return call_contract_function_with_retry(self.contract.functions.asset(), block_number=block_number)
    
    def get_supply(self, block_number=None):
        """Get the current erc20 token supply"""
        block_number = block_number or self.block_number
        return call_contract_function_with_retry(self.contract.functions.totalSupply(), block_number=block_number)
    
    def get_redeem_rate(self, block_number=None):
        """Get the current redemption rate"""
        block_number = block_number or self.block_number
        erc20_info = get_erc20_info(self.address)
        return call_contract_function_with_retry(self.contract.functions.previewRedeem(10 ** erc20_info.decimals), block_number=block_number)

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    client = WrappedDepositClient('0x00b174d66adA7d63789087F50A9b9e0e48446dc1')
    rate = client.get_redeem_rate()
    logging.info(rate)
