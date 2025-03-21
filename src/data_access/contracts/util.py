import logging
import json
import os
import time
from tools.util import topic_is_address
import websockets

from web3 import HTTPProvider

from constants.addresses import *
from constants.config import *

from constants import dry_run_entries

with open(
    os.path.join(os.path.dirname(__file__), "../../constants/abi/erc20_abi.json")
) as erc20_abi_file:
    erc20_abi = json.load(erc20_abi_file)
with open(
    os.path.join(os.path.dirname(__file__), "../../constants/abi/erc1155_abi.json")
) as erc1155_abi_file:
    erc1155_abi = json.load(erc1155_abi_file)
with open(
    os.path.join(os.path.dirname(__file__), "../../constants/abi/aquifer_abi.json")
) as aquifer_abi_file:
    aquifer_abi = json.load(aquifer_abi_file)
with open(
    os.path.join(os.path.dirname(__file__), "../../constants/abi/well_abi.json")
) as well_abi_file:
    well_abi = json.load(well_abi_file)
with open(
    os.path.join(os.path.dirname(__file__), "../../constants/abi/beanstalk_abi.json")
) as beanstalk_abi_file:
    beanstalk_abi = json.load(beanstalk_abi_file)
with open(
    os.path.join(os.path.dirname(__file__), "../../constants/abi/bean_price_abi.json")
) as bean_price_abi_file:
    bean_price_abi = json.load(bean_price_abi_file)
with open(
    os.path.join(os.path.dirname(__file__), "../../constants/abi/fertilizer_abi.json")
) as fertilizer_abi_file:
    fertilizer_abi = json.load(fertilizer_abi_file)
with open(
    os.path.join(os.path.dirname(__file__), "../../constants/abi/wrapped_silo_erc20_abi.json")
) as wrapped_silo_erc20_abi_file:
    wrapped_silo_erc20_abi = json.load(wrapped_silo_erc20_abi_file)
with open(
    os.path.join(os.path.dirname(__file__), "../../constants/abi/curve_spectra_abi.json")
) as curve_spectra_abi_file:
    curve_spectra_abi = json.load(curve_spectra_abi_file)

class ChainClient:
    """Base class for clients of Eth chain data."""

    def __init__(self, web3=None):
        self._web3 = web3 or get_web3_instance()
        
web3_instance = Web3(HTTPProvider(RPC_URL))
def get_web3_instance():
    """Get an instance of web3 lib."""
    return web3_instance

def get_well_contract(address, web3=get_web3_instance()):
    """Get a web.eth.contract object for a well. Contract is not thread safe."""
    return web3.eth.contract(address=address, abi=well_abi)

def get_aquifer_contract(web3=get_web3_instance()):
    """Get a web.eth.contract object for the aquifer. Contract is not thread safe."""
    return web3.eth.contract(address=AQUIFER_ADDR, abi=aquifer_abi)

def get_wrapped_silo_contract(addr, web3=get_web3_instance()):
    """Get a web.eth.contract object for the requested wrapped silo token. Contract is not thread safe."""
    return web3.eth.contract(address=addr, abi=wrapped_silo_erc20_abi)

def get_bean_contract(web3=get_web3_instance()):
    """Get a web.eth.contract object for the Bean token contract. Contract is not thread safe."""
    return web3.eth.contract(address=BEAN_ADDR, abi=erc20_abi)

def get_beanstalk_contract(web3=get_web3_instance()):
    """Get a web.eth.contract object for the Beanstalk contract. Contract is not thread safe."""
    return web3.eth.contract(address=BEANSTALK_ADDR, abi=beanstalk_abi)

def get_bean_price_contract(web3=get_web3_instance()):
    """Get a web.eth.contract object for the Bean price contract. Contract is not thread safe."""
    return web3.eth.contract(address=BEANSTALK_PRICE_ADDR, abi=bean_price_abi)

def get_fertilizer_contract(web3=get_web3_instance()):
    """Get a web.eth.contract object for the Barn Raise Fertilizer contract. Contract is not thread safe."""
    return web3.eth.contract(address=FERTILIZER_ADDR, abi=fertilizer_abi)

def get_erc20_contract(address, web3=get_web3_instance()):
    """Get a web3.eth.contract object for a standard ERC20 token contract."""
    address = web3.toChecksumAddress(address.lower())
    return web3.eth.contract(address=address, abi=erc20_abi)

def get_erc1155_contract(address, web3=get_web3_instance()):
    """Get a web3.eth.contract object for a standard ERC1155 token contract."""
    address = web3.toChecksumAddress(address.lower())
    return web3.eth.contract(address=address, abi=erc1155_abi)

def get_curve_spectra_contract(address, web3=get_web3_instance()):
    """Get a web3.eth.contract object for a spectra curve amm."""
    address = web3.toChecksumAddress(address.lower())
    return web3.eth.contract(address=address, abi=curve_spectra_abi)

def get_tokens_sent(token, receipt, recipient, log_index_bounds):
    """Return the amount (as a float) of token sent in a transaction to the given recipient, within the log index bounds"""
    logs = get_erc20_transfer_logs(token, recipient, receipt, log_index_bounds)
    total_sum = 0
    for entry in logs:
        total_sum += int(entry.data, 16)
    return total_sum

def get_eth_sent(receipt, recipient, web3, log_index_bounds):
    """
    Return the amount (as a float) of ETH or WETH sent in a transaction to the given recipient, within the log index bounds.
    If an aggregate value (ETH + WETH) is required, a specialized approach should be taken for the particular use case.
    This is because it is unclear who is the recipient of the ETH based on the .value property.
    """
    # Assumption is if WETH was sent, that any ETH from transaction.value would have already been wrapped and included
    logs = get_erc20_transfer_logs(WETH, recipient, receipt, log_index_bounds)
    total_sum = 0
    for entry in logs:
        total_sum += int(entry.data, 16)
    if total_sum != 0:
        return total_sum

    txn_value = web3.eth.get_transaction(receipt.transactionHash).value
    return txn_value

def safe_get_block(web3, block_number="latest"):
    max_tries = 15
    try_count = 0
    while try_count < max_tries:
        try:
            return web3.eth.get_block(block_number)
        except websockets.exceptions.ConnectionClosedError as e:
            logging.warning(e, exc_info=True)
            time.sleep(2)
            try_count += 1
    raise Exception("Failed to safely get block")

def call_contract_function_with_retry(function, max_tries=10, block_number="latest"):
    """Try to call a web3 contract object function and retry with exponential backoff."""
    try_count = 1
    while True:
        try:
            return function.call(block_identifier=block_number)
        except Exception as e:
            if try_count < max_tries:
                try_count += 1
                time.sleep(0.5)
                continue
            else:
                logging.error(
                    f'Failed to access "{function.fn_name}" function at contract address "{function.address}" after {max_tries} attempts. Raising exception...'
                )
                raise (e)

def get_erc20_transfer_logs(token, recipient, receipt, log_index_bounds=[0,999999999]):
    """Return all logs matching transfer signature to the recipient before the end index."""
    lower_idx, upper_idx = log_index_bounds
    retval = []
    for log in receipt.logs:
        if log.logIndex >= lower_idx and log.logIndex <= upper_idx:
            try:
                if log.address == token and log.topics[0].hex() == ERC20_TRANSFER_EVENT_SIG and topic_is_address(log.topics[2], recipient):
                    retval.append(log)
            # Ignore anonymous events (logs without topics).
            except IndexError:
                pass
    return retval

def is_valid_wallet_address(address):
    """Return True is address is a valid ETH address. Else False."""
    if not Web3.isAddress(address):
        return False
    return True

def token_to_float(token_long, decimals):
    if not token_long:
        return 0
    return int(token_long) / (10**decimals)

def eth_to_float(gwei):
    return token_to_float(gwei, ETH_DECIMALS)

def lp_to_float(lp_long):
    return token_to_float(lp_long, LP_DECIMALS)

def bean_to_float(bean_long):
    return token_to_float(bean_long, BEAN_DECIMALS)

def soil_to_float(soil_long):
    return token_to_float(soil_long, SOIL_DECIMALS)

def stalk_to_float(stalk_long):
    return token_to_float(stalk_long, STALK_DECIMALS)

def seeds_to_float(seeds_long):
    return token_to_float(seeds_long, SEED_DECIMALS)

def pods_to_float(pod_long):
    return token_to_float(pod_long, POD_DECIMALS)

def underlying_if_unripe(token):
    if token.startswith(UNRIPE_TOKEN_PREFIX):
        return UNRIPE_UNDERLYING_MAP[token]
    return token

def get_test_entries(dry_run=None):
    """Get a list of onchain transaction entries to use for testing."""
    from attributedict.collections import AttributeDict
    from hexbytes import HexBytes

    time.sleep(1)

    if dry_run:
        if dry_run[0] == 'all':
            return dry_run_entries.entries
        elif dry_run[0] == 'seasons':
            return []
        else:
            entries = []
            for i in range(len(dry_run)):
                entries.append(AttributeDict({"transactionHash": HexBytes(dry_run[i])}))
            return entries
