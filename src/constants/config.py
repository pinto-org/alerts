import sys
import os
import logging
from constants.addresses import *
from web3 import Web3

# Misc configuration constants

# Strongly encourage Python 3.8+.
# If not 3.8+ uncaught exceptions on threads will not be logged.
MIN_PYTHON = (3, 8)
if sys.version_info < MIN_PYTHON:
    logging.critical(
        "Python %s.%s or later is required for proper exception logging.\n" % MIN_PYTHON
    )
LOGGING_FORMAT_STR_SUFFIX = "%(levelname)s : %(asctime)s : %(message)s"
LOGGING_FORMATTER = logging.Formatter(LOGGING_FORMAT_STR_SUFFIX)

BEANSTALK_GRAPH_ENDPOINT = "https://graph.pinto.money/pintostalk"
BEAN_GRAPH_ENDPOINT = "https://graph.pinto.money/pinto"
BASIN_GRAPH_ENDPOINT = "https://graph.pinto.money/exchange"
API_ENDPOINT = "https://api.pinto.money"

# The following time values are all provided in seconds.
SEASON_DURATION = 3600
PREVIEW_CHECK_PERIOD = 10
BEANSTALK_CHECK_RATE = 10
PEG_CHECK_PERIOD = 10
WELL_CHECK_RATE = 10
# Initial time to wait before reseting dead monitor.
RESET_MONITOR_DELAY_INIT = 15

# Bytes in 100 megabytes.
ONE_HUNDRED_MEGABYTES = 100 * 1000000
# Timestamp for deployment of Basin.
BASIN_DEPLOY_EPOCH = 1732033800

DISCORD_NICKNAME_LIMIT = 32

# For WalletMonitoring - I dont think this is actually used
WALLET_WATCH_LIMIT = 10

RPC_URL = "https://" + os.environ["RPC_URL"]
if "localhost" in RPC_URL:
    RPC_URL = RPC_URL.replace("https", "http")
ENS_RPC_URL = os.environ["ENS_RPC_URL"]

# Decimals for conversion from chain int values to float decimal values.
ETH_DECIMALS = 18
LP_DECIMALS = 18
BEAN_DECIMALS = 6
SOIL_DECIMALS = 6
STALK_DECIMALS = 16
SEED_DECIMALS = 6
POD_DECIMALS = 6
WELL_LP_DECIMALS = 18

# Number of txn hashes to keep in memory to prevent duplicate processing.
TXN_MEMORY_SIZE_LIMIT = 100

# Newline character to get around limits of f-strings.
NEWLINE_CHAR = "\n"

ERC20_TRANSFER_EVENT_SIG = Web3.keccak(text="Transfer(address,address,uint256)").hex()

# Incomplete of Beanstalk Terming of Tokens for human use.
SILO_TOKENS_MAP = {
    BEAN_ADDR.lower(): "PINTO",
    WETH.lower(): "WETH",
    CBETH.lower(): "cbETH",
    CBBTC.lower(): "cbBTC",
    WSOL.lower(): "WSOL",
    USDC.lower(): "USDC",
    PINTO_WETH_ADDR.lower(): "PINTOWETH",
    PINTO_CBETH_ADDR.lower(): "PINTOcbETH",
    PINTO_CBBTC_ADDR.lower(): "PINTOcbBTC",
    PINTO_WSOL_ADDR.lower(): "PINTOWSOL",
    PINTO_USDC_ADDR.lower(): "PINTOUSDC",
}

WHITELISTED_WELLS = [
    PINTO_CBETH_ADDR,
    PINTO_CBBTC_ADDR,
    PINTO_USDC_ADDR
]
DEWHITELISTED_WELLS = [
    PINTO_WSOL_ADDR,
    PINTO_WETH_ADDR
]

# Mapping of words to their emojis (see embellish_token_emojis function)
# Keys must be uppercase
is_prod = os.environ["IS_PROD"].lower() == "true"
DISCORD_TOKEN_EMOJIS = {
    "PT-SPINTO": "<:SpectraPT:1353112256723816488>" if is_prod else "<:SpectraPT:1353111805508976770>",
    "YT-SPINTO": "<:SpectraYT:1353112247240753162>" if is_prod else "<:SpectraYT:1353111793203019858>",
    "SPECTRA_LP": "<:SpectraLP:1353112268581113976>" if is_prod else "<:SpectraLP:1353111773812752535>",
    "PINTO": "<:PINTO:1308203775756075101>" if is_prod else "<:PINTO:1301707525149822976>",
    "PINTOWETH": "<:PINTOWETH:1308203737470206008>" if is_prod else "<:PINTOWETH:1301707650584678460>",
    "PINTOCBETH": "<:PINTOcbETH:1308203744487542796>" if is_prod else "<:PINTOcbETH:1301707637725069335>",
    "PINTOCBBTC": "<:PINTOcbBTC:1308203753354166333>" if is_prod else "<:PINTOcbBTC:1300620473591271515>",
    "PINTOWSOL": "<:PINTOWSOL:1308203729769463901>" if is_prod else "<:PINTOWSOL:1304499399669321859>",
    "PINTOUSDC": "<:PINTOUSDC:1308203762434969721>" if is_prod else "<:PINTOUSDC:1301707622839226388>",
    "SPINTO": "<:sPINTO:1346662452695273502>" if is_prod else "<:sPINTO:1346661973181333514>",
    "WETH": "<:WETH:1308203713164214312>" if is_prod else "<:WETH:1301707663830155368>",
    "CBETH": "<:cbETH:1308203784861650985>" if is_prod else "<:cbETH:1301707504627220511>",
    "CBBTC": "<:cbBTC:1308203792818241628>" if is_prod else "<:cbBTC:1301707489527464056>",
    "WSOL": "<:WSOL:1308203700149555231>" if is_prod else "<:WSOL:1304499424545996831>",
    "USDC": "<:USDC:1308203721225670656>" if is_prod else "<:USDC:1301707657270267966>",
    "MC": "<:PintoMC:1346666068717863025>" if is_prod else "<:PintoMC:1346666003097980968>"
}
TG_TOKEN_EMOJIS = {
    "PINTO": "🟢",
    "PINTOWETH": "🟤",
    "PINTOCBETH": "🔴",
    "PINTOCBBTC": "🟠",
    "PINTOWSOL": "🟣",
    "PINTOUSDC": "🔵",
    "SPINTO": "⚪️",
    "WETH": "🟤",
    "CBETH": "🔴",
    "CBBTC": "🟠",
    "WSOL": "🟣",
    "USDC": "🔵",
    "MC": "🧑‍🌾"
}

GRAPH_FIELDS_PLACEHOLDER = "_FIELDS_"

### From Beanstalk ###

# import sys
# import os
# import logging
# from constants.addresses import *
# from web3 import Web3

# # Misc configuration constants

# # Strongly encourage Python 3.8+.
# # If not 3.8+ uncaught exceptions on threads will not be logged.
# MIN_PYTHON = (3, 8)
# if sys.version_info < MIN_PYTHON:
#     logging.critical(
#         "Python %s.%s or later is required for proper exception logging.\n" % MIN_PYTHON
#     )
# LOGGING_FORMAT_STR_SUFFIX = "%(levelname)s : %(asctime)s : %(message)s"
# LOGGING_FORMATTER = logging.Formatter(LOGGING_FORMAT_STR_SUFFIX)

# DAO_SNAPSHOT_NAME = "beanstalkdao.eth"
# FARMS_SNAPSHOT_NAME = "beanstalkfarms.eth"

# BEANSTALK_GRAPH_ENDPOINT = "https://graph.bean.money/beanstalk"
# BEAN_GRAPH_ENDPOINT = "https://graph.bean.money/bean"
# BASIN_GRAPH_ENDPOINT = "https://graph.bean.money/basin"
# SNAPSHOT_GRAPH_ENDPOINT = "https://hub.snapshot.org/graphql"

# # The following time values are all provided in seconds.
# SEASON_DURATION = 3600
# PREVIEW_CHECK_PERIOD = 5
# BEANSTALK_CHECK_RATE = 5
# PEG_CHECK_PERIOD = 5
# WELL_CHECK_RATE = 5
# BARN_RAISE_CHECK_RATE = 10
# # Initial time to wait before reseting dead monitor.
# RESET_MONITOR_DELAY_INIT = 15

# # Bytes in 100 megabytes.
# ONE_HUNDRED_MEGABYTES = 100 * 1000000
# # Timestamp for deployment of Basin.
# BASIN_DEPLOY_EPOCH = 1692814103

# DISCORD_NICKNAME_LIMIT = 32

# # For WalletMonitoring - I dont think this is actually used
# WALLET_WATCH_LIMIT = 10

# RPC_URL = "https://" + os.environ["RPC_URL"]

# # Decimals for conversion from chain int values to float decimal values.
# ETH_DECIMALS = 18
# LP_DECIMALS = 18
# BEAN_DECIMALS = 6
# SOIL_DECIMALS = 6
# STALK_DECIMALS = 16
# SEED_DECIMALS = 6
# POD_DECIMALS = 6
# WELL_LP_DECIMALS = 18

# # Number of txn hashes to keep in memory to prevent duplicate processing.
# TXN_MEMORY_SIZE_LIMIT = 100

# # Newline character to get around limits of f-strings.
# NEWLINE_CHAR = "\n"

# ERC20_TRANSFER_EVENT_SIG = Web3.keccak(text="Transfer(address,address,uint256)").hex()

# # Incomplete of Beanstalk Terming of Tokens for human use.
# SILO_TOKENS_MAP = {
#     BEAN_ADDR.lower(): "BEAN",
#     BEAN_ETH_ADDR.lower(): "BEANETH",
#     BEAN_WSTETH_ADDR.lower(): "BEANwstETH",
#     BEAN_WEETH_ADDR.lower(): "BEANweETH",
#     BEAN_WBTC_ADDR.lower(): "BEANWBTC",
#     BEAN_USDC_ADDR.lower(): "BEANUSDC",
#     BEAN_USDT_ADDR.lower(): "BEANUSDT",
#     UNRIPE_ADDR.lower(): "urBEAN",
#     UNRIPE_LP_ADDR.lower(): "urBEANwstETH"
# }

# WHITELISTED_WELLS = [
#     BEAN_ETH_ADDR,
#     BEAN_WSTETH_ADDR,
#     BEAN_WEETH_ADDR,
#     BEAN_WBTC_ADDR,
#     BEAN_USDC_ADDR,
#     BEAN_USDT_ADDR
# ]

# UNRIPE_UNDERLYING_MAP = {
#     UNRIPE_ADDR: BEAN_ADDR,
#     UNRIPE_LP_ADDR: BEAN_WSTETH_ADDR
# }

# GRAPH_FIELDS_PLACEHOLDER = "_FIELDS_"
