from bots.util import *
from constants.spectra import SPECTRA_SPINTO_POOLS
from monitors.messages.morpho import morpho_market_str
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

    def __init__(self, msg_spinto, msg_spectra, msg_morpho, prod=False, dry_run=None):
        super().__init__(
            "Integrations", None, BEANSTALK_CHECK_RATE, prod=prod, dry_run=dry_run
        )
        self.msg_spinto = msg_spinto
        self.msg_spectra = msg_spectra
        self.msg_morpho = msg_morpho
        self._eth_event_clients = [
            EthEventsClient([EventClientType.SPINTO_SPECTRA]),
            EthEventsClient([EventClientType.MORPHO]),
        ]

    def _monitor_method(self):
        last_check_time = 0
        while self._thread_active:
            if time.time() < last_check_time + self.query_rate:
                time.sleep(0.5)
                continue
            last_check_time = time.time()
            for client in self._eth_event_clients:
                for txn_pair in client.get_new_logs(dry_run=self._dry_run):
                    try:
                        self._handle_txn_logs(txn_pair.logs)
                    except Exception as e:
                        logging.info(f"\n\n=> Exception during processing of txnHash {txn_pair.txn_hash.hex()}\n")
                        raise

    def _handle_txn_logs(self, event_logs):
        for event_log in event_logs:
            event_str = None
            # sPinto integration
            if event_log.address == SPINTO_ADDR:
                event_str = spinto_str(event_log)
                msg_fn = self.msg_spinto

            # spectra
            spectra_pool = next((s for s in SPECTRA_SPINTO_POOLS if event_log.address == s.pool), None)
            if spectra_pool:
                event_str = spectra_pool_str(event_log, spectra_pool)
                msg_fn = self.msg_spectra

            # morpho
            if event_log.address == MORPHO:
                morpho_market = next((m for m in MORPHO_MARKETS if cmp_hex(event_log.args.id, m.id)), None)
                if not morpho_market:
                    raise Exception(f"Unexpected unknown morpho market encountered: {event_log.args.id.hex()}")
                event_str = morpho_market_str(event_log, morpho_market)
                msg_fn = self.msg_morpho

            if event_str:
                event_str += links_footer(event_logs[0].receipt)
                msg_fn(event_str)
