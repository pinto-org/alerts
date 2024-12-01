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

    def bean_price(self):
        """Returns float representing the most recent cost of a BEAN in USD."""
        return float(self.get_bean_field("price"))

    def get_bean_field(self, field):
        """Get a single field from the bean object."""
        return self.get_bean_fields(fields=[field])[field]

    def get_bean_fields(self, fields=["price"]):
        """Retrieve the specified fields for the bean token.

        Args:
            fields: an array of strings specifying which fields should be retried.

        Returns:
            dict containing all request field:value pairs (fields and values are strings).

        Raises:
            gql.transport.exceptions.TransportQueryError: Invalid field name provided.
        """
        # General query string with bean sub fields placeholder.
        query_str = (
            """
            query get_bean_fields {
                beans(first: 1)
                { """
            + GRAPH_FIELDS_PLACEHOLDER
            + """ }
            }
        """
        )
        # Stringify array and inject fields into query string.
        query_str = string_inject_fields(query_str, fields)

        # Create gql query and execute.
        # Note that there is always only 1 bean item returned.
        return execute(self._client, query_str)["beans"][0]

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
    
    def get_seasonal_stats(self, season_num):
        query_str = f"""
            query {{
                beanHourlySnapshot(id: "{BEAN_ADDR.lower()}-{season_num}") {{
                    price
                    supply
                    marketCap
                    supplyInPegLP
                    deltaCrosses
                }}
            }}
        """
        return BeanSeasonStats(execute(self._client, query_str))

class BeanSeasonStats:
    def __init__(self, graph_response):
        self.price = float(graph_response["beanHourlySnapshot"]["price"])
        self.supply = int(graph_response["beanHourlySnapshot"]["supply"]) / 10 ** 6
        self.marketCap = float(graph_response["beanHourlySnapshot"]["marketCap"])
        self.supplyInPegLP = float(graph_response["beanHourlySnapshot"]["supplyInPegLP"])
        self.deltaCrosses = int(graph_response["beanHourlySnapshot"]["deltaCrosses"])

if __name__ == "__main__":
    """Quick test and demonstrate functionality."""
    logging.basicConfig(level=logging.INFO)

    bean_sql_client = BeanGraphClient()
    print(f"Last peg cross: {bean_sql_client.last_cross()}")
    print(f"Last peg crosses: {bean_sql_client.get_last_crosses(4)}")
    print(f"Seasonal stats: {bean_sql_client.get_seasonal_stats(267).__dict__}")
    print(f"Seasonal crosses: {bean_sql_client.get_seasonal_stats(267).deltaCrosses}")
