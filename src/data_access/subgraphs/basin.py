from gql import Client
from gql.transport.aiohttp import AIOHTTPTransport

from data_access.subgraphs.util import *
from data_access.contracts.util import *
from constants.addresses import *
from constants.config import *

class BasinGraphClient(object):
    def __init__(self):
        transport = AIOHTTPTransport(url=BASIN_GRAPH_ENDPOINT)
        self._client = Client(
            transport=transport, fetch_schema_from_transport=False, execute_timeout=7
        )

    def get_latest_well_snapshots(self, num_snapshots):
        """Get a single well snapshot."""
        query_str = f"""
            query {{
                wells(orderBy: totalLiquidityUSD, orderDirection: desc, where: {{totalLiquidityUSD_gt: 1000}}) {{
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
        return execute(self._client, query_str)["wells"]

    def get_wells_stats(self):
        """Get high level stats of all wells."""
        query_str = f"""
            query {{
                wells(orderBy: totalLiquidityUSD, orderDirection: desc) {{
                    id
                    cumulativeTradeVolumeUSD
                    totalLiquidityUSD
                }}
            }}
        """
        # Create gql query and execute.
        return execute(self._client, query_str)["wells"]
    
    def get_well_liquidity(self, well):
        """Get the current USD liquidity for the requested Well"""
        query_str = f"""
            query {{
                well(id: "{well}") {{
                    totalLiquidityUSD
                }}
            }}
        """
        # Create gql query and execute.
        return execute(self._client, query_str).get("well").get("totalLiquidityUSD")

    def get_well_hourlies(self, timestamp):
        """
        Gets info from all whitelisted wells' hourly snapshots.
        Uses the hour corresponding to the provided timestmap
        """
        hour_id = int((timestamp - (timestamp % 3600)) / 3600)
        query_str = f"""
            query {{
                wellHourlySnapshots(where: {{ hour: {hour_id} }}) {{
                    deltaTradeVolumeUSD
                    well {{
                        id
                    }}
                }}
            }}
        """
        return execute(self._client, query_str)["wellHourlySnapshots"]

    def try_get_well_deposit_info(self, txn_hash, log_index):
        """Get deposit tokens. Retry if data not available. Return {} if it does not become available.

        This is expected to be used for realtime data retrieval, which means the subgraph may not yet have populated
        the data. Repeated queries give the subgraph a chance to catch up.
        """
        query_str = f"""
            query {{
                deposits(where: {{
                    logIndex: {log_index}
                    hash: "{txn_hash.hex()}"
                }}) {{
                    reserves
                    amountUSD
                }}
            }}
        """
        return try_execute_with_wait("deposits", self._client, query_str)[0]
