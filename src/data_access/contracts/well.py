from data_access.contracts.util import *

class WellClient(ChainClient):
    """Client for interacting with well contracts."""

    def __init__(self, address, block_number="latest", web3=get_web3_instance()):
        super().__init__(web3)
        self.address = address
        self.block_number = block_number
        self.contract = get_well_contract(address, web3=web3)

    def tokens(self, block_number=None):
        """Returns a list of ERC20 tokens supported by the Well."""
        block_number = block_number or self.block_number
        return call_contract_function_with_retry(self.contract.functions.tokens(), block_number=block_number)
