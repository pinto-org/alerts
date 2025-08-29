from data_access.contracts.erc20 import get_erc20_info
from data_access.contracts.util import *
from data_access.contracts.eth_events import *

class WrappedDepositClient(ChainClient):

    def __init__(self, wrapper, underlying, block_number="latest", web3=get_web3_instance()):
        super().__init__(web3)
        self.wrapper = wrapper
        self.underlying = underlying
        self.block_number = block_number
        self.contract = get_wrapped_silo_contract(wrapper, web3=web3)

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
        wrapper_erc20_info = get_erc20_info(self.wrapper)
        underlying_erc20_info = get_erc20_info(self.underlying)
        return token_to_float(
            call_contract_function_with_retry(
                self.contract.functions.previewRedeem(10 ** wrapper_erc20_info.decimals),
                block_number=block_number
            ),
            underlying_erc20_info.decimals
        )

class CurveSpectraClient(ChainClient):

    def __init__(self, spectra_pool, block_number="latest", web3=get_web3_instance()):
        super().__init__(web3)
        self.spectra_pool = spectra_pool
        self.block_number = block_number
        self.contract = get_curve_spectra_contract(spectra_pool.pool, spectra_pool.is_legacy_abi, web3=web3)

    def get_ibt_to_pt_rate(self, block_number=None):
        """Gets the current exchange rate from one of ibt to how much pt in this pool"""
        block_number = block_number or self.block_number
        ibt_erc20_info = get_erc20_info(self.spectra_pool.ibt)
        pt_erc20_info = get_erc20_info(self.spectra_pool.pt)
        return token_to_float(
            call_contract_function_with_retry(
                self.contract.functions.get_dy(0, 1, 10 ** ibt_erc20_info.decimals),
                block_number=block_number
            ),
            pt_erc20_info.decimals
        )

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    client = WrappedDepositClient('0x00b174d66adA7d63789087F50A9b9e0e48446dc1', '0xb170000aeefa790fa61d6e837d1035906839a3c8')
    rate = client.get_redeem_rate()
    logging.info(rate)

    spectra_client = CurveSpectraClient(SPECTRA_SPINTO_POOLS[0])
    ibt_to_pt_rate = spectra_client.get_ibt_to_pt_rate()
    logging.info(ibt_to_pt_rate)
