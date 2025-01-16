from gql import Client
from gql.transport.aiohttp import AIOHTTPTransport

from data_access.subgraphs.util import *
from data_access.contracts.util import *
from constants.addresses import *
from constants.config import *

class BeanGraphClient(object):
    def __init__(self):
        transport = AIOHTTPTransport(url=BEAN_GRAPH_ENDPOINT)
        self._client = Client(
            transport=transport, fetch_schema_from_transport=False, execute_timeout=7
        )

    def last_cross(self):
        """Returns a dict containing the most recent peg cross."""
        return self.get_last_crosses(n=1)[0]

    def get_last_crosses(self, n=1):
        """Retrieve the last n peg crosses, including timestamp and cross direction.

        Args:
            n: number of recent crosses to retrieve.

        Returns:
            array of dicts containing timestamp and cross direction for each cross.
        """
        query_str = f"""
            query {{
                beanCrosses(first: {n}, orderBy: timestamp, orderDirection: desc) {{
                    id
                    above
                    timestamp
                }}
            }}
        """
        return execute(self._client, query_str)["beanCrosses"]
    
    def season_stats(self, num_seasons=2):
        query_str = f"""
            query {{
                beanHourlySnapshots(first: {num_seasons} orderBy: season__season orderDirection: desc) {{
                    supply
                    marketCap
                    instPrice
                    l2sr
                    crosses
                    deltaCrosses
                    season {{
                        season
                    }}
                }}
            }}
        """
        result = execute(self._client, query_str)
        # Return list of BeanSeasonStats class instances
        return [BeanSeasonStats(result, i) for i in range(len(result["beanHourlySnapshots"]))]

class BeanSeasonStats:
    def __init__(self, graph_response, result_index):
        bean_hourly = graph_response["beanHourlySnapshots"][result_index]
        self.season = int(bean_hourly["season"]["season"])
        self.price = float(bean_hourly["instPrice"])
        self.supply = int(bean_hourly["supply"]) / 10 ** 6
        self.marketCap = float(bean_hourly["marketCap"])
        self.l2sr = float(bean_hourly["l2sr"])
        self.crosses = int(bean_hourly["crosses"])
        self.deltaCrosses = int(bean_hourly["deltaCrosses"])

if __name__ == "__main__":
    """Quick test and demonstrate functionality."""
    logging.basicConfig(level=logging.INFO)

    bean_sql_client = BeanGraphClient()
    print(f"Last peg cross: {bean_sql_client.last_cross()}")
    print(f"Last peg crosses: {bean_sql_client.get_last_crosses(4)}")
    print(f"Seasonal stats: {bean_sql_client.season_stats()[0].__dict__}")
    print(f"Seasonal crosses: {bean_sql_client.season_stats()[1].deltaCrosses}")
