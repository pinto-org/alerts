import logging
import threading
import time

class MsgAggregator:
    def __init__(self, send_func, send_interval=1):
        self.send_func = send_func
        self.send_interval = send_interval

        self.msg_buffer = []
        self.lock = threading.Lock()
        self.running = True

        # Start the background thread
        self.worker_thread = threading.Thread(target=self._process_buffer)
        self.worker_thread.daemon = True
        self.worker_thread.start()

    def append_message(self, message):
        """Add a message to the buffer."""
        with self.lock:
            self.msg_buffer.append(message)

    def _process_buffer(self):
        """Periodically process the buffer."""
        while self.running:
            try:
                time.sleep(self.send_interval)
                with self.lock:
                    if self.msg_buffer:
                        # Process up to 3 messages at a time
                        chunk_size = 3
                        chunk = self.msg_buffer[:chunk_size]
                        concatenated_message = "\n".join(chunk)
                        self.send_func(concatenated_message)
                        # Remove only the sent messages
                        self.msg_buffer = self.msg_buffer[chunk_size:]
            except Exception as e:
                logging.error("Exception in _process_buffer", exc_info=True)

    def stop(self):
        """Stop the background thread."""
        self.running = False
        self.worker_thread.join()