from data_access.contracts.beanstalk import BeanstalkClient

from bots.util import *
from monitors.monitor import Monitor
from data_access.contracts.util import *
from data_access.contracts.eth_events import *
from data_access.contracts.bean import BeanClient
from data_access.subgraphs.beanstalk import BeanstalkGraphClient
from data_access.util import *
from constants.addresses import *
from constants.config import *

class MarketMonitor(Monitor):
    """Monitor the Beanstalk contract for market events."""

    def __init__(self, message_function, prod=False, dry_run=None):
        super().__init__(
            "Market", message_function, BEANSTALK_CHECK_RATE, prod=prod, dry_run=dry_run
        )
        self._eth_event_client = EthEventsClient([EventClientType.MARKET])
        self.beanstalk_contract = get_beanstalk_contract()

    def _monitor_method(self):
        self.last_check_time = 0
        while self._thread_active:
            if time.time() < self.last_check_time + self.query_rate:
                time.sleep(0.5)
                continue
            self.last_check_time = time.time()
            for txn_pair in self._eth_event_client.get_new_logs(dry_run=self._dry_run):
                try:
                    self._handle_txn_logs(txn_pair.txn_hash, txn_pair.logs)
                except Exception as e:
                    logging.info(f"\n\n=> Exception during processing of txnHash {txn_pair.txn_hash.hex()}\n")
                    raise

    def _handle_txn_logs(self, txn_hash, event_logs):
        """Process the beanstalk event logs for a single txn.

        Note that Event Log Object is not the same as Event object.
        """
        # Match the txn invoked method. Matching is done on the first 10 characters of the hash.
        transaction_receipt = get_txn_receipt(self._web3, txn_hash)

        # Handle txn logs individually using default strings.
        for event_log in event_logs:
            event_str = self.farmers_market_str(event_log, transaction_receipt)
            # Ignore second+ events for a single multi-event transaction.
            if not event_str:
                continue
            event_str += links_footer(event_logs[0].receipt)
            self.message_function(event_str)

    def farmers_market_str(self, event_log, transaction_receipt):
        """Create a human-readable string representing an event related to the farmer's market.

        Assumes event_log is an event of one of the types implemented below.
        Uses events from Beanstalk contract.
        """
        bean_client = BeanClient(block_number=event_log.blockNumber)
        beanstalk_client = BeanstalkClient(block_number=event_log.blockNumber)
        beanstalk_graph_client = BeanstalkGraphClient(block_number=event_log.blockNumber)

        event_str = ""
        bean_amount = 0
        pod_amount = 0

        cost_in_beans = bean_to_float(event_log.args.get("costInBeans"))

        if cost_in_beans or event_log.event == "PodListingCreated":
            pod_amount = pods_to_float(event_log.args.get("podAmount"))
        else:
            bean_amount = bean_to_float(event_log.args.get("beanAmount"))

        price_per_pod = pods_to_float(event_log.args.get("pricePerPod"))
        if cost_in_beans:
            bean_amount = cost_in_beans

        if not bean_amount:
            bean_amount = pod_amount * price_per_pod
        if not pod_amount and price_per_pod:
            pod_amount = bean_amount / price_per_pod
        if not price_per_pod and pod_amount:
            price_per_pod = bean_amount / pod_amount

        # Index of the plot (place in line of first pod of the plot).
        plot_index = pods_to_float(event_log.args.get("index"))
        # ID of the order.
        order_id = event_log.args.get("id")
        if order_id:
            # order_id = order_id.decode('utf8')
            # order_id = self._web3.keccak(text=order_id).hex()
            order_id = order_id.hex()
        # Index of earliest pod to list, relative to start of plot.
        relative_start_index = pods_to_float(event_log.args.get("start"))
        # Absolute index of the first pod to list.
        start_index = plot_index + relative_start_index
        # Current index at start of pod line (number of pods ever harvested).
        pods_harvested = beanstalk_client.get_harvested_pods()
        # Lowest place in line of a listing.
        start_place_in_line = start_index - pods_harvested
        # Highest place in line an order will purchase.
        order_max_place_in_line = pods_to_float(event_log.args.get("maxPlaceInLine"))

        bean_price = bean_client.avg_bean_price()
        start_place_in_line_str = round_num(start_place_in_line, 0)
        order_max_place_in_line_str = round_num(order_max_place_in_line, 0)

        # If this was a pure cancel (not relist, reorder, or harvest).
        if (
            event_log.event == "PodListingCancelled"
            and not self.beanstalk_contract.events["PodListingCreated"]().processReceipt(
                transaction_receipt, errors=DISCARD
            )
            and not self.beanstalk_contract.events["PodOrderFilled"]().processReceipt(
                transaction_receipt, errors=DISCARD
            )
            and not self.beanstalk_contract.events["Harvest"]().processReceipt(
                transaction_receipt, errors=DISCARD
            )
        ) or (
            event_log.event == "PodOrderCancelled"
            and not self.beanstalk_contract.events["PodOrderCreated"]().processReceipt(
                transaction_receipt, errors=DISCARD
            )
            and not self.beanstalk_contract.events["PodListingFilled"]().processReceipt(
                transaction_receipt, errors=DISCARD
            )
        ):
            if event_log.event == "PodListingCancelled":
                listing_graph_id = event_log.args.get("lister").lower() + "-" + str(event_log.args.get("index"))
                pod_listing = beanstalk_graph_client.get_pod_listing(listing_graph_id)
                # If this listing did not exist, or was inactive, ignore cancellation.
                if pod_listing is None or pod_listing["status"] != "CANCELLED":
                    logging.info(
                        f"Ignoring listing cancel with graph id {listing_graph_id} and txn hash {event_log.transactionHash.hex()}"
                    )
                    return ""
                pod_amount_str = round_num(pods_to_float(int(pod_listing["amount"])), 0)
                start_place_in_line_str = round_num(
                    pods_to_float(int(pod_listing["index"]) + int(pod_listing["start"]))
                    - pods_harvested,
                    0,
                )
                price_per_pod_str = round_num(bean_to_float(pod_listing["pricePerPod"]), 3)
                event_str += f"❌ Pod Listing Cancelled"
                event_str += f" - {pod_amount_str} Pods Listed at {start_place_in_line_str} @ {price_per_pod_str} Pinto/Pod"
            else:
                pod_order = beanstalk_graph_client.get_pod_order(order_id)
                # If this order did not exist, ignore cancellation.
                if pod_order is None:
                    logging.info(
                        f"Ignoring null order cancel with graph id {order_id} and txn hash {event_log.transactionHash.hex()}"
                    )
                    return ""
                pod_amount = (float(pod_order["beanAmount"]) - float(pod_order["beanAmountFilled"])) / float(pod_order["pricePerPod"])
                max_place = pods_to_float(pod_order["maxPlaceInLine"])
                price_per_pod = bean_to_float(pod_order["pricePerPod"])
                event_str += f"❌ Pod Order Cancelled"
                event_str += f" - {round_num(pod_amount,0)} Pods Ordered before {round_num(max_place,0)} @ {round_num(price_per_pod,3)} Pinto/Pod"
        # If a new listing or relisting.
        elif event_log.event == "PodListingCreated":
            # Check if this was a relist, if so send relist message.
            if self.beanstalk_contract.events["PodListingCancelled"]().processReceipt(
                transaction_receipt, errors=DISCARD
            ):
                # Check if this plot was already listed before this transaction
                listing_graph_id = event_log.args.get("lister").lower() + "-" + str(event_log.args.get("index"))
                pod_listing = beanstalk_graph_client.get_pod_listing(listing_graph_id, block_number=event_log.blockNumber - 1)
                if pod_listing is not None and pod_listing["status"] == "ACTIVE":
                    event_str += f"♻ Pods re-Listed"
                else:
                    event_str += f"✏ Pods Listed"
            else:
                event_str += f"✏ Pods Listed"
            expiration = pods_to_float(event_log.args.get("maxHarvestableIndex")) - pods_harvested
            expiration_str = round_num(expiration, 0, avoid_zero=True)
            event_str += f" - {round_num(pod_amount, 0)} Pods Listed at {start_place_in_line_str} @ {round_num(price_per_pod, 3)} Pinto/Pod ({round_num(pod_amount * bean_price * price_per_pod, avoid_zero=True, incl_dollar=True)})"
            event_str += f"\n_Expires once the Pod Line moves by {expiration_str} Pod{'s' if expiration_str != '1' else ''}_"
            event_str += f"\n⚖️ <https://pinto.money/market/pods/buy/{event_log.args.get('index')}>"
        # If a new order or reorder.
        elif event_log.event == "PodOrderCreated":
            # Check if this was a relist.
            if self.beanstalk_contract.events["PodOrderCancelled"]().processReceipt(
                transaction_receipt, errors=DISCARD
            ):
                event_str += f"♻ Pods re-Ordered"
            else:
                event_str += f"🖌 Pods Ordered"
            event_str += f" - {round_num(pod_amount, 0)} Pods Ordered before {order_max_place_in_line_str} @ {round_num(price_per_pod, 3)} Pinto/Pod ({round_num(pod_amount * bean_price * price_per_pod, avoid_zero=True, incl_dollar=True)})"
            event_str += f"\n<https://pinto.money/market/pods/sell/0x{order_id}>"
        # If a fill.
        elif event_log.event in ["PodListingFilled", "PodOrderFilled"]:
            event_str += f"💰 Pods Exchanged - "
            # Pull the Bean Transfer log to find cost.
            if event_log.event == "PodListingFilled":
                event_str += f"{round_num(pod_amount, 0)} Pods Listed at {start_place_in_line_str} in Line Filled"
                if price_per_pod:
                    event_str += f" @ {round_num(price_per_pod, 3)} Pinto/Pod ({round_num(bean_price * bean_amount, avoid_zero=True, incl_dollar=True)})"
                    event_str += f"\n{value_to_emojis(bean_price * bean_amount)}"
            elif event_log.event == "PodOrderFilled":
                event_str += (
                    f"{round_num(pod_amount, 0)} Pods Ordered at "
                    f"{start_place_in_line_str} in Line Filled @ {round_num(price_per_pod, 3)} "
                    f"Pinto/Pod ({round_num(bean_price * bean_amount, avoid_zero=True, incl_dollar=True)})"
                )
                event_str += f"\n{value_to_emojis(bean_price * bean_amount)}"
        return event_str
