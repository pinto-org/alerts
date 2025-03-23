import logging

from constants.config import ERC20_TRANSFER_EVENT_SIG, SILO_TOKENS_MAP
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

def get_amount_minted(token, receipt):
    """Gets the total amount of token which was minted in the given transaction receipt"""
    return sum(int(log.data, 16) for log in get_mint_logs(token, receipt))

def get_amount_burned(token, receipt):
    """Gets the total amount of token which was burned in the given transaction receipt"""
    return sum(int(log.data, 16) for log in get_burn_logs(token, receipt))

def get_mint_logs(token, receipt):
    """Gets all logs corresponding to token mints"""
    return _get_transfer_null_logs(token, receipt, 1)

def get_burn_logs(token, receipt):
    """Gets all logs corresponding to token burns"""
    return _get_transfer_null_logs(token, receipt, 2)

def _get_transfer_null_logs(token, receipt, null_topic_index):
    """Gets the total amount of token which was transferred from or to the null address in the given transaction receipt"""
    logs = []
    for log in receipt.logs:
        if log.address == token and log.topics[0].hex() == ERC20_TRANSFER_EVENT_SIG:
            if log.topics[null_topic_index].hex().replace("0", "") == "x":
                logs.append(log)
    return logs

class Erc20Info:
    def __init__(self, addr, name, symbol, decimals):
        self.addr = addr
        self.name = name
        self.symbol = symbol
        self.decimals = decimals

    def parse(self):
        return (self.addr, self.name, self.symbol, self.decimals)