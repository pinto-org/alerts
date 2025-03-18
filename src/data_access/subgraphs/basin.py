from gql import Client
from gql.transport.aiohttp import AIOHTTPTransport

from data_access.subgraphs.util import *
from data_access.contracts.util import *
from constants.addresses import *
from constants.config import *

class BasinGraphClient(object):
    _transport = AIOHTTPTransport(url=BASIN_GRAPH_ENDPOINT)

    def __init__(self, block_number="latest"):
        self.block_number = block_number
        self.client = Client(transport=BasinGraphClient._transport, fetch_schema_from_transport=False, execute_timeout=7)

    def get_latest_well_snapshots(self, num_snapshots, block_number=None):
        """Get a single well snapshot."""
        query_str = f"""
            query {{
                wells(
                    {get_block_query_str(block_number or self.block_number)}
                    where: {{totalLiquidityUSD_gt: 1000}}
                    orderBy: totalLiquidityUSD
                    orderDirection: desc
                ) {{
                    id
                    name
                    symbol
                    dailySnapshots(first: {num_snapshots}, orderBy: day, orderDirection: desc) {{
                        totalLiquidityUSD
                        deltaTradeVolumeUSD
                    }}
                }}
            }}
        """
        # Create gql query and execute.
        return execute(self.client, query_str)["wells"]

    def get_wells_stats(self, block_number=None):
        """Get high level stats of all wells."""
        query_str = f"""
            query {{
                wells(
                    {get_block_query_str(block_number or self.block_number)}
                    orderBy: totalLiquidityUSD
                    orderDirection: desc
                ) {{
                    id
                    cumulativeTradeVolumeUSD
                    totalLiquidityUSD
                }}
            }}
        """
        # Create gql query and execute.
        return execute(self.client, query_str)["wells"]
    
    def get_well_liquidity(self, well, block_number=None):
        """Get the current USD liquidity for the requested Well"""
        query_str = f"""
            query {{
                well(
                    {get_block_query_str(block_number or self.block_number)}
                    id: "{well}"
                ) {{
                    totalLiquidityUSD
                }}
            }}
        """
        # Create gql query and execute.
        return execute(self.client, query_str).get("well").get("totalLiquidityUSD")

    def get_well_hourlies(self, timestamp, block_number=None):
        """
        Gets info from all whitelisted wells' hourly snapshots.
        Uses the hour corresponding to the provided timestmap
        """
        hour_id = int((timestamp - (timestamp % 3600)) / 3600)
        query_str = f"""
            query {{
                wellHourlySnapshots(
                    {get_block_query_str(block_number or self.block_number)}
                    where: {{ hour: {hour_id} }}
                ) {{
                    deltaTradeVolumeUSD
                    well {{
                        id
                    }}
                }}
            }}
        """
        return execute(self.client, query_str)["wellHourlySnapshots"]

    def get_add_liquidity_info(self, txn_hash, log_index, block_number=None):
        """Get deposit tokens. Retry if data not available. Return None if it does not become available.

        This is expected to be used for realtime data retrieval, which means the subgraph may not yet have populated
        the data. Repeated queries give the subgraph a chance to catch up.
        """
        query_str = f"""
            query {{
                trades(
                    {get_block_query_str(block_number or self.block_number)}
                    where: {{
                        tradeType: "ADD_LIQUIDITY"
                        hash: "{txn_hash.hex()}"
                        logIndex: {log_index}
                    }}
                ) {{
                    liqReservesAmount
                    transferVolumeUSD
                }}
            }}
        """
        result = try_execute_with_wait("trades", self.client, query_str, check_len=True)
        return result[0] if result else None
