from bots.util import *
from constants.spectra import SPECTRA_SPINTO_POOLS
from monitors.messages.spectra import spectra_pool_str
from monitors.messages.spinto import spinto_str
from monitors.monitor import Monitor
from data_access.contracts.util import *
from data_access.contracts.eth_events import *
from data_access.util import *
from constants.addresses import *
from constants.config import *

class IntegrationsMonitor(Monitor):
    """Monitors various external contracts interacting with beanstalk."""

    def __init__(self, msg_spinto, msg_spectra, prod=False, dry_run=None):
        super().__init__(
            "Integrations", None, BEANSTALK_CHECK_RATE, prod=prod, dry_run=dry_run
        )
        self.msg_spinto = msg_spinto
        self.msg_spectra = msg_spectra
        self._eth_event_client = EthEventsClient(EventClientType.INTEGRATIONS)

    def _monitor_method(self):
        last_check_time = 0
        while self._thread_active:
            if time.time() < last_check_time + self.query_rate:
                time.sleep(0.5)
                continue
            last_check_time = time.time()
            for txn_pair in self._eth_event_client.get_new_logs(dry_run=self._dry_run):
                try:
                    self._handle_txn_logs(txn_pair.logs)
                except Exception as e:
                    logging.info(f"\n\n=> Exception during processing of txnHash {txn_pair.txn_hash.hex()}\n")
                    raise

    def _handle_txn_logs(self, event_logs):
        for event_log in event_logs:
            # sPinto integration
            if event_log.address == SPINTO_ADDR:
                event_str = spinto_str(event_log)
                msg_fn = self.msg_spinto

            # spectra
            spectra_pool = next((s for s in SPECTRA_SPINTO_POOLS if event_log.address == s.pool), None)
            if spectra_pool:
                event_str = spectra_pool_str(event_log, spectra_pool)
                msg_fn = self.msg_spectra

            if not event_str:
                continue
            event_str += links_footer(event_logs[0].receipt)
            msg_fn(event_str)
