from data_access.subgraphs.season_stats import BeanstalkSeasonStats
from gql import Client
from gql.transport.aiohttp import AIOHTTPTransport

from data_access.subgraphs.util import *
from data_access.contracts.util import *
from constants.addresses import *
from constants.config import *

# Funderberker comment:
# Somewhat arbitrary prediction of number of assets that have to be pulled to be sure that all
# assets of interest across 1 most recent season are retrieved. This is a function of number of
# assets. User will need to consider potential early leading seasons from withdrawals, and
# bypassing ongoing season season. So should be
# at least current # of assets * 3 (with 1 season withdraw delay). This is used to
# pull down graph data that is not properly grouped by season due to implementation issues with
# subgraph. Will probably need to be increased someday. Would be better to find it
# programmatically, but regularly checking the subgraph creates an inefficiency and I am tired
# of compensating for subgraph implementation problems here.
MAX_ASSET_SNAPSHOTS_PER_SEASON = 10

class BeanstalkGraphClient(object):
    _transport = AIOHTTPTransport(url=BEANSTALK_GRAPH_ENDPOINT)
    _client = Client(transport=_transport, fetch_schema_from_transport=False, execute_timeout=7)

    def __init__(self, block_number="latest"):
        self.block_number = block_number

    @classmethod
    def get_client(cls):
        return cls._client

    def get_pod_listing(self, id, block_number=None):
        """Get a single pod listing based on id.

        id is "{lister_address}-{listing_index}"
        """
        query_str = f"""
            query {{
                podListing(
                    {get_block_query_str(block_number or self.block_number)}
                    id: "{id}"
                ) {{
                    id
                    status
                    pricePerPod
                    amount
                    originalAmount
                    filled
                    index
                    start
                }}
            }}
        """
        # Create gql query and execute.
        return execute(self.get_client(), query_str)["podListing"]

    def get_pod_order(self, id, block_number=None):
        """Get a single pod order based on id."""
        # Market order subgraph IDs are strings that must begin with 0x.
        if not id.startswith("0x"):
            id = "0x" + id
        query_str = f"""
            query {{
                podOrder(
                    {get_block_query_str(block_number or self.block_number)}
                    id: "{id}"
                ) {{
                    maxPlaceInLine
                    id
                    pricePerPod
                    beanAmount
                    beanAmountFilled
                    podAmountFilled
                }}
            }}
        """
        # Create gql query and execute.
        return execute(self.get_client(), query_str)["podOrder"]

    def season_stats(
        self,
        num_seasons=2,
        seasons=True,
        siloHourlySnapshots=True,
        fieldHourlySnapshots=True,
        block_number=None
    ):
        """Get a standard set of data corresponding to current season.

        Returns array of last 2 season in descending order, each value a graphql map structure of all requested data.
        """
        query_str = "query season_stats {"
        if seasons:
            query_str += f"""
                seasons(
                    {get_block_query_str(block_number or self.block_number)}
                    first: {num_seasons}
                    skip: 0
                    orderBy: season
                    orderDirection: desc
                ) {{
                    season
                    createdAt
                    price
                    deltaBeans
                    deltaB
                    beans
                    rewardBeans
                    incentiveBeans
                    sunriseBlock
                }}
            """
        if siloHourlySnapshots:
            query_str += f"""
                siloHourlySnapshots(
                    {get_block_query_str(block_number or self.block_number)}
                    where: {{silo: "{BEANSTALK_ADDR.lower()}"}}
                    orderBy: season
                    orderDirection: desc
                    first: {num_seasons}
                ){{
                    season
                    stalk
                    deltaBeanMints
                    depositedBDV
                    beanToMaxLpGpPerBdvRatio
                }}
                siloAssetHourlySnapshots(
                    {get_block_query_str(block_number or self.block_number)}
                    where: {{
                        depositedAmount_gt: "0",
                        siloAsset_: {{silo: "{BEANSTALK_ADDR.lower()}"}}
                    }}
                    orderBy: season
                    orderDirection: desc
                    first: {num_seasons * len(SILO_TOKENS_MAP)}
                ) {{
                    depositedAmount
                    depositedBDV
                    season
                    siloAsset {{
                        token
                    }}
                }}
            """
        if fieldHourlySnapshots:
            query_str += f"""
                fieldHourlySnapshots(
                    {get_block_query_str(block_number or self.block_number)}
                    where: {{field: "{BEANSTALK_ADDR.lower()}"}}
                    orderBy: season
                    orderDirection: desc
                    first: {num_seasons}
                ) {{
                    id
                    season
                    temperature
                    podRate
                    issuedSoil
                    deltaSownBeans
                    deltaPodIndex
                }}
            """

        query_str += "}"

        # Create gql query and execute.
        result = execute(self.get_client(), query_str)

        # Return list of BeanstalkSeasonStats class instances
        return [BeanstalkSeasonStats(result, i) for i in range(len(result["seasons"]))]

    def get_account_gspbdv(self, account, block_number=None):
        """Returns the current grown stalk per bdv of the requested account"""
        query_str = f"""
            query {{
                silo(
                    {get_block_query_str(block_number or self.block_number)}
                    id: "{account.lower()}"
                ) {{
                    stalk
                    depositedBDV
                }}
            }}
        """
        # Create gql query and execute.
        result = execute(self.get_client(), query_str)
        return -1 + stalk_to_float(result["silo"]["stalk"]) / bean_to_float(result["silo"]["depositedBDV"])
