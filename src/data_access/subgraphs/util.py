import asyncio
import logging
import time

from gql import gql

from constants.config import *

# Reduce log spam from the gql package.
from gql.transport.aiohttp import log as requests_logger

requests_logger.setLevel(logging.WARNING)

class GraphAccessException(Exception):
    """Sustained failure to access the graph."""

def string_inject_fields(string, fields):
    """Modify string by replacing fields placeholder with stringified array of fields."""
    # Index where desired fields should be injected.
    fields_index_start = string.find(GRAPH_FIELDS_PLACEHOLDER)
    fields_index_end = string.find(GRAPH_FIELDS_PLACEHOLDER) + len(GRAPH_FIELDS_PLACEHOLDER)

    # Stringify array and inject it into query string.
    return string[:fields_index_start] + " ".join(fields) + string[fields_index_end:]

def execute(client, query_str, max_tries=10):
    """Convert query string into a gql query and execute query."""
    query = gql(query_str)

    try_count = 0
    retry_delay = 3  # seconds
    while not max_tries or try_count < max_tries:
        # logging.info(f"GraphQL query:" f'{query_str.replace(NEWLINE_CHAR, "").replace("    ", "")}')
        try_count += 1
        try:
            result = client.execute(query)
            # logging.info(f"GraphQL result:{result}")
            return result
        except asyncio.TimeoutError:
            logging.warning(f"Timeout error on {client_subgraph_name(client)} subgraph access. Retrying...")
        except RuntimeError as e:
            # This is a bad state. It means the underlying thread exiting without properly
            # stopping these threads. This state is never expected.
            logging.error(e)
            logging.error("Main thread no longer running. Exiting.")
            exit(1)
        except Exception as e:
            if try_count == max_tries:
                logging.warning(e, exc_info=True)
                logging.info(f"Failing GraphQL query: {query_str}")
            else:
                logging.warning(f"Error on {client_subgraph_name(client)} subgraph access. Retrying...")
        time.sleep(retry_delay)
    logging.error("Unable to access subgraph data")
    raise GraphAccessException

def try_execute_with_wait(check_key, client, query_str, check_len=False, max_tries=1, max_wait_blocks=10):
    """Perform execute. Wait a 5s and try again if return data is empty. Eventually return None if no data.

    Also do not raise exception on failure, log warning and proceed.
    """
    result = None
    for _ in range(max_wait_blocks):
        try:
            result = execute(client, query_str, max_tries=max_tries)[check_key]
            if check_len and len(result) == 0:
                result = None
        except GraphAccessException:
            pass
        if result is not None:  # null
            break
        logging.info("Data not found. Waiting 5s, retrying...")
        time.sleep(5)
    return result

def client_subgraph_name(client):
    """Return a plain string name of the subgraph for the given gql.Client object."""
    url = client.transport.url
    if url == BEAN_GRAPH_ENDPOINT:
        return "Bean"
    elif url == BEANSTALK_GRAPH_ENDPOINT:
        return "Beanstalk"
    elif url == BASIN_GRAPH_ENDPOINT:
        return "Basin"
    else:
        return "unknown"

def get_block_query_str(block_number="latest"):
    """Returns the block part of the query if something other than the latest block is requested"""
    return f"block: {{number: {block_number}}}" if block_number != 'latest' else ""
