from bots.util import *
from monitors.monitor import Monitor
from data_access.contracts.util import *
from data_access.contracts.eth_events import *
from data_access.util import *
from constants.addresses import *
from constants.config import *

class ContractsMigrated(Monitor):
    """Monitor the Beanstalk contract for contract migration events."""

    def __init__(self, message_function, prod=False, dry_run=None):
        super().__init__(
            "Contract Migration", message_function, BEANSTALK_CHECK_RATE, prod=prod, dry_run=dry_run
        )
        self._eth_event_client = EthEventsClient([EventClientType.CONTRACT_MIGRATED])

    def _monitor_method(self):
        self.last_check_time = 0
        while self._thread_active:
            if time.time() < self.last_check_time + self.query_rate:
                time.sleep(0.5)
                continue
            self.last_check_time = time.time()
            for txn_pair in self._eth_event_client.get_new_logs(dry_run=self._dry_run):
                try:
                    self._handle_txn_logs(txn_pair.logs)
                except Exception as e:
                    logging.info(f"\n\n=> Exception during processing of txnHash {txn_pair.txn_hash.hex()}\n")
                    raise

    def _handle_txn_logs(self, event_logs):
        """Process the beanstalk event logs for a single txn.

        Note that Event Log Object is not the same as Event object.
        """

        event_str = ""
        breakdown_str = ""

        for event_log in event_logs:

            owner = event_log.args.get("owner")
            receiver = event_log.args.get("receiver")

            if event_log.event == "L1BeansMigrated":
                beans = round_num(token_to_float(event_log.args.get("amount"), 6))
                destination = 'circulating' if event_log.args.get("toMode") == 0 else 'internal'
                breakdown_str += f"\n- Received {beans} Beans to {destination} balance"
            elif event_log.event == "L1DepositsMigrated":
                all_bdv = event_log.args.get("bdvs")
                breakdown_str += f"\n- Received {round_num(sum(token_to_float(bdv, 6) for bdv in all_bdv))} bdv to the silo"
            elif event_log.event == "L1PlotsMigrated":
                all_pods = event_log.args.get("pods")
                breakdown_str += f"\n- Received {round_num(sum(token_to_float(pods, 6) for pods in all_pods))} pods"
            elif event_log.event == "L1InternalBalancesMigrated":
                tokens = event_log.args.get("tokens")
                breakdown_str += f"\n- Received balances of {len(tokens)} tokens to internal balance"
            elif event_log.event == "L1FertilizerMigrated":
                amounts = event_log.args.get("amounts")
                breakdown_str += f"\n- Received {sum(amounts)} fertilizer units across {len(amounts)} unique id(s)"
            elif event_log.event == "ReceiverApproved":
                breakdown_str += f"\n- Approved L2 receiver: {shorten_hash(receiver)}"
            else:
                continue

        if not breakdown_str:
            return
        
        if owner:
            event_str += f"L1 Owner: {shorten_hash(owner)}"

        event_str += f"\nL2 Receiver: {shorten_hash(receiver)}"
        event_str += breakdown_str

        event_str += links_footer(event_logs[0].receipt)
        self.message_function(event_str)
