import asyncio
import os
from collections import OrderedDict
from enum import IntEnum

from constants.spectra import SPECTRA_SPINTO_POOLS
from data_access.contracts.tractor_events import TractorEvents
from tools.util import get_txn_receipt
from web3 import Web3
from web3 import exceptions as web3_exceptions
from web3.logs import DISCARD
from web3.datastructures import AttributeDict

from data_access.contracts.util import *

from constants.addresses import *

# NOTE(funderberker): Pretty lame that we cannot automatically parse these from the ABI files.
#   Technically it seems very straight forward, but it is not implemented in the web3 lib and
#   parsing it manually is not any better than just writing it out here.


def add_event_to_dict(signature, sig_dict, sig_list):
    """Add both signature_hash and event_name to the bidirectional dict.

    Configure as a bijective map. Both directions will be added for each event type:
        - signature_hash:event_name
        - event_name:signature_hash
    """
    event_name = signature.split("(")[0]
    event_signature_hash = Web3.keccak(text=signature).hex()
    sig_dict[event_name] = event_signature_hash
    sig_dict[event_signature_hash] = event_name
    sig_list.append(event_signature_hash)
    # NOTE Must config prior to logs otherwise all logging breaks
    # logging.basicConfig(level=logging.INFO)
    # logging.info(f'event signature: {signature}  -  hash: {event_signature_hash}')

AQUIFER_EVENT_MAP = {}
AQUIFER_SIGNATURES_LIST = []
# IERC20 types will just be addresses.
add_event_to_dict(
    "BoreWell(address,address,address[],(address,bytes),(address,bytes)[],bytes)",  # IERC == address
    AQUIFER_EVENT_MAP,
    AQUIFER_SIGNATURES_LIST,
)


WELL_EVENT_MAP = {}
WELL_SIGNATURES_LIST = []
# IERC20 types will just be addresses.
add_event_to_dict(
    "Swap(address,address,uint256,uint256,address)", WELL_EVENT_MAP, WELL_SIGNATURES_LIST
)
add_event_to_dict("AddLiquidity(uint256[],uint256,address)", WELL_EVENT_MAP, WELL_SIGNATURES_LIST)
add_event_to_dict(
    "RemoveLiquidity(uint256,uint256[],address)", WELL_EVENT_MAP, WELL_SIGNATURES_LIST
)
add_event_to_dict(
    "RemoveLiquidityOneToken(uint256,address,uint256,address)", WELL_EVENT_MAP, WELL_SIGNATURES_LIST
)
add_event_to_dict("Shift(uint256[],address,uint256,address)", WELL_EVENT_MAP, WELL_SIGNATURES_LIST)
add_event_to_dict("Sync(uint256[],uint256,address)", WELL_EVENT_MAP, WELL_SIGNATURES_LIST)


BEANSTALK_EVENT_MAP = {}
BEANSTALK_SIGNATURES_LIST = []
add_event_to_dict(
    "Sow(address,uint256,uint256,uint256,uint256)", BEANSTALK_EVENT_MAP, BEANSTALK_SIGNATURES_LIST
)
add_event_to_dict(
    "Harvest(address,uint256,uint256[],uint256)", BEANSTALK_EVENT_MAP, BEANSTALK_SIGNATURES_LIST
)
add_event_to_dict(
    "AddDeposit(address,address,int96,uint256,uint256)",
    BEANSTALK_EVENT_MAP,
    BEANSTALK_SIGNATURES_LIST,
)
add_event_to_dict(
    "RemoveDeposit(address,address,int96,uint256,uint256)",
    BEANSTALK_EVENT_MAP,
    BEANSTALK_SIGNATURES_LIST,
)
add_event_to_dict(
    "RemoveDeposits(address,address,int96[],uint256[],uint256,uint256[])",
    BEANSTALK_EVENT_MAP,
    BEANSTALK_SIGNATURES_LIST,
)
add_event_to_dict(
    "Convert(address,address,address,uint256,uint256)",
    BEANSTALK_EVENT_MAP,
    BEANSTALK_SIGNATURES_LIST,
)
add_event_to_dict(
    "ConvertDownPenalty(address,uint256,uint256)",
    BEANSTALK_EVENT_MAP,
    BEANSTALK_SIGNATURES_LIST,
)
add_event_to_dict(
    "PublishRequisition(((address,bytes,bytes32[],uint256,uint256,uint256),bytes32,bytes))",
    BEANSTALK_EVENT_MAP,
    BEANSTALK_SIGNATURES_LIST,
)
add_event_to_dict(
    "CancelBlueprint(bytes32)",
    BEANSTALK_EVENT_MAP,
    BEANSTALK_SIGNATURES_LIST,
)
add_event_to_dict(
    "Tractor(address,address,bytes32,uint256,uint256)",
    BEANSTALK_EVENT_MAP,
    BEANSTALK_SIGNATURES_LIST,
)
add_event_to_dict(
    "TractorExecutionBegan(address,address,bytes32,uint256,uint256)",
    BEANSTALK_EVENT_MAP,
    BEANSTALK_SIGNATURES_LIST,
)
add_event_to_dict(
    "Chop(address,address,uint256,uint256)", BEANSTALK_EVENT_MAP, BEANSTALK_SIGNATURES_LIST
)
add_event_to_dict("Plant(address,uint256)", BEANSTALK_EVENT_MAP, BEANSTALK_SIGNATURES_LIST)
add_event_to_dict("Pick(address,address,uint256)", BEANSTALK_EVENT_MAP, BEANSTALK_SIGNATURES_LIST)
# On Fertilizer contract.
add_event_to_dict(
    "ClaimFertilizer(uint256[],uint256)", BEANSTALK_EVENT_MAP, BEANSTALK_SIGNATURES_LIST
)
# Needed to identify cases where AddDeposit should be ignored
add_event_to_dict(
    "L1DepositsMigrated(address,address,uint256[],uint256[],uint256[])",
    BEANSTALK_EVENT_MAP,
    BEANSTALK_SIGNATURES_LIST,
)

# Season/sunrise events
SEASON_EVENT_MAP = {}
SEASON_SIGNATURES_LIST = []
add_event_to_dict(
    "Sunrise(uint256)",
    SEASON_EVENT_MAP,
    SEASON_SIGNATURES_LIST,
)
add_event_to_dict(
    "SeasonOfPlentyWell(uint256,address,address,uint256)",
    SEASON_EVENT_MAP,
    SEASON_SIGNATURES_LIST,
)
add_event_to_dict(
    "SeasonOfPlentyField(uint256)",
    SEASON_EVENT_MAP,
    SEASON_SIGNATURES_LIST,
)

# Farmer's market events.
MARKET_EVENT_MAP = {}
MARKET_SIGNATURES_LIST = []
add_event_to_dict(
    "PodListingCreated(address,uint256,uint256,uint256,uint256,uint24,uint256,uint256,uint8)",
    MARKET_EVENT_MAP,
    MARKET_SIGNATURES_LIST,
)
add_event_to_dict(
    "PodListingFilled(address,address,uint256,uint256,uint256,uint256,uint256)",
    MARKET_EVENT_MAP,
    MARKET_SIGNATURES_LIST,
)
add_event_to_dict("PodListingCancelled(address,uint256,uint256)", MARKET_EVENT_MAP, MARKET_SIGNATURES_LIST)
add_event_to_dict(
    "PodOrderCreated(address,bytes32,uint256,uint256,uint24,uint256,uint256)",
    MARKET_EVENT_MAP,
    MARKET_SIGNATURES_LIST,
)
add_event_to_dict(
    "PodOrderFilled(address,address,bytes32,uint256,uint256,uint256,uint256,uint256)",
    MARKET_EVENT_MAP,
    MARKET_SIGNATURES_LIST,
)
add_event_to_dict("PodOrderCancelled(address,bytes32)", MARKET_EVENT_MAP, MARKET_SIGNATURES_LIST)

# Barn Raise events.
FERTILIZER_EVENT_MAP = {}
FERTILIZER_SIGNATURES_LIST = []
add_event_to_dict(
    "TransferSingle(address,address,address,uint256,uint256)",
    FERTILIZER_EVENT_MAP,
    FERTILIZER_SIGNATURES_LIST,
)
add_event_to_dict(
    "TransferBatch(address,address,address,uint256[],uint256[])",
    FERTILIZER_EVENT_MAP,
    FERTILIZER_SIGNATURES_LIST,
)
# Needed to identify when fert mints should be ignored
add_event_to_dict(
    "L1FertilizerMigrated(address,address,uint256[],uint128[],uint128)",
    FERTILIZER_EVENT_MAP,
    FERTILIZER_SIGNATURES_LIST,
)

# L2 Migration events
CONTRACTS_MIGRATED_EVENT_MAP = {}
CONTRACTS_MIGRATED_SIGNATURES_LIST = []
add_event_to_dict(
    "L1BeansMigrated(address,uint256,uint8)",
    CONTRACTS_MIGRATED_EVENT_MAP,
    CONTRACTS_MIGRATED_SIGNATURES_LIST,
)
add_event_to_dict(
    "L1DepositsMigrated(address,address,uint256[],uint256[],uint256[])",
    CONTRACTS_MIGRATED_EVENT_MAP,
    CONTRACTS_MIGRATED_SIGNATURES_LIST,
)
add_event_to_dict(
    "L1PlotsMigrated(address,address,uint256[],uint256[])",
    CONTRACTS_MIGRATED_EVENT_MAP,
    CONTRACTS_MIGRATED_SIGNATURES_LIST,
)
add_event_to_dict(
    "L1InternalBalancesMigrated(address,address,address[],uint256[])",
    CONTRACTS_MIGRATED_EVENT_MAP,
    CONTRACTS_MIGRATED_SIGNATURES_LIST,
)
add_event_to_dict(
    "L1FertilizerMigrated(address,address,uint256[],uint128[],uint128)",
    CONTRACTS_MIGRATED_EVENT_MAP,
    CONTRACTS_MIGRATED_SIGNATURES_LIST,
)
add_event_to_dict(
    "ReceiverApproved(address,address)",
    CONTRACTS_MIGRATED_EVENT_MAP,
    CONTRACTS_MIGRATED_SIGNATURES_LIST,
)

# Integrations (sPinto)
INTEGRATIONS_EVENT_MAP = {}
INTEGRATIONS_SIGNATURES_LIST = []
add_event_to_dict(
    "Deposit(address,address,uint256,uint256)",
    INTEGRATIONS_EVENT_MAP,
    INTEGRATIONS_SIGNATURES_LIST,
)
add_event_to_dict(
    "Withdraw(address,address,address,uint256,uint256)",
    INTEGRATIONS_EVENT_MAP,
    INTEGRATIONS_SIGNATURES_LIST,
)
add_event_to_dict(
    "TokenExchange(address,uint256,uint256,uint256,uint256)",
    INTEGRATIONS_EVENT_MAP,
    INTEGRATIONS_SIGNATURES_LIST,
)
add_event_to_dict(
    "AddLiquidity(address,uint256[2],uint256,uint256)",
    INTEGRATIONS_EVENT_MAP,
    INTEGRATIONS_SIGNATURES_LIST,
)
add_event_to_dict(
    "RemoveLiquidity(address,uint256[2],uint256)",
    INTEGRATIONS_EVENT_MAP,
    INTEGRATIONS_SIGNATURES_LIST,
)
add_event_to_dict(
    "RemoveLiquidityOne(address,uint256,uint256,uint256)",
    INTEGRATIONS_EVENT_MAP,
    INTEGRATIONS_SIGNATURES_LIST,
)

class EventClientType(IntEnum):
    BEANSTALK = 0
    SEASON = 1
    MARKET = 2
    BARN_RAISE = 3
    WELL = 4
    AQUIFER = 5
    CONTRACT_MIGRATED = 6
    INTEGRATIONS = 7

class TxnPair:
    """The logs, in order, associated with a transaction."""

    txn_hash = ""
    logs = []

    def __init__(self, txn_hash, logs):
        self.txn_hash = txn_hash
        self.logs = logs

class EthEventsClient:
    def __init__(self, client_types, addresses=[]):
        if not client_types:
            raise ValueError("Mut specify at least one client type")

        # Track recently seen txns to avoid processing same txn multiple times.
        self._recent_processed_txns = OrderedDict()
        self._web3 = get_web3_instance()
        self._client_types = client_types

        self._contracts = []
        self._contract_addresses = []
        self._signature_list = []
        self._events_dict = {}

        for client_type in client_types:
            if client_type == EventClientType.AQUIFER:
                self._contracts.append(get_aquifer_contract())
                self._contract_addresses.append(AQUIFER_ADDR)
                self._signature_list.extend(AQUIFER_SIGNATURES_LIST)
                self._events_dict.update(AQUIFER_EVENT_MAP)
            elif client_type == EventClientType.WELL:
                self._contracts.append(get_well_contract(None))
                self._contract_addresses.extend(addresses)
                self._signature_list.extend(WELL_SIGNATURES_LIST)
                self._events_dict.update(WELL_EVENT_MAP)
            elif client_type == EventClientType.BEANSTALK:
                self._contracts.append(get_beanstalk_contract())
                self._contract_addresses.append(BEANSTALK_ADDR)
                self._signature_list.extend(BEANSTALK_SIGNATURES_LIST)
                self._events_dict.update(BEANSTALK_EVENT_MAP)
            elif client_type == EventClientType.SEASON:
                self._contracts.append(get_beanstalk_contract())
                self._contract_addresses.append(BEANSTALK_ADDR)
                self._signature_list.extend(SEASON_SIGNATURES_LIST)
                self._events_dict.update(SEASON_EVENT_MAP)
            elif client_type == EventClientType.MARKET:
                self._contracts.append(get_beanstalk_contract())
                self._contract_addresses.append(BEANSTALK_ADDR)
                self._signature_list.extend(MARKET_SIGNATURES_LIST)
                self._events_dict.update(MARKET_EVENT_MAP)
            elif client_type == EventClientType.BARN_RAISE:
                self._contracts.append(get_fertilizer_contract())
                self._contracts.append(get_beanstalk_contract())
                self._contract_addresses.extend([FERTILIZER_ADDR, BEANSTALK_ADDR])
                self._signature_list.extend(FERTILIZER_SIGNATURES_LIST)
                self._events_dict.update(FERTILIZER_EVENT_MAP)
            elif client_type == EventClientType.CONTRACT_MIGRATED:
                self._contracts.append(get_beanstalk_contract())
                self._contract_addresses.append(BEANSTALK_ADDR)
                self._signature_list.extend(CONTRACTS_MIGRATED_SIGNATURES_LIST)
                self._events_dict.update(CONTRACTS_MIGRATED_EVENT_MAP)
            elif client_type == EventClientType.INTEGRATIONS:
                self._contracts.append(get_wrapped_silo_contract(SPINTO_ADDR))
                self._contracts.extend(get_curve_spectra_contract(s.pool) for s in SPECTRA_SPINTO_POOLS)
                self._contract_addresses.append(SPINTO_ADDR)
                self._contract_addresses.extend(s.pool for s in SPECTRA_SPINTO_POOLS)
                self._signature_list.extend(INTEGRATIONS_SIGNATURES_LIST)
                self._events_dict.update(INTEGRATIONS_EVENT_MAP)
        self._set_filters()

    def _set_filters(self):
        """This is located in a method so it can be reset on the fly."""
        self._event_filters = []
        for address in self._contract_addresses:
            self._event_filters.append(
                safe_create_filter(
                    self._web3,
                    address=address,
                    topics=[self._signature_list],
                    from_block=os.environ.get("DRY_RUN_FROM_BLOCK", "latest"),
                    to_block=os.environ.get("DRY_RUN_TO_BLOCK", "latest"),
                )
            )

    def get_log_range(self, from_block, to_block="latest"):
        filters = []
        for address in self._contract_addresses:
            filters.append(
                safe_create_filter(
                    self._web3,
                    address=address,
                    topics=[self._signature_list],
                    from_block=from_block,
                    to_block=to_block,
                )
            )
        return self.get_new_logs(filters=filters, get_all=True)

    def get_log_with_topics(self, event_name, indexed_topics):
        """Returns all matching logs"""
        signature = [s for s in self._events_dict if event_name in self._events_dict[s]]
        if signature:
            filters = []
            for address in self._contract_addresses:
                filters.append(
                    safe_create_filter(
                        self._web3,
                        address=address,
                        topics=[signature[0], *indexed_topics],
                        from_block=0,
                        to_block="latest"
                    )
                )
            return self.get_new_logs(filters=filters, get_all=True)
        return []

    def get_new_logs(self, dry_run=None, filters=None, get_all=False):
        """Iterate through all entries passing filter and return list of decoded Log Objects.

        Each on-chain event triggered creates one log, which is associated with one entry. We
        assume that an entry here will contain only one log of interest. It is
        possible to have multiple entries on the same block though, with each entry
        representing a unique txn.

        Note that there may be multiple unique entries with the same topic. Though we assume
        each entry indicates one log of interest.
        """
        self_filters = filters is None
        if self_filters:
            filters = self._event_filters
        # All decoded logs of interest from each txn.
        txn_hash_set = set()
        txn_logs_list = []

        if not dry_run:
            new_entries = []
            # Loop filters to accommodate reset in case of errors
            for i in range(len(filters)):
                try_count = 0
                while try_count < 3:
                    try_count += 1
                    try:
                        new_entries.extend(self.safe_get_new_entries(filters[i], get_all=get_all))
                        break
                    except (
                        ValueError,
                        asyncio.TimeoutError,
                        websockets.exceptions.ConnectionClosedError,
                        Exception,
                    ) as e:
                        logging.warning(e, exc_info=True)
                        logging.warning(
                            f"[{self_filters}] filter.safe_get_new_entries() failed or timed out. Retrying..."
                        )
                        time.sleep(1)
                        # Establish new filters and re-loop
                        self._set_filters()
                        filters = self._event_filters
        else:
            new_entries = get_test_entries(dry_run)
            time.sleep(3)

        # Track which unique logs have already been processed from this event batch.
        for entry in new_entries:
            # There can be zero topics for dry run
            if len(entry.get("topics", [])) > 0:
                topic_hash = entry["topics"][0].hex()
                # Do not process topics outside of this classes topics of interest.
                if topic_hash not in self._events_dict:
                    logging.warning(
                        f"Unexpected topic ({topic_hash}) seen in "
                        f"{', '.join(ct.name for ct in self._client_types)} EthEventsClient"
                    )
                    continue

            # Do not process the same txn multiple times.
            txn_hash = entry["transactionHash"]
            if txn_hash in txn_hash_set:
                continue

            # Retrieve the full txn and txn receipt.
            receipt = get_txn_receipt(self._web3, txn_hash)
            decoded_logs = self.logs_from_receipt(receipt)

            # Add all remaining txn logs to log map.
            txn_hash_set.add(txn_hash)
            tractor_separated = TractorEvents(receipt, decoded_logs)
            # If tractor logs are present, this inserts multiple entries for each tractor bound.
            for logs in tractor_separated.all_separated_events():
                txn_logs_list.append(TxnPair(txn_hash, logs))

        txn_logs_list.sort(key=lambda entry: (entry.logs[0].receipt.blockNumber if entry.logs else float('inf'), entry.logs[0].logIndex if entry.logs else float('inf')))
        return txn_logs_list

    def safe_get_new_entries(self, filter, get_all=False):
        """Retrieve all new entries that pass the filter.

        Returns one entry for every log that matches a filter. So if a single txn has multiple logs
        of interest this will return multiple entries.
        Catch any exceptions that may arise when attempting to connect to Infura.
        """

        if get_all or "DRY_RUN_FROM_BLOCK" in os.environ:
            return filter.get_all_entries()
        # We must verify new_entries because get_new_entries() will occasionally pull
        # entries that are not actually new. May be a bug with web3 or may just be a relic
        # of the way block confirmations work.
        new_entries = filter.get_new_entries()
        new_unique_entries = []
        # Remove entries w txn hashes that already processed on past get_new_entries calls.
        for i in range(len(new_entries)):
            entry = new_entries[i]
            # If we have not already processed this txn hash.
            if entry.transactionHash not in self._recent_processed_txns:
                new_unique_entries.append(entry)
            else:
                pass
                # logging.warning(
                #     f"Ignoring txn that has already been processed ({entry.transactionHash})"
                # )
        # Add all new txn hashes to recent processed set/dict.
        for entry in new_unique_entries:
            # Arbitrary value. Using this as a set.
            self._recent_processed_txns[entry.transactionHash] = True
        # Keep the recent txn queue size within limit.
        for _ in range(max(0, len(self._recent_processed_txns) - TXN_MEMORY_SIZE_LIMIT)):
            self._recent_processed_txns.popitem(last=False)
        return new_unique_entries
        # return filter.get_all_entries() # Use this to search for old events.

    def logs_from_receipt(self, receipt):
        """Decode and return all logs of interest from the given receipt"""
        decoded_logs = []
        for signature in self._signature_list:
            for contract in self._contracts:
                try:
                    decoded_type_logs = contract.events[
                        self._events_dict[signature]
                    ]().processReceipt(receipt, errors=DISCARD)
                except web3_exceptions.ABIEventFunctionNotFound:
                    continue
                for log in decoded_type_logs:
                    # Attach the full receipt
                    updated_log = AttributeDict({**dict(log), "receipt": receipt})
                    decoded_logs.append(updated_log)
        return decoded_logs

def safe_create_filter(web3, address, topics, from_block, to_block):
    """Create a filter but handle connection exceptions that web3 cannot manage."""
    max_tries = 15
    try_count = 0
    while try_count < max_tries:
        try:
            filter_params = {
                "topics": topics,
                "fromBlock": from_block,
                "toBlock": to_block
            }
            # Include the address in the filter params only if it is not None
            if address:
                filter_params["address"] = address
            return web3.eth.filter(filter_params)
        except websockets.exceptions.ConnectionClosedError as e:
            logging.warning(e, exc_info=True)
            time.sleep(2)
            try_count += 1
    raise Exception("Failed to safely create filter")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    filter = safe_create_filter(
        get_web3_instance(),
        address=BEANSTALK_ADDR,
        topics=[BEANSTALK_SIGNATURES_LIST],
        from_block="256715188",
        to_block="256715781",
    )
    entries = filter.get_new_entries()
    logging.info(f"found {len(entries)} entries")
