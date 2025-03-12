import logging

from constants.config import SILO_TOKENS_MAP
from data_access.contracts.util import call_contract_function_with_retry, get_erc20_contract, token_to_float

# Global cache for erc20 info that is static.
erc20_info_cache = {}
def get_erc20_info(addr):
    """Get the name, symbol, and decimals of an ERC-20 token."""
    addr = addr.lower()
    if addr not in erc20_info_cache:
        logging.info(f"Querying chain for erc20 token info of {addr}.")
        contract = get_erc20_contract(addr)
        name = call_contract_function_with_retry(contract.functions.name())
        # Use custom in-house Beanstalk Symbol name, if set, otherwise default to on-chain symbol.
        symbol = SILO_TOKENS_MAP.get(addr) or call_contract_function_with_retry(
            contract.functions.symbol()
        )
        decimals = call_contract_function_with_retry(contract.functions.decimals())
        erc20_info_cache[addr] = Erc20Info(addr, name, symbol, decimals)
    return erc20_info_cache[addr]

def get_erc20_total_supply(addr, block_number="latest"):
    """Get the total supply of ERC-20 token in circulation as float."""
    contract = get_erc20_contract(addr)
    erc20_info = get_erc20_info(addr)
    return token_to_float(
        call_contract_function_with_retry(contract.functions.totalSupply(), block_number=block_number),
        erc20_info.decimals
    )

class Erc20Info:
    def __init__(self, addr, name, symbol, decimals):
        self.addr = addr
        self.name = name
        self.symbol = symbol
        self.decimals = decimals

    def parse(self):
        return (self.addr, self.name, self.symbol, self.decimals)