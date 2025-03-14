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
    def __init__(self):
        transport = AIOHTTPTransport(url=BEANSTALK_GRAPH_ENDPOINT)
        self._client = Client(
            transport=transport, fetch_schema_from_transport=False, execute_timeout=7
        )

    def get_pod_listing(self, id, block_number=-1):
        """Get a single pod listing based on id.

        id is "{lister_address}-{listing_index}"
        """
        block_query_str = f"block: {{number: {block_number}}}" if block_number != -1 else ""

        query_str = f"""
            query {{
                podListing(
                    id: "{id}"
                    {block_query_str}
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
        return execute(self._client, query_str)["podListing"]

    def get_pod_order(self, id):
        """Get a single pod order based on id.

        id is arbitrary?
        """
        # Market order subgraph IDs are strings that must begin with 0x.
        if not id.startswith("0x"):
            id = "0x" + id
        query_str = f"""
            query {{
                podOrder(id: "{id}") {{
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
        return execute(self._client, query_str)["podOrder"]

    def get_fertilizer_bought(self):
        # Include Fertilizer from L1 which has not migrated yet
        query_str = """
            query {
                fertilizers {
                    supply
                    unmigratedL1Supply
                }
            }
        """
        # Create gql query and execute.
        result = execute(self._client, query_str)
        return float(result["fertilizers"][0]["supply"]) + float(result["fertilizers"][0]["unmigratedL1Supply"])

    def get_start_stalk_by_season(self, season):
        if season <= 1:
            return 0
        query_str = f"""
        query MyQuery {{
            siloHourlySnapshots(
                orderDirection: desc
                first: 1
                where: {{season: {season - 1}  silo: "{BEANSTALK_ADDR.lower()}"}}
            ) {{
                season
                stalk
            }}
        }}
        """
        # Create gql query and execute.
        return float(execute(self._client, query_str)["siloHourlySnapshots"][0]["stalk"])

    def silo_assets_seasonal_changes(self, current_silo_assets=None, previous_silo_assets=None):
        """Get address, delta balance, and delta BDV of all silo assets across last season.

        parameters are same shape as SeasonStats.pre_assets - lists of dicts.

        Note that season snapshots are created at the beginning of each season and updated throughout season.

        Returns:
            Map of asset deltas with keys [token, delta_amount, delta_bdv].
        """
        if current_silo_assets is None or previous_silo_assets is None:
            current_silo_assets, previous_silo_assets = [
                season_stats.pre_assets
                for season_stats in self.season_stats(
                    seasons=False, siloHourlySnapshots=True, fieldHourlySnapshots=False
                )
            ]

        # If there are a different number of assets between seasons, do not associate, just accept it is edge case and display less data.
        if len(current_silo_assets) != len(previous_silo_assets):
            logging.warning("Number of assets in this season changed. Was a new asset added?")
            return []

        assets_changes = []
        for i in range(len(previous_silo_assets)):
            assets_changes.append(AssetChanges(previous_silo_assets[i], current_silo_assets[i]))
        # logging.info(f"assets_changes: {assets_changes}")
        return assets_changes

    def season_stats(
        self,
        num_seasons=2,
        seasons=True,
        siloHourlySnapshots=True,
        fieldHourlySnapshots=True
    ):
        """Get a standard set of data corresponding to current season.

        Returns array of last 2 season in descending order, each value a graphql map structure of all requested data.
        """
        query_str = "query season_stats {"
        if seasons:
            query_str += f"""
                seasons(first: {num_seasons}, skip: 0, orderBy: season, orderDirection: desc) {{
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
                    orderBy: season
                    orderDirection: desc
                    first: {num_seasons * len(SILO_TOKENS_MAP)}
                    where: {{depositedAmount_gt: "0",
                             siloAsset_: {{silo: "{BEANSTALK_ADDR.lower()}"}}
                           }}
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
        result = execute(self._client, query_str)

        # Return list of SeasonStats class instances
        return [SeasonStats(result, i) for i in range(len(result["seasons"]))]


    # NOTE(funderberker): Hour to season conversion is imperfect. Unsure why.
    # Perhaps due to paused hours. Or subgraph data is different than expectations.
    # WARNING(funderberker): This is a very slow call on non-recent seasons.
    def get_season_id_by_timestamp(self, timestamp):
        pull_size = 500
        pulled_seasons = 0
        while True:
            query_str = f"""
                query {{
                    seasons(first: {pull_size}, skip: {pulled_seasons}, orderBy: season, orderDirection: desc) {{
                        id
                        createdAt
                    }}
                }}
            """
            seasons = execute(self._client, query_str)["seasons"]
            pulled_seasons += pull_size
            if timestamp < int(seasons[-1]["createdAt"]):
                continue
            # Assumes pulling in descending order.
            if timestamp > int(seasons[0]["createdAt"]):
                return int(seasons[0]["id"])
            for i in range(len(seasons) - 1):
                if timestamp < int(seasons[i]["createdAt"]) and timestamp >= int(
                    seasons[i + 1]["createdAt"]
                ):
                    return int(seasons[i + 1]["id"])

    def get_account_gspbdv(self, account):
        """Returns the current grown stalk per bdv of the requested account"""
        query_str = f"""
            query {{
                silo(id: "{account.lower()}") {{
                    stalk
                    depositedBDV
                }}
            }}
        """
        # Create gql query and execute.
        result = execute(self._client, query_str)
        return -1 + stalk_to_float(result["silo"]["stalk"]) / bean_to_float(result["silo"]["depositedBDV"])

class SeasonStats:
    """Standard object containing fields for all fields of interest for a single season.

    Populated from subgraph data.
    """

    def __init__(self, graph_seasons_response, season_index=0, season=None):
        """Create a SeasonStats object directly from the response of a graphql request.

        If the response contains multiple seasons use the season_index to pull desired season.
        """
        season_index = int(season_index)
        if season is None and "seasons" not in graph_seasons_response:
            raise ValueError(
                "Must specify season or include season data to create SeasonStats object."
            )
        self.season = season or graph_seasons_response["seasons"][season_index]["season"]
        if "seasons" in graph_seasons_response:
            self.created_at = graph_seasons_response["seasons"][season_index]["createdAt"]
            self.price = float(graph_seasons_response["seasons"][season_index]["price"])
            # deltaB at beginning of season
            self.delta_beans = bean_to_float(
                graph_seasons_response["seasons"][season_index]["deltaBeans"]
            )
            # time weighted deltaB based from previous 2 seasons - same as from oracle - used to determine mints and soil
            self.delta_b = bean_to_float(graph_seasons_response["seasons"][season_index]["deltaB"])
            self.total_beans = bean_to_float(
                graph_seasons_response["seasons"][season_index]["beans"]
            )  # Bean supply
            # silo rewards + fert rewards + pods harvestable
            self.reward_beans = bean_to_float(
                graph_seasons_response["seasons"][season_index]["rewardBeans"]
            )
            self.incentive_beans = bean_to_float(
                graph_seasons_response["seasons"][season_index]["incentiveBeans"]
            )
            self.sunrise_block = int(
                graph_seasons_response["seasons"][season_index]["sunriseBlock"]
            )
        if "siloHourlySnapshots" in graph_seasons_response:
            # Beans minted this season # newFarmableBeans
            self.stalk = stalk_to_float(
                graph_seasons_response["siloHourlySnapshots"][season_index]["stalk"]
            )
            self.silo_hourly_bean_mints = bean_to_float(
                graph_seasons_response["siloHourlySnapshots"][season_index]["deltaBeanMints"]
            )
            self.deposited_bdv = bean_to_float(
                graph_seasons_response["siloHourlySnapshots"][season_index]["depositedBDV"]
            )
            self.beanToMaxLpGpPerBdvRatio = int(graph_seasons_response["siloHourlySnapshots"][season_index]["beanToMaxLpGpPerBdvRatio"])
            # List of each asset at the start of the season. Note that this is offset by 1 from subgraph data.
            self.pre_assets = []
            # logging.info(
            #     f'siloAssetHourlySnapshots: {graph_seasons_response["siloAssetHourlySnapshots"]}'
            # )
            for asset_season_snapshot in graph_seasons_response["siloAssetHourlySnapshots"]:
                # Shift back by one season since asset amounts represent current/end of season values.
                if int(asset_season_snapshot["season"]) == self.season - 1:
                    self.pre_assets.append(asset_season_snapshot)
            # logging.info(f"self.pre_assets: {self.pre_assets}")
        if "fieldHourlySnapshots" in graph_seasons_response:
            self.temperature = float(
                graph_seasons_response["fieldHourlySnapshots"][season_index]["temperature"]
            )
            self.pod_rate = float(
                graph_seasons_response["fieldHourlySnapshots"][season_index]["podRate"]
            )
            self.issued_soil = soil_to_float(
                graph_seasons_response["fieldHourlySnapshots"][season_index]["issuedSoil"]
            )
            self.sown_beans = bean_to_float(
                graph_seasons_response["fieldHourlySnapshots"][season_index]["deltaSownBeans"]
            )
            self.new_pods = bean_to_float(
                graph_seasons_response["fieldHourlySnapshots"][season_index]["deltaPodIndex"]
            )

class AssetChanges:
    """Class representing change in state of an asset across seasons."""

    def __init__(self, init_season_asset, final_season_asset):
        self.init_season_asset = init_season_asset
        self.final_season_asset = final_season_asset
        self.token = init_season_asset["siloAsset"]["token"]
        self.delta_asset = int(final_season_asset["depositedAmount"]) - int(
            init_season_asset["depositedAmount"]
        )
        # self.delta_asset_percent = (
        #     int(final_season_asset['depositedAmount']) /
        #     int(init_season_asset['depositedAmount']) - 1) * 100
        self.delta_bdv = int(final_season_asset["depositedBDV"]) - int(
            init_season_asset["depositedBDV"]
        )
        # self.delta_bdv_percent = (
        #     int(final_season_asset['depositedBDV']) /
        #     int(init_season_asset['depositedBDV']) - 1) * 100
