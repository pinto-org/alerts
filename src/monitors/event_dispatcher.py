import logging
import time
from collections import Counter
from concurrent.futures import ALL_COMPLETED, ThreadPoolExecutor, wait

from constants.addresses import *
from constants.config import *
from constants.spectra import SPECTRA_SPINTO_POOLS
from data_access.contracts.eth_events import *
from data_access.contracts.util import get_rpc_request_counts
from monitors.monitor import Monitor


class EventRoute:
    def __init__(self, name, monitor, event_names, handler, addresses=None, batch_handler=None):
        self.name = name
        self.monitor = monitor
        self.event_names = set(event_names)
        self.handler = handler
        self.addresses = {addr.lower() for addr in addresses} if addresses else None
        self.batch_handler = batch_handler

    def logs_for_txn(self, txn_pair):
        route_logs = []
        for log in txn_pair.logs:
            if log.event not in self.event_names:
                continue
            if self.addresses is not None and log.address.lower() not in self.addresses:
                continue
            route_logs.append(log)
        return route_logs


class EventDispatcher(Monitor):
    """Poll one shared event client and route decoded transaction logs to monitors."""

    def __init__(self, routes, well_addresses, prod=False, dry_run=None):
        super().__init__("EventDispatcher", None, BEANSTALK_CHECK_RATE, prod=prod, dry_run=dry_run)
        self.routes = routes
        self._eth_event_client = EthEventsClient(
            [
                EventClientType.WELL,
                EventClientType.BEANSTALK,
                EventClientType.MARKET,
                EventClientType.INTEGRATIONS,
            ],
            well_addresses,
            combine_filters=True,
        )

    def _monitor_method(self):
        self.last_check_time = 0
        self.last_heartbeat_time = time.time()
        logging.info(
            "EventDispatcher started with "
            f"{len(self._eth_event_client._event_filters)} shared filter(s)"
        )
        while self._thread_active:
            if time.time() - self.last_heartbeat_time > 15 * 60:
                logging.info("EventDispatcher heartbeat")
                self.last_heartbeat_time = time.time()
            if time.time() < self.last_check_time + self.query_rate:
                time.sleep(0.5)
                continue

            self.last_check_time = time.time()
            for route in self.routes:
                route.monitor.last_check_time = self.last_check_time

            rpc_counts_before = get_rpc_request_counts()
            txn_pairs = self._eth_event_client.get_new_logs(dry_run=self._dry_run)
            route_counts = self._dispatch(txn_pairs)
            rpc_counts_after = get_rpc_request_counts()
            self._log_cycle_counts(txn_pairs, route_counts, rpc_counts_before, rpc_counts_after)

    def _dispatch(self, txn_pairs):
        route_counts = {
            route.name: {
                "txns": 0,
                "logs": 0,
                "errors": 0,
            }
            for route in self.routes
        }

        for txn_pair in txn_pairs:
            for route in self.routes:
                route_logs = route.logs_for_txn(txn_pair)
                if not route_logs:
                    continue

                route_log_count = len(route_logs)
                route_counts[route.name]["txns"] += 1
                route_counts[route.name]["logs"] += route_log_count
                if route.batch_handler:
                    continue
                try:
                    route.handler(txn_pair.txn_hash, list(route_logs))
                except Exception:
                    route_counts[route.name]["errors"] += 1
                    logging.error(
                        f"EventDispatcher route {route.name} failed for txn "
                        f"{txn_pair.txn_hash.hex()}",
                        exc_info=True,
                    )

        for route in self.routes:
            if not route.batch_handler:
                continue

            route_txns = []
            for txn_pair in txn_pairs:
                route_logs = route.logs_for_txn(txn_pair)
                if route_logs:
                    route_txns.append((txn_pair.txn_hash, list(route_logs)))
            if not route_txns:
                continue

            try:
                route_counts[route.name]["errors"] += route.batch_handler(route_txns)
            except Exception:
                route_counts[route.name]["errors"] += len(route_txns)
                logging.error(
                    f"EventDispatcher batch route {route.name} failed",
                    exc_info=True,
                )

        for route in self.routes:
            if hasattr(route.monitor, "on_event_dispatcher_cycle"):
                route.monitor.on_event_dispatcher_cycle(route_counts[route.name]["txns"])

        return route_counts

    def _log_cycle_counts(self, txn_pairs, route_counts, rpc_counts_before, rpc_counts_after):
        decoded_log_count = sum(len(txn_pair.logs) for txn_pair in txn_pairs)
        method_counts_before = Counter(rpc_counts_before["methods"])
        method_counts_after = Counter(rpc_counts_after["methods"])
        rpc_method_counts = method_counts_after - method_counts_before
        route_counts_str = ", ".join(
            f"{route_name}=txns:{counts['txns']}/logs:{counts['logs']}/errors:{counts['errors']}"
            for route_name, counts in route_counts.items()
        )
        logging.info(
            "EventDispatcher cycle: "
            f"filters={len(self._eth_event_client._event_filters)}, "
            f"rpc_methods=[{self._format_counts(rpc_method_counts)}], "
            f"decoded_txns={len(txn_pairs)}, decoded_logs={decoded_log_count}, "
            f"routes=[{route_counts_str}]"
        )

    def _format_counts(self, method_counts):
        if not method_counts:
            return "none"
        return ", ".join(
            f"{method}={count}" for method, count in method_counts.most_common()
        )


def event_names_from_map(event_map):
    return {key for key in event_map if isinstance(key, str) and not key.startswith("0x")}


def dispatch_well_messages(wells_monitor, txn_hash, logs):
    for msg_fn, event_str, to_tg in wells_monitor._handle_txn_logs(txn_hash, logs):
        msg_fn(event_str, to_tg=to_tg)


def dispatch_well_messages_batch(wells_monitor, route_txns):
    error_count = 0
    batch_size = 25
    with ThreadPoolExecutor(max_workers=batch_size) as executor:
        for i in range(0, len(route_txns), batch_size):
            batch = route_txns[i:i + batch_size]
            futures = []
            future_to_hash = {}
            for txn_hash, logs in batch:
                future = executor.submit(wells_monitor._handle_txn_logs, txn_hash, logs)
                futures.append(future)
                future_to_hash[future] = txn_hash

            wait(futures, return_when=ALL_COMPLETED)

            for future in futures:
                try:
                    messages = future.result()
                    for msg_fn, event_str, to_tg in messages:
                        msg_fn(event_str, to_tg=to_tg)
                except Exception:
                    error_count += 1
                    logging.error(
                        f"EventDispatcher Well route failed for txn "
                        f"{future_to_hash[future].hex()}",
                        exc_info=True,
                    )
    return error_count


def main_discord_event_routes(wells_monitor, beanstalk_monitor, market_monitor, integrations_monitor):
    integration_addresses = [SPINTO_ADDR, *[s.pool for s in SPECTRA_SPINTO_POOLS]]
    return [
        EventRoute(
            "Well",
            wells_monitor,
            event_names_from_map(WELL_EVENT_MAP),
            lambda txn_hash, logs: dispatch_well_messages(wells_monitor, txn_hash, logs),
            addresses=wells_monitor.pool_addresses,
            batch_handler=lambda route_txns: dispatch_well_messages_batch(wells_monitor, route_txns),
        ),
        EventRoute(
            "Beanstalk",
            beanstalk_monitor,
            event_names_from_map(BEANSTALK_EVENT_MAP),
            lambda txn_hash, logs: beanstalk_monitor._handle_txn_logs(logs),
            addresses=[BEANSTALK_ADDR],
        ),
        EventRoute(
            "Market",
            market_monitor,
            event_names_from_map(MARKET_EVENT_MAP),
            lambda txn_hash, logs: market_monitor._handle_txn_logs(txn_hash, logs),
            addresses=[BEANSTALK_ADDR],
        ),
        EventRoute(
            "Integrations",
            integrations_monitor,
            event_names_from_map(INTEGRATIONS_EVENT_MAP),
            lambda txn_hash, logs: integrations_monitor._handle_txn_logs(logs),
            addresses=integration_addresses,
        ),
    ]
