import logging

from data_access.contracts.util import bean_to_float, soil_to_float, stalk_to_float

def silo_assets_seasonal_changes(current_silo_assets, previous_silo_assets):
    """Generates AssetChanges class for the deltas in each of the provided time points for these silo assets"""

    # If there are a different number of assets between seasons, do not associate, just accept it is edge case and display less data.
    if len(current_silo_assets) != len(previous_silo_assets):
        logging.warning("Number of assets in this season changed. Was a new asset added?")
        return []

    assets_changes = []
    for i in range(len(previous_silo_assets)):
        assets_changes.append(AssetChanges(previous_silo_assets[i], current_silo_assets[i]))
    return assets_changes

class BeanstalkSeasonStats:
    """Oobject encapsulating beanstalk subgraph season data"""

    def __init__(self, graph_seasons_response, season_index=0, season=None):
        """
        Create directly from the response of a graphql request.
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
            # silo rewards + pods harvestable
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
            for asset_season_snapshot in graph_seasons_response["siloAssetHourlySnapshots"]:
                # Shift back by one season since asset amounts represent current/end of season values.
                if int(asset_season_snapshot["season"]) == self.season - 1:
                    self.pre_assets.append(asset_season_snapshot)
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
        self.delta_bdv = int(final_season_asset["depositedBDV"]) - int(
            init_season_asset["depositedBDV"]
        )

class BeanSeasonStats:
    """Oobject encapsulating bean subgraph season data"""

    def __init__(self, bean_graph_response, result_index):
        bean_hourly = bean_graph_response["beanHourlySnapshots"][result_index]
        self.season = int(bean_hourly["season"]["season"])
        self.price = float(bean_hourly["instPrice"])
        self.supply = int(bean_hourly["supply"]) / 10 ** 6
        self.marketCap = float(bean_hourly["marketCap"])
        self.l2sr = float(bean_hourly["l2sr"])
        self.crosses = int(bean_hourly["crosses"])
        self.deltaCrosses = int(bean_hourly["deltaCrosses"])
